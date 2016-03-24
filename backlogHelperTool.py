
import os, sys

# TODO: Move settings to a common file?
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
    
    for folder, subs, files in os.walk(backlog_processor.OUTPUT_IMAGE_FOLDER):
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

def main():
    
    extractAllDebugImages()


if __name__ == "__main__":
    sys.exit(main())