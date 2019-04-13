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

import pyodbc

import offline_config
import IrgGeoFunctions
import source_image_utils
import georefDbWrapper

import django
from django.conf import settings
django.setup()


class InputDbWrapper(object):
    """Class to handle the connection to the source MS SQL
       database which contains input image information.
    """

    def __init__(self):
        '''Connect to the database'''

        self._dbConnection = None
        self._dbCursor     = None
        self._connect()

    def _connect(self):
        '''Connect to the SQL server'''

        s = 'DRIVER={SQL Server};SERVER=localhost;DATABASE=testdb;UID=me;PWD=pass'
        s = ('DRIVER={SQL Server};SERVER=%s;DATABASE=%s;UID=%s;PWD=%s'
             % (offline_config.MS_DB_HOST, offline_config.MS_DB_NAME,
                offline_config.MS_DB_USER, offline_config.MS_DB_PASS))
        self._dbConnection = pyodbc.connect(s)
        self._dbCursor     = self._dbConnection.cursor()


    def getMissionList(self):
        '''Returns a list of the supported missions'''

        # Each subfolder is either like "ISS015" or "ISS042_Batch02",
        # just ignore the extra batch folders to get the full list.
        folder = offline_config.RAW_IMAGE_FOLDER
        files = os.listdir(folder)
        files = [f for f in files if '_' not in f]

        return return files

    def getCandidatesInMission(self, mission=None, roll=None, frame=None, checkCoords=True):
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
        self._dbCursor.execute(cmd)
        rows = self._dbCursor.fetchall()

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


    def loadFrame(self, mission, roll, frame):
        '''Populate from an entry in the database'''
        self._dbCursor.execute('select * from Frames where trim(MISSION)=? and trim(ROLL)=? and trim(FRAME)=?',
                       (mission, roll, frame))
        rows = self._dbCursor.fetchall()
        if len(rows) != 1: # Make sure we found the next lines
            raise Exception('Could not find any data for frame: ' +
                            source_image_utils.getFrameString(mission, roll, frame))

        output = source_image_utils.FrameInfo()
        rows = rows[0]
        #print rows
        output.mission         = mission
        output.roll            = roll
        output.frame           = frame
        output.exposure        = str(rows[0]).strip()
        output.tilt            = str(rows[3]).strip()
        output.time            = str(rows[8]).strip()
        output.date            = str(rows[9]).strip()
        output.cloudPercentage = float(rows[13]) / 100
        output.altitude        = float(rows[15])
        output.focalLength     = float(rows[18])
        output.centerLat       = float(rows[19])
        output.centerLon       = float(rows[20])
        output.nadirLat        = float(rows[21])
        output.nadirLon        = float(rows[22])
        output.camera          = str(rows[23]).strip()
        output.film            = str(rows[24]).strip()
        if (output.centerLat) and (output.centerLon):
            output.centerPointSource = georefDbWrapper.AUTOWCENTER
        output.metersPerPixel  = None # This information is not stored in the database

        # Clean up the time format
        output.time = output.time[0:2] +':'+ output.time[2:4] +':'+ output.time[4:6]

        # The input tilt can be in letters or degrees so convert
        #  it so that it is always in degrees.
        if (output.tilt == 'NV') or not output.tilt:
            output.tilt = '0'
        if output.tilt == 'LO': # We want to try these
            output.tilt = '30'
        if output.tilt == 'HO': # Do not want to try these!
            output.tilt = '80'
        output.tilt = float(output.tilt)

        # Convert the date to 'YYYY.MM.DD' format that the image fetcher wants
        # - TODO: Use a standardized format!
        output.date = output.date[0:4] + '.' + output.date[4:6] + '.' +  output.date[6:8]

        # Get the sensor size
        (output.sensorWidth, output.sensorHeight) = \
          source_image_utils.getSensorSize(output.camera)

        #if not output.isGoodAlignmentCandidate():
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
            output.imageList.append(path)

            # Record if this is the highest resolution image
            width     = int(row[6])
            height    = int(row[7])
            numPixels = width*height
            if numPixels > bestNumPixels:
                output.width     = width
                output.height    = height

        # Try to find an associated RAW file
        thisRaw = source_image_utils.getRawPath(output.mission, output.roll, output.frame)
        if os.path.exists(thisRaw):
            output.rawPath = thisRaw
        else:
            print 'Did not find: ' + thisRaw

        # TODO: Handle images with no RAW data
        # Get the image size
        if output.rawPath:
            (output.width, output.height) = \
              source_image_utils.getRawImageSize(output.rawPath)

        if output.width == 0:
            [outputPath, exifSourcePath] = source_image_utils.getSourceImage(output)
            output.width, output.height = IrgGeoFunctions.getImageSize(outputPath)
        print "width is %d" % output.width
        print "height is %d" % output.height



def test():

    # Open the input database
    print 'Initializing database connection...'
    db = InputDbWrapper()

    #(mission, roll, frame) = ('ISS001', '347', '24')
    #(mission, roll, frame) = ('ISS026', 'E', '29592')
    #(mission, roll, frame) = ('ISS043', 'E', '91884')  # Warp trouble?
    #(mission, roll, frame) = ('ISS043', 'E', '93251')  # Works poorly on snow!
    #(mission, roll, frame) = ('ISS043', 'E', '122588') # Good only on lake
    #(mission, roll, frame) = ('ISS044', 'E', '868')    # Should be better
    #(mission, roll, frame) = ('ISS044', 'E', '1998')   # Tough image

    (mission, roll, frame) = ('ISS043', 'E', '101805') # Weird Landsat

    print 'Fetching frame information...'
    frameDbData = db.loadFrame(mission, roll, frame)

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
