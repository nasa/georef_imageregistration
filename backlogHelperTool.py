
import os, sys

# TODO: Move settings to a common file?
import offline_config
import dbLogger
import registration_common
import backlog_processor

OVERVIEW_FOLDER = '/home/smcmich1/georef_overview_images'

def extractDebugImages(inputFolder, outputFolder):
    '''Add symbolic links to debug images in a single folder for convenience.'''

    # TODO: These file conventions are not explicit enough.
    
    if not os.path.exists(outputFolder):
        os.mkdir(outputFolder)
    
    filesToLink = ['match_debug_image.tif']
    prefix      = os.path.basename(inputFolder) + '-'
    
    # Generate symlinks for all the files
    for f in filesToLink:
        inputPath  = os.path.join(inputFolder, f)
        outputPath = os.path.join(outputFolder, prefix + f)
        if (not os.path.exists(outputPath)) and os.path.exists(inputPath):
            print outputPath
            os.symlink(inputPath, outputPath)


def extractAllDebugImages():
    '''Fully populate the consolidated debug image folder'''
    
    outputFolder = OVERVIEW_FOLDER
    
    for folder, subs, files in os.walk(offline_config.OUTPUT_IMAGE_FOLDER):
        if (files == []) or not (subs == []):
            continue
        print 'Linking images from: ' + folder
        extractDebugImages(folder, outputFolder)
            
        
        #print (folder, subs, files)
        #print folder
        #print subs
        #print files
        #for f in files:
        #    print f


def populateDb():
    '''Populate our database file from the images on disk'''
    
    # Currently we don't store enough data to fully populate the
    #  database information, but we can get most of it.
    
    print 'Opening the output log database...'
    db= dbLogger.DatabaseLogger(offline_config.OUTPUT_DATABASE_PATH)
    
    # Loop through all of our output files
    for folder, subs, files in os.walk(offline_config.OUTPUT_IMAGE_FOLDER):
        if (files == []) or not (subs == []):
            continue
        
        # Get the path to the warped and unwarped files
        prefix = folder
        if folder[-1] == '\\':
            prefix = folder[:-1]
        
        (mission, roll, frame) = backlog_processor.getFrameFromFolder(folder)
        
        warpedPath   = folder + '-warp.tif'
        unwarpedPath = folder + '-no_warp.tif'
        
        confidence = 'NONE'
        if os.path.exists(warpedPath):
            confidence = 'HIGH'
        
        # Currently can't recover this
        imageToProjectedTransform = registration_common.getIdentityTransform()
        
        # We can parse these from the unwarped path, but 
        imageInliers = []
        gdcInliers   = []
        
        db.addResult(mission, roll, frame,
                      imageToProjectedTransform, confidence, imageInliers, gdcInliers)
    
    
    
    


def main():
    
    extractAllDebugImages()


if __name__ == "__main__":
    sys.exit(main())