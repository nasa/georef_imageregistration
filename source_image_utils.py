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
import subprocess
import urllib2
import offline_config
import piexif
from PIL import Image, ExifTags
import datetime

import registration_common

import django
from django.conf import settings
django.setup()

"""
This file contains utilities for working with the input images stored
on the server.
"""

#=======================================================
# Helper functions


def getExifData(filename):
    """Exif utility Functions
       referenced: https://gist.github.com/erans/983821
    """
    pilImageObj = Image.open(filename)
    exifData = {}
    try: 
        pilExif = pilImageObj._getexif()
        for tag,value in pilExif.items():
            decoded = ExifTags.TAGS.get(tag, tag)
            if tag in ExifTags.TAGS:
                if decoded == "GPSInfo":
                    gpsData = {}
                    for t in value:
                        gpsDecoded = ExifTags.GPSTAGS.get(t, t)
                        gpsData[gpsDecoded] = value[t]
                    exifData[decoded] = gpsData
                else: 
                    exifData[ExifTags.TAGS[tag]] = value
    except: 
        pass
    return exifData

def getFrameString(mission, roll, frame):
    return (mission +', '+ roll +', '+ frame)

# The official RAW conversion method uses Photoshop's RAW plugin.
# Largest JPEG image: Crop away six pixels on each edge.
# Low Res JPEG image: As largest, then resize large edge to 640 and keep the resolution.

# TODO: Play around with this to get the best possible output images
def convertRawFileToTiff(rawPath, outputPath):
    '''Convert one of the .raw image formats to a .tif format using
       the open-source dcraw software.'''
    if not os.path.exists(rawPath):
        raise Exception('Raw image file does not exist: ' + rawPath)
    cmd = offline_config.DCRAW_PATH + ' +M -W -c -o 1 -T ' + rawPath + ' > ' + outputPath
    print cmd
    os.system(cmd)
    if not os.path.exists(outputPath):
        raise Exception('Failed to convert input file ' + rawPath)


def getSourceImage(frameInfo, overwrite=False):
    '''Obtains the source image we will work on, ready to use.
       Downloads it, converts it, or whatever else is needed.
       Has a fixed location where the image is written to.'''

    outputPath = registration_common.getWorkingPath(frameInfo.mission, frameInfo.roll, frameInfo.frame)
    #if os.path.exists(outputPath) and (not overwrite): # TODO: Need to handle the exif file too!
    #    return outputPath
    exifSourcePath = None
    if offline_config.USE_RAW:
        #print 'Converting RAW to TIF...'
        convertRawFileToTiff(frameInfo.rawPath, outputPath)
        exifSourcePath = frameInfo.rawPath

    else: # JPEG input
        print 'Grabbing JPEG'
        # Download to a temporary file
        datetimeString = datetime.datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S%Z')
        tempFileName =  os.path.dirname(outputPath) + "/%s-%s-%s-%s-temp.jpeg" % (frameInfo.mission, frameInfo.roll, frameInfo.frame, datetimeString)
        grabJpegFile(frameInfo.mission, frameInfo.roll, frameInfo.frame, tempFileName)
        # Crop off the label if it exists
        registration_common.cropImageLabel(tempFileName, outputPath)
        exifSourcePath = tempFileName
    
    return [outputPath, exifSourcePath]

def clearExif(exifPath):
    '''Clear an exif file if it is a temporary jpeg file'''
    if 'temp.jpeg' in exifPath:
        os.remove(exifPath)

def getRawImageSize(rawPath):
    '''Returns the size in pixels of the raw camera file'''

    cmd = [offline_config.DCRAW_PATH, '-i',  '-v', rawPath]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    textOutput, err = p.communicate()
    lines = textOutput.split('\n')
    for line in lines:
        if 'Full size' not in line:
            continue
        parts  = line.split()
        width  = int(parts[2])
        height = int(parts[4])
        return (width, height)
    raise Exception('Unable to determine size of image: ' + rawPath)


def grabJpegFile(mission, roll, frame, outputPath):
    '''Fetches a full size jpeg image from the ISS website'''

    # Get the data URL
    url = (('http://eol.jsc.nasa.gov/DatabaseImages/ESC/large/%s/%s-%s-%s.JPG') %
           (mission, mission, roll, frame) )

    # Download the data
    #print 'Downloading image from ' + url
    data = urllib2.urlopen(url)
    with open(outputPath, 'wb') as fp:
        while True:
            chunk = data.read(16 * 1024)
            if not chunk:
                break
            fp.write(chunk)
    if not os.path.exists(outputPath):
        raise Exception('Error fetching jpeg image ' + str((mission, roll, frame)))
    #print 'Download complete!'


#=======================================================
# Primary file info grabbing functions


def chooseSubFolder(frame, cutoffList, pathList):
    '''Helper function to reduce boilerplate in getRawPath.
       Choose which subfolder a file is in based on the frame number.'''
    numVals = len(cutoffList)
    if not (len(pathList)-1) == numVals:
        raise Exception('Bad cutoff list!')
    for i in range(0,numVals):
        if frame < cutoffList[i]:
            return pathList[i]
    return pathList[-1]


def getRawPath(mission, roll, frame):
    '''Generate the full path to a specified RAW file.'''

    # The file storage system is not consistent, so
    #  many missions need some special handling.

    # TODO: Make this more automatic!

    # Zero pad values as needed
    FRAME_DIGITS = 6
    zFrame = frame.rjust(FRAME_DIGITS, '0')

    # The default conventions
    name       = mission.lower() + roll.lower() + zFrame
    ext        = '.nef'
    subFolder  = mission # The mission name in caps
    iFrame     = int(frame)
    missionNum = int(mission[3:])

    if ( (mission == 'ISS006') or
         (mission == 'ISS011') or
         (mission == 'ISS012') or
         (mission == 'ISS013') or
         (mission == 'ISS014') or
         (mission == 'ISS016') or
         (mission == 'ISS017')):
        FRAME_DIGITS = 5
        zFrame = frame.rjust(FRAME_DIGITS, '0')
        name = mission + roll + zFrame
        ext  = '.dcr'

    if ( (mission == 'ISS015') or
         (mission == 'ISS014')):
        name = mission + roll + zFrame
        ext  = '.DCR'

    if ( (mission == 'ISS018') or
         (mission == 'ISS019') or
         (mission == 'ISS019')):
        name = mission + roll + zFrame

    if ( (mission == 'ISS032') or
         (mission == 'ISS033') or
         (mission == 'ISS034') or
         (mission == 'ISS035') or
         (mission == 'ISS036') or
         (mission == 'ISS037') or
         (mission == 'ISS038') or
         (mission == 'ISS039') or
         (mission == 'ISS040') or
         (mission == 'ISS041') or
         (mission == 'ISS042') or
         (mission == 'ISS046')):
        ext  = '.NEF'

    if mission == 'ISS022':
        subFolder = 'ISS022/' + chooseSubFolder(iFrame,
            [46575, 60274, 66153, 72633, 78049, 81235, 87189, 99095, 102079, 102303],
            ['e031971-e046574', 'e046575-e060273', 'e060274-e066152',
             'e066153-e072632', 'e072633-e078048', 'e078049-e081234',
             'e081235-e087188', 'e087189-e099094', 'e099095-e102078',
             'e102079-e102302', 'e102303-e102923'])

    if mission == 'ISS023':
        subFolder = 'ISS023/' + chooseSubFolder(iFrame,
            [8826, 14780, 19842, 24906, 29099, 34136,
             40035, 45624, 51324, 58386, 58480],
            ['e005000-e008825', 'e008826-e014779', 'e014780-e019841',
             'e019842-e024905', 'e024906-e029098', 'e029099-e034135',
             'e034136-e040034', 'e040035-e045623', 'e045624-e051323',
             'e051324-e058385', 'e058386-e058479', 'e058480-e060753'])

    if mission == 'ISS030':
        ext  = '.NEF'
        subFolder = chooseSubFolder(iFrame,
            [107724, 209872, 228051],
            ['ISS030', 'ISS030_Batch02', 'ISS030_Batch03', 'ISS030_Batch04'])

    if mission == 'ISS031':
        subFolder = chooseSubFolder(iFrame, [95961], ['ISS031', 'ISS031_Batch02'])

    if missionNum > 31:
        ext  = '.NEF' # Switched over at this point for all later missions

    if mission == 'ISS042':
        subFolder = chooseSubFolder(iFrame,
            [170284, 280908], ['ISS042', 'ISS042_Batch02', 'ISS030_Batch03'])

    if mission == 'ISS043':
        subFolder = chooseSubFolder(iFrame, [159293], ['ISS043', 'ISS043_Batch02'])

    if mission == 'ISS045':
        subFolder = chooseSubFolder(iFrame, [152311], ['ISS045', 'ISS045_Batch02'])

    if mission == 'ISS047':
        subFolder = chooseSubFolder(iFrame, [6717], ['ISS047', 'ISS047_Batch02'])

    if mission == 'ISS053':
        subFolder = chooseSubFolder(iFrame, [96155, 189901, 269778, 349194, 431000],
                                            ['ISS053',         'ISS053_Batch02',
                                             'ISS053_Batch03', 'ISS053_Batch04'
                                             'ISS053_Batch05', 'ISS053_Batch06'])

    if mission == 'ISS056':
        subFolder = chooseSubFolder(iFrame, [94331], ['ISS056', 'ISS056_Batch02'])

    subPath  = os.path.join(subFolder, name+ext)
    fullPath = os.path.join(offline_config.RAW_IMAGE_FOLDER, subPath)
    return fullPath

def getSensorSize(cameraCode):
    '''Returns sensor (width, height) in mm given the two letter
       camera code from the database.'''
    if cameraCode == 'E2':
        return (27.6, 18.5)
    if cameraCode == 'E3':
        return (27.6, 18.5)
    if cameraCode == 'E4':
        return (27.6, 18.5)
    if cameraCode == 'N1':
        return (23.6, 15.5)
    if cameraCode == 'N2':
        return (23.7, 15.7)
    if cameraCode == 'N3':
        return (36.0, 23.9)
    if cameraCode == 'N4':
        return (35.9, 24.0)
    if cameraCode == 'N5':
        return (36.0, 23.9)
    if cameraCode == 'N6':
        return (36.0, 23.9)
    if cameraCode == 'N7':
        return (35.9, 24.0)
    print 'Warning: Missing sensor code for camera ' + cameraCode
    return (0,0)


#=======================================================


class FrameInfo(object):
    """Class that contains the metadata for one frame.
       This is mostly information stored in the database of
       input images that we do not maintain.
    """

    def __init__(self):
        '''Init to default values'''
        self.mission         = None
        self.roll            = None
        self.frame           = None
        self.centerLon       = None
        self.centerLat       = None
        self.centerPointSource = None
        self.nadirLon        = None
        self.nadirLat        = None
        self.altitude        = None
        self.date            = None
        self.time            = None
        self.focalLength     = None
        self.exposure        = 'N'
        self.tilt            = 'NV'
        self.cloudPercentage = 0.0
        self.camera          = None
        self.imageList       = []
        self.rawPath         = None
        self.width           = 0
        self.height          = 0
        self.sensorHeight    = 0
        self.sensorWidth     = 0

    def __str__(self):
        '''Print out the values'''
        return str(self.__dict__)


    def getMySqlDateTime(self):
        '''Format a datetime string for MySQL'''
        s = self.date.replace('.','-') + ' ' + self.time
        return s

    # These functions check individual metadata parameters to
    #  see if the image is worth trying to process.
    def isExposureGood(self):
        return (self.exposure == 'N') or (self.exposure == '')
    def isTiltGood(self):
        return (self.tilt < offline_config.MAX_TILT_ANGLE)
    def isCloudPercentageGood(self):
        return (self.cloudPercentage < offline_config.MAX_CLOUD_PERCENTAGE)

    def isImageSizeGood(self):
        return (self.width !=0) and (self.height !=0)
    #    '''Return True if the image is a good candidate for automatic alignment'''
    #    return (self.isExposureGood() and
    #            self.isTiltGood() and
    #            self.isCloudPercentageGood() and
    #            self.rawPath)

    def isGoodAlignmentCandidate(self):
        '''Return True if the image is a good candidate for automatic alignment'''
        print "exposure good? %s" % self.isExposureGood()
        print "tilt good? %s" % self.isTiltGood() 
        print "cloud percentage good? %s" % self.isCloudPercentageGood()
        print "is width and height good? %s" % self.isImageSizeGood() 

        return (self.isExposureGood() and
                self.isTiltGood() and
                self.isCloudPercentageGood() and
                self.isImageSizeGood())

    def isCenterWithinDist(self, lon, lat, dist):
        '''Returns True if the frame center is within a distance of lon/lat.
           Currently works in degree units.'''
        return (abs(self.centerLon - lon) < dist) and (abs(self.centerLat - lat) < dist)

    def getIdString(self):
        '''Return the id consistent with our internal conventions'''
        return self.mission+'-'+self.roll+'-'+self.frame


