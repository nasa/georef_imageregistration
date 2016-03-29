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

"""IrgGeoFunctions.py - Functions for working with different geo-data formats"""

import sys, os, glob, re, shutil, subprocess, string, time, errno
import re
import IrgStringFunctions


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


def getGdalInfoTagValue(text, tag):
    """Gets the value of a gdal parameter in a [""] tag or None if it is absent."""

    try:
        lineAfterTag = IrgStringFunctions.getLineAfterText(text, tag)
        
        # The remaining line should look like this: ",25],
        commaPos   = lineAfterTag.find(',')
        bracketPos = lineAfterTag.find(']')
        # The value is always returned as a string
        return IrgStringFunctions.convertToFloatIfNumber(lineAfterTag[commaPos+1:bracketPos])
    
    except Exception: # Requested tag was not found
        return None

def parseLonLatDMS(s):
    '''Parses a single DMS number like 177d16'20.85"E'''
    # Clear whitespace
    s = s.strip()
    
    # Determine if this is a positive or negative degree values
    isNeg = 1.0
    if ('W' in s) or ('S' in s):
        isNeg = -1.0

    s = s[:-2] # Strip compass direction and "
    
    # Extract DMS components
    dms = re.split("""d|'""", s)
    
    # Convert to decimal
    value = float(dms[0]) + float(dms[1])/60.0 + float(dms[2])/3600.0
    return value * isNeg
    

def parseGdalLonLatBounds(line):
    """Finds and parses the lonlat information in a line like this:
        Upper Left  ( -161674.633, 1392019.475) (177d16'20.85"E, 23d29' 2.91"N) """
    
    numberSets = []
    
    # Find all number sets in the text
    parenGroups = re.findall( r'''\([ \d.,-dEWNS'"]*\)''', line) 
    
    # The projected coordinates should always be there but 
    #  not always the DMS coordinates
    for p in parenGroups:
    
        numberText = p[1:-1] # Remove ()
        numberList = numberText.split(',')
        if ('E' in numberText or 'N' in numberText or 'S' in numberText or 'W' in numberText):
            # DMS coordinates
            numbers = [parseLonLatDMS(numberList[0]), 
                       parseLonLatDMS(numberList[1])]
        else: # Projected coordinates, easy to parse
            numbers = []
            for n in numberList: # Convert strings to floats
                numbers.append(float(n))
        numberSets.append(numbers) # Add this set of numbers to output list

    # If only one set of numbers return a list
    if len(numberSets) == 1:
        return numberSets[0]
    else: # Otherwise return a list of lists
        return numberSets


# This can take a while if stats are requested
def getImageGeoInfo(imagePath, getStats=True):
    """Obtains some image geo information from gdalinfo in dictionary format"""
    
    outputDict = {}
    
    # Call command line tool silently
    cmd = ['gdalinfo', imagePath, '-proj4']
    if getStats:
        cmd.append('-stats')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # Get the size in pixels
    imageSizeLine = IrgStringFunctions.getLineAfterText(textOutput, 'Size is ')
    sizeVals      = imageSizeLine.split(',')
    outputDict['image_size'] = (int(sizeVals[0]), int(sizeVals[1])) #cols, rows

    # Get origin location and pixel size    
    originLine    = IrgStringFunctions.getLineAfterText(textOutput, 'Origin = ')
    pixelSizeLine = IrgStringFunctions.getLineAfterText(textOutput, 'Pixel Size = ')    
    originVals    = IrgStringFunctions.getNumbersInParentheses(originLine)
    pixelSizeVals = IrgStringFunctions.getNumbersInParentheses(pixelSizeLine)
    outputDict['origin']     = originVals
    outputDict['pixel_size'] = pixelSizeVals

    # Get bounding box in projected coordinates and possibly lonlat coordinates
    upperLeftLine  = IrgStringFunctions.getLineAfterText(textOutput, 'Upper Left')
    lowerRightLine = IrgStringFunctions.getLineAfterText(textOutput, 'Lower Right')
    ulCoords       = parseGdalLonLatBounds(upperLeftLine)
    brCoords       = parseGdalLonLatBounds(lowerRightLine)
    if (len(ulCoords) == 2):
        (minX,   maxY)   = ulCoords[0]
        (maxX,   minY)   = brCoords[0]
        (minLon, maxLat) = ulCoords[1]
        (maxLon, minLat) = brCoords[1]
        while (maxLon < minLon): # Get lon values in the same degree range
            maxLon += 360.0
        outputDict['lonlat_bounds'] = (minLon, maxLon, minLat, maxLat)
    else:
        (minX, maxY) = ulCoords
        (maxX, minY) = brCoords
    outputDict['projection_bounds'] = (minX, maxX, minY, maxY)

    # Get some proj4 values
    outputDict['standard_parallel_1'] = getGdalInfoTagValue(textOutput, 'standard_parallel_1')
    outputDict['central_meridian']    = getGdalInfoTagValue(textOutput, 'central_meridian')

    # TODO: Get the projection type!
    if '+proj=eqc' in textOutput:
        outputDict['projection'] = 'EQUIRECTANGULAR'
    elif '+proj=ster' in textOutput:
        outputDict['projection'] = 'POLAR STEREOGRAPHIC'
    outputDict['projection'] = 'UNKNOWN'
    
    # Extract this variable which ASP inserts into its point cloud files
    try:
        pointOffsetLine = IrgStringFunctions.getLineAfterText(textOutput, 'POINT_OFFSET=') # Tag name must be synced with C++ code
        offsetValues    = pointOffsetLine.split(' ')
        outputDict['point_offset'] =  (float(offsetValues[0]), float(offsetValues[1]), float(offsetValues[2]))        
    except:
        pass # In most cases this line will not be present

    
    if getStats: # TODO: Which fields are set by this?

        # List of dictionaries per band
        outputDict['band_info'] = []
    
        # Populate band information
        band = 1
        while (True): # Loop until we run out of bands
            bandString = 'Band ' + str(band) + ' Block='
            bandLoc = textOutput.find(bandString)
            if bandLoc < 0: # Ran out of bands
                break
        
            # Found the band, read pertinent information
            bandInfo = {}
        
            # Get the type string
            bandLine = IrgStringFunctions.getLineAfterText(textOutput, bandString)
            typePos  = bandLine.find('Type=')
            commaPos = bandLine.find(',')
            typeName = bandLine[typePos+5:commaPos-1]
            bandInfo['type'] = typeName
        
            outputDict['band_info'] = bandInfo
        
            band = band + 1 # Move on to the next band
        
    return outputDict

def doesImageHaveGeoData(imagePath):
    '''Returns true if a file has geo data associated with it'''
    
    if not os.path.exists(imagePath):
        raise Exception('Image file ' + imagePath + ' not found!')
    
    # Call command line tool silently
    cmd = ['gdalinfo', imagePath, '-proj4']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # For now we just do a very simple check
    if "Coordinate System is `'" in textOutput:
        return False
    else:
        return True
    


def getImageStats(imagePath):
    """Obtains some image statistics from gdalinfo"""
    
    if not os.path.exists(imagePath):
        raise Exception('Image file ' + imagePath + ' not found!')
    
    # Call command line tool silently
    cmd = ['gdalinfo', imagePath, '-stats']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # Statistics are computed seperately for each band
    bandStats = []
    band = 0
    while (True): # Loop until we run out of bands
        # Look for the stats line for this band
        bandString = 'Band ' + str(band+1) + ' Block='
        bandLoc = textOutput.find(bandString)
        if bandLoc < 0:
            return bandStats # Quit if we did not find it
            
        # Now parse out the statistics for this band
        bandMaxStart  = textOutput.find('STATISTICS_MAXIMUM=', bandLoc)
        bandMeanStart = textOutput.find('STATISTICS_MEAN=',    bandLoc)
        bandMinStart  = textOutput.find('STATISTICS_MINIMUM=', bandLoc)
        bandStdStart  = textOutput.find('STATISTICS_STDDEV=',  bandLoc)
               
        bandMax  = IrgStringFunctions.getNumberAfterEqualSign(textOutput, bandMaxStart)
        bandMean = IrgStringFunctions.getNumberAfterEqualSign(textOutput, bandMeanStart)
        bandMin  = IrgStringFunctions.getNumberAfterEqualSign(textOutput, bandMinStart)
        bandStd  = IrgStringFunctions.getNumberAfterEqualSign(textOutput, bandStdStart)
            
        # Add results to the output list
        bandStats.append( (bandMin, bandMax, bandMean, bandStd) )
            
        band = band + 1 # Move to the next band
    

def getGeoTiffBoundingBox(geoTiffPath):
    """Returns (minLon, maxLon, minLat, maxLat) for a geotiff image"""
    
    if not os.path.exists(geoTiffPath):
        raise Exception('Input file does not exist: ' + geoTiffPath)
    
    # Call command line tool silently
    cmd = ['geoRefTool', '--printBounds', geoTiffPath]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()

    # Check that the call did not fail
    if (textOutput.find('Failed') >= 0):
        raise Exception('Error: getGeoTiffBoundingBox failed on input image: ' + geoTiffPath)
    
    # Parse the output
    try:
        minLat = float( IrgStringFunctions.getLineAfterText(textOutput, 'Min latitude  =') )
        maxLat = float( IrgStringFunctions.getLineAfterText(textOutput, 'Max latitude  =') )
        minLon = float( IrgStringFunctions.getLineAfterText(textOutput, 'Min longitude =') )
        maxLon = float( IrgStringFunctions.getLineAfterText(textOutput, 'Max longitude =') )
    except Exception,e:
        print 'In file: ' + geoTiffPath
        print 'In text:'
        print textOutput
        raise e
    
    return (minLon, maxLon, minLat, maxLat)


def getProjectedBoundsFromIsisLabel(filePath):
    '''Function to read the projected coordinates bounding box from an ISIS label file'''

    if not os.path.exists(filePath):
        raise Exception('Error, missing label file path!')
    
    # Read all the values!
    minX    = None
    maxY    = None
    pixRes  = None
    numRows = None
    numCols = None
    f = open(filePath, 'r')
    for line in f:
        if ('UpperLeftCornerX' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<')
            if (endPos >= 0):
                minX = float(s[:endPos-1])
            else:
                minX = float(s)
            continue
        if ('UpperLeftCornerY' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<')
            if (endPos >= 0):
                maxY = float(s[:endPos-1])
            else:
                maxY = float(s)
            continue
        if ('PixelResolution' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<')
            if (endPos >= 0):
                pixRes = float(s[:endPos-1])
            else:
                pixRes = float(s)
            continue
        if ('      Samples =' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            numCols = float(s)
            continue
        if ('      Lines   =' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            numRows = float(s)
            continue
        
    f.close()
    if (not minX) or (not maxY) or (not pixRes) or (not numRows) or (not numCols):
        raise Exception('Failed to find projected bounds in file ' + filePath)

    # Compute the other bounds
    maxX = minX + pixRes*numCols
    minY = maxY - pixRes*numRows

    return (minX, maxX, minY, maxY)

def getProjectionFromIsisLabel(filePath):
    '''Function to read the projection type from an ISIS label file'''

    if not os.path.exists(filePath):
        raise Exception('Error, missing label file path!')
    
    f = open(filePath, 'r')
    for line in f:
        if ('MAP_PROJECTION_TYPE          =' in line) or ('ProjectionName     =' in line):
            line = line.replace('"','') # Strip quotes
            projType = IrgStringFunctions.getLineAfterText(line, '=').strip()
            f.close()
            return projType
    f.close()
    raise Exception('Unable to find projection type in file ' + filePath)

def getBoundingBoxFromIsisLabel(filePath):
    '''Function to read the bounding box from an ISIS label file'''

    if not os.path.exists(filePath):
        raise Exception('Error, missing label file path!')
    
    numFound = 0
    f = open(filePath, 'r')
    for line in f:
        if ('MINIMUM_LATITUDE' in line) or ('MinimumLatitude' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<')
            if (endPos >= 0):
                minLat = float(s[:endPos-1])
            else:
                minLat = float(s)
            numFound = numFound + 1
            continue
        if ('MAXIMUM_LATITUDE' in line) or ('MaximumLatitude' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<')
            if (endPos >= 0):
                maxLat = float(s[:endPos-1])
            else:
                maxLat = float(s)
            numFound = numFound + 1
            continue
        if ('EASTERNMOST_LONGITUDE' in line) or ('MAXIMUM_LONGITUDE' in line)  or ('MaximumLongitude' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<') # Check for unit name
            if (endPos >= 0):
                maxLon = float(s[:endPos-1])
            else:
                maxLon = float(s)
            numFound = numFound + 1
            continue
        if ('WESTERNMOST_LONGITUDE' in line) or ('MINIMUM_LONGITUDE' in line) or ('MinimumLongitude' in line):
            s = IrgStringFunctions.getLineAfterText(line, '=')
            endPos = s.find('<') # Check for unit name
            if (endPos >= 0):
                minLon = float(s[:endPos-1])
            else:
                minLon = float(s)
            numFound = numFound + 1
            continue
        if numFound == 4:
            break

    f.close()
    if numFound < 4:
        raise Exception('Failed to find lat/lon bounds in file ' + filePath)

    return (minLon, maxLon, minLat, maxLat)


def getImageBoundingBox(filePath):
    """Returns (minLon, maxLon, minLat, maxLat) for a georeferenced image file"""

    extension = os.path.splitext(filePath)[1]
    if '.cub' in extension:
        return IrgIsisFunctions.getIsisBoundingBox(filePath)
    else: # Handle all other types
        return getGeoTiffBoundingBox(filePath)
          
    # Any other file types will end up raising some sort of exception
    
    
    
    

def build_vrt( fullImageSize, tileLocs, tilePaths, outputPath ):
    """Generates a VRT file from a set of image tiles and their locations in the output image"""

    outputFolder = os.path.dirname(outputPath)

    f = open(outputPath, 'w')
    f.write("<VRTDataset rasterXSize=\"%i\" rasterYSize=\"%i\">\n" % (int(fullImageSize[0]),int(fullImageSize[1])) ) # Write whole image size

    #
    ## If a tile is missing, for example, in the case we
    ## skipped it when it does not intersect user's crop box,
    ## substitute it with a different one, to ensure the mosaic
    ## does not have holes. --> Does this make sense?
    #goodFilename = ""
    #for tile in tiles: # Find the first valid tile (we don't care which one)
    #    directory = settings['out_prefix'][0] + tile.name_str()
    #    filename  = directory + "/" + tile.name_str() + tile_postfix
    #    if os.path.isfile(filename):
    #        goodFilename = filename
    #        break
    #if goodFilename == "":
    #    raise Exception('No tiles were generated')

    
    # Read some metadata from one of the tiles
    gdalInfo = getImageGeoInfo(tilePaths[0])
    
    num_bands = len(gdalInfo['band_info'])
    data_type = gdalInfo['band_info'][0]['type']

    # This special metadata value is only used for ASP stereo point cloud files!    
    if 'point_offset' in gdalInfo:
        f.write("  <Metadata>\n    <MDI key=\"" + 'POINT_OFFSET' + "\">" +
                gdalInfo['point_offset'][0] + "</MDI>\n  </Metadata>\n")
      

    # Write each band
    for b in range( 1, num_bands + 1 ):
        f.write("  <VRTRasterBand dataType=\"%s\" band=\"%i\">\n" % (data_type, b) ) # Write band data type and index

        for tile, tileLoc in zip(tilePaths, tileLocs):
            filename  = tile
            
            imageSize = getImageSize(filename) # Get the image size for this tile

            ## Replace missing tile paths with the good tile we found earlier
            #if not os.path.isfile(filename): filename = goodFilename

            relative = os.path.relpath(filename, outputPath) # Relative path from the output file to the input tile
            f.write("    <SimpleSource>\n")
            f.write("       <SourceFilename relativeToVRT=\"1\">%s</SourceFilename>\n" % relative) # Write relative path
            f.write("       <SourceBand>%i</SourceBand>\n" % b)
            f.write("       <SrcRect xOff=\"%i\" yOff=\"%i\" xSize=\"%i\" ySize=\"%i\"/>\n" % (tileLoc[0], tileLoc[1], imageSize[0], imageSize[1]) ) # Source ROI (entire tile)
            f.write("       <DstRect xOff=\"%i\" yOff=\"%i\" xSize=\"%i\" ySize=\"%i\"/>\n" % (tileLoc[0], tileLoc[1], imageSize[0], imageSize[1]) ) # Output ROI (entire tile)
            f.write("    </SimpleSource>\n")
        f.write("  </VRTRasterBand>\n")
    f.write("</VRTDataset>\n")
    f.close()    
    

# TODO: Move to the main version of this file!
def extractGcps(geoTiffPath):
    '''Returns a list of the GCPs listed in a geotiff file'''
    
    # Call command line tool silently
    cmd = ['gdalinfo', geoTiffPath]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # Loop through all the text output looking for GCPs
    continuing = False
    lines = textOutput.split('\n')
    imagePoints = []
    worldPoints = []
    for line in lines:
        
        # Each GCP spans two lines, so use "continuing" to grab the second line.
        if continuing or ('GCP' in line):
            
            
            if not continuing:
                # Nothing to do here?
                continuing = True
            else:
                # Parse the GCP info
                s = line.replace(')','').replace('(','')
                center = line.find('->')
                first  = line[:center]
                second = line[center+2:]
                partsFirst  = first.split(',')
                partsSecond = first.split(',')
                imageCoord  = (float(partsFirst [0]), float(partsFirst [1]))
                worldCoord  = (float(partsSecond[0]), float(partsSecond[1]))
                
                imagePoints.append(imageCoord)
                worldPoints.append(worldCoord)
                continuing = False
    
    return (imagePoints, worldPoints)
    
    
    
    
    
    
    
    