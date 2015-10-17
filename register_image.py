

import os
import sys
import argparse
import subprocess
import traceback
import tempfile
import numpy
import ImageFetcher.fetchReferenceImage

import IrgStringFunctions, IrgGeoFunctions

# TODO: Make sure this gets found!
basepath    = os.path.abspath(sys.path[0])
pythonpath  = os.path.abspath(basepath + '/../geocamTiePoint/geocamTiePoint')
sys.path.insert(0, pythonpath)
import geocamTiePoint.transform

#======================================================================================
# Supporting functions

# These codes are used to define the confidence in the detected image registration
CONFIDENCE_NONE = 0
CONFIDENCE_LOW  = 1
CONFIDENCE_HIGH = 2

CONFIDENCE_STRINGS = ['NONE', 'LOW', 'HIGH']

def convertTransformToGeo(transform, newImagePath, refImagePath, refImageGeoTransform=None):
    '''Converts an image-to-image homography to the ProjectiveTransform
       class used elsewhere in geocam.
       Either the reference image must be geo-registered, or the geo transform for it
       must be provided.'''

    # Convert the image-to-image transform parameters to a class
    temp = numpy.array([transform[0:3], transform[3:6], transform[6:9]] )
    imageToRefTransform = geocamTiePoint.transform.ProjectiveTransform(temp)

    newImageSize = ImageFetcher.miscUtilities.getImageSize(newImagePath)

    if not refImageGeoTransform:
        # Make a transform from ref pixel to GDC using metadata on disk
        refStats     = IrgGeoFunctions.getImageGeoInfo(refImagePath, False)
        (minLon, maxLon, minLat, maxLat) = refStats['lonlat_bounds']
        xScale = (maxLon - minLon) / refStats['image_size'][1]
        yScale = (maxLat - minLat) / refStats['image_size'][0]
        refPixelToGdcTransform = numpy.array([[xScale, 0,      minLon],
                                              [0,      yScale, minLat],
                                              [0 ,     0,      1     ]])

    # Generate a list of point pairs
    imagePoints = []
    worldPoints = []
    
    # Loop through a grid of pixels in the new image
    # - For each pixel, compute the desired output coordinate
    pointPixelSpacing = (newImageSize[0] + newImageSize[1]) / 20 # Results in about 100 points
    for r in range(0, newImageSize[0], pointPixelSpacing):
        for c in range(0, newImageSize[1], pointPixelSpacing):
            thisPixel = numpy.array([float(c), float(r)])
            pixelInRefImage = imageToRefTransform.forward(thisPixel)
            homogPixel = numpy.array(list(pixelInRefImage) + [1], dtype='float64') # Homogenize the input point
            
            if (not refImageGeoTransform):
                # Use the geo information of the 
                gdcCoordinate   = refPixelToGdcTransform.dot(homogPixel)[0:2]
                projectedCoordinate = geocamTiePoint.transform.lonLatToMeters(gdcCoordinate)
            else: # Use the user-provided transform
                projectedCoordinate = refImageGeoTransform.forward(homogPixel)
                
            imagePoints.append(thisPixel)
            worldPoints.append(projectedCoordinate)
            #print str(thisPixel) + ' --> ' + str(gdcCoordinate) + ' <--> ' + str(projectedCoordinate)

    # Compute a transform object that converts from the new image to projected coordinates
    #print 'Converting transform to world coordinates...'
    outputTransform = geocamTiePoint.transform.getTransform(numpy.asarray(worldPoints),
                                                            numpy.asarray(imagePoints))
    
    #print outputTransform   
    #for i, w in zip(imagePoints, worldPoints):
    #    print str(i) + ' --> ' + str(w) + ' <--> ' + str(outputTransform.forward(i))
    
    return outputTransform


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


def alignImages(testImagePath, refImagePath, workPrefix, force):
    '''Call the C++ code to find the image alignment'''
    
    transformPath = workPrefix + '-transform.txt'
    
    # Run the C++ command if we need to generate the transform
    if (not os.path.exists(transformPath) or force):
        if os.path.exists(transformPath):
            os.remove(transformPath) # Clear out any old results
        cmd = ['build/registerGeocamImage', refImagePath, testImagePath, transformPath, '--debug']
        #print cmd
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        textOutput, err = p.communicate()
    
    if not os.path.exists(transformPath):
        #raise Exception('Failed to compute transform!')
        transform = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        confidence = CONFIDENCE_NONE
        return (transform, confidence)
    
    # Load the computed transform and confidence
    handle   = open(transformPath, 'r')
    fileText = handle.read()
    handle.close()
    lines = fileText.split('\n')
    confidence = CONFIDENCE_NONE
    if 'CONFIDENCE_LOW' in lines[0]:
        confidence = CONFIDENCE_LOW
    if 'CONFIDENCE_HIGH' in lines[0]:
        confidence = CONFIDENCE_HIGH
    transform = [float(f) for f in lines[1].split(',')] +  \
                [float(f) for f in lines[2].split(',')] +  \
                [float(f) for f in lines[3].split(',')]
    
    return (transform, confidence)


#======================================================================================
# Main interface function


def register_image(imagePath, centerLon, centerLat, focalLength, imageDate,
                   refImagePath=None, referenceGeoTransform=None):
    '''Attempts to geo-register the provided image.
       Returns a transform from image coordinates to projected meters coordinates.
       Also returns an evaluation of how likely the registration is to be correct.'''

    # Set up paths in a temporary directory
    workDir = tempfile.mkdtemp()
    workPrefix = workDir + '/work-'
    
    if not referenceImage:
        # Fetch the reference image
        estimatedMpp = estimateGroundResolution(focalLength)
        refImagePath = os.path.join(workDir, 'ref_image.tif')
        ImageFetcher.fetchReferenceImage.fetchReferenceImage(centerLon, centerLat,
                                                             estimatedMpp, imageDate, refImagePath)
    else: # The user provided a reference image
        if not os.path.exists(refImagePath):
            raise Exception('Provided reference image path does not exist!')

    # Try to align to the reference image
    force = True
    (transform, confidence) = alignImages(imagePath, refImagePath, workPrefix, force)

    # Convert the transform into a pixel-->Projected coordinate transform
    geoTransform = register_image.convertTransformToGeo(transform, testImagePath, refImagePath, referenceGeoTransform)

    return (geoTransform, confidence)







