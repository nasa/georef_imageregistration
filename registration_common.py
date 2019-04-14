#__BEGIN_LICENSE__
# Copyright (c) 2017, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All rights reserved.
#
# The GeoRef platform is licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#__END_LICENSE__

import os
import sys
import math
import subprocess
import traceback
import json
import numpy
import shutil
import piexif
import datetime
import tempfile

import IrgGeoFunctions
import offline_config

basepath    = os.path.abspath(sys.path[0]) # Scott debug
sys.path.insert(0, basepath + '/../geocamTiePoint')
sys.path.insert(0, basepath + '/../geocamUtilWeb')

from geocamTiePoint import transform
from django.conf import settings


# These codes are used to define the confidence in the detected image registration
CONFIDENCE_NONE = 0
CONFIDENCE_LOW  = 1
CONFIDENCE_HIGH = 2

CONFIDENCE_STRINGS = ['NONE', 'LOW', 'HIGH']

def confidenceFromString(s):
    if s == 'LOW':
        return CONFIDENCE_LOW
    if s == 'HIGH':
        return CONFIDENCE_HIGH
    return CONFIDENCE_NONE

# Geographig projection used to write output files
OUTPUT_PROJECTION = '+proj=longlat +datum=WGS84'

# TODO: Split up this file!

# TODO: Make sure that information entered via the GUI gets handled properly!


class TemporaryDirectory(object):
    """Context manager for tempfile.mkdtemp() so it's usable with "with" statement."""
    def __enter__(self):
        self.name = tempfile.mkdtemp()
        return self.name

    def __exit__(self, exc_type, exc_value, traceback):
        if '/tmp' in self.name:
            shutil.rmtree(self.name)


def safeMakeDir(folder):
    '''Make sure a folder exists and ignore any errors.'''
    try:
        os.mkdir(folder)
    except:
        pass


def cropImageLabel(jpegPath, outputPath):
    '''Create a copy of a jpeg file with any label cropped off'''
    
    # Check if there is a label using a simple command line tool
    cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/detectImageTag'
    cmd    = [cmdPath, jpegPath]
    print cmd
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
   
    
    if 'NO_LABEL' in textOutput:
        # The file is fine, just copy it.
        print 'Copy ' + jpegPath +' --> '+ outputPath
        try:
            shutil.copy(jpegPath, outputPath)
        except:
            print 'Copy failed, try again!'
#            shutil.copy(jpegPath, outputPath)
            os.system('cp ' + jpegPath +' '+ outputPath)
            if not os.path.exists(outputPath):
                raise Exception('Still failed!')
            print 'Retry successful!'
    else:
        lines = textOutput.strip().split('\n') # Get the parts of the last line
        parts = lines[-1].split()
        if len(parts) != 3:
            raise Exception('Error running detectImageTag, got response: ' + textOutput)
        side     = parts[1]
        labelPos = int(parts[2])
        print 'Detected image label: ' + side + ' at index ' + str(labelPos)
        # Trim the label off of the bottom of the image
        imageSize = IrgGeoFunctions.getImageSize(jpegPath)
        x = 0
        y = 0
        width  = imageSize[0]
        height = imageSize[1]
        if side == 'LEFT':
            x = labelPos
            width = width - labelPos
        if side == 'RIGHT':
            width = labelPos
        if side == 'TOP':
            y = labelPos
            height = height - labelPos
        if side == 'BOTTOM':
            height = labelPos
        cmd = ('gdal_translate -of jpeg -srcwin %d %d %d %d %s %s' 
                % (x, y, width, height, jpegPath, outputPath))
        print cmd
        os.system(cmd)

def updateExif(exifSourcePath, geotiffFilePath):
    '''Copy EXIF info from the source file to the geotiff file'''

    # These two files contain a bunch of arguments that are read by exiftool
    creationArgsFile = settings.STATIC_ROOT + '/georef_imageregistration/creation-args.txt'
    extrasArgsFile = settings.STATIC_ROOT + '/georef_imageregistration/extras-args.txt'
    
    outputFileName = geotiffFilePath
    # rename the geotiff input to "temp" so that we can generate a new geotiffFilePath geotiff file with updated exif.
    #     tempFileName = geotiffFilePath + ".temp"  
    filename, file_extension = os.path.splitext(outputFileName)
    tempFileName = os.path.dirname(outputFileName) + "/temp-%s%s" % (datetime.datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S%Z'), file_extension)
    
    os.rename(outputFileName, tempFileName)
    print "Exif Source Path: %s"
    
    try: 
        exifCmd = 'exiftool -tagsFromFile %s -@ %s -@ %s -ModifyDate="`date \'+%%Y:%%m:%%d %%H:%%M:%%S\'`" -EXIF:Software="%s" -o %s %s' \
                    % (exifSourcePath, creationArgsFile, extrasArgsFile, "GeoRef", outputFileName, tempFileName)      
        os.system(exifCmd)
        os.remove(tempFileName)  
    except Exception as e: 
        os.rename(tempFileName, outputFileName)
        print "Failed to copy over the exif information. %s" % e


def getIdentityTransform():
    '''Return an identity transform from the transform.py file'''
    return transform.ProjectiveTransform(numpy.matrix([[1,0,0],[0,1,0],[0,0,1]],dtype='float64'))

def isPixelValid(pixel, size):
    '''Simple pixel bounds check'''
    return ((pixel[0] >= 0      ) and (pixel[1] >= 0      ) and
            (pixel[0] <  size[0]) and (pixel[1] <  size[1])    )


def estimateGroundResolution(focalLength, width, height, sensorWidth, sensorHeight,
                             stationLon, stationLat, stationAlt, centerLon, centerLat, tilt=0.0):
    '''Estimates a ground resolution in meters per pixel using the focal length.'''
    # TODO: Use the angle to get a more accurate computation!
    # Divide by four since it is half the distance squared
    sensorDiag = math.sqrt(sensorWidth*sensorWidth/4 + sensorHeight*sensorHeight/4)
    pixelDiag  = math.sqrt(width*width/4 + height*height/4)

    angle = math.atan2(sensorDiag, focalLength)
    
    NAUTICAL_MILES_TO_METERS = 1852.0
    DEGREES_TO_RADIANS = 3.14159 / 180.0
    distance   = (stationAlt * NAUTICAL_MILES_TO_METERS) / math.cos(tilt*DEGREES_TO_RADIANS)
    groundDiag = math.tan(angle) * distance

    #print str(math.cos(tilt*DEGREES_TO_RADIANS))
    #print 'sensorDiag = ' + str(sensorDiag)
    #print 'angle      = ' + str(angle)
    #print 'distance   = ' + str(distance)
    #print 'groundDiag = ' + str(groundDiag)
    #print 'pixelDiag  = ' + str(pixelDiag)
        
    pixelSize = groundDiag / pixelDiag # Meters / pixels
    return pixelSize


def getWorkingDir(mission, roll, frame):
    # Break up frames so that there are 1000 per folder
    FRAMES_PER_FOLDER = 1000
    FRAME_DIGITS = 6
    frameFolderNum = (int(frame) // FRAMES_PER_FOLDER)*1000
    frameFolder    = str(frameFolderNum).rjust(FRAME_DIGITS, '0')
    
    # Store data in /mission/roll/frameF/file, skip roll if E.
    safeMakeDir(offline_config.OUTPUT_IMAGE_FOLDER)
    
    # make mission directory
    subFolder = os.path.join(offline_config.OUTPUT_IMAGE_FOLDER, mission)
    safeMakeDir(subFolder)
    
    # make roll directory
    if not (roll.lower() == 'e'):
        subFolder = os.path.join(subFolder, roll)
        safeMakeDir(subFolder)
        
    # make frame directory
    subFolder = os.path.join(subFolder, frameFolder)
    safeMakeDir(subFolder)
    
    return subFolder


def getZipFilePath(mission, roll, frame):
    '''Get the full path for an output zip file'''

    # Store data in /mission/mission-roll-frame/file
    issIdFolder = mission + '-' + roll + '-' + frame
    safeMakeDir(offline_config.OUTPUT_ZIP_FOLDER)
    
    subFolder = os.path.join(offline_config.OUTPUT_ZIP_FOLDER, mission)
    safeMakeDir(subFolder)
    
    subFolder = os.path.join(subFolder, issIdFolder)
    safeMakeDir(subFolder)
    
    return subFolder


def getWorkingPath(mission, roll, frame):
    '''Get a good location to process this image.'''
    
    if offline_config.USE_RAW:
        ext = '.tif'
    else:
        ext = '.jpg'
    
    # Generate a file name similar to the RAW storage scheme
    FRAME_DIGITS = 6
    zFrame   = frame.rjust(FRAME_DIGITS, '0')
    filename = mission.lower() + roll.lower() + zFrame + ext

    subFolder = getWorkingDir(mission, roll, frame)

    return os.path.join(subFolder, filename)


# TODO: Move this to the transform.py file?
def getFitError(imageInliers, gdcInliers):
    '''Computes the RMS error of the transform fit of the provided points.'''

    # The error is computed in pixels, but meters might be better.
    lonlatToPixels = transform.ProjectiveTransform.fit(numpy.asarray(imageInliers),
                                                       numpy.asarray(gdcInliers))
    
    numPoints = float(len(imageInliers))
    rms = 0.0
    for (pixel, lonlat) in zip(imageInliers, gdcInliers):
        tformPixel = lonlatToPixels.forward(lonlat)
        dx         = pixel[0] - tformPixel[0]
        dy         = pixel[1] - tformPixel[1]
        errSq      = dx*dx + dy*dy
        #print 'pixel = ' + str(pixel) +', tform = ' + str(tformPixel)
        rms += errSq / numPoints
    
    return math.sqrt(rms)


def getPixelToGdcTransform(imagePath, pixelToProjectedTransform=None):
    '''Returns a pixel to GDC transform.
       The input image must either be a nicely georegistered image from Earth Engine
       or a pixel to projected coordinates transform must be provided.'''

    if pixelToProjectedTransform:
        # Have image to projected transform, convert it to an image to GDC transform.

        # Use the simple file info call (the input file may not have geo information)
        (width, height) = IrgGeoFunctions.getImageSize(imagePath)
        
        imagePoints = []
        gdcPoints   = []
        
        # Loop through a spaced out grid of pixels in the image
        pointPixelSpacing = (width + height) / 20 # Results in about 100 points
        for r in range(0, width, pointPixelSpacing):
            for c in range(0, height, pointPixelSpacing):
                # This pixel --> projected coords --> lonlat coord
                thisPixel           = numpy.array([float(c), float(r)])
                projectedCoordinate = pixelToProjectedTransform.forward(thisPixel)
                gdcCoordinate       = transform.metersToLatLon(projectedCoordinate)
        
                imagePoints.append(thisPixel)
                gdcPoints.append(gdcCoordinate)
        # Solve for a transform with all of these point pairs
        pixelToGdcTransform = transform.getTransform(numpy.asarray(gdcPoints),
                                                     numpy.asarray(imagePoints))
        
    else: # Using a reference image from EE which will have nice bounds.

        # Use the more thorough file info call
        stats  = IrgGeoFunctions.getImageGeoInfo(imagePath, False)
        (width, height) = stats['image_size']
        (minLon, maxLon, minLat, maxLat) = stats['lonlat_bounds']
        
        # Make a transform from ref pixel to GDC using metadata on disk
        xScale = (maxLon - minLon) / width
        yScale = (maxLat - minLat) / height
        transformMatrix = numpy.array([[xScale,  0,      minLon],
                                       [0,      -yScale, maxLat],
                                       [0 ,      0,      1     ]])
        pixelToGdcTransform = transform.LinearTransform(transformMatrix)
    
    return pixelToGdcTransform


def getGdcTransformFromPixelTransform(imageSize, pixelTransform, refImageGdcTransform):
    '''Converts an image-to-image transform chained with a GDC transform
       to a pixel to GDC transform for this image.'''

    # Convert the image-to-image transform parameters to a class
    temp = numpy.array([tform[0:3], tform[3:6], tform[6:9]] )
    imageToRefTransform = transform.ProjectiveTransform(temp)

    newImageSize = ImageFetcher.miscUtilities.getImageSize(newImagePath)

    # Generate a list of point pairs
    imagePoints = []
    gdcPoints   = []

    # Loop through an evenly spaced grid of pixels in the new image
    # - For each pixel, compute the desired output coordinate
    pointPixelSpacing = (newImageSize[0] + newImageSize[1]) / 20 # Results in about 100 points
    for r in range(0, newImageSize[0], pointPixelSpacing):
        for c in range(0, newImageSize[1], pointPixelSpacing):
            # Get pixel in new image and matching pixel in the reference image,
            #  then pass that into the GDC transform.
            thisPixel       = numpy.array([float(c), float(r)])
            pixelInRefImage = pixelTransform.forward(thisPixel)
            gdcCoordinate   = refImageGdcTransform.forward(pixelInRefImage)

            imagePoints.append(thisPixel)
            gdcPoints.append(gdcCoordinate)

    # Compute a transform object that converts from the new image to projected coordinates
    imageToGdcTransform = transform.getTransform(numpy.asarray(worldPoints),
                                                 numpy.asarray(gdcPoints))

    return imageToGdcTransform




def alignImages(testImagePath, refImagePath, workPrefix, force, debug=False, slowMethod=False):
    '''Call the C++ code to find the image alignment'''
    
    transformPath = workPrefix + '-transform.txt'

    # The computed transform is from testImage to refImage
    
    # Run the C++ command if we need to generate the transform
    if (not os.path.exists(transformPath) or force):
        if os.path.exists(transformPath):
            os.remove(transformPath) # Clear out any old results
        
        print 'Running C++ image alignment tool...'
        cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/registerGeocamImage'
        
        cmd = [cmdPath, refImagePath, testImagePath, transformPath]
        if debug: cmd.append('y')
        else:     cmd.append('n')
        if slowMethod: cmd.append('y')
        else:          cmd.append('n')

        if debug:
            print cmd
        #os.system('build/registerGeocamImage '+ refImagePath+' '+testImagePath+' '+transformPath+' --debug')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        textOutput, err = p.communicate()
        print textOutput
    
    if not os.path.exists(transformPath):
        raise Exception('Failed to compute transform!')
        tform = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        confidence = CONFIDENCE_NONE
        return (tform, confidence)
    
    # Load the computed transform, confidence, and inliers.
    handle   = open(transformPath, 'r')
    fileText = handle.read()
    handle.close()
    lines = fileText.split('\n')
    confidence = CONFIDENCE_NONE
    if 'CONFIDENCE_LOW' in lines[0]:
        confidence = CONFIDENCE_LOW
    if 'CONFIDENCE_HIGH' in lines[0]:
        confidence = CONFIDENCE_HIGH
    tform = [float(f) for f in lines[2].split(',')] +  \
            [float(f) for f in lines[3].split(',')] +  \
            [float(f) for f in lines[4].split(',')]
    refInliers  = []
    testInliers = []
    for line in lines[6:]:
        if len(line) < 2:
            break
        numbers = [float(f) for f in line.split(',')]
        refInliers.append( (numbers[0], numbers[1]))
        testInliers.append((numbers[2], numbers[3]))
    
    #print tform
    #print refInliers
    #print testInliers
    
    return (tform, confidence, testInliers, refInliers)


def alignScaledImages(testImagePath, refImagePath, testImageScaling, workPrefix, force, debug=False, slowMethod=False):
    '''Align a possibly higher resolution input image with a reference image.
       This call handles the fact that registration should be performed at the same resolution.'''
    
    # If the scale is within this amount, don't bother rescaling.
    SCALE_TOLERANCE = 0.10
    if abs(testImageScaling - 1.0) < SCALE_TOLERANCE:
        # In this case just use the lower level function
        return alignImages(testImagePath, refImagePath, workPrefix, force, debug, slowMethod)

   
    # Generate a scaled version of the input image
    scaledImagePath = workPrefix + '-scaledInputImage.tif'
    outPercentage = str(testImageScaling*100.0)
    cmd = 'gdal_translate -outsize ' + outPercentage +'% ' + outPercentage +'% '+ testImagePath +' '+ scaledImagePath
    print cmd
    os.system(cmd)
    if not os.path.exists(scaledImagePath):
        raise Exception('Failed to rescale image with command:\n' + cmd)
    
    # Call alignment with the scaled version
    (scaledTform, confidence, scaledImageInliers, refInliers) = \
            alignImages(scaledImagePath, refImagePath, workPrefix, force, debug, slowMethod)
    
    # De-scale the output transform so that it applies to the input sized image.
    testInliers = []
    for pixel in scaledImageInliers:
        testInliers.append( (pixel[0]/testImageScaling, pixel[1]/testImageScaling) )
    print 'scaled tform = \n' + str(scaledTform)
    tform = scaledTform
    for i in [0, 1, 3, 4, 6, 7]: # Scale the six coefficient values
        tform[i] = tform[i] * testImageScaling
    print 'tform = \n' + str(tform)

    if not debug: # Clean up the scaled image
        os.remove(scaledImagePath)

    return (tform, confidence, testInliers, refInliers)



def logRegistrationResults(outputPath, pixelTransform, confidence,
                           refImagePath, imageToGdcTransform=None):
    '''Log the registration results so they can be read back in later.
       Provides enough data so that the image can be '''

    # TODO: Delete this function?  What was it for?
    raise Exception('BROKEN FUNCTION!')
    
    # Generate a scaled version of the input image
    scaledImagePath = workPrefix + '-scaledInputImage.tif'
    outPercentage = str(testImageScaling*100.0)
    cmd = 'gdal_translate -outsize ' + outPercentage +'% ' + outPercentage +'% '+ testImagePath +' '+ scaledImagePath
    print cmd
    os.system(cmd)
    if not os.path.exists(scaledImagePath):
        raise Exception('Failed to rescale image with command:\n' + cmd)
    
    # Call alignment with the scaled version
    (scaledTform, confidence, scaledImageInliers, refInliers) = \
            alignImages(scaledImagePath, refImagePath, workPrefix, force, debug, slowMethod)
    
    # De-scale the output transform so that it applies to the input sized image.
    testInliers = []
    for pixel in scaledImageInliers:
        testInliers.append( (pixel[0]/testImageScaling, pixel[1]/testImageScaling) )
    print 'scaled tform = \n' + str(scaledTform)
    tform = scaledTform
    for i in [0, 1, 3, 4, 6, 7]: # Scale the six coefficient values
        tform[i] = tform[i] * testImageScaling
    print 'tform = \n' + str(tform)

    if not debug: # Clean up the scaled image
        os.remove(scaledImagePath)

    return (tform, confidence, testInliers, refInliers)


def convertGcps(inputGdcCoords, imageToProjectedTransform, width, height):
    '''Given a set of GDC coordinates and image registration info,
       produces a set of GCPs for that image.'''

    size = (width, height)

    imageCoords = []
    gdcCoords   = []

    for inputCoord in inputGdcCoords:
        # Convert from GDC to Google projected coordinate
        coordMeters = transform.lonLatToMeters(inputCoord)
        
        # Get image coordinate
        pixel = imageToProjectedTransform.reverse(coordMeters)

        # Only keep GCPs that actually fall within the image
        if isPixelValid(pixel, size):
            gdcCoords.append(inputCoord)
            imageCoords.append(pixel)

    return (imageCoords, gdcCoords)


def recordOutputImages(sourceImagePath, exifSourcePath, outputPrefix, imageInliers, 
                       gdcInliers, minUncertaintyMeters, centerPointSource, 
                       isManualRegistration=False, overwrite=True):
    '''Generates all the output image files that we create for each successfully processed image.'''
    
    # We generate two pairs of images, one containing the image data
    #  and another with the same format but containing the uncertainty distances.
    outputPrefix = outputPrefix + '-' + centerPointSource
    uncertaintyOutputPrefix = outputPrefix + '-uncertainty'
    rawUncertaintyPath      = outputPrefix + '-uncertainty_raw.tif'
    
    # Create the raw uncertainty image
    (width, height) = IrgGeoFunctions.getImageSize(sourceImagePath)
    posError = generateUncertaintyImage(width, height, imageInliers,
                                        minUncertaintyMeters, rawUncertaintyPath)
    
    # Get a measure of the fit error
    fitError = getFitError(imageInliers, gdcInliers)
    
    # Generate the two pairs of images in the same manner
    try:
        (noWarpOutputPath, warpOutputPath) = \
            generateGeotiff(sourceImagePath, outputPrefix, imageInliers, gdcInliers,
                                            posError, fitError, isManualRegistration,
                                            exifSourcePath,
                                            writeHeaders=True, overwrite=True)
    except Exception as e:
        print str(e)
    
    try:
        (noWarpOutputPath, warpOutputPath) = \
            generateGeotiff(rawUncertaintyPath, uncertaintyOutputPrefix, imageInliers, gdcInliers,
                                                posError, fitError, isManualRegistration,
                                                exifSourcePath,
                                                writeHeaders=False, overwrite=True)
    except Exception as e:
        print str(e)
    
    # Clean up the raw uncertainty image and any extraneous files
    rawXmlPath = rawUncertaintyPath + '.aux.xml'
    os.remove(rawUncertaintyPath)
    if os.path.exists(rawXmlPath):
        os.remove(rawXmlPath)

def generateUncertaintyImage(width, height, imageInliers, minUncertainty, outputPath):
    '''Given a list of GCPs in an image, generate a distance image containing the
       distance from each pixel to the nearest GCP location.
       Returns the RMS error.'''
    
    # Create a white image with black dots at each GCP coordinate
    drawLine = ''
    for point in imageInliers:
        drawLine += (" point "+ str(point[0]) +","+ str(point[1]))
    
    tempPath1 = outputPath + '-tempDot.tif'
    tempPath2 = outputPath + '-tempDist.tif'
    cmd = ("convert +depth -size "+str(width)+"x"+str(height)+
           " xc:white  -fill black -draw '"+drawLine+"' " +tempPath1)
    #print cmd
    os.system(cmd)
    if not os.path.exists(tempPath1):
        print "tempPath1 is %s" % tempPath1
        raise Exception('Failed to generate GCP point image!')

    # Get the distance from each 
    cmd2 = ('convert '+tempPath1+' -morphology Distance Euclidean:1,1 '+ tempPath2)
    #print cmd2
    os.system(cmd2)
    if not os.path.exists(tempPath2):
        raise Exception('Failed to generate GCP distance image!')

    # TODO: Improve this calculation!

    # For each pixel away from a GCP, the uncertainty increases by this
    #  fraction of the minimum uncertainty.
    UNCERTAINTY_STEP_FRACTION = 0.03
    uncertaintyStep = minUncertainty * UNCERTAINTY_STEP_FRACTION
    
    # Figure out the uncertainty range in the output image and generate a scale string.
    UINT16_MAX = 65535
    maxUncertainty    = UINT16_MAX * UNCERTAINTY_STEP_FRACTION + minUncertainty
    uncertaintyString = ((' 0 %d %f %f ') % (UINT16_MAX, minUncertainty, maxUncertainty))
    
    # Use gdal_translate to convert from Uint16 to a scaled 32 bit floating point image
    #  with the final error numbers.
    cmd3 = ('gdal_translate -b 1 -ot Float32 -scale '+uncertaintyString+ tempPath2 +' '+ outputPath)
    #print cmd3
    os.system(cmd3)
    if not os.path.exists(outputPath):
        raise Exception('Failed to generate uncertainty image!')

    # Compute the RMS error using a simple command line tool
    cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/computeImageRms'
    cmd4    = [cmdPath, outputPath]
    #print cmd4
    p = subprocess.Popen(cmd4, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # Parse the line "RMS: 123"
    parts    = textOutput.split(':')
    rmsError = float(parts[1])

    # Clean up
    os.remove(tempPath1)
    os.remove(tempPath2)
    
    return rmsError


def qualityGdalwarp(imagePath, outputPath, imagePoints, gdcPoints):
    '''Use some workarounds to get a higher quality gdalwarp output than is normally possible.'''

    # Generate a high resolution grid of fake GCPs based on a transform we compute,
    # then call gdalwarp using a high order polynomial to accurately match our transform.

    #trans = transform.ProjectiveTransform.fit(numpy.asarray(gdcPoints),numpy.asarray(imagePoints))ls 
    trans = transform.getTransform(numpy.asarray(gdcPoints),numpy.asarray(imagePoints))
    transformName = trans.getJsonDict()['type']
    
    tempPath = outputPath + '-temp.tif'
    
    # Generate a temporary image containing the grid of fake GCPs
    cmd = ('gdal_translate -co "COMPRESS=LZW" -co "tiled=yes"  -co "predictor=2" -a_srs "'
           + OUTPUT_PROJECTION +'" '+ imagePath +' '+ tempPath)
    
    # Generate the GCPs in a grid, keeping the total under about 500 points so
    # that GDAL does not complain.
    (width, height) = IrgGeoFunctions.getImageSize(imagePath)
    xStep = width /22
    yStep = height/22
    MAX_DEG_SIZE = 20
    minLon = 999 # Keep track of the lonlat size and don't write if it is too big.
    minLat = 999 # - This would work better if it was in pixels, but how to get that size?
    maxLon = -999
    maxLat = -999
    for r in range(0,height,yStep):
        for c in range(0,width,xStep):
            pixel  = (c,r)
            lonlat = trans.forward(pixel)
            cmd += ' -gcp '+ str(c) +' '+str(r) +' '+str(lonlat[0]) +' '+str(lonlat[1])
            if lonlat[0] < minLon:
                minLon = lonlat[0]
            if lonlat[1] < minLat:
                minLat = lonlat[1]
            if lonlat[0] > maxLon:
                maxLon = lonlat[0]
            if lonlat[1] > maxLat:
                maxLat = lonlat[1]
    #print cmd
    os.system(cmd)
    if max((maxLon - minLon), (maxLat - minLat)) > MAX_DEG_SIZE:
        raise Exception('Warped image is too large to generate!\n'
                        '-> LonLat bounds: ' + str((minLon, minLat, maxLon, maxLat)))

    # Now generate a warped geotiff.
    # - "order 2" looks terrible with fewer GCPs, but "order 1" does not accurately
    #   capture the footprint of higher tilt images.
    # - tps seems to work well with the evenly spaced grid of virtual GCPs.
    cmd = ('gdalwarp -co "COMPRESS=LZW" -co "tiled=yes"  -co "predictor=2"'
               + ' -dstalpha -overwrite -tps -multi -r cubic -t_srs "'
           + OUTPUT_PROJECTION +'" ' + tempPath +' '+ outputPath)
    print cmd
    os.system(cmd)

    # Check output and cleanup
    os.remove(tempPath)
    if not os.path.exists(outputPath):
        raise Exception('Failed to create warped geotiff file: ' + outputPath)

    return transformName



def generateGeotiff(imagePath, outputPrefix, imagePoints, gdcPoints, posError, fitError,
                    isManualRegistration, exifSourcePath, writeHeaders, overwrite=False):
    '''Converts a plain tiff to a geotiff using the provided geo information.'''

    # Check inputs
    if len(imagePoints) != len(gdcPoints):
        raise Exception('Unequal length correspondence points passed to generateGeoTiff!')

    noWarpOutputPath = outputPrefix + '-no_warp.tif'
    warpOutputPath   = outputPrefix + '-warp.tif'

    if isManualRegistration:
        registrationMethodString = 'Manual'
    else:
        registrationMethodString = 'Automated'

    exifData = piexif.load(exifSourcePath)
    acquisitionTime = exifData['Exif'][piexif.ExifIFD.DateTimeOriginal]
    
    # TODO: Do the manual registrations not use Landsat?
    extraMetadataString = ('-mo POSITION_UNCERTAINTY_RMS_METERS=' + str(posError)
                         + ' -mo FIT_ERROR_RMS_PIXELS=' + str(fitError)
                         + ' -mo REGISTRATION_METHOD=' + registrationMethodString
                         + ' -mo REGISTRATION_REFERENCE=Landsat'
                         + ' -mo ACQUISITION_DATETIME="' + acquisitionTime + '"'
                         + ' -mo ACQUISITION_DATETIME_TIMEZONE="GMT"')

    # First generate a geotiff that adds metadata but does not change the image data.
    # TODO - This may not be useful unless we can duplicate how they processed their RAW data!
    if (not os.path.exists(noWarpOutputPath)) or overwrite:
        print 'Generating UNWARPED output tiff'
        cmd = ('gdal_translate ' + extraMetadataString
               + ' -co "COMPRESS=LZW" -co "tiled=yes"  -co "predictor=2" -a_srs "'
               + OUTPUT_PROJECTION +'" '+ imagePath +' '+ noWarpOutputPath)
        
        ## Include an arbitrary tag with our estimated error amount
        #if errorMeters:
        #    cmd += ' -mo "REGISTRATION_ERROR=+/-'+str(errorMeters)+' meters" '
        
        # Include the actual GCPs that we matched to our Landsat data.
        MAX_NUM_GCPS = 500 # Too many GCPs breaks gdal!
        count = 0
        for (imagePoint, gdcPoint) in zip(imagePoints, gdcPoints):
            s = (' -gcp %f %f %f %f' % (imagePoint[0], imagePoint[1], gdcPoint[0], gdcPoint[1]))
            cmd += s
            count += 1
            if count == MAX_NUM_GCPS:
                break
            
        # Generate the file using gdal_translate
        print cmd
        os.system(cmd)
        if not os.path.exists(noWarpOutputPath):
            raise Exception('Failed to create geotiff file: ' + noWarpOutputPath)
        
        if writeHeaders:
            generateStandaloneMetadataFile(noWarpOutputPath)
            
        updateExif(exifSourcePath, noWarpOutputPath)

    # Now generate a warped geotiff.
    if (not os.path.exists(warpOutputPath)) or overwrite:
        print 'Generating WARPED output tiff'

        transformName = qualityGdalwarp(imagePath, warpOutputPath, imagePoints, gdcPoints)
        
        # Add some extra metadata fields.
        cmd = ('gdal_edit.py -mo TIFFTAG_DOCUMENTNAME= ' + extraMetadataString
                + ' -mo RESAMPLING_METHOD=cubic -mo WARP_TRANSFORM='+transformName+' ' + warpOutputPath)
        #print cmd
        os.system(cmd)
    
        if not os.path.exists(warpOutputPath):
            raise Exception('Failed to create warped geotiff file: ' + warpOutputPath)
        
        if writeHeaders:
            generateStandaloneMetadataFile(warpOutputPath)
        
        updateExif(exifSourcePath, warpOutputPath)
        
    
    return (noWarpOutputPath, warpOutputPath)


def generateStandaloneMetadataFile(inputImagePath):
    '''Convert geotiff metadata into a nicely formatted external text file.'''

    # Silently quit when the input image does not exist, that error should already have
    #  been handled.
    if not os.path.exists(inputImagePath):
        return

    outputPath = os.path.splitext(inputImagePath)[0] + '_metadata.txt'

    print 'Generating metadata file ' + outputPath

    cmd = ['gdalinfo', inputImagePath]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()

    lines = textOutput.split('\n')

    imageStartLine = metadataStartLine = coordSystemStartLine = gcpStartLine = imageSizeLine = 0
    index = 0
    for line in lines:
        if 'Image Structure Metadata' in line:
            imageStartLine = index
        if line == 'Metadata:':
            metadataStartLine = index
        if 'Coordinate System is' in line:
            coordSystemStartLine = index
        if 'GCP[  0]' in line:
            gcpStartLine = index
        if 'Size is ' in line:
            imageSizeLine = line
        
        index += 1

    headerText = 'File Type: GeoTiff\n' + imageSizeLine + '\n'
    ipHeader = '''[Tie-Points Used For Georeferencing] {Point format is: (pixel column, pixel row) -> (longitude, latitude, 0)}\n'''
    
    if gcpStartLine > 0:
        ipText = ipHeader + '\n'.join(lines[gcpStartLine:metadataStartLine])
    else:
        ipText = ''
    
    geoText = '[Geographic Coordinate Information]\n' + '\n'.join(lines[coordSystemStartLine+1:coordSystemStartLine+9])
    
    imageText = '[Image Structure Metadata]\n' + '\n'.join(lines[imageStartLine+1:])

    METADATA_SKIP_LIST = ['TIFFTAG', 'AREA_OR_POINT']
    
    metadataText = lines[metadataStartLine+1:imageStartLine]
    
    accuracyText = '[Accuracy Measures For Georeferencing Result]\n'
    cameraText = '[Camera Metadata]\n'
    for line in metadataText:
        # Ignore certain lines
        skip = False
        for item in METADATA_SKIP_LIST:
            if item in line:
                skip = True
        if skip:
            continue
        # Otherwise send the line to the correct section
        if 'EXIF' in line:
            cameraText += line + '\n'
        else:
            accuracyText += line + '\n'
            
    # Generate the output file
    f = open(outputPath, 'w')
    f.write(headerText + '\n')
    f.write(imageText + '\n')
    f.write(geoText      + '\n\n')
    if len(ipText) > 20:
        f.write(ipText       + '\n\n')
    f.write(accuracyText)
    if len(cameraText) > 20: # The warped image does not have this information
        f.write('\n' + cameraText)
    f.close()
    
    print 'Finished writing header file.'



