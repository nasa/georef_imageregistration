
import os
import sys
import math
import subprocess
import traceback
import json
import numpy
import shutil
import IrgGeoFunctions

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


def getIdentityTransform():
    '''Return an identity transform from the transform.py file'''
    return transform.ProjectiveTransform(numpy.matrix([[1,0,0],[0,1,0],[0,0,1]],dtype='float64'))


def isPixelValid(pixel, size):
    '''Simple pixel bounds check'''
    return ((pixel[0] >= 0      ) and (pixel[1] >= 0      ) and
            (pixel[0] <  size[0]) and (pixel[1] <  size[1])    )

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
        #cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/registerGeocamImage'
        cmdPath = 'build/registerGeocamImage'
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

#
#def logRegistrationResults(outputPath, pixelTransform, confidence,
#                           refImagePath, imageToGdcTransform=None):
#    '''Log the registration results so they can be read back in later.
#       Provides enough data so that the image can be '''
#
#    dataDict = {'pixelTransform':tform,
#                'confidence':confidence,
#                'refImagePath':refImagePath,
#                'imageGdcTransform':imageToGdcTransform}
#    
#    with open(outputPath, 'w') as outFile:
#        json.dumps(dataDict, outFile)
#
#
#def readRegistrationLog(logPath):
#    '''Reads a log file written by logRegistrationResults.
#       Returns None for every value if the log does not exist.'''
#    
#    if not os.path.exists(logPath):
#        return (None, None, None, None)
#    
#    with open(logPath, 'r') as inFile:
#        dataDict = json.loads(inFile)
#    
#    return (dataDict['pixelTransform'],    dataDict['confidence'],
#            dataDict['refImagePath'], dataDict['imageToGdcTransform'])
#


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
    print cmd
    os.system(cmd)
    if not os.path.exists(tempPath1):
        raise Exception('Failed to generate GCP point image!')

    # Get the distance from each 
    cmd2 = ('convert '+tempPath1+' -morphology Distance Euclidean:1,1 '+ tempPath2)
    print cmd2
    os.system(cmd2)
    if not os.path.exists(tempPath2):
        raise Exception('Failed to generate GCP distance image!')


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
    print cmd3
    os.system(cmd3)
    if not os.path.exists(outputPath):
        raise Exception('Failed to generate uncertainty image!')

    # Compute the RMS error using a simple command line tool
    #cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/computeImageRms'
    cmdPath = 'build/computeImageRms'
    cmd4    = [cmdPath, outputPath]
    print cmd4
    p = subprocess.Popen(cmd4, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # Parse the line "RMS: 123"
    parts    = textOutput.split(':')
    rmsError = float(parts[1])

    # Clean up
    os.remove(tempPath1)
    os.remove(tempPath2)
    
    return rmsError


def cropImageLabel(jpegPath, outputPath):
    '''Create a copy of a jpeg file with any label cropped off'''
    
    # Check if there is a labelusing a simple command line tool
    #cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/computeImageRms'
    cmdPath = 'build/detectImageTag'
    cmd    = [cmdPath, jpegPath]
    print cmd
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    
    # The label is always the same number of pixels
    CROP_AMOUNT = 56
    
    if 'NO_LABEL' in textOutput:
        # The file is fine, just copy it.
        shutil.copy(jpegPath, outputPath)
    else:
        # Trim the label off of the bottom of the image
        imageSize    = IrgGeoFunctions.getImageSize(jpegPath)
        imageSize[1] = imageSize[1] - CROP_AMOUNT
        cmd = ('gdal_translate -srcwin 0 0 ' + str(imageSize[0]) +' '+ str(imageSize[1]) +' '+
               jpegPath +' '+ outputPath)
        print cmd
        os.system(cmd)



def generateGeotiff(imagePath, outputPrefix, imagePoints, gdcPoints, rmsError, overwrite=False):
    '''Converts a plain tiff to a geotiff using the provided geo information.'''

    # Check inputs
    if len(imagePoints) != len(gdcPoints):
        raise Exception('Unequal length correspondence points passed to generateGeoTiff!')

    noWarpOutputPath      = outputPrefix + '-no_warp.tif'
    warpOutputPath        = outputPrefix + '-warp.tif'
    
    OUTPUT_PROJECTION = '+proj=longlat +datum=WGS84'

    # First generate a geotiff that adds metadata but does not change the image data.
    # TODO - This may not be useful unless we can duplicate how they processed their RAW data!
    if (not os.path.exists(noWarpOutputPath)) or overwrite:
        print 'Generating UNWARPED output tiff'
        cmd = ('gdal_translate -mo RMS_UNCERTAINTY='+str(rmsError)
               + ' -co "COMPRESS=LZW" -co "tiled=yes"  -co "predictor=2" -a_srs "'
               + OUTPUT_PROJECTION +'" '+ imagePath +' '+ noWarpOutputPath)
        
        ## Include an arbitrary tag with our estimated error amount
        #if errorMeters:
        #    cmd += ' -mo "REGISTRATION_ERROR=+/-'+str(errorMeters)+' meters" '
        
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

    # Now generate a warped geotiff.
    # - TODO: Is this method accurate enough?
    # - "order 2" looks terrible with fewer GCPs, but "order 1" may not accurately
    #   capture the footprint of higher tilt images.
    if (not os.path.exists(warpOutputPath)) or overwrite:
        print 'Generating WARPED output tiff'
        
        # Use a low order to prevent overly aggressize transform fitting
        cmd = ('gdalwarp -co "COMPRESS=LZW" -co "tiled=yes"  -co "predictor=2"'
               + ' -dstalpha -overwrite -order 1 -multi -r cubic -t_srs "'
               + OUTPUT_PROJECTION +'" ' + noWarpOutputPath +' '+ warpOutputPath)
        # Generate the file using gdal_translate
        print cmd
        os.system(cmd)
        # Add some extra metadata fields.
        cmd2 = ('gdal_edit.py -mo TIFFTAG_DOCUMENTNAME= -mo RMS_UNCERTAINTY=' +str(rmsError)
                + ' -mo RESAMPLING_METHOD=cubic -mo WARP_METHOD=poly_order_1 ' + warpOutputPath)
        print cmd2
        os.system(cmd2)
        
        if not os.path.exists(warpOutputPath):
            raise Exception('Failed to create geotiff file: ' + warpOutputPath)








