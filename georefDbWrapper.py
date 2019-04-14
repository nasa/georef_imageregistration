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
import MySQLdb
import numpy
import datetime
import json
import registration_common
import offline_config

basepath    = os.path.abspath(sys.path[0]) # Scott debug
sys.path.insert(0, basepath + '/../geocamTiePoint')
sys.path.insert(0, basepath + '/../geocamUtilWeb')

import django
from django.conf import settings
django.setup()

from geocamTiePoint import transform

"""
Center point source options (in order of "goodness").
"""
MANUAL = 'manual'
AUTOWCENTER = 'autowcenterpt'
GEOSENS = 'geosens'

'''
   This file contains code for reading/writing the database
   containing our processing results.
   
   TODO: Update write statements to use safer input wrapping method!
'''

if __name__ == "__main__":
    
    # Try connecting to the MySQL server
    print 'connect'
    db = MySQLdb.connect(host="localhost", user="root", passwd="vagrant", db="georef")
    cursor = db.cursor();
    print 'cmd'
    cursor.execute('show tables;')
    tables = cursor.fetchall()
    print tables
    
    for table in tables:
        print '\n========================================='
        print table[0]
        cursor.execute('describe ' + table[0])
        result = cursor.fetchall()
        print result

    db.close()
    print 'done'


class DatabaseLogger(object):
    '''Main class that interfaces with the MySQL database.'''
    
    def __init__(self):
        '''Connect to the database'''

        self._dbConnection = None
        self._dbCursor     = None
        self._connect()

    def _connect(self):
        '''Connect to the SQL server'''
        
        self._dbConnection = MySQLdb.connect(host  =settings.GEOREF_DB_HOST,
                                             user  =settings.GEOREF_DB_USER,
                                             passwd=settings.GEOREF_DB_PASS,
                                             db    =settings.GEOREF_DB_NAME)
        self._dbCursor     = self._dbConnection.cursor()
    
        #self._executeCommand("set session transaction isolation level READ COMMITTED")
    
    def __del__(self):
        '''Clean up the SQL connection'''
        if self._dbConnection:
            self._dbConnection.close()
    
    def _missionRollFrameToMRF(self, mission, roll, frame):
        '''Convert mission, roll, frame to our database format'''
        return mission+'-'+roll+'-'+frame
    
    def _MRFToMissionRollFrame(self, MRF):
        parts = MRF.split('-')
        if len(parts) < 3: # Failure case
            return ('', '', '')
        return (parts[0], parts[1], parts[2])

    def _transformToText(self, tform):
        '''Converts a transform to text for database storage'''
        text = str(tform.matrix).replace('\n', ' ')
        return text
    
    def _textToTransform(self, text):
        '''Converts a database text entry to a transform'''
        
        # Make rows seperated by ;
        t = text.replace('[','').replace(']',' ')
        parts = [float(x) for x in t.split()]
        
        mat = numpy.array([[parts[0], parts[1], parts[2]],
                           [parts[3], parts[4], parts[5]],
                           [parts[6], parts[7], parts[8]]],
                          dtype='float64')
        tform = transform.ProjectiveTransform(mat)       
        return tform

    def _executeCommand(self, command, commit=False):
        '''Execute an SQL command.'''
        
        # Stick code here so it does not have to be duplicated
        def inner(command, commit):
            self._dbCursor.execute(command)
            if commit:
                self._dbConnection.commit()
                return None
            else:
                rows = self._dbCursor.fetchall()
                self._dbConnection.commit()
                return rows
        
        try:
            return inner(command, commit)
        except:
            # Try to reconnect after a timeout failure
            print 'Attempting to reconnect to our MySQL database...'
            self._dbConnection.close()
            self._connect()
            return inner(command, commit)
            

# -------------------------------------------------------------------
# These functions are for working with registration results
    
    def getProcessingStats(self, mission=None):
        '''Computes some statistics from our logged results.
           Returns the counts: [total, NONE, LOW, HIGH].
           Does not include manual results.'''
        if mission:
            cmd = 'SELECT matchConfidence FROM geocamTiePoint_automatchresults WHERE issMRF LIKE"'+mission+'%"'
        else:
            cmd = 'SELECT matchConfidence FROM geocamTiePoint_automatchresults'
        rows = self._executeCommand(cmd)
        
        counts = [0, 0, 0, 0]
        counts[0] = len(rows)
        for row in rows:
            if row[0] == 'NONE':
                counts[1] += 1
            elif row[0] == 'LOW':
                counts[2] += 1
            elif row[0] == 'HIGH':
                counts[3] += 1
            else:
                raise Exception('Unknown confidence type!')
        
        return counts
    
    
    def doWeHaveResult(self, mission, roll, frame, overwriteLevel=None):
        '''Returns True if we have a result for the given frame, otherwise False.
           If overwriteLevel is specified, return False if we have that confidence or less'''
        
        # If we have a manual result there will be a center point in the overlay table.
        (lonManual, latManual) = self.getManualGeorefCenterPoint(mission, roll, frame)
        if (lonManual != None) and (latManual != None):
            return True
   
        # If we don't have a manual center point, check the autoregistration results.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd=('SELECT matchConfidence FROM geocamTiePoint_automatchresults WHERE issMRF="'+mrf+'"')
        rows = self._executeCommand(cmd)
        if len(rows) != 1: # Data not found
            return False
        if not overwriteLevel:
            return True
        # Otherwise compare the level
        level = registration_common.confidenceFromString(rows[0][0])
        return (level > overwriteLevel)
    

    def getRegistrationResult(self, mission, roll, frame):
        '''Fetches a result from the database and packs it into a dictionary'''

        # If we have a manual result, use that!
        manualResult = self.getManualRegistrationResult(mission, roll, frame)
        if manualResult:
            return manualResult

        # No manual result, check the auto results.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = 'SELECT matchConfidence, registrationMpp, extras, centerPointSource FROM geocamTiePoint_automatchresults WHERE issMRF="'+mrf+'"'
        rows = self._executeCommand(cmd)

        if len(rows) != 1: # Data not found
            return {}
        row = rows[0]

        confidence                = registration_common.confidenceFromString(row[0])
        registrationMpp           = row[1]
        resultsDict = json.loads(row[2])
        #imageToProjectedTransform = self._textToTransform(resultsDict.imageToProjectedTransform)
        imageInliers              = resultsDict['imageInliers']
        gdcInliers                = resultsDict['gdcInliers']
        centerPointSource         = row[3]
        # Currently we don't read the date
        
        return {'confidence':confidence, 'imageInliers':imageInliers,
                'gdcInliers':gdcInliers, 'registrationMpp':registrationMpp, 
                'isManual':False, 'centerPointSource': centerPointSource}


    def getManualRegistrationResult(self, mission, roll, frame):
        '''As getResult, but only checks manual results.'''
        
        # Grab the center point from the extras in the overlay table, but we
        #  need to link to the imagedata table to check the MRF.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = ('SELECT over.extras, image.height, image.width FROM geocamTiePoint_overlay over'+
               ' INNER JOIN geocamTiePoint_imagedata image'+
               ' ON over.imageData_id = image.id'+
               ' WHERE image.issMRF="'+mrf+'"')
        print cmd
        rows = self._executeCommand(cmd)

        DEFAULT_MPP = 30 # Manual registration does not really have an MPP size...
        
        if len(rows) != 1:
            return None

        pixelHeight = rows[0][1]
        pixelWidth  = rows[0][2]
        extrasText  = rows[0][0]
        data = json.loads(extrasText)
        (imageInliers, gdcInliers) = self.parseManualEntryPointPairs(data)

        return {'confidence':registration_common.CONFIDENCE_HIGH, 'imageInliers':imageInliers,
                'gdcInliers':gdcInliers, 'registrationMpp':DEFAULT_MPP, 'isManual':True,
                'manualImageHeight':pixelHeight, 'manualImageWidth':pixelWidth, 
                'centerPointSource': MANUAL}


    def getManualGeorefCenterPoint(self, mission, roll, frame):
        '''Returns the lon/lat manually created by the user in Georef.
           This is the most trusted image center.
           Returns (None, None) if not available'''
        
        # Grab the center point from the extras in the overlay table, but we
        #  need to link to the imagedata table to check the MRF.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = ('SELECT over.extras FROM geocamTiePoint_overlay over'+
               ' INNER JOIN geocamTiePoint_imagedata image'+
               ' ON over.imageData_id = image.id'+
               ' WHERE image.issMRF="'+mrf+'"')
        #print cmd
        rows = self._executeCommand(cmd)
        
        if len(rows) == 1:
            text = rows[0][0]
            data = json.loads(text)
            if 'centerLat' in data:
                lat = data['centerLat']
                lon = data['centerLon']
                return (lon, lat)
        return (None, None)

    def getGeosensCenterPoint(self, mission, roll, frame):
        '''Returns the lon/lat computed by our geosense tool.
           Returns (None, None) if not available'''
        
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = ('SELECT centerLon, centerLat FROM geocamTiePoint_geosens'
               +' WHERE issMRF="'+mrf+'"')
        rows = self._executeCommand(cmd)
        if len(rows) == 1:
            lon = rows[0][0] # TODO: Handle null values
            lat = rows[0][1]
            return (lon, lat)
        return (None, None)

    
    def getAutomatchResults(self, mission, roll, frame):
        """
        Returns existing automatch results for a given ISS ID.
        """
        centerPointSource = None
        lonNew = None
        latNew = None
        confidence = None
        
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd=('SELECT centerLon, centerLat, matchConfidence, centerPointSource FROM'
             +' geocamTiePoint_automatchresults WHERE issMRF="'+mrf+'"')
        #print cmd
        rows = self._executeCommand(cmd)
        if len(rows) > 1:
            raise Exception('ERROR: Found '+ str(len(rows)) + ' entries for ' + mrf)

        if len(rows) == 1:
            print 'Found: ' + str(rows)
            lonNew = rows[0][0] # TODO: Handle null values
            latNew = rows[0][1]
            centerPointSource = rows[0][3]
            confidence = registration_common.confidenceFromString(rows[0][2])
        else:
            print 'Did not find ' + mrf + ' in our DB'
        
        return (lonNew, latNew, confidence, centerPointSource)
        
    
    def getBestCenterPoint(self, mission, roll, frame, frameInfo):
        '''Returns the best center point for this frame and the registration
           status.  The input lonlat values are from the input JSC database.'''
        centerPointSource = None
        confidence = None
        lon = None
        lat = None
        
        # see if the center lat and lon can be retrieved from CEO's database.]
        if (frameInfo.centerPointSource == AUTOWCENTER):
            ceoCenterLon = frameInfo.centerLon 
            ceoCenterLat = frameInfo.centerLat
         
        # Check if there is a manual georef center point, the most trusted source.
        (manualLon, manualLat) = self.getManualGeorefCenterPoint(mission, roll, frame)
        if manualLon and manualLat:
            confidence = registration_common.CONFIDENCE_HIGH
            (lon, lat) = (manualLon, manualLat)
            centerPointSource = MANUAL
        elif ceoCenterLon and ceoCenterLat:
            (lon, lat) = (ceoCenterLon, ceoCenterLat)
            centerPointSource = AUTOWCENTER
            confidence = 'None'
        else: 
            # Check if there is a computed geosense center point
            (lonNew, latNew) = self.getGeosensCenterPoint(mission, roll, frame)
            if lonNew != None:
                (lon, lat) = (lonNew, latNew)
                centerPointSource = GEOSENS
                confidence = 'NONE'

        return (lon, lat, confidence, centerPointSource)
            

    def findNearbyGoodResults(self, timestamp, frameLimit, mission=None):
        '''Find all good results nearby a given time.
           If mission is provided restrict to the mission.'''

        # We get one set each of manual and auto results.
        # - There probably won't be too many manual results.
        MAX_TIME_DIFF = 60*30 # 30 minutes
        results = self.findNearbyManualResults(timestamp, MAX_TIME_DIFF, missionIn=mission)

        # Find the N closest frames with a maximum difference of 10 minutes.
        cmd = ('SELECT * FROM geocamTiePoint_automatchresults WHERE matchConfidence="HIGH" '
                               + ' AND abs(TIMESTAMPDIFF(second, capturedTime, "'+timestamp+'"))<1800')
        if mission:
            cmd += ' AND issMRF LIKE "%'+mission+'%"'
        cmd += ' ORDER BY abs(TIMESTAMPDIFF(second, capturedTime, "'+timestamp+'"))'
        cmd += ' LIMIT ' + str(frameLimit)
        print cmd
        rows = self._executeCommand(cmd)

        for row in rows:
            mission, roll, frame      = self._MRFToMissionRollFrame(row[2])
            confidence                = registration_common.confidenceFromString(row[4])
            resultsDict = json.loads(row[5])
            imageToProjectedTransform = self._textToTransform(resultsDict['imageToProjectedTransform'])
            imageInliers              = resultsDict['imageInliers']
            gdcInliers                = resultsDict['gdcInliers']

            results[frame] = (imageToProjectedTransform, confidence, imageInliers, gdcInliers)

        return results  


    def parseManualEntryPointPairs(self, manualInfoDict):
        '''Unpack the inlier point pairs from an entry in the geocamTiePoint_overlay table'''
    
        imageInliers = []
        gdcInliers   = []
        allPoints = manualInfoDict['points']
        for point in allPoints:
            if (point[0] == None) or (point[1] == None) or (point[2] == None) or (point[3] == None):
                continue # Skip buggy entries!
            # The world coordinates in the manual table are stored in projected coordinates
            gdcCoord = transform.metersToLatLon((point[0], point[1]))
            gdcInliers.append(gdcCoord)
            imageInliers.append((point[2], point[3]))
            
        return (imageInliers, gdcInliers)
    

    def findNearbyManualResults(self, timestamp, maxTimeDiff, missionIn=None):
        '''Find all manual registration results near a certain time.'''
        
        # Fetch results from manual table in the DB
        results = dict()
        cmd = ('SELECT over.extras, image.issMRF FROM geocamTiePoint_overlay over'+
               ' INNER JOIN geocamTiePoint_imagedata image'+
               ' ON over.imageData_id = image.id')
        print cmd
        rows = self._executeCommand(cmd)
        
        TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
        timeIn = datetime.datetime.strptime(timestamp, TIME_FORMAT)
        
        # Check each result for time distance
        for row in rows:
            try:
                # Restrict to the mission if it was provided
                mission, roll, frame = self._MRFToMissionRollFrame(row[1])
                if missionIn and (mission != missionIn):
                    continue
                
                # Unpack all the text data
                data = json.loads(row[0])
    
                # Convert and compare the timestamps
                acqDate     = data['acquisitionDate']
                acqTime     = data['acquisitionTime']
                timeString  = acqDate.replace('/','-') +' '+ acqTime
                timeRow     = datetime.datetime.strptime(timeString, TIME_FORMAT)
                diffSeconds = abs((timeIn - timeRow).total_seconds())
                print row[1] + ' --> ' + str(diffSeconds / 60.0)
                if diffSeconds > maxTimeDiff:
                    continue

                # If the time is in range then we will use the result
                confidence                 = registration_common.CONFIDENCE_HIGH
                imageToProjectedTransform  = transform.makeTransform(data['transform'])
                (imageInliers, gdcInliers) = self.parseManualEntryPointPairs(data)
                
                results[frame] = (imageToProjectedTransform, confidence, imageInliers, gdcInliers)
            except: # For now just ignore failing entries
                pass
        return results

    
    def addResult(self, mission, roll, frame,
                  imageToProjectedTransform, imageToGdcTransform,
                  centerLat, centerLon, registrationMpp,
                  confidence, imageInliers, gdcInliers,
                  matchedImageId, sourceTime, centerPointSource):
        '''Adds a new result to the database'''
       
        # Pack some of the parameters in text format
        resultDict = {'imageInliers':imageInliers, 'gdcInliers':gdcInliers,
                      'imageToProjectedTransform':self._transformToText(imageToProjectedTransform),
                      'imageToGdcTransform':      self._transformToText(imageToGdcTransform)
                      }
        resultText = json.dumps(resultDict) # Goes into the "extras" field
        confidenceText = registration_common.CONFIDENCE_STRINGS[confidence]

        # May be useful to have include the time the record was added
        # -> Can probably have the database do this automatically
        dateText = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        writtenToFile = 0
        
        cmd = ("REPLACE INTO geocamTiePoint_automatchresults (issMRF, matchedImageId,"
               +" matchConfidence, matchDate, centerPointSource, extras, capturedTime,"
               +" writtenToFile, centerLat, centerLon, registrationMpp)"
               +" VALUES('%s','%s','%s','%s','%s','%s','%s',%d,%d,%d,%d)"
                             % (mrf, matchedImageId, confidenceText, dateText,
                                centerPointSource, resultText, sourceTime,
                                writtenToFile, centerLat, centerLon, registrationMpp))
        self._executeCommand(cmd, commit=True)
    
    
    def markAsWritten(self, mission, roll, frame):
        '''Update a registration result to mark that we wrote the output images.'''
        
        # Check if there is a manual result for this MRF
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = ('SELECT over.key FROM geocamTiePoint_overlay over'+
               ' INNER JOIN geocamTiePoint_imagedata image'+
               ' ON over.imageData_id = image.id WHERE image.issMRF="'+mrf+'"')
        #print cmd
        rows = self._executeCommand(cmd)
        if len(rows) > 1:
            raise Exception('Multiple manual results found for ' + mrf)
        
        if len(rows) == 1: # Set the writtenToFile flag
            self._dbCursor.execute("UPDATE geocamTiePoint_overlay SET writtenToFile=1 WHERE geocamTiePoint_overlay.key=%s",
                                   (rows[0][0]))
            self._dbConnection.commit()
            return

        # If there is not, it must be an automatic result.
        cmd = ('UPDATE geocamTiePoint_automatchresults SET writtenToFile=1'
               +' WHERE issMRF="'+mrf+'"')
        self._executeCommand(cmd, commit=True)
        return
    

#-------------------------------------------------------
# Other data retrieval functions

    #Center point locations:
    #    0 - nadir point
    #    1 - Computed geosense --> In the geosens table
    #    2 - JSC database --> Handled by other class
    #    3 - automatching
    #    4 - georef database (overlay->extras)

    # -> Michael is generating the center points!
    def getImagesToComputeCenterPoint(self):
        '''Returns a list of images with ISS and Geosense information but no
           existing center point.'''
           
        query1 = ('SELECT issMRF FROM geocamTiePoint_isstelemetry, geocamTiePoint_geosens, geocamTiePoint_automatchresults'+
                  ' WHERE geocamTiePoint_isstelemetry.issMRF = geocamTiePoint_geosens.issMRF')
        query2 = ('SELECT issMRF FROM geocamTiePoint_automatchresults WHERE lon IS NOT NULL AND lat IS NOT NULL')
        mainCmd = ('SELECT issMRF FROM ('+query1+') WHERE issMRF NOT IN ('+query2+')')
        rows = self._executeCommand(mainCmd)
        
        output = []
        for row in rows:
            output.append(_MRFToMissionRollFrame(row[0]))
        
        return output
        
    
    def getImagesReadyForOutput(self, confidence='HIGH', limit=0,
                                autoOnly=False, manualOnly=False):
        '''Returns a list of images where the required registration information is available.'''

        if autoOnly and manualOnly:
            raise Exception("Can't require both manual and automatic images!")

        # First check the manual results, these are higher priority to process.
        output = []
        if not autoOnly:
            cmd = ('SELECT over.extras, image.issMRF FROM geocamTiePoint_overlay over'+
                   ' INNER JOIN geocamTiePoint_imagedata image'+
                   ' ON over.imageData_id = image.id WHERE over.writtenToFile=0 and readyToExport=1')
            print cmd
            rows = self._executeCommand(cmd)
            
            for row in rows:
                try:
                    # Check if this image has enough information to be written.
                    data = json.loads(row[0])
                    try:
                        if len(data['points']) < 3:
                            continue
                    except:
                        continue
                    
                    # Otherwise add to the list
                    output.append(self._MRFToMissionRollFrame(row[1]))
                    
                    # Stop whenever we get enough data
                    if limit and (len(output) >= limit):
                        return output
                except: # For now just ignore failing entries
                    pass
        # End manually registered search

        if not manualOnly:
            # If we need more images, now look at the automatic table.
            cmd = ('SELECT issMRF FROM geocamTiePoint_automatchresults WHERE matchConfidence="'
                   +confidence+'" AND writtenToFile=0')
            if limit: # Only get the amount we need
                cmd += ' LIMIT ' + str(limit-len(output))
            print cmd
            rows = self._executeCommand(cmd)
            
            for row in rows:
                output.append(self._MRFToMissionRollFrame(row[0]))
        # End automatic registration search
        
        return output


    # TODO Do we have any need for this function?
    def getImagesReadyForRegistration(self, ):
        """
        Returns a list of image MRFs ready for autoregistration.
        The requirements for registration are the center point
        and a camera model.  If available, image quality information
        can be considered.  The center point can be obtained from
        one of multiple sources.
        """
        raise Exception('Center point is being computed elsewhere!')
 
        # TODO: Look at the table contents to refine further
        # Currently looks for telemetry + image entries with NO result entry.
        cmd = ('SELECT issMRF FROM (geocamTiePoint_geosens sens'+
               ' INNER JOIN geocamTiePoint_isstelemetry telem'+
               ' ON sens.issMRF = telem.issMRF'+
               ' INNER JOIN geocamTiePoint_imagedata im'+
               ' ON sens.issMRF = im.issMRF)'+
               ' WHERE issMRF NOT IN (SELECT issMRF FROM geocamTiePoint_automatchresults)')
        rows = self._executeCommand(cmd)
     
        output = []
        for row in rows:
            output.append(_MRFToMissionRollFrame(row[0]))
         
        return output
