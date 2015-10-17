

import os
import sys
import argparse
import subprocess
import traceback
import numpy

import ImageFetcher.miscUtilities
import ImageFetcher.fetchReferenceImage
import register_image
import IrgStringFunctions, IrgGeoFunctions

# TODO: Make sure this gets found!
basepath    = os.path.abspath(sys.path[0])
pythonpath  = os.path.abspath(basepath + '/../geocamTiePoint/geocamTiePoint')
sys.path.insert(0, pythonpath)
import geocamTiePoint.transform


class TestInstance:
    '''Class representing a single test case'''
    
    def __init__(self, string=None):
        self.imagePath      = None
        self.imageCenterLoc = (0, 0)
        self.issNadirLoc    = (0, 0)
        self.focalLength    = 0 # In mm
        self.date           = None # Stored as a string
        #self.idealTransformPath = None
        
        if string:
            self.readFromLine(string)

    def readFromLine(self, string):
        '''Instantiates the class from a log string'''
        parts = string.split(',')
        parts = [part.strip() for part in parts]
        self.imagePath      = parts[0]
        self.imageCenterLoc = (float(parts[1]), float(parts[2]))
        self.issNadirLoc    = (float(parts[3]), float(parts[4]))
        self.focalLength    = float(parts[5])
        if len(parts) > 6:
            self.date = parts[6]
        

def readTestInfo():
    '''Read in the test data set information from a file'''
    
    testData = []
    testData.append(TestInstance( 'ISS011-E-7860.JPG,   59.5,  46.0,   56.3,   48.0, 180, 2005.06.03' )) # GOOD
    testData.append(TestInstance( 'ISS017-E-9641.JPG,  -92.5,  45.9,  -91.4,   45.9, 400, 2008.06.18' )) # Basemap too low res?
    testData.append(TestInstance( 'ISS006-E-30169.JPG,-104.0,  44.0, -113.2,   48.9, 50, 2003.02.20' ))
    testData.append(TestInstance( 'ISS002-386-32.JPG, -108.0,  36.5, -110.3,   36.5, 110, 2001.07.08' ))
    testData.append(TestInstance( 'ISS004-E-8271.JPG,  -77.0,  42.0,    0.0,    0.0, 400, 2002.02.26' ))
    testData.append(TestInstance( 'ISS004-E-6686.JPG, -146.0, -16.0, -144.8,  -17.0, 400, 2002.01.22' ))
    testData.append(TestInstance( 'ISS004-E-5201.JPG, -113.0,  32.5,    0.0,    0.0, 0' ))
    testData.append(TestInstance( 'ISS005-E-16101.JPG, -67.0, -14.0,  -67.2,  -12.6, 180, 2002.09.26' ))
    testData.append(TestInstance( 'ISS005-E-13496.JPG,  -5.4,  50.4,   -2.3,   50.4, 400, 2002.09.10' ))
    testData.append(TestInstance( 'ISS006-E-34067.JPG, -81.0,  51.0,  -81.8,   51.5, 50, 2003.02.26' ))
    testData.append(TestInstance( 'ISS006-E-21717.JPG, 114.0,   9.0,  112.5,    7.5, 340, 2003.01.31' ))
    testData.append(TestInstance( 'ISS006-E-9482.JPG,  -58.0,  49.0,  -62.0,   48.9, 400, 2002.12.17' ))
    testData.append(TestInstance( 'ISS010-E-6710.JPG,  116.5, -23.0,  117.90, -23.9, 180, 2004.11.12' ))
    testData.append(TestInstance( 'ISS012-E-19064.JPG, -71.0,  41.5,  -68.2,   42.6, 800, 2006.03.04' ))
    testData.append(TestInstance( 'ISS012-E-8578.JPG,  -80.0,  33.5,  -80.3,   31.5, 180, 2005.11.19' )) # GOOD
    testData.append(TestInstance( 'ISS012-E-7953.JPG,  -74.0,  41.4,  -72.8,   42.3, 400, 2005.11.14' ))
    testData.append(TestInstance( 'ISS013-E-6881.JPG,  -74.1,  22.7,  -72.7,   24.9, 800, 2006.04.12' )) # GOOD
    testData.append(TestInstance( 'ISS017-E-18969.JPG, -74.8,  45.0,  -74.3,   48.5, 800, 2008.10.10' ))
    #testData.append(TestInstance( 'STS066-117-11.JPG, -143.5, 62.0, -144.0, 57.1, 100, 1994.11.09' ))
    
    dataFolder = '/home/smcmich1/data/geocam_images'
    for i in testData:
        i.imagePath = os.path.join(dataFolder, i.imagePath)
    
    
    return testData



def computeTransformDiff(idealTransform, transform):
    '''Compute a similarity measure between the computed
        transform and the ideal transform'''
       
    diff = 0
    for i in range(len(transform)):
        diff += (idealTransform[i] - transform[i])**2
    return sqrt(diff)

   

def runTest(test, options):
    '''Performs a test registration on a single image'''

    testImagePath = test.imagePath
    lon = test.imageCenterLoc[0]
    lat = test.imageCenterLoc[1]


    # Set up paths
    imageBase    = os.path.splitext(testImagePath)[0]
    refImagePath = imageBase + '/ref_image.tif'
    workFolder   = imageBase + '/'
    workPrefix   = imageBase + '/' + options.testPrefix
    idealTransformPath = workFolder + 'truth-transform.txt'
    if not os.path.exists(workFolder):
        os.mkdir(workFolder)
    
    # Make sure we have the image to match to
    if not os.path.exists(refImagePath) or options.reloadRefs:
        print 'Fetching reference image for input ' + testImagePath
            
        estimatedMpp = register_image.estimateGroundResolution(test.focalLength)
        ImageFetcher.fetchReferenceImage.fetchReferenceImage(test.imageCenterLoc[0], test.imageCenterLoc[1],
                                                             estimatedMpp, test.date, refImagePath)


    #print 'Skipping image processing!'
    #return 0 # DEBUG skip processing, just fetch the images!

    #raise Exception('DEBUG')

    # TODO: Don't care about the tranform path!
    transformPath = workPrefix + '-transform.txt'
    force = not options.useExisting
    (transform, confidence) = register_image.alignImages(testImagePath, refImagePath, workPrefix, force)
    if confidence == register_image.CONFIDENCE_NONE:
        raise Exception('Failed to register image!')

    # TODO: First generate the ideal transform for every data set!

    if not os.path.exists(idealTransformPath):
        #print 'TODO: Set up the ideal transform file!'
        diff = -1
    else:
        # TODO: Load the ideal transform!
        diff = 999
        #diff = computeTransformDiff(idealTransform, transformPath)

    # Test geo conversion
    geoTransform = register_image.convertTransformToGeo(transform, testImagePath, refImagePath)

    return (diff, confidence, geoTransform)

def main():

    parser = argparse.ArgumentParser()
    #parser.add_argument('command', choices=['sync',  'sync-parallel', 'show-modified'])

    #parser.add_argument('--test-file',    dest='testFile', default='TODO',
    #                                      help='Read in test information from this file')
    parser.add_argument('--test-prefix',  dest='testPrefix', default='result',
                                          help='Name prepended to debug files')
    parser.add_argument('--refetch-refs', dest='reloadRefs', action='store_true', default=False,
                                          help='Force refetching of the reference images')
    parser.add_argument('--use-existing', dest='useExisting', action='store_true', default=False,
                                          help='Just print results for the last computed transforms')
    
    parser.add_argument('--sequence', dest='testSequence', action='store_true', default=False,
                                          help='Run the sequence test.')
    

    options = parser.parse_args()
    
    # A seperate test for processing a sequence of images
    if options.testSequence:
        print '----- Running sequence test -----'
        
        seqSeed = TestInstance('/home/smcmich1/data/geocam_images/sequence/ISS001-400-4.JPG, ' + 
                               '31.0, 30.0, 33.1, 31.1, 350, 2001.02.26' )
        
        otherImagePaths = ['/home/smcmich1/data/geocam_images/sequence/ISS001-400-5.JPG',
                           '/home/smcmich1/data/geocam_images/sequence/ISS001-400-8.JPG',
                           '/home/smcmich1/data/geocam_images/sequence/ISS001-400-10.JPG',
                           '/home/smcmich1/data/geocam_images/sequence/ISS001-400-14.JPG',
                           '/home/smcmich1/data/geocam_images/sequence/ISS001-400-15.JPG']
        
        # Run the initial seed
        print 'Processing initial seed...'
        (transform, confidence) = register_image.register_image(seqSeed.imagePath,
                                                                seqSeed.imageCenterLoc[0],
                                                                seqSeed.imageCenterLoc[1],
                                                                seqSeed.focalLength,
                                                                seqSeed.date)
        if not (confidence == register_image.CONFIDENCE_HIGH):
            raise Exception('Cannot run sequence test if first image fails!')
        
        # Run all the other images
        for path in otherImagePaths:
            print 'Testing image: ' + path
            force = not options.useExisting
            (transform, confidence) = register_image.register_image(path,
                                                                    seqSeed.imageCenterLoc[0],
                                                                    seqSeed.imageCenterLoc[1],
                                                                    seqSeed.focalLength,
                                                                    seqSeed.date,
                                                                    seqSeed.imagePath, transform)
            print 'Got confidence: ' + str(confidence)

        print '----- Finished sequence test -----'
        return 0
    

    print '===================== Started running tests ====================='

    testInfo = readTestInfo()
    confidenceCounts = [0, 0, 0]
    results = []
    for i in testInfo:
        try:
            (score, confidence, geoTransform) = runTest(i, options)
        except Exception, e:
            score      = 0
            confidence = register_image.CONFIDENCE_NONE
            print 'Failed to process image ' + i.imagePath
            print(traceback.format_exc())
        results.append(score)
        
        confidenceCounts[confidence] += 1
        print i.imagePath + ' ---> ' + str(score) + ' == ' + register_image.CONFIDENCE_STRINGS[confidence]

        #raise Exception('DEBUG')
    
    print 'Confidence counts: ' + str(confidenceCounts)
    
    print '===================== Finished running tests ====================='

if __name__ == "__main__":
    sys.exit(main())
