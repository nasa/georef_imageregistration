
import os
import sys
import math
import subprocess
import traceback
import json
import numpy
import IrgGeoFunctions

#basepath    = os.path.abspath(sys.path[0]) # Scott debug
#sys.path.insert(0, basepath + '/../geocamTiePoint')
#sys.path.insert(0, basepath + '/../geocamUtilWeb')

from geocamTiePoint import transform
from django.conf import settings

# These codes are used to define the confidence in the detected image registration
CONFIDENCE_NONE = 0
CONFIDENCE_LOW  = 1
CONFIDENCE_HIGH = 2

CONFIDENCE_STRINGS = ['NONE', 'LOW', 'HIGH']


#def estimateGroundResolution(focalLength):
#    if not focalLength: # Guess a low resolution for a zoomed out image
#        return 150
#    
#    # Based on all the focal lengths we have seen so far
#    if focalLength <= 50:
#        return 200
#    if focalLength <= 110:
#        return 80
#    if focalLength <= 180:
#        return 55
#    if focalLength <= 250:
#        return 30
#    if focalLength <= 340:
#        return 25
#    if focalLength <= 400:
#        return 20
#    if focalLength <= 800:
#        return 10
#    return 0

def estimateGroundResolution(focalLength, width, height, sensorWidth, sensorHeight,
                             stationLon, stationLat, stationAlt, centerLon, centerLat):
    '''Estimates a ground resolution in meters per pixel using the focal length.'''
    
    # TODO: Use the angle to get a more accurate computation!
    # Divide by four since it is half the distance squared
    sensorDiag = math.sqrt(sensorWidth*sensorWidth/4 + sensorHeight*sensorHeight/4)
    pixelDiag  = math.sqrt(width*width/4 + height*height/4)

    angle = math.atan2(sensorDiag, focalLength)
    
    NAUTICAL_MILES_TO_METERS = 1852.0
    distance = stationAlt * NAUTICAL_MILES_TO_METERS
    groundDiag = math.tan(angle) * distance

    print 'sensorDiag = ' + str(sensorDiag)
    print 'angle      = ' + str(angle)
    print 'distance   = ' + str(distance)
    print 'groundDiag = ' + str(groundDiag)
    print 'pixelDiag  = ' + str(pixelDiag)
        
    pixelSize = groundDiag / pixelDiag # Meters / pixels
    return pixelSize
    
    


# This function is copied from the NGT Tools repo!    
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


def getPixelToGdcTransform(imagePath, pixelToProjectedTransform=None):
    '''Returns a pixel to GDC transform.
       The input image must either be a nicely georegistered image from Earth Engine
       or a pixel to projected coordinates transform must be provided.'''

    stats  = IrgGeoFunctions.getImageGeoInfo(imagePath, False)
    width  = stats['image_size'][0]
    height = stats['image_size'][1]
    
    if pixelToProjectedTransform:
        # Have image to projected transform, convert it to an image to GDC transform.
        
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
        # Make a transform from ref pixel to GDC using metadata on disk
        (minLon, maxLon, minLat, maxLat) = stats['lonlat_bounds']
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
        #cmdPath = 'build/registerGeocamImage'
        cmd = [cmdPath, refImagePath, testImagePath, transformPath]
        if debug: cmd.append('y')
        else:     cmd.append('n')
        if slowMethod: cmd.append('y')
        else:          cmd.append('n')
        print "command is "
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

    dataDict = {'pixelTransform':tform,
                'confidence':confidence,
                'refImagePath':refImagePath,
                'imageGdcTransform':imageToGdcTransform}
    
    with open(outputPath, 'w') as outFile:
        json.dumps(dataDict, outFile)


def readRegistrationLog(logPath):
    '''Reads a log file written by logRegistrationResults.
       Returns None for every value if the log does not exist.'''
    
    if not os.path.exists(logPath):
        return (None, None, None, None)
    
    with open(logPath, 'r') as inFile:
        dataDict = json.loads(inFile)
    
    return (dataDict['pixelTransform'],    dataDict['confidence'],
            dataDict['refImagePath'], dataDict['imageToGdcTransform'])



