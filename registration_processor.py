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

import registration_common
import register_image
import traceback
import numpy
import time
import signal
import multiprocessing

import IrgGeoFunctions
import georefDbWrapper
import source_image_utils
import offline_config

import django
from django.conf import settings
django.setup()

'''
This tool monitors for files that we have a center point for
and attempts to geo-register them.
'''
def computeFrameInfoMetersPerPixel(frameInfo):
    '''Estimate the meters per pixel value for a FrameInfo object'''
    frameInfo.metersPerPixel = registration_common.estimateGroundResolution(frameInfo.focalLength,
                                frameInfo.width, frameInfo.height, frameInfo.sensorWidth,
                                frameInfo.sensorHeight, frameInfo.nadirLon, frameInfo.nadirLat,
                                frameInfo.altitude, frameInfo.centerLon, frameInfo.centerLat,
                                frameInfo.tilt)
    return frameInfo



def findNearbyResults(targetFrameData, sourceDb, georefDb):
    '''Looks for results we have that we may be able to match to.'''

    imageTime = targetFrameData.getMySqlDateTime()
    
    # Get a list of our results we have that we can compare to, restricting to mission.
    ourResults = georefDb.findNearbyGoodResults(imageTime,
                                2*offline_config.LOCAL_ALIGNMENT_MAX_FRAME_RANGE,
                                mission=targetFrameData.mission)
    if not ourResults:
        return []
    
    print 'Candidate nearby results:'
    print ourResults
    
    # Loop through the results, keys are the frame numbers (as strings).
    results = []
    numAttempts  = 0
    for k, v in ourResults.iteritems():
    
        # Fetch info for this frame from the input database
        frameDbData = source_image_utils.FrameInfo()
        frameDbData = sourceDb.loadFrame(targetFrameData.mission, targetFrameData.roll, k)
    
        # Estimate the meters per pixel value
        frameDbData = computeFrameInfoMetersPerPixel(frameDbData)
    
        # Check the quality and distance
        if (frameDbData.isGoodAlignmentCandidate() and
            frameDbData.isCenterWithinDist(targetFrameData.centerLon, targetFrameData.centerLat,
                                           offline_config.LOCAL_ALIGNMENT_MAX_DIST)):
            
            # Add to the list of frames we will compare to.
            results.append((frameDbData, v))
            print 'Found potential local match frame: ' + frameDbData.frame
            numAttempts += 1
        
        if numAttempts == offline_config.LOCAL_ALIGNMENT_MAX_ATTEMPTS:
            break

    print 'Near results:'
    print results
    return results
    

def matchLocally(mission, roll, frame, sourceDb, georefDb, sourceImagePath):
    '''Performs image alignment to an already aligned ISS image'''

    # Load new frame info
    targetFrameData = source_image_utils.FrameInfo()
    targetFrameData = sourceDb.loadFrame(mission, roll, frame)
    targetFrameData = computeFrameInfoMetersPerPixel(targetFrameData)

    # Find candidate names to match to
    possibleNearbyMatches = findNearbyResults(targetFrameData, sourceDb, georefDb)

    if not possibleNearbyMatches:
        print 'Did not find any potential local matches!'

    for (otherFrame, ourResult) in possibleNearbyMatches:

        print 'Trying local match with frame: ' + str(otherFrame.frame)

        # Get path to other frame image
        otherImagePath, exifSourcePath = source_image_utils.getSourceImage(otherFrame)
        source_image_utils.clearExif(exifSourcePath)
        otherTransform = ourResult[0] # This is still in the google projected format

        #print 'otherTransform = ' + str(otherTransform.matrix)

        print 'New image mpp = ' + str(targetFrameData.metersPerPixel)
        print 'Local match image mpp = ' + str(otherFrame.metersPerPixel)
        # If we could not estimate the MPP value of the new image, guess that it is the same as
        #  the local reference image we are about to try.
        thisMpp = targetFrameData.metersPerPixel
        if not thisMpp:
            thisMpp = otherFrame.metersPerPixel
        
        print 'Attempting to register image...'
        (imageToProjectedTransform, imageToGdcTransform, confidence, imageInliers, gdcInliers, refMetersPerPixel) = \
            register_image.register_image(sourceImagePath,
                                          otherFrame.centerLon, otherFrame.centerLat,
                                          thisMpp, targetFrameData.date,
                                          refImagePath         =otherImagePath,
                                          referenceGeoTransform=otherTransform,
                                          refMetersPerPixelIn  =otherFrame.metersPerPixel,
                                          debug=options.debug, force=True, slowMethod=False)       
        if not options.debug:
            os.remove(otherImagePath) # Clean up the image we matched against

        # Quit once we get a good match
        if confidence == registration_common.CONFIDENCE_HIGH:
            print 'High confidence match!'
            # Convert from the image-to-image GCPs to the reference image GCPs
            #  located in the new image.
            refFrameGdcInliers = ourResult[3] # TODO: Clean this up!
            (width, height)    = IrgGeoFunctions.getImageSize(sourceImagePath)
            
            print '\n\n'
            print refFrameGdcInliers
            print '\n\n'
            
            (imageInliers, gdcInliers) = registration_common.convertGcps(refFrameGdcInliers,
                                                imageToProjectedTransform, width, height)
            
            print imageInliers
            print '\n\n'
            
            # If none of the original GCPs fall in the new image, don't use this alignment result.
            # - We could use this result, but we don't in order to maintain accuracy standards.
            if imageInliers:
                print 'Have inliers'
                print otherFrame
                return (imageToProjectedTransform, imageToGdcTransform, confidence,
                        imageInliers, gdcInliers, refMetersPerPixel, otherFrame)
            else:
                print 'Inliers out of bounds!'

    # Match failure, return junk values
    return (registration_common.getIdentityTransform(), registration_common.getIdentityTransform(),
            registration_common.CONFIDENCE_NONE, [], [], 9999, None)


def computeCenterGdcCoord(imageToGdcTransform, frameDbData):
    '''Compute the center GDC coord from registration results'''
    try:
        centerPixel = numpy.array([float(frameDbData.width/2.0), float(frameDbData.height/2.0)])
        centerGdc = imageToGdcTransform.forward(centerPixel)
        return (centerGdc[0], centerGdc[1])
    except: # Failed to compute location, use a flag value.
        return (-999,-999)


def doNothing(options, frameInfo, searchNearby, georefDb):
    print 'DO NOTHING'
    return 0

def processFrame(options, frameDbData, searchNearby=False):
    '''Process a single specified frame.
       Returns True if we attempted to perform image alignment and did not hit an exception.'''
    try:
        georefDb = georefDbWrapper.DatabaseLogger()
        # Increase the error slightly for chained image transforms
        LOCAL_TRANSFORM_ERROR_ADJUST = 1.10
        sourceImagePath, exifSourcePath = source_image_utils.getSourceImage(frameDbData, overwrite=True)
        if not options.debug:
            source_image_utils.clearExif(exifSourcePath)
        try:
            # If requested, get nearby previously matched frames to compare to.
            if searchNearby:
                sourceDb = input_db_wrapper.InputDbWrapper()

                (imageToProjectedTransform, imageToGdcTransform, confidence, imageInliers, gdcInliers, refMetersPerPixel, otherFrame) = \
                    matchLocally(frameDbData.mission, frameDbData.roll, frameDbData.frame, sourceDb, georefDb, sourceImagePath)
                if otherFrame:
                    matchedImageId = otherFrame.getIdString()
                else:
                    matchedImageId = 'None'

            else: # Try to register the image to Landsat
                print 'Attempting to register image...'
                (imageToProjectedTransform, imageToGdcTransform, confidence, imageInliers, gdcInliers, refMetersPerPixel) = \
                    register_image.register_image(sourceImagePath,
                                                  frameDbData.centerLon, frameDbData.centerLat,
                                                  frameDbData.metersPerPixel, frameDbData.date,
                                                  refImagePath=None,
                                                  debug=False, force=True, slowMethod=True)
                matchedImageId = 'Landsat'
        except Exception as e:
            print 'Computing transform for frame '+frameDbData.getIdString()+', caught exception: ' + str(e)
            print "".join(traceback.format_exception(*sys.exc_info()))
            print 'Logging the result as no-confidence.'
            confidence   = registration_common.CONFIDENCE_NONE
            imageInliers = []
            gdcInliers   = []
            matchedImageId    = 'NA'
            refMetersPerPixel = 999
            imageToProjectedTransform = registration_common.getIdentityTransform()
            imageToGdcTransform       = registration_common.getIdentityTransform()

        # A very rough estimation of localization error at the inlier locations!
        errorMeters = refMetersPerPixel * 1.5
        # Convert into format that our DB is looking for.
        sourceDateTime = frameDbData.getMySqlDateTime()
        if confidence > registration_common.CONFIDENCE_NONE:
            (centerLon, centerLat) = computeCenterGdcCoord(imageToGdcTransform, frameDbData)
        else:
            (centerLon, centerLat) = (-999, -999)
        # Log the results to our database
        centerPointSource = frameDbData.centerPointSource 
        georefDb.addResult(frameDbData.mission, frameDbData.roll, frameDbData.frame,
                           imageToProjectedTransform, imageToGdcTransform,
                           centerLon, centerLat, refMetersPerPixel,
                           confidence, imageInliers, gdcInliers,
                           matchedImageId, sourceDateTime, centerPointSource)
        # This tool just finds the interest points and computes the transform,
        # a different tool will actually write the output images.
        if not options.debug:
            os.remove(sourceImagePath) # Clean up the source image
        print ('Finished processing frame ' + frameDbData.getIdString()
               + ' with confidence ' + registration_common.CONFIDENCE_STRINGS[confidence])
        return confidence
    
    except Exception as e:
        print 'Processing frame '+frameDbData.getIdString()+', caught exception: ' + str(e)
        print "".join(traceback.format_exception(*sys.exc_info()))
        #raise Exception('FAIL')
        return 0
    

def findReadyImages(options, sourceDb, georefDb, limit=1):
    '''Get the next image that is ready to process'''

    # Get a list of all images which might be ready to register (center point does not have to be available).
    candidateImages = sourceDb.getCandidatesInMission(options.mission, options.roll, options.frame, checkCoords=False)
    
    print 'Found ' + str(len(candidateImages)) +' matches.'
    
    # Now filter based on center point and our results
    # - We have to check each frame in our DB one at a time to see if we already registered it.
    results = []
    for (mission, roll, frame, lon, lat) in candidateImages:
        # Load remaining information about the frame from the JSC source database
        frameInfo = source_image_utils.FrameInfo()
        try:
            frameInfo = sourceDb.loadFrame(mission, roll, frame)
            # make sure the image is a good alignment candidate (no clouds, good exposure, etc). If not, skip
            good = frameInfo.isGoodAlignmentCandidate()
        except: 
            print "failed to load information about the frame %s, %s, %s" % (mission, roll, frame)
            good = False
        
        if not good:
            print 'Bad candidate'
            continue
        
        # At this point, frameInfo may contain centerLon and centerLat (the "AUTOWCENTER" source).
        
        # Retrieve existing automatch results from our database
        (autolon, autolat, confidence, autoMatchCenterSource) = georefDb.getAutomatchResults(mission, roll, frame)
        # Get the current best center point that is available.
        (bestlon, bestlat, confidence, bestCenterSource) = georefDb.getBestCenterPoint(mission, roll, frame, frameInfo)    
 
        lon = None
        lat = None
        centerPointSource = None       
        
        # TODO: Check this logic!
        if (autolon and autolat) and ((autoMatchCenterSource != bestCenterSource) and (autoMatchCenterSource != georefDbWrapper.MANUAL)):
            # The image has been autoregistered and no better data is available.
            lon = autolon
            lat = autolat
            centerPointSource = autoMatchCenterSource
            continue
        else:  # not previously auto registered or there is better data available.
            lon = bestlon
            lat = bestlat
            centerPointSource = bestCenterSource
    
        # Now that we have a good frame, update some information before returning the frame info
        frameInfo.centerLon = lon
        frameInfo.centerLat = lat
        frameInfo.centerPointSource = centerPointSource
        frameInfo = computeFrameInfoMetersPerPixel(frameInfo)
        
        # Retain info and see if we have enough frames
        results.append(frameInfo)
        if len(results) >= limit:
            break
        
    return results


# TODO: Move this
def print_stats(options, sourceDb, georefDb):
    
    if options.mission:
        missionList = [options.mission]
    else:
        missionList = sourceDb.getMissionList()

    # Print a header line
    print 'MISSION\t-->\tTOTAL\tNONE\tLOW\tHIGH\tHIGH_FRACTION'
    
    # Process each of the selected missions
    for mission in missionList:
        
        counts = georefDb.getProcessingStats(mission)
        try:
            ratio  = float(counts[3])/float(counts[0])
        except:
            ratio = 0.0
        print ('%s\t-->\t%d\t%d\t%d\t%d\t%.2f' %
            (mission, counts[0], counts[1], counts[2], counts[3], ratio))


def sleepOnNumJobs(jobList, jobLimit):
    '''Sleep until the number of jobs get under a limit.'''

    # TODO: Add an absolute timeout?

    # Loop until at least on job finishes.    
    while len(jobList) >= jobLimit:
        time.sleep(2)
        # If any of the jobs are complete, remove them.
        for job in jobList:
            if job[1].ready():
                print 'Removing job for frame ' + job[0]
                dummy = job[1].get() # Currently we don't care about the status.
                jobList.remove(job)


def initWorker():
    '''Called at the start of each process'''
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def registrationProcessor(options):
    """
    The main function that gets called with options.
    """
    # Handle overwrite options
    options.overwrite = False
    if options.overwriteLevel:
        options.overwriteLevel = registration_common.confidenceFromString(options.overwriteLevel)
        options.overwrite      = True

    print '---=== Registration Processor has started ===---'

    # Set up wrappers for the input and output databases.
    sourceDb = input_db_wrapper.InputDbWrapper()
    georefDb = georefDbWrapper.DatabaseLogger()
    
    print 'Finished opening databases.'

    if options.printStats:
        print_stats(options, sourceDb, georefDb)
        return 0

    # TODO: Set up logging

    # Initialize the multi-threading worker pool
    print 'Setting up worker pool with ' + str(options.numThreads) +' threads.'
    pool = multiprocessing.Pool(options.numThreads, initWorker)

    # Don't let our list of pending jobs get too enormous.
    jobLimit = options.limit
    if (jobLimit < 1) or (jobLimit > 60):
        jobLimit = 60

    readyFrames = []
    jobList  = []
    count = 0
    
    try:
        while True:
            # Wait here if our work queue is full
            sleepOnNumJobs(jobList, jobLimit)
        
            # If we are out of ready frames, find a new set.
            if not readyFrames:
                print '============================================================='
                print 'Frame update!'
                
                print 'In progress frames:'
                for job in jobList:
                    print job[0]
                
                readyFrames = findReadyImages(options, sourceDb, georefDb, jobLimit)
    
                if not readyFrames:
                    print 'Registration Processor found no more data!'
                    #TODO maybe it should sleep.
                    break
    
                # Delete all frames from the readyFrames list that are already
                #  assigned to a job in the jobList.
                copyFrames = readyFrames
                for job in jobList:
                    for frame in copyFrames:
                        if job[0] == frame.getIdString():
                            print 'Remove in progress: ' + frame.getIdString()
                            readyFrames.remove(frame)

                if not readyFrames:
                    print 'Registration Processor found no more data!'
                    #TODO maybe it should sleep.
                    break

                print 'Remaining frames:'
                for frame in readyFrames:
                    print frame.getIdString()

                #if count > 0:
                #    raise Exception('DEBUG!!!')

                print '============================================================='
    
            frameInfo = readyFrames.pop() # Grab one of the ready frames from the list
    
            print 'Registration Processor assigning job: ' + frameInfo.getIdString()

            # Add this process to the processing pool
            processResult = pool.apply_async(processFrame, args=(options, frameInfo, options.localSearch))

            # Hang on to the process handle and the associated frame ID
            jobList.append((frameInfo.getIdString(), processResult))
    
            ## If that did not succeed, try to register to a local image.
            #if confidence < registration_common.CONFIDENCE_HIGH:
            #    confidence = processFrame(sourceImagePath, frameInfo, searchNearby=True)
    
            count += 1
    
            if options.frame or (options.limit and (count >= options.limit)):
                print 'Registration Processor has started processing the requested number of images.'
                break
    
    
        if pool: # Wait for all the tasks to complete
            print('Waiting for processes to complete...')
            for job in jobList:
                confidence = job[1].get()

    except KeyboardInterrupt:
        print "Caught KeyboardInterrupt, terminating workers"
        pool.terminate()
        pool.join()

    POOL_KILL_TIMEOUT = 5 # The pool should not be doing any work at this point!
    if pool:
        print('Cleaning up the processing thread pool...')
        # Give the pool processes a little time to stop, them kill them.
        pool.close()
        time.sleep(POOL_KILL_TIMEOUT)
        pool.terminate()
        pool.join()

    print '---=== Registration Processor has stopped ===---'
    
    
def main(argsIn):
    try:
        usage = "usage: registration_processor.py [--help]\n  "
        parser = optparse.OptionParser(usage=usage)
        
        parser.add_option("--mission", dest="mission", default=None,
                          help="Specify a mission to process.")
        parser.add_option("--roll",    dest="roll",    default=None,
                          help="Specify a roll to process.  Requires mission.")
        parser.add_option("--frame",   dest="frame",   default=None,
                          help="Specify a frame to process. Requires roll.")

        parser.add_option("--debug", dest="debug", action="store_true", default=False,
                          help="Write debug images.")

        parser.add_option("--local-search", dest="localSearch", action="store_true", default=False,
                          help="Align images locally instead of to Landsat data.")

        parser.add_option("--overwrite-level",   dest="overwriteLevel",   default=None,
                          help="Set to NONE, LOW or HIGH to re-process images with those ratings.")

        parser.add_option("--limit",   dest="limit",   default=0, type="int",
                          help="Do not process more than this many frames.")

        parser.add_option("--threads", type="int", dest="numThreads", default=4,
                          help="Number of threads to use for processing.")

        parser.add_option("--print-stats", dest="printStats", action="store_true", default=False,
                          help="Instead of aligning images, print current result totals.")
        (options, args) = parser.parse_args(argsIn)
        #if ((options.mission or options.roll or options.frame) and 
        #    not (options.mission and options.roll and options.frame)):
        #    raise Exception('mission/roll/frame must be provided together!')

        # Check options
        if options.roll and not options.mission:
            print 'Roll option requires mission option to be specified!'
            return -1
        if options.frame and not options.roll:
            print 'Frame option requires roll option to be specified!'
            return -1

    except optparse.OptionError, msg:
        raise Usage(msg)

    registrationProcessor(options)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
