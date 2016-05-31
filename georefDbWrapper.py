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

from geocamTiePoint import transform

'''
   This file contains code for reading/writing the database
   containing our processing results.
   
   TODO: Manage our file outputs as well!
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
        
        self._dbConnection = MySQLdb.connect(host  =offline_config.GEOREF_DB_HOST,
                                             user  =offline_config.GEOREF_DB_USER,
                                             passwd=offline_config.GEOREF_DB_PASS,
                                             db    =offline_config.GEOREF_DB_NAME)
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

    def getResult(self, mission, roll, frame):
        '''Fetches a result from the database: (confidence, imagePoints, gdcPoints, mpp).
           Returns (None, None, None, None) if there is no data for this frame.'''

        # If we have a manual result, use that!
        manualResult = self.getManualResult(mission, roll, frame)
        if manualResult[0] != None:
            return manualResult

        # No manual result, check the auto results.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = 'SELECT matchConfidence, registrationMpp, extras FROM geocamTiePoint_automatchresults WHERE issMRF="'+mrf+'"'
        rows = self._executeCommand(cmd)

        if len(rows) != 1: # Data not found
            return (None, None, None, None)
        row = rows[0]

        confidence                = registration_common.confidenceFromString(row[0])
        registrationMpp           = row[1]
        resultsDict = json.loads(row[2])
        #imageToProjectedTransform = self._textToTransform(resultsDict.imageToProjectedTransform)
        imageInliers              = resultsDict['imageInliers']
        gdcInliers                = resultsDict['gdcInliers']
        # Currently we don't read the date
        
        return (confidence,
                imageInliers, gdcInliers, registrationMpp)


    def getManualResult(self, mission, roll, frame):
        '''As getResult, but only checks manual results.'''
        
        # Grab the center point from the extras in the overlay table, but we
        #  need to link to the imagedata table to check the MRF.
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        cmd = ('SELECT over.extras FROM geocamTiePoint_overlay over'+
               ' INNER JOIN geocamTiePoint_imagedata image'+
               ' ON over.imageData_id = image.id'+
               ' WHERE image.issMRF="'+mrf+'"')
        print cmd
        rows = self._executeCommand(cmd)
        
        # TODO: Double check this!
        
        print rows
        if len(rows) == 1:
            text = rows[0][0]
            data = json.loads(text)
            if ['lat'] in data:
                lat = data['lat']
                lon = data['lon']
                return (lon, lat)
        return (None, None)



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

    def getGeosenseCenterPoint(self, mission, roll, frame):
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

    def getBestCenterPoint(self, mission, roll, frame, lon=None, lat=None):
        '''Returns the best center point for this frame and the registration
           status.  The input lonlat values are from the input JSC database.'''
        
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
        processed = False
        confidence = 'NONE'
        
        print '=== Checking for our results for ' + mrf

        # First check the registration results
        cmd=('SELECT centerLon, centerLat, matchConfidence FROM'
             +' geocamTiePoint_automatchresults WHERE issMRF="'+mrf+'"')
        #print cmd
        rows = self._executeCommand(cmd)
        
        if len(rows) > 1:
            raise Exception('ERROR: Found '+ str(len(rows)) + ' entries for ' + mrf)
        
        if len(rows) == 1:
            print 'Found: ' + str(rows)
            lonNew = rows[0][0] # TODO: Handle null values
            latNew = rows[0][1]
            #print 'Found lon ' + str(lonNew) + ', found lat ' + str(latNew)
            confidence = registration_common.confidenceFromString(rows[0][2])
            processed  = True # TODO: Can we have an entry with no processing?
            if confidence == registration_common.CONFIDENCE_HIGH:
                (lon, lat) = (lonNew, latNew)
        else:
            print 'Did not find ' + mrf + ' in our DB'

        # TODO: Is this really the most trusted source?
        # Check if there is a manual georef center point, the most trusted source.
        (lonNew, latNew) = self.getManualGeorefCenterPoint(mission, roll, frame)
        if lonNew != None:
            print 'Found manual entry for ' + mrf
            processed  = True
            confidence = registration_common.CONFIDENCE_HIGH
            (lon, lat) = (lonNew, latNew)
            
        if (lonNew!=None) or processed: # Already have the best coordinates
            return (processed, confidence, lon, lat)
        
        # Check if there is a computed geosense center point
        print 'Checking for geosense point...'
        (lonNew, latNew) = self.getGeosenseCenterPoint(mission, roll, frame)
        if lonNew != None:
            print 'found it!'
            (lon, lat) = (lonNew, latNew)
        return (processed, confidence, lon, lat)

    # TODO: Verify that this works properly!
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
                timeString  = acqDate.replace(':','-') +' '+ acqTime
                timeRow     = datetime.datetime.strptime(timeString, TIME_FORMAT)
                diffSeconds = abs((timeIn - timeRow).total_seconds())
                print row[1] + ' --> ' + str(diffSeconds / 60.0)
                if diffSeconds > maxTimeDiff:
                    continue

                # If the time is in range then we will use the result
                confidence                = registration_common.CONFIDENCE_HIGH
                imageToProjectedTransform = transform.makeTransform(data['transform'])
                
                imageInliers = []
                gdcInliers   = []
                allPoints = data['points']
                for point in allPoints:
                    if (point[0] == None) or (point[1] == None) or (point[2] == None) or (point[3] == None):
                        continue # Skip buggy entries!
                    # The world coordinates in the manual table are stored in projected coordinates
                    gdcCoord = transform.metersToLatLon((point[0], point[1]))
                    gdcInliers.append(gdcCoord)
                    imageInliers.append((point[2], point[3]))
                
                results[frame] = (imageToProjectedTransform, confidence, imageInliers, gdcInliers)
            except: # For now just ignore failing entries
                pass
        return results


    
    def addResult(self, mission, roll, frame,
                  imageToProjectedTransform, imageToGdcTransform,
                  centerLat, centerLon, registrationMpp,
                  confidence, imageInliers, gdcInliers,
                  matchedImageId, sourceTime):
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
        centerPointSource = 'Autoregistration' # This field can be deleted?
        writtenToFile = 0
        
        cmd = ("REPLACE INTO geocamTiePoint_automatchresults (issMRF, matchedImageId,"
               +" matchConfidence, matchDate, centerPointSource, extras, capturedTime,"
               +" writtenToFile, centerLat, centerLon, registrationMpp)"
               +" VALUES('%s','%s','%s','%s','%s','%s','%s',%d,%d,%d,%d)"
                             % (mrf, matchedImageId, confidenceText, dateText,
                                centerPointSource, resultText, sourceTime,
                                writtenToFile, centerLat, centerLon, registrationMpp))
        self._executeCommand(cmd, commit=True)
        
        # Before we return, verify that our result actually made it into the database.
        # Make checks periodically until we find it or give up.
        #NUM_CHECKS = 6
        #for i in range(0,NUM_CHECKS):
        #    if self.doWeHaveResult(mission, roll, frame):
        #        print 'Verified result add.'
        #        return
        #    print 'Waiting for DB addition...'
        #    time.sleep(5)
        
        #raise Exception('Database failed to add frame ' + mrf)

    def markAsWritten(self, mission, roll, frame):
        '''Update a registration result to mark that we wrote the output images.'''
        mrf = self._missionRollFrameToMRF(mission, roll, frame)
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
        
    
    def getImagesReadyForOutput(self, confidence='HIGH', limit=0):
        '''Returns a list of images where the required registration information is available.'''

        # TODO: Do we need to check the geocamTiePoint_overlay table too?
        #       --> It contains points, transform, etc in the extras field.

        cmd = ('SELECT issMRF FROM geocamTiePoint_automatchresults WHERE matchConfidence="'
               +confidence+'" AND writtenToFile=0')
        if limit > 0:
            cmd += ' LIMIT ' + str(limit)
        rows = self._executeCommand(cmd)
        
        output = []
        for row in rows:
            output.append(self._MRFToMissionRollFrame(row[0]))
        
        return output


    

    def getImagesReadyForRegistration(self, ):
        '''Returns a list of image MRFs ready for autoregistration.
           The requirements for registration are the center point
           and a camera model.  If available, image quality information
           can be considered.  The center point can be obtained from
           one of multiple sources.'''

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













