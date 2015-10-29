#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __BEGIN_LICENSE__
#  Copyright (c) 2009-2013, United States Government as represented by the
#  Administrator of the National Aeronautics and Space Administration. All
#  rights reserved.
#
#  The NGT platform is licensed under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance with the
#  License. You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# __END_LICENSE__

"""IrgIsisFunctions.py - Functions for working with ISIS file types"""

import sys, os, re, subprocess, string, time, errno

import IrgStringFunctions, IrgFileFunctions


# TODO: This would make more sense in IrgGeoFunctions but some functions here need it!
def getImageSize(imagePath):
    """Returns the size [samples, lines] in an image"""

    # Make sure the input file exists
    if not os.path.exists(imagePath):
        raise Exception('Image file ' + imagePath + ' not found!')
       
    # Use subprocess to suppress the command output
    cmd = ['gdalinfo', imagePath]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()

    # Extract the size from the text
    sizePos    = textOutput.find('Size is')
    endPos     = textOutput.find('\n', sizePos+7)
    sizeStr    = textOutput[sizePos+7:endPos]
    sizeStrs   = sizeStr.strip().split(',')
    numSamples = int(sizeStrs[0])
    numLines   = int(sizeStrs[1])
    
    size = [numSamples, numLines]
    return size

def isIsisFile(filePath):
    """Returns True if the file is an ISIS file, False otherwise."""

    # Currently we treat all files with .cub extension as ISIS files
    extension = os.path.splitext(filePath)[1]
    return (extension == '.cub')


def parseHeadOutput(headText, cubePath):
    """Parses the output from head [cube path] and returns a dictionary containing all kernels"""

    kernelDict = dict()

    isisDataFolder = os.environ['ISIS3DATA']
    cubeFolder     = os.path.dirname(cubePath)

    # Search each line in the folder for a required kernel file
    
    lastLine = ''
    kernelsStarted = False
    currentKernelType = 'ERROR!'
    for line in headText.split('\n'):
        # Append leftovers from last line and clear left/right whitespace
        workingLine = lastLine + line.strip()
        lastLine = ''

#        print 'workingLine =' + workingLine

        # Skip lines until we find the start of the kernel section
        if (not kernelsStarted ) and (workingLine.find('Group = Kernels') < 0):
            continue
        kernelsStarted = True

        # Quit when we reach the end of the kernel section
        if (workingLine.find('End_Group') >= 0):
            return kernelDict

        # Check if the current line is cut off with an append character
        if (workingLine[-1] == '-'): # This means ISIS has done a weird truncation to the next line
            lastLine = workingLine[:-1] # Strip trailing - and append next line to it next pass
#            print '===   ' + lastLine
            continue

        # Maintain the current kernel type
        if (workingLine.find('LeapSecond') >= 0):
            currentKernelType = 'LeapSecond'
        elif (workingLine.find('TargetAttitudeShape') >= 0):
            currentKernelType = 'TargetAttitudeShape'
        elif (workingLine.find('TargetPosition') >= 0):
            currentKernelType = 'TargetPosition'
        elif (workingLine.find('InstrumentPointing') >= 0):
            currentKernelType = 'InstrumentPointing'
        elif (workingLine.find('InstrumentPosition') >= 0):
            currentKernelType = 'InstrumentPosition'
        elif (workingLine.find('InstrumentAddendum') >= 0):
            currentKernelType = 'InstrumentAddendum'
        elif (workingLine.find('Instrument') >= 0): # This must be check after the other instrument lines!
            currentKernelType = 'Instrument'
        elif (workingLine.find('SpacecraftClock') >= 0):
            currentKernelType = 'SpacecraftClock'
        elif (workingLine.find('ShapeModel') >= 0):
            currentKernelType = 'ShapeModel'

        # Now look for any kernel files on the line 
        # TODO: This will fail if one kernel ends on a line and the next gets a continuation!
        remainingSearchLine = workingLine
        while (len(remainingSearchLine) > 3):
        
            # Look through the line for the next kernel
            m = re.search('[$a-zA-Z0-9/._\-]*'+
                          '((\.tls)|(\.tpc)|(\.tf)|(\.bpc)|(\.bsp)|(\.bc)|(\.tf)|(\.ti)|(\.tsc)|(\.cub))', 
                          remainingSearchLine) 
            
            if not m: # Did not find a kernel
                #print 'Failed to find kernel in line: ' + workingLine
                break # If we did not find a match move on to the next line

            # Found a kernel, handle abbreviations
            if m.group(0)[0] == '$': # Located in ISIS data folder
                kernelPath = os.path.join(isisDataFolder, m.group(0)[1:])
            else: # Path relative to the file location, make it an absolute path
                kernelPath = os.path.join(cubeFolder, m.group(0))

            # Handle special case where two different kinds of files are in the same category
            if (currentKernelType == 'InstrumentPointing') and (kernelPath.find('.tf') > 0):
                currentKernelType = 'Frame'

            # Store the kernel in the dictionary
            if not (currentKernelType in kernelDict):
                kernelDict[currentKernelType] = [kernelPath]
            else:
                kernelDict[currentKernelType].append(kernelPath)

#            print 'In type: ' + currentKernelType + ' Found kernel ' + kernelPath

            # Set up whatever is left of the line for more searching
            remainingSearchLine = remainingSearchLine[m.end()+1:]
#            print remainingSearchLine
#            print len(remainingSearchLine)
#            print '\n'

    # Return the list of kernels
    return kernelDict


def getKernelsFromCube(cubePath):
    """Returns a list of all the SPICE kernels needed by a cube """

    # Call head -120 on file, write to a temp file for parsing
    cmd = ['head', '-120', cubePath]
    #print cmd
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    outputText, err = p.communicate()
    
    # Parse output looking for all the kernel files
    #print 'Looking for source frame file...'
    kernelList = parseHeadOutput(outputText, cubePath)
    if not kernelList:
        raise Exception('Unable to find any kernel files in ' + cubePath)

    return kernelList # Success!




def getPixelLocInCube(cubePath, sample, line):
    """Returns the BodyFixedCoordinate of a pixel from a cube"""

    DEFAULT_MOON_RADIUS = 1737400 # In meters

    # Make sure the input file exists
    if not os.path.exists(cubePath):
        raise Exception('Cube file ' + cubePath + ' not found!')
       
    # Use subprocess to parse the command output
    cmd = ['campt', 'from=', cubePath, 'sample=', str(sample), 'line=', str(line)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    cmdOut, err = p.communicate()


    # Read in the output file to extract the pixel coordinates
    gccLine       = ''
    latLine       = ''
    lonLine       = ''
    radiusLine    = ''
    lineAfterBody = False
    for line in cmdOut.split('\n'):
        
        # GCC stuff
        if lineAfterBody: # BodyFixedCoordinate takes up two lines
            gccLine       = gccLine + line
            lineAfterBody = False
            
        if (gccLine == ''): # Look for start of the info (this check must come second)
            if (line.find('BodyFixedCoordinate') >= 0):
                gccLine     = line
                lineAfterBody = True
        
        # GDC stuff
        if line.find('PlanetocentricLatitude') >= 0:
            latLine = line
            #print line
        if line.find('PositiveEast180Longitude') >= 0:
            lonLine = line
            #print line
        if line.find('LocalRadius') >= 0:
            radiusLine = line
            #print line

    # Make sure we found the desired lines
    if (gccLine == ''):
        raise Exception("Unable to find BodyFixedCoordinate in file " + cubePath)
    if (latLine == ''):
        raise Exception("Unable to find PlanetocentricLatitude in file " + cubePath)
    if (lonLine == ''):
        raise Exception("Unable to find PositiveEast180Longitude in file " + cubePath)
    if (radiusLine == ''):
        raise Exception("Unable to find LocalRadius in file " + cubePath)

    # Extract GCC coordinates
    startParen = gccLine.find('(')
    stopParen  = gccLine.find(')')
    numString  = gccLine[startParen+1:stopParen]
    x,y,z = numString.split(',')

    # Convert output from kilometers to meters
    pixelLocationGcc = [0, 0, 0]
    pixelLocationGcc[0] = float(x) * 1000.0
    pixelLocationGcc[1] = float(y) * 1000.0
    pixelLocationGcc[2] = float(z) * 1000.0
    
    # Extract GDC coordinates
    latStart     = latLine.find('=')+2
    lonStart     = lonLine.find('=')+2
    radiusStart  = radiusLine.find('=')+2
    radiusEnd    = radiusLine.find('<') - 1
    latNumStr    = latLine[latStart:]
    lonNumStr    = lonLine[lonStart:]
    radiusNumStr = radiusLine[radiusStart:radiusEnd]
    pixelLocationGdc = [float(lonNumStr), float(latNumStr), float(radiusNumStr)-1737400.0]
                        
    pixelInformation = dict()
    pixelInformation['gcc'] = pixelLocationGcc
    pixelInformation['gdc'] = pixelLocationGdc
    return pixelInformation



def getCubeElevationEstimate(cubePath, workDir=''):
    """Returns the surface elevation at the center of a cube"""

    DEFAULT_MOON_RADIUS = 1737400 # In meters

    # TODO: Get these values from the file!
    sample = 2500
    line   = 25000

    # Make sure the input file exists
    if not os.path.exists(cubePath):
        raise Exception('Cube file ' + cubePath + ' not found!')

    # Default working directory is the cubePath folder
    outputFolder = workDir
    if workDir == '':
        outputFolder = os.path.dirname(cubePath)
       
    if not os.path.exists(outputFolder):
        os.mkdir(outputFolder)

    # Call ISIS campt function to compute the pixel location
    tempTextPath = os.path.join(outputFolder, 'camptOutput.txt')
    if os.path.exists(tempTextPath):
        os.remove(tempTextPath) # Make sure any existing file is removed!
        
    # Use subprocess to suppress the command output
    cmd = ['campt', 'from=', cubePath, 'to=', tempTextPath, 'sample=', str(sample), 'line=', str(line)]
    FNULL = open(os.devnull, 'w')
    subprocess.call(cmd, stdout=FNULL, stderr=subprocess.STDOUT)

    # Check that we created the temporary file
    if not os.path.exists(tempTextPath):
        raise Exception('campt failed to create temporary file ' + tempTextPath)
        
    # Read in the output file to extract the pixel coordinates
    foundLine   = ''
    infoFile    = open(tempTextPath, 'r')
    for line in infoFile:
        if (line.find('LocalRadius') >= 0):
            foundLine = line
            break

    os.remove(tempTextPath) # Remove the file to clean up

    # Make sure we found the desired lines
    if (foundLine == ''):
        raise Exception("Unable to find LocalRadius in file " + tempTextPath)

    # ExtractfoundLine the desired coordinates
    eqPos     = foundLine.find('=')
    endPos    = foundLine.find('<')
    numString = foundLine[eqPos+2:endPos-2]

    # Convert the absolute radius into a height relative to the mean radius of the moon
    localRadius = float(numString) - DEFAULT_MOON_RADIUS
    print 'found local radius ' + str(localRadius)

    return localRadius

# TODO: Create a real bounding box class or something
def getIsisBoundingBox(cubePath):
    """Returns (minLon, maxLon, minLat, maxLat) for an ISIS compatible object"""
   
    # Get the cube size, then request the positions of the four corners
    cubeSize = getImageSize(cubePath)
    
    # Note that the underlying ISIS tool is one-based
    points  = []
    firstPt =     getPixelLocInCube(cubePath, 1,           1,         )['gdc']
    points.append(getPixelLocInCube(cubePath, cubeSize[0], 1,         )['gdc'])
    points.append(getPixelLocInCube(cubePath, 1,           cubeSize[1])['gdc'])
    points.append(getPixelLocInCube(cubePath, cubeSize[0], cubeSize[1])['gdc'])

    # Go through the four corners and get the bounding box
    minLon = firstPt[0]
    maxLon = firstPt[0]
    minLat = firstPt[1]
    maxLat = firstPt[1]
    
    for p in points:
        if p[0] < minLon:
            minLon = p[0]
        if p[0] > maxLon:
            maxLon = p[0]
        if p[1] < minLat:
            minLat = p[1]
        if p[1] > maxLat:
            maxLat = p[1]

    return (minLon, maxLon, minLat, maxLat)


def getCubeCenterLatitude(cubePath, workDir='tmp'):
    """Calls caminfo on a cube and returns the CenterLatitude value"""

    # Make sure the requested file is present
    if not os.path.exists(cubePath):
        raise Exception('File ' + cubePath + ' does not exist!')

    # Call caminfo (from ISIS) on the input cube to find out the CenterLatitude value
    camInfoOuputPath = workDir + "/camInfoOutput.txt"
    cmd = 'caminfo from=' + cubePath + ' to=' + camInfoOuputPath
    print cmd
    os.system(cmd)

    if not os.path.exists(camInfoOuputPath):
        raise Exception('Call to caminfo failed on file ' + cubePath)

    # Read in the output file to extract the CenterLatitude value
    centerLatitude = -9999
    infoFile       = open(camInfoOuputPath, 'r')
    for line in infoFile:
        if (line.find('CenterLatitude') >= 0):
            centerLatitude = IrgStringFunctions.getNumberAfterEqualSign(line, )
            break
    # Make sure we found the desired value
    if (centerLatitude == -9999) or (isinstance(centerLatitude, basestring)):
        raise Exception("Unable to find CenterLatitude from file " + cubePath)

    # Clean up temporary file
    os.remove(camInfoOuputPath)
    
    return centerLatitude
    

# TODO: Clean this up!  It only works for the Moon!
def imgDemToIsisDem(imgPath, outputPath):
    """Converts a DEM in .IMG format (such as LRO WAC DTM) into ISIS compatible format"""
    
    outputFolder = os.path.dirname(outputPath)
    
    temp1 = outputPath + '_temp1.cub'
    temp2 = outputPath + '_temp2.cub'
    
    cmd = 'pds2isis from= ' + imgPath + ' to= ' + temp1
    os.system(cmd)
    if not os.path.exists(temp1):
        raise Exception('Error executing: ' + cmd)
    
    cmd = 'algebra  from= ' + temp1   + ' to= ' + temp2 + ' operator=unary A=1 C=1737400'
    os.system(cmd)
    if not os.path.exists(temp2):
        raise Exception('Error executing: ' + cmd)
    
    cmd = 'demprep  from= ' + temp2   + ' to= ' + outputPath
    os.system(cmd)
    if not os.path.exists(outputPath):
        raise Exception('Error executing: ' + cmd)

    # Clean up output files
    os.remove(temp1)
    os.remove(temp2)

    return True


def prepareCtxImage(inputPath, outputFolder, keep):
    """Prepare a single CTX image for processing"""

    # Set up paths
    cubPath = IrgFileFunctions.replaceExtensionAndFolder(inputPath, outputFolder, '.cub')
    calPath = IrgFileFunctions.replaceExtensionAndFolder(inputPath, outputFolder, '.cal.cub')

    # Convert to ISIS format
    if not os.path.exists(cubPath):
        cmd = 'mroctx2isis from=' + inputPath  + ' to=' + cubPath
        os.system(cmd)
    
    # Init Spice data
    cmd = 'spiceinit from=' + cubPath
    os.system(cmd)
    
    # Apply image correction
    if not os.path.exists(calPath):
        cmd = 'ctxcal from='+cubPath+' to='+calPath
        os.system(cmd)

    #you can also optionally run ctxevenodd on the cal.cub files, if needed

    if not keep:
        os.remove(cubPath)
    
    return calPath







