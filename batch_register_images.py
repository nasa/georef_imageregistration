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



# TODO: Make this work!
def getImageMetadata(path):
    '''Retrieves the required image metadata for a file'''
    
    metadata = dict()
    metadata['mpp'] = 0
    metadata['centerLon'] = 0
    metadata['centerLat'] = 0
    metadata['priorImage'] = ''
    metadata['date'] = ''
    metadata['imageSize'] = registration_common.getImageSize(path)
    
    return metadata


def getLogLocation(imagePath, logFolder):
    '''Returns the log path for an input image'''

    imageName = os.path.splitext(os.path.basename(imagePath))[0]
    logPath   = os.path.join(logFolder, imageName + '_alignLog.txt')
    return logPath


def getLoggedPixelToGdcTransform(imagePath, logFolder):
    '''Checks if an image has a logged pixelToGdcTransform and if so returns it'''

    logPath = getLogLocation(imagePath, logFolder)
    (pixelTransform, confidence, refImagePath, imageToGdcTransform) = \
            registration_common.readRegistrationLog(path)
    return imageToGdcTransform

def processImage(imagePath, logFolder, workDir, debug, force, slowMethod, localOnly):
    '''Process one image and record a log file for it.
       - localOnly means only image-to-previous-image alignment.
       - upgradeOnly means dont'''
    
    logPath  = getLogLocation(imagePath, logFolder)
    metadata = getImageMetadata(imagePath)

    # Check what existing logged information we can use
    if not force:
        (logPixelTransform, logConfidence, logRefImagePath, logImageToGdcTransform) = \
                registration_common.readRegistrationLog(logPath)
    else: # If force is set, pretend the log does not exist.
        (logPixelTransform, logConfidence, logRefImagePath, logImageToGdcTransform) = \
                (None, None, None, None)
    if logImageToGdcTransform:
        return # Already have all the information we need

    # Update current status to reflect the log information
    pixelTransform = logPixelTransform
    confidence     = logConfidence
    bestStatus     = logConfidence
    if not logConfidence:
        bestStatus = registration_common.CONFIDENCE_NONE
    
    # Try to register the image to the previous image
    try:
        if metadata['priorImage']:
            
            # If we already have a logged match, dont redo this unless forced to.
            # - The results are pre-populated with log information.
            if not logConfidence:
                workPrefix = os.path.join(workDir, imageName + '_work_series')
                (pixelTransform, confidence, imageInliers, refInliers) = \
                    registration_common.alignImages(imagePath, metadata['priorImage'], workPrefix,
                                                    force, debug, slowMethod)
                bestStatus = confidence

            # Whether we got the transform/confidence from the log or from just now,
            #  try to improve it with GDC information.

            # If we can get a GDC transform for the prior image, we can get one for this image.
            # - Otherwise tha GDC transform will be left blank.
            refImageGdcTransform = getLoggedPixelToGdcTransform(refImagePath, logFolder)
            if refImageGdcTransform:
                imageToGdcTransform = getGdcTransformFromPixelTransform(
                                            metadata['imageSize'], pixelTransform, refImageGdcTransform)
            else:
                imageToGdcTransform = None
            
            # Log the image with only the pixel transform to the previous image
            registration_common.logRegistrationResults(logPath, pixelTransform, confidence,
                                                       metadata['priorImage'],
                                                       imageToGdcTransform)
            return

    except Exception,e:
        print 'Caught exception while aligning to previous image on: ' + imagePath
        print str(e)

    # If not a good match, try with a downloaded image.
    try:
        if (not localOnly) and (bestStatus != registration_common.CONFIDENCE_HIGH):
            # Fetch a reference image
            refImagePath = os.path.join(workDir, imageName + '_ref_image.tif')
            ImageFetcher.fetchReferenceImage.fetchReferenceImage(metadata['centerLon'],
                                                                 metadata['centerLat'],
                                                                 metadata['mpp'],
                                                                 metadata['date'],
                                                                 refImagePath)
            if not os.path.exists(refImagePath):
                raise Exception('Failed to download reference image!')

            workPrefix = os.path.join(workDir, imageName + '_work_EE')
            (pixelTransform, confidence, imageInliers, refInliers) = \
                registration_common.alignImages(imagePath, refImagePath, workPrefix,
                                                force, debug, slowMethod)

            if confidence >= bestStatus: # This will overwrite any existing log file.
                
                # Compute the imageToGdc transform
                refImageGdcTransform = registration_common.getPixelToGdcTransform(refImagePath)
                imageToGdcTransform  = getGdcTransformFromPixelTransform(
                                        metadata['imageSize'], pixelTransform, refImageGdcTransform)

                # Log the image with the pixel and GDC transforms.
                registration_common.logRegistrationResults(logPath, pixelTransform, confidence,
                                                           refImagePath, imageToGdcTransform)
            return

    except Exception,e:
        print 'Caught exception while aligning to EE image on: ' + imagePath
        print str(e)

    raise Exception('Unable to align image:' + imagePath)


#======================================================================================
# Main interface function


def batchRegisterImages(imageList, logFolder,
                   debug=False, force=False, slowMethod=False, localOnly=False):
    '''Attempts to georegister all of the input images.  Outputs will be written to logFolder.'''


    # Set up the output folder and a working directory
    if not os.path.exists(logFolder):
        os.mkdir(logFolder)
    if not debug:
        workDir = tempfile.mkdtemp()
    else: # In debug mode, create a more permanent work location.
        workDir = os.path.join(logFolder, 'workDir')
        if not os.path.exists(workDir):
            os.mkdir(workDir)
    workPrefix = workDir + '/work'

    # Process each of the images
    numImages = len(imageList)
    for i in range(0,numImages):
        
        try:
            # TODO: Search for existing logs and see if there is an existing sequence to append to
            thisImage     = imageList[i]
            processImage(thisImage, logFolder, workDir, debug, force, slowMethod, localOnly)
        except Exception,e:
            print 'Caught exception while processing image: ' + thisImage
            print str(e)


def test():
  '''Run a simple test to make sure the code runs'''
  
  batchRegisterImage('/home/smcmich1/data/geocam_images/ISS030-E-254011.JPG', -7.5, 29.0, 400, '2012.04.21',
                 refImagePath=None, referenceGeoTransform=None, debug=True, force=True, slowMethod=False)

# Simple test script
if __name__ == "__main__":
    sys.exit(test())





