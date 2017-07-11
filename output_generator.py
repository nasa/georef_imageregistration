#!/usr/bin/env python
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

import os, sys
import optparse
import sqlite3
import time
import datetime
#from pysqlite2 import dbapi2 as sqlite3

import registration_common
import register_image
import traceback

import dbLogger
import source_database
import offline_config
import georefDbWrapper
import IrgGeoFunctions

import django
from django.conf import settings
django.setup()

from geocamTiePoint import quadTree
from geocamUtil import imageInfo


'''
This tool monitors for images which are finished processing
and generates the output files for them.
'''

# TODO: There are some duplicates with backlog_processor

def findReadyImages(mission, roll, frame, limit, autoOnly, manualOnly, georefDb):
    '''Get the next image which is ready to process'''

    if frame:
        return [(mission, roll, frame)]

    imageList = georefDb.getImagesReadyForOutput(limit=limit, autoOnly=autoOnly,
                                                 manualOnly=manualOnly)

    return imageList


def getImageRegistrationInfo(frameDbData, georefDb):
    '''Get information for the specified image'''
        
    # Retrieve needed image info from our DB
    registrationResult = georefDb.getRegistrationResult(frameDbData.mission, frameDbData.roll, frameDbData.frame)
    
    # This function generates/fetches the source image if it does not exist
    sourceImagePath, exifSourcePath = source_database.getSourceImage(frameDbData)
    registrationResult['sourceImagePath'] = sourceImagePath
    registrationResult['exifSourcePath'] = exifSourcePath
    
    return registrationResult


def correctPixelCoordinates(registrationResult):
    '''Rescales the pixel coordinates based on the resolution they were collected at
       compared to the full image resolution.'''
       
    # TODO: Account for the image side labels adjusting the image size!

    sourceHeight = registrationResult['manualImageHeight']
    sourceWidth  = registrationResult['manualImageWidth' ]
    
    (outputWidth, outputHeight) = IrgGeoFunctions.getImageSize(registrationResult['sourceImagePath'])

    if (sourceHeight != outputHeight) or (sourceWidth != outputWidth):

        # Compute rescale
        heightScale = float(outputHeight) / float(sourceHeight)
        widthScale  = float(outputWidth)  / float(sourceWidth)

        # Apply to each of the pixel coordinates
        out = []
        for pixel in registrationResult['imageInliers']:
            newPixel = (pixel[0]*widthScale, pixel[1]*heightScale)
            out.append(newPixel)
        registrationResult['imageInliers'] = out
    
    return registrationResult


def getOutputPrefix(mission, roll, frame):
    '''Return the output prefix for this frame'''
    filePath = registration_common.getWorkingPath(mission, roll, frame)
    prefix   = os.path.splitext(filePath)[0]
    
    return prefix


def setupOutputGenerator():
    """
    This needs to be called before we can run "runOutputGenerator"
    """
    # TODO: Turn the input DB into a full wrapper.
    sourceDb = sqlite3.connect(offline_config.DB_PATH)
    sourceDbCursor = sourceDb.cursor()
    georefDb = georefDbWrapper.DatabaseLogger()
    return [sourceDb, sourceDbCursor, georefDb]


def createZipFile(successFrame, centerPointSource):
    mission, roll, frame = successFrame
    timenow = datetime.datetime.utcnow()
    # define the path where zipfile will be saved
    zipFileName = mission + '-' + roll + '-' + frame + '_' + centerPointSource + '_' + timenow.strftime('%Y-%m-%d-%H%M%S-UTC') + '.zip'
    zipFileDir = registration_common.getZipFilePath(mission, roll, frame)
    zipFilePath = zipFileDir + '/' + zipFileName 
    # geotiff images and metadata files to be zipped
    sourceFilesDir = registration_common.getWorkingDir(mission, roll, frame)
    
    writer = quadTree.ZipWriter(sourceFilesDir, zipFilePath)
    writer.addDir(frame, centerPointSource)
    

def output_generator(mission, roll, frame, limit, autoOnly, manualOnly, sleepInterval):
    """
    Main function that gets called to generate the output.
    """
    sourceDb, sourceDbCursor, georefDb = setupOutputGenerator()
    while True:
        # Get images to process
        targetFrames = findReadyImages(mission, roll, frame, limit, autoOnly, manualOnly, georefDb)
        print "found target frames"
        # keep looking for autoregister data every minute.
        while len(targetFrames) == 0:
            time.sleep(60)    
            targetFrames = findReadyImages(mission, roll, frame, limit, autoOnly, manualOnly, georefDb)
        
        successFrames = list(targetFrames)
        
        for (_mission, _roll, _frame) in targetFrames:
            print "_mission is %s " % _mission
            print "_roll is %s" % _roll
            print "_frame is %s " % _frame
            
            try:
                print str((_mission, _roll, _frame))
                frameDbData = source_database.FrameInfo()
                #frameDbData.loadFromDb(sourceDbCursor, _mission, _roll, _frame)
                frameDbData.mission = _mission
                frameDbData.roll = _roll
                frameDbData.frame = _frame
                
        		# Get the registration info for this image, then apply manual pixel coord correction.
                imageRegistrationInfo = getImageRegistrationInfo(frameDbData, georefDb)
                if imageRegistrationInfo['isManual']:
                    imageRegistrationInfo = correctPixelCoordinates(imageRegistrationInfo)
    
                outputPrefix = getOutputPrefix(_mission, _roll, _frame)
                centerPointSource = imageRegistrationInfo['centerPointSource']
                #TODO: append the center point source to the outputPrefix.
                registration_common.recordOutputImages(imageRegistrationInfo['sourceImagePath'], 
                                                       imageRegistrationInfo['exifSourcePath'],
                                                       outputPrefix,
                                                       imageRegistrationInfo['imageInliers'],
                                                       imageRegistrationInfo['gdcInliers'],
                                                       imageRegistrationInfo['registrationMpp'],
                                                       imageRegistrationInfo['centerPointSource'],
                                                       imageRegistrationInfo['isManual'], overwrite=True)
                
                # create a zipfile.
                createZipFile((_mission, _roll, _frame), centerPointSource)
                
                # Clean up the source image we generated
                os.remove(imageRegistrationInfo['sourceImagePath'])
                # Update the database to record that we wrote the image
                georefDb.markAsWritten(_mission, _roll, _frame)
    
            except Exception as e:
                print e
#                 print 'Caught exception:'
                successFrames.remove((_mission, _roll, _frame))
                test = successFrames
#                 continue
        time.sleep(sleepInterval)
            
            
def main():
    try: 
        parser = optparse.OptionParser('usage: %prog')
        parser.add_option("--mission", dest="mission", default=None,
                          help="Specify a mission to process.")
        parser.add_option("--roll",    dest="roll",    default=None,
                          help="Specify a roll to process.  Requires mission.")
        parser.add_option("--frame",   dest="frame",   default=None,
                          help="Specify a frame to process. Requires roll.")
        
        parser.add_option("--manual-only", dest="manualOnly", action="store_true", default=False,
                          help="Restrict to processing only manually-registered images.")
        parser.add_option("--auto-only", dest="autoOnly", action="store_true", default=False,
                          help="Restrict to processing only automatically-registered images.")
    
        parser.add_option("--limit",   dest="limit",   default=0, type="int",
                          help="Do not process more than this many frames.")
        
        parser.add_option("--sleepInterval",   dest="sleepInterval",   default=0, type="int",
                          help="Sleep interval in seconds (frequency)")
        opts, _args = parser.parse_args()
        
        # Error checking
        if ((opts.mission or opts.roll or opts.frame) and 
            not (opts.mission and opts.roll and opts.frame)):
            raise Exception('mission/roll/frame must be provided together!')
            
        if opts.autoOnly and opts.manualOnly:
            raise Exception("auto-only and manual-only opts are mutually exclusive!")
    
    except optparse.OptionError, msg:
        raise Usage(msg)
    
    print '---=== Output Generator has started ===---'

    print 'Connecting to our database...'
    output_generator(opts.mission, opts.roll, opts.frame, opts.limit, 
                       opts.autoOnly, opts.manualOnly, opts.sleepInterval)
    
    print '---=== Output Generator has stopped ===---'


if __name__ == '__main__':
    main()
