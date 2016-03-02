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

import registration_common

#======================================================================================
# Supporting functions



def convertTransformToGeo(tform, newImagePath, refImagePath, refImageGeoTransform=None):
    '''Converts an image-to-image homography to the ProjectiveTransform
       class used elsewhere in geocam.
       Either the reference image must be geo-registered, or the geo transform for it
       must be provided.'''

    # Convert the image-to-image transform parameters to a class
    temp = numpy.array([tform[0:3], tform[3:6], tform[6:9]] )
    imageToRefTransform = transform.ProjectiveTransform(temp)

    newImageSize = registration_common.getImageSize(newImagePath)

    # Get a pixel to GDC transform for the reference image
    refPixelToGdcTransform = registration_common.getPixelToGdcTransform(
                                            refImagePath, refImageGeoTransform)

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
            registration_common.alignImages(imagePath, refImagePath, workPrefix, force, debug, slowMethod)

    if (confidence == registration_common.CONFIDENCE_NONE):
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





