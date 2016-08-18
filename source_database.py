import os, sys
import subprocess
import sqlite3
import urllib2
import offline_config

import registration_common
import register_image
import traceback

import dbLogger

import georefDbWrapper as georefDb

'''
This file contains tools for reading the source database and
some of the input file formats.
'''

# TODO: Separate RAW data folder description into a separate file?

#=======================================================
# Helper functions

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
    if os.path.exists(outputPath) and (not overwrite):
        return outputPath
    
    if offline_config.USE_RAW:
        #print 'Converting RAW to TIF...'
        convertRawFileToTiff(frameInfo.rawPath, outputPath)
    else: # JPEG input
        #print 'Grabbing JPEG'
        # Download to a temporary file
        tempPath = outputPath + '-temp.jpeg'
        grabJpegFile(frameInfo.mission, frameInfo.roll, frameInfo.frame, tempPath)
        # Crop off the label if it exists
        registration_common.cropImageLabel(tempPath, outputPath)
        os.remove(tempPath) # Clean up temp file
        
    return outputPath


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
    
    # Zero pad values as needed
    FRAME_DIGITS = 6
    zFrame = frame.rjust(FRAME_DIGITS, '0')
    
    # The default conventions
    name      = mission.lower() + roll.lower() + zFrame
    ext       = '.nef'
    subFolder = mission # The mission name in caps
    iFrame = int(frame)
    
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
        ext  = '.nef'
        subFolder = chooseSubFolder(iFrame, [95961], ['ISS031', 'ISS031_Batch02'])

    if mission == 'ISS042':
        ext  = '.NEF'
        subFolder = chooseSubFolder(iFrame,
            [170284, 280908], ['ISS042', 'ISS042_Batch02', 'ISS030_Batch03'])

    if mission == 'ISS043':
        ext  = '.NEF'
        subFolder = chooseSubFolder(iFrame, [159293], ['ISS043', 'ISS043_Batch02'])
        
    if mission == 'ISS045':
        ext  = '.NEF'
        subFolder = chooseSubFolder(iFrame, [152311], ['ISS045', 'ISS045_Batch02'])
    
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


class FrameInfo(object):
    '''Class that contains the metadata for one frame.'''
    
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
        
    def loadFromDb(self, dbCursor, mission, roll, frame):
        '''Populate from an entry in the database'''
        dbCursor.execute('select * from Frames where trim(MISSION)=? and trim(ROLL)=? and trim(FRAME)=?',
                       (mission, roll, frame))
        rows = dbCursor.fetchall()
        if len(rows) != 1: # Make sure we found the next lines
            raise Exception('Could not find any data for frame: ' +
                            getFrameString(mission, roll, frame))
            
        rows = rows[0]
        #print rows
        self.mission         = mission
        self.roll            = roll
        self.frame           = frame
        self.exposure        = str(rows[0]).strip()
        self.tilt            = str(rows[3]).strip()
        self.time            = str(rows[8]).strip()
        self.date            = str(rows[9]).strip()
        self.cloudPercentage = float(rows[13]) / 100
        self.altitude        = float(rows[15])
        self.focalLength     = float(rows[18])
        self.centerLat       = float(rows[19])
        self.centerLon       = float(rows[20])
        self.nadirLat        = float(rows[21])
        self.nadirLon        = float(rows[22])
        self.camera          = str(rows[23]).strip()
        self.film            = str(rows[24]).strip()
        if (self.centerLat) and (self.centerLon):
            self.centerPointSource = georefDb.AUTOWCENTER
        self.metersPerPixel  = None # This information is not stored in the database
        
        # Clean up the time format
        self.time = self.time[0:2] +':'+ self.time[2:4] +':'+ self.time[4:6]
        
        # The input tilt can be in letters or degrees so convert
        #  it so that it is always in degrees.
        if (self.tilt == 'NV') or not self.tilt:
            self.tilt = '0'
        if self.tilt == 'LO': # We want to try these
            self.tilt = '30'
        if self.tilt == 'HO': # Do not want to try these!
            self.tilt = '80'
        self.tilt = float(self.tilt)
       
        # Convert the date to 'YYYY.MM.DD' format that the image fetcher wants
        # - TODO: Use a standardized format!
        self.date = self.date[0:4] + '.' + self.date[4:6] + '.' +  self.date[6:8]
       
        # Get the sensor size
        (self.sensorWidth, self.sensorHeight) = getSensorSize(self.camera)
       
        #if not self.isGoodAlignmentCandidate():
        #    return # In this case don't bother finding the images
    
        # Fetch the associated non-raw image files
        dbCursor.execute('select * from Images where trim(MISSION)=? and trim(ROLL)=? and trim(FRAME)=?',
                           (mission, roll, frame))
        rows = dbCursor.fetchall()
        if len(rows) < 1: # No images provided
            return
        # Record the image paths
        bestNumPixels = 0
        for row in rows:
            # Get the file path and verify it exists
            folder = str(row[4]).strip()
            name   = str(row[5]).strip()
            path   = os.path.join(folder, name)
            if not os.path.exists(path):
                continue           
            self.imageList.append(path)
            
            # Record if this is the highest resolution image
            width     = int(row[6])
            height    = int(row[7])
            numPixels = width*height
            if numPixels > bestNumPixels:
                self.width     = width
                self.height    = height
        
        # Try to find an associated RAW file
        thisRaw = getRawPath(self.mission, self.roll, self.frame)
        if os.path.exists(thisRaw):
            self.rawPath = thisRaw
        else:
            print 'Did not find: ' + thisRaw
        
        # TODO: Handle images with no RAW data
        # Get the image size
        if self.rawPath:
            (self.width, self.height) = getRawImageSize(self.rawPath)
    
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
    
    def isGoodAlignmentCandidate(self):
        '''Return True if the image is a good candidate for automatic alignment'''
        rawPath = self.rawPath
        if offline_config.USE_RAW == False:
            rawPath = True
        
        return (self.isExposureGood() and
                self.isTiltGood() and
                self.isCloudPercentageGood() and
                rawPath)

    def isCenterWithinDist(self, lon, lat, dist):
        '''Returns True if the frame center is within a distance of lon/lat.
           Currently works in degree units.'''
        return (abs(self.centerLon - lon) < dist) and (abs(self.centerLat - lat) < dist)
    
    def getIdString(self):
        '''Return the id consistent with our internal conventions'''
        return self.mission+'-'+self.roll+'-'+self.frame

def getMissionList(cursor):
    '''Returns a list of the supported missions'''
    
    # Currently missions need to be added manually!
    missionList = ['ISS006', 'ISS015', 'ISS020', 'ISS025', 'ISS030', 'ISS036',
                   'ISS041', 'ISS047', 'ISS011', 'ISS016', 'ISS021', 'ISS026',
                   'ISS032', 'ISS037', 'ISS042', 'ISS044', 'ISS012', 'ISS017',
                   'ISS022', 'ISS027', 'ISS033', 'ISS038', 'ISS045', 'ISS013',
                   'ISS018', 'ISS023', 'ISS028', 'ISS034', 'ISS039', 'ISS014',
                   'ISS019', 'ISS024', 'ISS029', 'ISS031', 'ISS035', 'ISS040',
                   'ISS043', 'ISS04']
    
    return missionList

def getCandidatesInMission(cursor, mission=None, roll=None, frame=None, checkCoords=True):
    '''Fetch a list of likely alignment candidates for a mission.
       Optionally filter by roll and frame.'''

    # Look up records for the mission that we may be able to process
    
    cmd = ('select MISSION, ROLL, FRAME, LON, LAT from Frames where nullif(CAMERA, "") notnull')
    
    # If requested, verify that the lon and lat values are present.
    if checkCoords:
        cmd += ' and nullif(LON, "") notnull and nullif(LAT, "") notnull'

    
    # If specified, apply these filters.
    if mission:
        cmd += ' and trim(MISSION)="'+mission+'"'
    if roll:
        cmd += ' and trim(ROLL)="'+roll+'"'
    if frame:
        cmd += ' and trim(FRAME)="'+frame+'"'

    # If the user did not fully specify a file, filter based on image quality.
    if (not roll) or (not frame):
        cmd += (' and (TILT != "HO") and CAST(TILT as real) < '+str(offline_config.MAX_TILT_ANGLE)
                +' and CLDP < ' + str(offline_config.MAX_CLOUD_PERCENTAGE_INT))
        
    print cmd
    cursor.execute(cmd)
    rows = cursor.fetchall()

    # Extract the results into a nice list
    results = []
    for row in rows:
        #print row
        mission = row[0].strip()
        roll    = row[1].strip()
        frame   = row[2].strip()
        lon     = row[3] # TODO: Handle NULLs
        lat     = row[4]
        results.append((mission, roll, frame, lon, lat))
    #print cmd
    #raise Exception('DEBUG')
    return results


def test():

    # Open the input database
    print 'Initializing database connection...'
    db     = sqlite3.connect(offline_config.DB_PATH)
    cursor = db.cursor()

    print 'Opening the output log database...'
    dbLog = dbLogger.DatabaseLogger(offline_config.OUTPUT_DATABASE_PATH)
    
    #(mission, roll, frame) = ('ISS001', '347', '24')
    #(mission, roll, frame) = ('ISS026', 'E', '29592')
    #(mission, roll, frame) = ('ISS043', 'E', '91884')  # Warp trouble?
    #(mission, roll, frame) = ('ISS043', 'E', '93251')  # Works poorly on snow!
    #(mission, roll, frame) = ('ISS043', 'E', '122588') # Good only on lake
    #(mission, roll, frame) = ('ISS044', 'E', '868')    # Should be better
    #(mission, roll, frame) = ('ISS044', 'E', '1998')   # Tough image
    
    (mission, roll, frame) = ('ISS043', 'E', '101805') # Weird Landsat
    
    print 'Fetching frame information...'
    frameDbData = FrameInfo()
    frameDbData.loadFromDb(cursor, mission, roll, frame)
    
    print 'Loaded frame info:\n' + str(frameDbData)
    
    if frameDbData.isGoodAlignmentCandidate():
        print 'This image IS a valid alignment candidate:'
    else:
        print 'This image is NOT a valid alignment candidate:'
        

    # Clean up   
    print 'Closing input database connection...'
    db.close()
    
    print 'Finished running source DB test'


# Simple test script
if __name__ == "__main__":
    sys.exit(test())