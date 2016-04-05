


import os, sys
import optparse
import sqlite3
#from pysqlite2 import dbapi2 as sqlite3

import registration_common
import register_image
import traceback

import IrgGeoFunctions
import dbLogger
import source_database
import offline_config



def safeMakeDir(folder):
    if not os.path.exists(folder):
        os.mkdir(folder)

    
def getWorkingPath(mission, roll, frame):
    '''Get a good location to process this image.'''
    
    if offline_config.USE_RAW:
        ext = '.tif'
    else:
        ext = '.jpg'
    
    # Generate a file name similar to the RAW storage scheme
    FRAME_DIGITS = 6
    zFrame   = frame.rjust(FRAME_DIGITS, '0')
    filename = mission.lower() + roll.lower() + zFrame + ext
    
    # Break up frames so that there are 1000 per folder
    FRAMES_PER_FOLDER = 1000
    frameFolderNum = (int(frame) // FRAMES_PER_FOLDER)*1000
    frameFolder    = str(frameFolderNum).rjust(FRAME_DIGITS, '0')
    
    # Store data in /mission/roll/frameF/file, skip roll if E.
    safeMakeDir(offline_config.OUTPUT_IMAGE_FOLDER)
    subFolder = os.path.join(offline_config.OUTPUT_IMAGE_FOLDER, mission)
    safeMakeDir(subFolder)
    if not (roll.lower() == 'e'):
        subFolder = os.path.join(subFolder, roll)
        safeMakeDir(subFolder)
    subFolder = os.path.join(subFolder, frameFolder)
    safeMakeDir(subFolder)
    return os.path.join(subFolder, filename)


def getFrameFromFolder(folder):
    '''Parse mission, roll, frame from an output folder'''

    name = os.path.basename(folder)
    if len(name) != 14:
        raise Exception(folder + ' is not a valid output folder!')
    
    mission = name[0:6].upper
    roll    = name[7].upper
    frame   = name[8:]
    
    return (mission, roll, frame)


def findNearbyResults(mission, roll, frame, cursor, dbLog):
    '''Looks for results we have that we may be able to match to.'''
       
    # Get a list of our results we have that we can compare to
    ourResults = dbLog.findNearbyGoodResults(mission, roll, frame,
                                offline_config.LOCAL_ALIGNMENT_MAX_FRAME_RANGE)
    if not ourResults:
        return []
    
    # Fetch info for this frame from the input database
    targetFrameData = source_database.FrameInfo()
    targetFrameData.loadFromDb(cursor, mission, roll, frame)
    
    # Loop through the allowed range of frames starting from the nearest frames
    results = []
    currentIndex = -1
    numAttempts  = 0
    while True:
        
        # Check if we have a result for this frame
        thisFrameString = str(int(frame) + currentIndex)
        if thisFrameString in ourResults:
            
            # Fetch info for this frame from the input database
            frameDbData = source_database.FrameInfo()
            frameDbData.loadFromDb(cursor, mission, roll, thisFrameString) 
        
            # Check the quality and distance
            if (frameDbData.isGoodAlignmentCandidate() and
                frameDbData.isCenterWithinDist(targetFrameData.centerLon, targetFrameData.centerLat,
                                               offline_config.LOCAL_ALIGNMENT_MAX_DIST)):
                
                # Add to the list of frames we will compare to.
                results.append((frameDbData, ourResults[thisFrameString]))
                print 'Found potential local match frame: ' + frameDbData.frame
                numAttempts += 1
        
        if numAttempts == offline_config.LOCAL_ALIGNMENT_MAX_ATTEMPTS:
            break
        
        # Negate the index and move one further out every other time
        if currentIndex > 0:
            currentIndex += 1
        currentIndex *= -1
        if abs(currentIndex) > offline_config.LOCAL_ALIGNMENT_MAX_FRAME_RANGE:
            break
       
    return results
    
    
def getSourceImage(frameDbData, overwrite=False):
    '''Obtains the source image we will work on, ready to use.'''
    
    outputPath = getWorkingPath(frameDbData.mission, frameDbData.roll, frameDbData.frame)
    if os.path.exists(outputPath) and (not overwrite):
        return outputPath
    
    if offline_config.USE_RAW:
        print 'Converting RAW to TIF...'
        source_database.convertRawFileToTiff(frameDbData.rawPath, outputPath)
    else: # JPEG input
        print 'Grabbing JPEG'
        # Download to a temporary file
        tempPath = outputPath + '-temp.jpeg'
        source_database.grabJpegFile(frameDbData.mission, frameDbData.roll, frameDbData.frame, tempPath)
        # Crop off the label if it exists
        registration_common.cropImageLabel(tempPath, outputPath)
        os.remove(tempPath) # Clean up temp file
        
    return outputPath


def processFrame(mission, roll, frame, cursor, dbLog, searchNearby=False):
    '''Process a single specified frame.
       Returns True if we attempted to perform image alignment and did not hit an exception.'''

    print 'Fetching frame information...'
    frameDbData = source_database.FrameInfo()
    frameDbData.loadFromDb(cursor, mission, roll, frame)
    
    if not frameDbData.isGoodAlignmentCandidate():
        print 'This image is not a valid alignment candidate:'
        print frameDbData
        return False
    
    print frameDbData
    
    # TODO: Make sure everything properly handles existing data!
    
    # We can't operate on the RAW file, so convert it to TIF.
    sourceImagePath = getSourceImage(frameDbData)
    
    # Estimate the pixel resolution on the ground
    metersPerPixel = registration_common.estimateGroundResolution(frameDbData.focalLength,
                            frameDbData.width, frameDbData.height, frameDbData.sensorWidth,
                            frameDbData.sensorHeight, frameDbData.nadirLon, frameDbData.nadirLat,
                            frameDbData.altitude, frameDbData.centerLon, frameDbData.centerLat,
                            frameDbData.tilt)
    print 'Meters per pixel = ' + str(metersPerPixel)

    # Increase the error slightly for chained image transforms
    LOCAL_TRANSFORM_ERROR_ADJUST = 1.10


    # Dummy values in case we don't get any real results
    imageToProjectedTransform = registration_common.getIdentityTransform()
    confidence                = registration_common.CONFIDENCE_NONE
    imageInliers              = []
    gdcInliers                = []
    refMetersPerPixel         = 9999

    # If requested, get nearby previously matched frames to compare to.
    if searchNearby:
        possibleNearbyMatches = findNearbyResults(mission, roll, frame, cursor, dbLog)
        
        if not possibleNearbyMatches:
            print 'Did not find any potential local matches!'
        
        for (otherFrame, ourResult) in possibleNearbyMatches:

            print 'Trying local match with frame: ' + str(otherFrame.frame)
            
            # Get path to other frame image
            otherImagePath = getSourceImage(otherFrame)
            otherTransform = ourResult[0] # This is still in the google projected format
            
            print 'otherTransform = ' + str(otherTransform.matrix)
            
            print 'Attempting to register image...'
            (imageToProjectedTransform, confidence, imageInliers, gdcInliers, refMetersPerPixel) = \
                register_image.register_image(sourceImagePath,
                                              frameDbData.centerLon, frameDbData.centerLat,
                                              metersPerPixel, frameDbData.date,
                                              refImagePath         =otherImagePath,
                                              referenceGeoTransform=otherTransform,
                                              debug=True, force=True, slowMethod=False)
            
            # Quit once we get a good match
            if confidence == registration_common.CONFIDENCE_HIGH:
                
                # Convert from the image-to-image GCPs to the reference image GCPs
                #  located in the new image.
                refFrameGdcInliers = ourResult[3] # TODO: Clean this up!
                (width, height)    = IrgGeoFunctions.getImageSize(sourceImagePath)
                
                (imageInliers, gdcInliers) = registration_common.convertGcps(refFrameGdcInliers,
                                                    imageToProjectedTransform, width, height)
                
                # If none of the original GCPs fall in the new image, don't use this alignment result.
                # - We could use this result, but we don't in order to maintain accuracy standards.
                if not imageInliers:
                    imageToProjectedTransform = registration_common.getIdentityTransform()
                    confidence                = registration_common.CONFIDENCE_NONE
                    imageInliers              = []
                    gdcInliers                = []
                    refMetersPerPixel         = 9999
                    
                else: # Success, no need to keep aligning images
                    break 
        
    else: # Try to register the image to Landsat
        
        print 'Attempting to register image...'
        (imageToProjectedTransform, confidence, imageInliers, gdcInliers, refMetersPerPixel) = \
            register_image.register_image(sourceImagePath,
                                          frameDbData.centerLon, frameDbData.centerLat,
                                          metersPerPixel, frameDbData.date,
                                          refImagePath=None,
                                          debug=True, force=True, slowMethod=True)


    # A very rough estimation of localization error at the inlier locations!
    errorMeters = refMetersPerPixel * 1.5
   
    # Log the results to our database
    dbLog.addResult(mission, roll, frame,
                    imageToProjectedTransform, confidence, imageInliers, gdcInliers)

    if confidence == registration_common.CONFIDENCE_HIGH:
        print 'Generating output geotiffs...'
        recordOutputImages(sourceImagePath, imageInliers, gdcInliers, errorMeters, overwrite=True)   
    
    print 'Finished processing frame'
    return True


# TODO: A function to determine how much the JPEG images are cropped compared to the RAW images!
def detectCropAmount():
    return 6


# The crop amount is NOT CONSTANT across missions
# - Since we only adjust the pixel coordinates, we don't have to worry about the
#   possible label bar at the bottom of the image.
def adjustGcpsForJpegCrop(inputPoints, inputGdc, cropAmount=6):
    '''Updates image pixel coordinates to reflect than cropping along each edge ocurred.'''

    outputPoints = []
    outputGdc    = []
    for (pixel, gdc) in zip(inputPoints, inputGdc):
        
        # Adjust the pixel and make sure it did not go off the edge
        newPixel = (pixel[0]-cropAmount, pixel[1]-cropAmount)
        if (newPixel[0] < 0) or (newPixel[1] < 0):
            continue
        # Buuld output lists
        outputPoints.append(newPixel)
        outputGdc.append(gdc)
        
    return (outputPoints, outputGdc)



def recordOutputImages(sourceImagePath, imageInliers, gdcInliers, minUncertaintyMeters, overwrite=True):
    '''Generates all the output image files that we create for each successfully processed image.'''
    
    # TODO: Generate the output images from JPEG images instead of TIFF images.
    #       - The JPEG images are cropped by six pixels at each edge, so update the
    #         image inlier list appropriately.
    
    # We generate two pairs of images, one containing the image data
    #  and another with the same format but containing the uncertainty distances.
    geotiffOutputPrefix     = os.path.splitext(sourceImagePath)[0]
    uncertaintyOutputPrefix = geotiffOutputPrefix + '-uncertainty'
    rawUncertaintyPath      = geotiffOutputPrefix + '-uncertainty_raw.tif'
    
    # Create the raw uncertainty image
    (width, height) = IrgGeoFunctions.getImageSize(sourceImagePath)
    rmsError = registration_common.generateUncertaintyImage(width, height, imageInliers,
                                                            minUncertaintyMeters, rawUncertaintyPath)
    
    # Generate the two pairs of images in the same manner
    registration_common.generateGeotiff(sourceImagePath, geotiffOutputPrefix, imageInliers, gdcInliers,
                                        rmsError, overwrite=True)
    registration_common.generateGeotiff(rawUncertaintyPath, uncertaintyOutputPrefix, imageInliers, gdcInliers,
                                        rmsError, overwrite=True)
    
    # Clean up the raw uncertainty image
    os.remove(rawUncertaintyPath)



def processMission(inputDb, outputDb, mission, roll=None, frame=None, localSearch=False,
                   processLimit=None, overwriteLevel=None):
    '''Processes the specified data'''
    
    inputCursor = inputDb.cursor()
    
    # Look up records for the mission that we may be able to process
    processingCandidates = source_database.getCandidatesInMission(inputCursor, mission, roll, frame)
    
    print 'Found ' + str(len(processingCandidates)) + ' images to process.'
    numProcessed = 0
    for candidate in processingCandidates:
        
        
        # Grab the frame identity and check if we have already processed it
        (mission, roll, frame) = candidate

        print '******** Processing: ' + source_database.getFrameString(mission, roll, frame) +' ********************'
        
        if (outputDb.doWeHaveResult(mission, roll, frame, overwriteLevel)):
            print '-- Already have a result, skipping.'
            continue

        try:
            result = processFrame(mission, roll, frame, inputCursor, outputDb, localSearch)
        except Exception as e:
            result    = False           
            errString = str(e)
            print 'Caught Exception: ' + errString
            print traceback.print_exc()


        if result:
            numProcessed += 1
        else:
            print 'Failed to compute the transform.'
    
        if processLimit and (numProcessed == processLimit):
            break
    
    print 'Processed ' + str(numProcessed) + ' new frames.'
       
    print 'Finished running backlog test'
    




def main(argsIn):

    try:
        usage = "usage: backlog_processor.py [--help]\n  "
        parser = optparse.OptionParser(usage=usage)
        
        parser.add_option("--mission", dest="mission", default=None,
                          help="Specify a mission to process.")
        parser.add_option("--roll",    dest="roll",    default=None,
                          help="Specify a roll to process.  Requires mission.")
        parser.add_option("--frame",   dest="frame",   default=None,
                          help="Specify a frame to process. Requires roll.")
        
        parser.add_option("--limit",   dest="limit",   default=None,
                          help="Do not process more than this many frames.")
        
        parser.add_option("--overwrite-level", dest="overwriteLevel", default=None,
                          help="If set, re-process frames where the result was this or worse [NONE, LOW, HIGH]")
        
        parser.add_option("--local-search", dest="localSearch", action="store_true", default=False,
                          help="Instead of matching to Landsat, try to match to nearby matched images.")

        parser.add_option("--print-stats", dest="printStats", action="store_true", default=False,
                          help="Instead of aligning images, print current result totals.")
        
        (options, args) = parser.parse_args(argsIn)

    except optparse.OptionError, msg:
        raise Usage(msg)

    # Check options
    if options.roll and not options.mission:
        print 'Roll option requires mission option to be specified!'
        return -1
    if options.frame and not options.roll:
        print 'Frame option requires roll option to be specified!'
        return -1

    # Convert from string to enum
    options.overwriteLevel = registration_common.confidenceFromString(options.overwriteLevel)

    if options.mission:
        missionList = [options.mission]
    else:
        print 'Proccessing all known missions.  This could take a long time!'
        raise Exception('DEBUG')
        missionList = source_database.getMissionList()
    
    
    
    
    
    # Open the input and output databases
    print 'Initializing database connection...'
    inputDb = sqlite3.connect(offline_config.DB_PATH)

    print 'Opening the output log database...' # This one has a wrapper class
    outputDb = dbLogger.DatabaseLogger(offline_config.OUTPUT_DATABASE_PATH)
    
    
    if options.printStats: # Print a header line
        print 'MISSION\t-->\tTOTAL\tNONE\tLOW\tHIGH\tHIGH_FRACTION'
    
    # Process each of the selected missions
    for mission in missionList:
        
        if options.printStats:
            
            counts = outputDb.getProcessingStats(mission)
            print ('%s\t-->\t%d\t%d\t%d\t%d\t%.2f' %
                (mission, counts[0], counts[1], counts[2], counts[3], float(counts[3])/float(counts[0])))
            
        else: # Perform alignment
            print '>>>>>> Processing mission '+ mission +' <<<<<<'
            processMission(inputDb, outputDb,
                           mission, options.roll, options.frame, options.localSearch,
                           options.limit, options.overwriteLevel)

    # Clean up  
    print 'Closing input database connection...'
    inputDb.close()


def test():

    # Open the input database
    print 'Initializing database connection...'
    inputDb = sqlite3.connect(offline_config.DB_PATH)
    cursor  = inputDb.cursor()

    print 'Opening the output log database...'
    outputDb = dbLogger.DatabaseLogger(offline_config.OUTPUT_DATABASE_PATH)
    
    #(mission, roll, frame) = ('ISS001', '347', '24')
    #(mission, roll, frame) = ('ISS026', 'E', '29592')
    #(mission, roll, frame) = ('ISS043', 'E', '101834') # Rivers
    #(mission, roll, frame) = ('ISS043', 'E', '101947') # Irrigation circles
    
    #(mission, roll, frame) = ('ISS043', 'E', '91884')  # Warp trouble?
    #(mission, roll, frame) = ('ISS043', 'E', '93251')  # Works poorly on snow!
    #(mission, roll, frame) = ('ISS043', 'E', '122588') # Good only on lake
    #(mission, roll, frame) = ('ISS044', 'E', '868')    # Should be better
    #(mission, roll, frame) = ('ISS044', 'E', '1998')   # Tough image
    #(mission, roll, frame) = ('ISS043', 'E', '101805') # Large city, need tons of IP.
    
    (mission, roll, frame) = ('ISS043', 'E', '39938') # Another IP count problem?
    
    #(mission, roll, frame) = ('ISS043', 'E', '101751') # Would be nice to get this!
    #(mission, roll, frame) = ('ISS043', 'E', '101848') # Would be nice to get this!
        # --> These requires a first pass at a smaller ref size or else WAY more key points
        #     or some kind of forced key point distribution.
        #  -> Alternately, an alternate method of preprocessing that highlights a different
        #     of features, maybe lines (not points) or larger scale.
    
    #(mission, roll, frame) = ('ISS043', 'E', '101654') # Make local matches to this one
    
    
    
    
    processFrame(mission, roll, frame, cursor, outputDb)

    # Clean up   
    print 'Closing input database connection...'
    inputDb.close()
    
    print 'Finished running backlog test'

# Simple test script
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))