


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

'''
This tool monitors for images which are finished processing
and generates the output files for them.
'''

# TODO: There are some duplicates with backlog_processor

# TODO: This tool should prioritize manually generated tiepoints/images

def findReadyImage(options, georefDb):
    '''Get the next image which is ready to process'''

    if options.frame:
        return (options.mission, options.roll, options.frame)

    NUM_IMAGES_TO_GET = 1
    imageList = georefDb.getImagesReadyForOutput(limit=NUM_IMAGES_TO_GET)
    if not imageList:
        return (None, None, None)

    return imageList[0] # (mission, roll, frame)


def getImageInfo(frameDbData, georefDb):
    '''Get information for the specified image'''
    
    # This function fetches the source image if it does not exist
    sourceImagePath = source_database.getSourceImage(frameDbData)
    
    # Retrieve needed image info from our DB
    (confidence, imageInliers, gdcInliers, registrationMpp) = \
        georefDb.getResult(frameDbData.mission, frameDbData.roll, frameDbData.frame)
    
    return (sourceImagePath, imageInliers, gdcInliers, registrationMpp)



def getOutputPrefix(mission, roll, frame):
    '''Return the output prefix for this frame'''
    
    filePath = registration_common.getWorkingPath(mission, roll, frame)
    prefix   = os.path.splitext(filePath)[0]
    
    return prefix


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
        
        parser.add_option("--limit",   dest="limit",   default=0, type="int",
                          help="Do not process more than this many frames.")

        (options, args) = parser.parse_args(argsIn)

        if ((options.mission or options.roll or options.frame) and 
            not (options.mission and options.roll and options.frame)):
            raise Exception('mission/roll/frame must be provided together!')
            
    except optparse.OptionError, msg:
        raise Usage(msg)

    print '---=== Output Generator has started ===---'


    print 'Connecting to our database...'
    
    # TODO: Turn the input DB into a full wrapper.
    sourceDb = sqlite3.connect(offline_config.DB_PATH)
    sourceDbCursor = sourceDb.cursor()
    georefDb = georefDbWrapper.DatabaseLogger()
    

    count = 0
    while True:
    
        # Get the next image to process
        (mission, roll, frame) = findReadyImage(options, georefDb)
    
        if not frame:
            print 'Output Generator found no more data.'
            break

        print str((mission, roll, frame))
        
        frameDbData = source_database.FrameInfo()
        frameDbData.loadFromDb(sourceDbCursor, mission, roll, frame)
        #print 'Output Generator obtained data: ' + str(frameDbData)
    
        (sourceImagePath, imageInliers, gdcInliers, minUncertaintyMeters) \
              = getImageInfo(frameDbData, georefDb)
    
        outputPrefix = getOutputPrefix(mission, roll, frame)
    
        registration_common.recordOutputImages(sourceImagePath, outputPrefix, imageInliers, gdcInliers,
                           minUncertaintyMeters, overwrite=True)
        
        # Clean up the source image we generated
        os.remove(sourceImagePath)
        
        # Update the database to record that we wrote the image
        georefDb.markAsWritten(mission, roll, frame)
        
        count += 1
        
        if options.frame or (options.limit and (count >= options.limit)):
            print 'Output Generator has processed the requested number of images.'
            break

    print '---=== Output Generator has stopped ===---'
    

#def test():


# Simple test script
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))