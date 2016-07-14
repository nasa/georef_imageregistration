import os, sys
import sqlite3
#from pysqlite2 import dbapi2 as sqlite3
import numpy
import datetime

import registration_common


basepath    = os.path.abspath(sys.path[0]) # Scott debug
sys.path.insert(0, basepath + '/../geocamTiePoint')
sys.path.insert(0, basepath + '/../geocamUtilWeb')

from geocamTiePoint import transform

'''
   This file contains code for reading/writing the database
   containing our processing results.
   
   TODO: Manage our file outputs as well!
'''


# This is the table description used to create our output results database!
TABLE_INIT_TEXT = \
"""
CREATE TABLE Results(
  MISSION      TEXT    NOT NULL,
  ROLL         TEXT    NOT NULL,
  FRAME        TEXT    NOT NULL,
  DATE         TEXT    NOT NULL,
  CONFIDENCE   TEXT    NOT NULL,
  TRANSFORM    TEXT,
  IMAGE_POINTS TEXT,
  GDC_POINTS   TEXT,
  PRIMARY KEY (MISSION, ROLL, FRAME)
);
"""


class DatabaseLogger(object):
    '''Main class that manages logging our results.'''
    
    def __init__(self, dbPath):
        '''Sets up logging given the main folder'''
        
        self._dbPath = dbPath
        
        self._dbConnection = None
        self._dbCursor     = None
        self._initSqlDatabase()
    
    def __del__(self):
        '''Clean up the SQL connection'''
        if self._dbConnection:
            self._dbConnection.close()
    
    def _initSqlDatabase(self):
        '''Makes sure that our SQLite database is set up and opens it'''
        
        needToInit =  not os.path.exists(self._dbPath)
        self._dbConnection = sqlite3.connect(self._dbPath)
        self._dbCursor     = self._dbConnection.cursor()    
        if not needToInit:
            return
        
        # Otherwise create the tables
        self._dbCursor.execute(TABLE_INIT_TEXT)
        self._dbConnection.commit()

    def _pointsToText(self, pointList):
        '''Converts a list of 2d points to text for database storage'''
        text = ''
        for point in pointList:
            text += str(point)
        # Make sure the symbols are consistent
        return text.replace('[','(').replace(']',')') 
    
    def _textToPoints(self, text):
        '''Converts a database text entry to a list of 2d points'''
    
        if text == '': # Handle empty lists
            return []
    
        # Make points seperated by ;
        t = text.replace('(','').replace(')',';')

        points = []        
        parts = t[0:-1].split(';') # Strip last ';' before split
        for part in parts:
            subparts = part.split(',')
            points.append( (float(subparts[0]), float(subparts[1])) )
        return points
    
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
    
    
    def getProcessingStats(self, mission=None):
        '''Computes some statistics from our logged results.
           Returns the counts: [total, NONE, LOW, HIGH]'''
        self._dbCursor.execute('select CONFIDENCE from Results where MISSION="'+mission+'"')
        rows = self._dbCursor.fetchall()
        
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
    
    
    def doWeHaveResult(self, mission, roll, frame, overwriteLevel):
        '''Returns True if we have a result for the given frame, otherwise False.
           If overwriteLevel is specified, return False if we have that confidence or less'''
        self._dbCursor.execute('select CONFIDENCE from Results where MISSION=? and ROLL=? and FRAME=?',
                               (mission, roll, frame))
        rows = self._dbCursor.fetchall()
        if len(rows) != 1: # Data not found
            return False
        if not overwriteLevel:
            return True
        # Otherwise compare the level
        level = registration_common.confidenceFromString(rows[0][0])
        return (level > overwriteLevel)
    
    def getResult(self, mission, roll, frame):
        '''Fetches a result from the database.
           Returns None if there is no data for this frame.'''
        
        self._dbCursor.execute('select * from Results where MISSION=? and ROLL=? and FRAME=?',
                               (mission, roll, frame))
        rows = self._dbCursor.fetchall()
        print rows
        if len(rows) != 1: # Data not found
            return (None, None, None, None)
        row = rows[0]
        
        confidence                = registration_common.confidenceFromString(row[4])
        imageToProjectedTransform = self._textToTransform(row[5])
        imageInliers              = self._textToPoints(row[6])
        gdcInliers                = self._textToPoints(row[7])
        # Currently we don't read the date
        
        return (imageToProjectedTransform, confidence, imageInliers, gdcInliers)


    def findNearbyGoodResults(self, mission, roll, frame, frameLimit):
        '''Find all good results within a range of frames from a given frame'''
        
        results = dict()
        self._dbCursor.execute('select * from Results where MISSION=? and ROLL=?'
                               + ' and CONFIDENCE="HIGH"'
                               + ' and ABS(CAST(FRAME as int)-?) < ?',
                               (mission, roll, frame, frameLimit))
        rows = self._dbCursor.fetchall()
        
        for row in rows:
            frame                     = row[2]
            confidence                = registration_common.confidenceFromString(row[4])
            imageToProjectedTransform = self._textToTransform(row[5])
            imageInliers              = self._textToPoints(row[6])
            gdcInliers                = self._textToPoints(row[7])
            results[frame] = (imageToProjectedTransform, confidence, imageInliers, gdcInliers)
            
        return results

    
    def addResult(self, mission, roll, frame,
                  imageToProjectedTransform, confidence, imageInliers, gdcInliers):
        '''Adds a new result to the database'''
        
       
        # Pack some of the parameters in text format
        imagePointText = self._pointsToText(imageInliers)
        gdcPointText   = self._pointsToText(gdcInliers)
        transformText  = self._transformToText(imageToProjectedTransform)
        confidenceText = registration_common.CONFIDENCE_STRINGS[confidence]

        # May be useful to have include the time the record was added
        dateText = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._dbCursor.execute('insert or replace into Results values (?, ?, ?, ?, ?, ?, ?, ?)',
                               (mission, roll, frame, dateText, confidenceText,
                                transformText, imagePointText, gdcPointText))
        self._dbConnection.commit()
        return


import MySQLdb

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
