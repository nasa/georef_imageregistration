import os, sys
import optparse
import sqlite3
#from pysqlite2 import dbapi2 as sqlite3

import registration_common
import register_image
import traceback

import dbLogger
import source_database
import offline_config
import georefDbWrapper
import IrgGeoFunctions


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
    registrationResult['sourceImagePath'] = source_database.getSourceImage(frameDbData)
    
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


def runOutputGenerator(mission, roll, frame, limit, autoOnly, manualOnly):
    # TODO: Turn the input DB into a full wrapper.
    sourceDb = sqlite3.connect(offline_config.DB_PATH)
    sourceDbCursor = sourceDb.cursor()
    georefDb = georefDbWrapper.DatabaseLogger()
    
    # Get images to process
    targetFrames = findReadyImages(mission, roll, frame, limit, autoOnly, manualOnly, georefDb)

    if len(targetFrames) == 0:
        print 'Did not find any frames ready to process.'

    count = 0
    successFrames = targetFrames
    centerPointSources = []
    
    for (_mission, _roll, _frame) in targetFrames:
        try:
            print str((_mission, _roll, _frame))
            frameDbData = source_database.FrameInfo()
            frameDbData.loadFromDb(sourceDbCursor, _mission, _roll, _frame)
            # Get the registration info for this image, then apply manual pixel coord correction.
            imageRegistrationInfo = getImageRegistrationInfo(frameDbData, georefDb)
            if imageRegistrationInfo['isManual']:
                imageRegistrationInfo = correctPixelCoordinates(imageRegistrationInfo)

            outputPrefix = getOutputPrefix(_mission, _roll, _frame)
            centerPointSource = imageRegistrationInfo['centerPointSource']
            #TODO: append the center point source to the outputPrefix.
            registration_common.recordOutputImages(imageRegistrationInfo['sourceImagePath'], outputPrefix,
                                                   imageRegistrationInfo['imageInliers'],
                                                   imageRegistrationInfo['gdcInliers'],
                                                   imageRegistrationInfo['registrationMpp'],
                                                   imageRegistrationInfo['centerPointSource'],
                                                   imageRegistrationInfo['isManual'], overwrite=True)
            
            # Clean up the source image we generated
            os.remove(imageRegistrationInfo['sourceImagePath'])
            # Update the database to record that we wrote the image
            georefDb.markAsWritten(_mission, _roll, _frame)
            centerPointSources.append(centerPointSource)

        except Exception as e:
            print 'Caught exception:'
            print(sys.exc_info()[0])
            print traceback.print_exc()
            successFrames.remove((_mission, _roll, _frame))
            centerPointSources.pop()
            
        # TODO: if it's autoOnly, make sure to save the metadatat file and and export into the autoregistration table in DB!
        # If it's manual, the saving to database gets done by the script.
        count += 1
    return [successFrames, centerPointSources]


def main(argsIn):

    try:
        usage = "usage: output_generator.py [--help]\n  "
        parser = optparse.OptionParser(usage=usage)
        
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

        (options, args) = parser.parse_args(argsIn)

        # Error checking
        if ((options.mission or options.roll or options.frame) and 
            not (options.mission and options.roll and options.frame)):
            raise Exception('mission/roll/frame must be provided together!')
            
        if options.autoOnly and options.manualOnly:
            raise Exception("auto-only and manual-only options are mutually exclusive!")
            
    except optparse.OptionError, msg:
        raise Usage(msg)

    print '---=== Output Generator has started ===---'

    print 'Connecting to our database...'
    runOutputGenerator(options.mission, options.roll, options.frame, options.limit, 
                       options.autoOnly, options.manualOnly)
    print '---=== Output Generator has stopped ===---'
    

#def test():


# Simple test script
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))