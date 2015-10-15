

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
NO_CONFIDENCE   = 0
LOW_CONFIDENCE  = 1
HIGH_CONFIDENCE = 2

def convertTransformToGeo(transform, newImagePath, refImagePath):
    '''Converts an image-to-image homography to the ProjectiveTransform
       class used elsewhere in geocam.'''

    # Convert the transform parameters to a class
    temp = numpy.array([transform[0:3], transform[3:6], transform[6:9]] )
    imageToRefTransform = geocamTiePoint.transform.ProjectiveTransform(temp)

    # Get metadata from the new and reference image
    newImageSize = ImageFetcher.miscUtilities.getImageSize(newImagePath)
    refStats     = IrgGeoFunctions.getImageGeoInfo(refImagePath, False)
    (minLon, maxLon, minLat, maxLat) = refStats['lonlat_bounds']
    
    # Make a transform for ref pixel to GDC
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
            temp = numpy.array(list(pixelInRefImage) + [1], dtype='float64') # Homogenize the input point
            gdcCoordinate   = refPixelToGdcTransform.dot(temp)[0:2]
            projectedCoordinate = geocamTiePoint.transform.lonLatToMeters(gdcCoordinate)
            imagePoints.append(thisPixel)
            worldPoints.append(projectedCoordinate)
            #print str(thisPixel) + ' --> ' + str(gdcCoordinate) + ' <--> ' + str(projectedCoordinate)

    # Compute a transform object that converts from the new image to projected coordinates
    print 'Converting transform to world coordinates...'
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
        cmd = ['build/registerGeocamImage', refImagePath, testImagePath, transformPath, '--debug']
        print cmd
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        textOutput, err = p.communicate()
    
    # Load the computed transform
    handle   = open(transformPath, 'r')
    fileText = handle.read()
    handle.close()
    lines = fileText.split('\n')
    transform = [float(f) for f in lines[1].split(',')] +  \
                [float(f) for f in lines[2].split(',')] +  \
                [float(f) for f in lines[3].split(',')]

    confidence = LOW_CONFIDENCE # TODO: Compute this!
    return (transform, confidence)


#======================================================================================
# Main interface function


def register_image(imagePath, centerLon, centerLat, focalLength, imageDate):
    '''Attempts to geo-register the provided image.
       Returns a transform from image coordinates to projected meters coordinates.
       Also returns an evaluation of how likely the registration is to be correct.'''

    # Set up paths in a temporary directory
    workDir = tempfile.mkdtemp()
    refImagePath = os.path.join(workDir, 'ref_image.tif')
    workPrefix = workDir + '/work-'
    
    # Fetch the reference image
    estimatedMpp = estimateGroundResolution(focalLength)
    return ImageFetcher.fetchReferenceImage.fetchReferenceImage(centerLon, centerLat,
                                                                estimatedMpp, imageDate, refImagePath)

    # Try to align to the reference image
    force = True
    (transform, confidence) = alignImages(imagePath, refImagePath, workPrefix, force)

    # Convert the transform into a pixel-->Projected coordinate transform
    geoTransform = register_image.convertTransformToGeo(transform, testImagePath, refImagePath)

    return (geoTransform, confidence)







