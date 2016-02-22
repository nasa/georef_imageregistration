import os
import sys
import argparse
import subprocess
import traceback
import tempfile
import numpy
import ImageFetcher.fetchReferenceImage
import IrgStringFunctions, IrgGeoFunctions

#basepath    = os.path.abspath(sys.path[0]) # Scott debug
#sys.path.insert(0, basepath + '/../geocamTiePoint')
#sys.path.insert(0, basepath + '/../geocamUtilWeb')

from geocamTiePoint import transform
from django.conf import settings

#======================================================================================
# Supporting functions

# These codes are used to define the confidence in the detected image registration
CONFIDENCE_NONE = 0
CONFIDENCE_LOW  = 1
CONFIDENCE_HIGH = 2

CONFIDENCE_STRINGS = ['NONE', 'LOW', 'HIGH']

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



def convertTransformToGeo(tform, newImagePath, refImagePath, refImageGeoTransform=None):
    '''Converts an image-to-image homography to the ProjectiveTransform
       class used elsewhere in geocam.
       Either the reference image must be geo-registered, or the geo transform for it
       must be provided.'''

    # Convert the image-to-image transform parameters to a class
    temp = numpy.array([tform[0:3], tform[3:6], tform[6:9]] )
    imageToRefTransform = transform.ProjectiveTransform(temp)

    newImageSize = ImageFetcher.miscUtilities.getImageSize(newImagePath)

    # Get a pixel to GDC transform for the reference image
    refPixelToGdcTransform = getPixelToGdcTransform(refImagePath, refImageGeoTransform)

    # Generate a list of point pairs
    imagePoints = []
    worldPoints = []
    
    # Loop through an evenly spaced grid of pixels in the new image
    # - For each pixel, compute the desired output coordinate
    pointPixelSpacing = (newImageSize[0] + newImageSize[1]) / 20 # Results in about 100 points
    for r in range(0, newImageSize[0], pointPixelSpacing):
        for c in range(0, newImageSize[1], pointPixelSpacing):
            # Get pixel in new image and matching pixel in the reference image
            thisPixel       = numpy.array([float(c), float(r)])
            pixelInRefImage = imageToRefTransform.forward(thisPixel)

            # Compute the location of this pixel in the projected coordinate system
            #  used by the transform.py file.
            if (not refImageGeoTransform):
                # Use the geo information of the reference image
                gdcCoordinate       = refPixelToGdcTransform.forward(pixelInRefImage)
                projectedCoordinate = transform.lonLatToMeters(gdcCoordinate)
            else: # Use the user-provided transform
                projectedCoordinate = refImageGeoTransform.forward(pixelInRefImage)
                
            imagePoints.append(thisPixel)
            worldPoints.append(projectedCoordinate)
            #print str(thisPixel) + ' --> ' + str(gdcCoordinate) + ' <--> ' + str(projectedCoordinate)

    # Compute a transform object that converts from the new image to projected coordinates
    #print 'Converting transform to world coordinates...'
    testImageToProjectedTransform = transform.getTransform(numpy.asarray(worldPoints),
                                                           numpy.asarray(imagePoints))
    
    #print refPixelToGdcTransform
    #print testImageToProjectedTransform
    #for i, w in zip(imagePoints, worldPoints):
    #    print str(i) + ' --> ' + str(w) + ' <--> ' + str(testImageToProjectedTransform.forward(i))
    
    return (testImageToProjectedTransform, refPixelToGdcTransform)


def estimateGroundResolution(focalLength):
    '''Estimates a ground resolution in meters per pixel using the focal length.'''
    
    if not focalLength: # Guess a low resolution for a zoomed out image
        return 150
    
    # Based on all the focal lengths we have seen so far
    if focalLength <= 50:
        return 200
    if focalLength <= 110:
        return 80
    if focalLength <= 180:
        return 55
    if focalLength <= 250:
        return 30
    if focalLength <= 340:
        return 25
    if focalLength <= 400:
        return 20
    if focalLength <= 800:
        return 10
    return 0


def alignImages(testImagePath, refImagePath, workPrefix, force, debug=False, slowMethod=False):
    '''Call the C++ code to find the image alignment'''
    
    transformPath = workPrefix + '-transform.txt'

    # The computed transform is from testImage to refImage
    
    # Run the C++ command if we need to generate the transform
    if (not os.path.exists(transformPath) or force):
        if os.path.exists(transformPath):
            os.remove(transformPath) # Clear out any old results
            
        cmdPath = settings.PROJ_ROOT + '/apps/georef_imageregistration/build/registerGeocamImage'
        #cmdPath = 'build/registerGeocamImage'
        cmd = [cmdPath, refImagePath, testImagePath, transformPath]
        if debug: cmd.append('y')
        else:     cmd.append('n')
        if slowMethod: cmd.append('y')
        else:          cmd.append('n')
        #print "command is "
        #print cmd
        #os.system('build/registerGeocamImage '+ refImagePath+' '+testImagePath+' '+transformPath+' --debug')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        textOutput, err = p.communicate()
        #print textOutput
    
    if not os.path.exists(transformPath):
        #raise Exception('Failed to compute transform!')
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


#======================================================================================
# Main interface function

# TODO: User passes in estimatedMpp or we need sensor information!

def register_image(imagePath, centerLon, centerLat, focalLength, imageDate,
                   refImagePath=None, referenceGeoTransform=None, debug=False, force=False, slowMethod=False):
    '''Attempts to geo-register the provided image.
       Returns a transform from image coordinates to projected meters coordinates.
       Also returns an evaluation of how likely the registration is to be correct.'''

    if not (os.path.exists(imagePath)):
        raise Exception('Input image path does not exist!')

    # Set up paths in a temporary directory
    if not debug:
        workDir = tempfile.mkdtemp()
    else: # In debug mode, create a more permanent work location.
        workDir = os.path.splitext(imagePath)[0]
    if not os.path.exists(workDir):
        os.mkdir(workDir)
    workPrefix = workDir + '/work'
    
    #print workDir
    
    if not refImagePath:
        # Fetch the reference image
        estimatedMpp = estimateGroundResolution(focalLength)
        refImagePath = os.path.join(workDir, 'ref_image.tif')
        if not os.path.exists(refImagePath):
            ImageFetcher.fetchReferenceImage.fetchReferenceImage(centerLon, centerLat,
                                                                 estimatedMpp, imageDate, refImagePath)
    else: # The user provided a reference image
        if not os.path.exists(refImagePath):
            raise Exception('Provided reference image path does not exist!')

    # Try to align to the reference image
    # - The transform is from image to refImage
    (tform, confidence, imageInliers, refInliers) = \
            alignImages(imagePath, refImagePath, workPrefix, force, debug, slowMethod)

    if (confidence == CONFIDENCE_NONE):
        raise Exception('Failed to compute tranform!')

    # Convert the transform into a pixel-->Projected coordinate transform
    (imageToProjectedTransform, refImageToGdcTransform) = \
            convertTransformToGeo(tform, imagePath, refImagePath, referenceGeoTransform)

    # For each input image inlier, generate the world coordinate.
    
    gdcInliers = []
    for pix in refInliers:
        gdcCoordinate = refImageToGdcTransform.forward(pix)
        gdcInliers.append(gdcCoordinate)
    #print gdcInliers

    return (imageToProjectedTransform, confidence, imageInliers, gdcInliers)


def test():
  '''Run a simple test to make sure the code runs'''
  
  register_image('/home/smcmich1/data/geocam_images/ISS030-E-254011.JPG', -7.5, 29.0, 400, '2012.04.21',
                 refImagePath=None, referenceGeoTransform=None, debug=True, force=True, slowMethod=False)

# Simple test script
if __name__ == "__main__":
    sys.exit(test())





