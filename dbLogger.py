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
   This file contains code for reading/writing our processing
   results so they can be easily used/modified in the future.
'''


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
        print needToInit
        if not needToInit:
            return
        # Otherwise create the tables
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
        self._dbCursor.execute(TABLE_INIT_TEXT)
        self._dbConnection.commit()

    
    #def _getLogFolder(self, mission, roll, frame):
    #    '''Returns the folder containing the specified log file'''
    #    pass
    
    #def _getLogPath(self, mission, roll, frame):
    #    '''Returns the full path to our log file for this frame'''
    #    pass


    def _pointsToText(self, pointList):
        '''Converts a list of 2d points to text for database storage'''
        text = ''
        for point in pointList:
            text += str(point)
        # Make sure the symbols are consistent
        return text.replace('[','(').replace(']',')') 
    
    def _textToPoints(self, text):
        '''Converts a database text entry to a list of 2d points'''
    
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
        t = text.replace('[','').replace(']',';')
        
        mat = numpy.matrix(t[0:-2]) # Strip last two ';' before parsing
        tform = transform.ProjectiveTransform(mat)
        return tform
    
    
    def checkStats(self, mission=None):
        '''Computes some statistics from our logged results'''
        print 'TODO GENERATE STATS'
    
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
        
        return (imageToProjectedTransform, confidence, imageInliers, gdcInliers)
    
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

        print 'Intersting into DB...'
        self._dbCursor.execute('insert or replace into Results values (?, ?, ?, ?, ?, ?, ?, ?)',
                               (mission, roll, frame, dateText, confidenceText,
                                transformText, imagePointText, gdcPointText))
        self._dbConnection.commit()
        print 'Done inserting.'
        return
        
        
        
        
        