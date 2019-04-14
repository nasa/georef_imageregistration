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
import numpy
import ImageFetcher.fetchReferenceImage
import IrgStringFunctions, IrgGeoFunctions

from registration_common import TemporaryDirectory
import registration_common

basepath = os.path.abspath(sys.path[0]) # Scott debug
sys.path.insert(0, basepath + '/../geocamTiePoint')
sys.path.insert(0, basepath + '/../geocamUtilWeb')

from geocamTiePoint import transform

"""Contains the primary image registration function.
"""

#======================================================================================
# Supporting functions

def convertTransformToGeo(imageToRefImageTransform, newImagePath, refImagePath, refImageGeoTransform=None):
    '''Converts an image-to-image homography to the ProjectiveTransform
       class used elsewhere in geocam.
       Either the reference image must be geo-registered, or the geo transform for it
       must be provided.'''

    # Convert the image-to-image transform parameters to a class
    temp = numpy.array([imageToRefImageTransform[0:3],
                        imageToRefImageTransform[3:6],
                        imageToRefImageTransform[6:9]] )
    imageToRefTransform = transform.ProjectiveTransform(temp)

    newImageSize = IrgGeoFunctions.getImageSize(newImagePath)
    refImageSize = IrgGeoFunctions.getImageSize(refImagePath)

    # Get a pixel to GDC transform for the reference image
    refPixelToGdcTransform = registration_common.getPixelToGdcTransform(
                                                  refImagePath, refImageGeoTransform)

    # Generate a list of point pairs
    imagePoints = []
    projPoints  = []
    gdcPoints   = []
    
    
    print 'transform = \n' + str(imageToRefTransform.matrix)
    
    # Loop through an evenly spaced grid of pixels in the new image
    # - For each pixel, compute the desired output coordinate
    pointPixelSpacing = (newImageSize[0] + newImageSize[1]) / 20 # Results in about 100 points
    for r in range(0, newImageSize[0], pointPixelSpacing):
        for c in range(0, newImageSize[1], pointPixelSpacing):
            # Get pixel in new image and matching pixel in the reference image
            thisPixel       = numpy.array([float(c), float(r)])
            pixelInRefImage = imageToRefTransform.forward(thisPixel)

            # If any pixel transforms outside the reference image our transform
            # is probably invalid but continue on skipping this pixel.
            if ((not registration_common.isPixelValid(thisPixel, newImageSize)) or
                (not registration_common.isPixelValid(pixelInRefImage, refImageSize))):
                continue

            # Compute the location of this pixel in the projected coordinate system
            #  used by the transform.py file.
            if (not refImageGeoTransform):
                # Use the geo information of the reference image
                gdcCoordinate       = refPixelToGdcTransform.forward(pixelInRefImage)
                projectedCoordinate = transform.lonLatToMeters(gdcCoordinate)
            else: # Use the user-provided transform
                projectedCoordinate = refImageGeoTransform.forward(pixelInRefImage)
                gdcCoordinate       = transform.metersToLatLon(projectedCoordinate)
                
            imagePoints.append(thisPixel)
            projPoints.append(projectedCoordinate)
            gdcPoints.append(gdcCoordinate)
            #print str(thisPixel) + ' --> ' + str(gdcCoordinate) + ' <--> ' + str(projectedCoordinate)

    # Compute a transform object that converts from the new image to projected coordinates
    #print 'Converting transform to world coordinates...'
    #testImageToProjectedTransform = transform.getTransform(numpy.asarray(worldPoints),
    #                                                       numpy.asarray(imagePoints))
    testImageToProjectedTransform = transform.ProjectiveTransform.fit(numpy.asarray(projPoints),
                                                                      numpy.asarray(imagePoints))
    
    testImageToGdcTransform = transform.ProjectiveTransform.fit(numpy.asarray(gdcPoints),
                                                                numpy.asarray(imagePoints))
    
    #print refPixelToGdcTransform
    #print testImageToProjectedTransform
    #for i, w in zip(imagePoints, worldPoints):
    #    print str(i) + ' --> ' + str(w) + ' <--> ' + str(testImageToProjectedTransform.forward(i))
    
    return (testImageToProjectedTransform, testImageToGdcTransform, refPixelToGdcTransform)





#======================================================================================
# Main interface function

def register_image(imagePath, centerLon, centerLat, metersPerPixel, imageDate,
                   refImagePath=None, referenceGeoTransform=None, refMetersPerPixelIn=None,
                   debug=False, force=False, slowMethod=False):
    '''Attempts to geo-register the provided image.
       Returns a transform from image coordinates to projected meters coordinates.
       Also returns an evaluation of how likely the registration is to be correct.'''

    if not (os.path.exists(imagePath)):
        raise Exception('Input image path does not exist!')

    with TemporaryDirectory() as myWorkDir:

        # Set up paths in a temporary directory
        if not debug:
            workDir = myWorkDir
        else: # In debug mode, create a more permanent work location.
            workDir = os.path.splitext(imagePath)[0]
        if not os.path.exists(workDir):
            os.mkdir(workDir)
        workPrefix = workDir + '/work'
        
        #print workDir
        
        if not refImagePath:
            # Fetch the reference image
            refImagePath    = os.path.join(workDir, 'ref_image.tif')
            refImageLogPath = os.path.join(workDir, 'ref_image_info.tif')
            if not os.path.exists(refImagePath):
                (percentValid, refMetersPerPixel) = ImageFetcher.fetchReferenceImage.fetchReferenceImage(
                                                        centerLon, centerLat,
                                                        metersPerPixel, imageDate, refImagePath)
                # Log the metadata
                handle = open(refImageLogPath, 'w')
                handle.write(str(percentValid) + '\n' + str(refMetersPerPixel))
                handle.close()
            else:
                # Load the reference image metadata that we logged earlier
                handle   = open(refImageLogPath, 'r')
                fileText = handle.read()
                handle.close()
                lines = fileText.split('\n')
                percentValid      = float(lines[0])
                refMetersPerPixel = float(lines[1])
        else: # The user provided a reference image
            refMetersPerPixel = refMetersPerPixelIn # In this case the user must provide an accurate value!
    
            if not os.path.exists(refImagePath):
                raise Exception('Provided reference image path does not exist!')
    
        # TODO: Reduce the input image to the resolution of the reference image!
        # The reference image may be lower resolution than the input image, in which case
        #  we will need to perform image alignment at the lower reference resolution.
        inputScaling = metersPerPixel / refMetersPerPixel
    
        print 'metersPerPixel    = ' + str(metersPerPixel)
        print 'refMetersPerPixel = ' + str(refMetersPerPixel)
        print 'inputScaling      = ' + str(inputScaling)
    
        # Try to align to the reference image
        # - The transform is from image to refImage
        (imageToRefImageTransform, confidence, imageInliers, refInliers) = \
                registration_common.alignScaledImages(imagePath, refImagePath, inputScaling, workPrefix, force, debug, slowMethod)
    
        # If we failed, just return dummy information with zero confidence.
        if (confidence == registration_common.CONFIDENCE_NONE):
            return (registration_common.getIdentityTransform(),
                    registration_common.getIdentityTransform(),
                    registration_common.CONFIDENCE_NONE, [], [], 0)
    
        # Convert the transform into a pixel-->Projected coordinate transform
        (imageToProjectedTransform, imageToGdcTransform, refImageToGdcTransform) = \
                convertTransformToGeo(imageToRefImageTransform, imagePath, refImagePath, referenceGeoTransform)
    
        # For each input image inlier, generate the world coordinate.
        
        gdcInliers = []
        for pix in refInliers:
            gdcCoordinate = refImageToGdcTransform.forward(pix)
            gdcInliers.append(gdcCoordinate)
    
        return (imageToProjectedTransform, imageToGdcTransform,
                confidence, imageInliers, gdcInliers, refMetersPerPixel)


def test():
    '''Run a simple test to make sure the code runs'''
  
    #register_image('/home/smcmich1/data/geocam_images/ISS030-E-254011.JPG', -7.5, 29.0, 6.7, '2012.04.21',
    #               refImagePath=None, referenceGeoTransform=None, debug=True, force=True, slowMethod=False)
    
    #register_image('/home/smcmich1/data/geocam_images/ISS013-E-6881.JPG',-74.1,  22.7, 10.7, '2006.04.12',
    #              refImagePath=None, referenceGeoTransform=None, debug=True, force=True, slowMethod=False)
    
    # Fails!
    #register_image('/home/smcmich1/data/geocam_images/ISS012-E-19064.JPG',-71.0,  41.5, 10.2, '2006.03.04',
    #              refImagePath=None, referenceGeoTransform=None, debug=True, force=True, slowMethod=False)


# Simple test script
if __name__ == "__main__":
    sys.exit(test())





