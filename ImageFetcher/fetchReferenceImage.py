# -----------------------------------------------------------------------------
# Copyright * 2014, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration. All
# rights reserved.
#
# The Crisis Mapping Toolkit (CMT) v1 platform is licensed under the Apache
# License, Version 2.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
# -----------------------------------------------------------------------------

'''
    Run MODIS based flood detection algorithms on many lakes at a single time
    and log the results compared with the permanent water mask.
'''

import logging
logging.basicConfig(level=logging.ERROR)
try:
    import ee_authenticate
except:
    import sys
    import os.path
    sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    import ee_authenticate
ee_authenticate.initialize()

import sys
import time
import os
import csv
import ee
import numpy
import traceback
import functools
import pprint

import miscUtilities



def get_image_collection_landsat5(bounds, start_date, end_date):
    '''Retrieve Landsat 5 imagery for the selected location and dates.'''

    ee_bounds  = bounds
    ee_points  = ee.List(bounds.bounds().coordinates().get(0))
    points     = ee_points.getInfo()
    points     = map(functools.partial(apply, ee.Geometry.Point), points)
    #collection = ee.ImageCollection('LT5_L1T_TOA').filterDate(start_date, end_date).filterBounds(points[0]).filterBounds(points[1]).filterBounds(points[2]).filterBounds(points[3])
    collection = ee.ImageCollection('LT5_L1T').filterDate(start_date, end_date).filterBounds(points[0]).filterBounds(points[1]).filterBounds(points[2]).filterBounds(points[3])
    return collection


def get_image_collection_modis(region, start_date, end_date):
    '''Retrieve MODIS imagery for the selected location and dates.'''

    print 'Fetching MODIS data...'

    ee_points    = ee.List(region.bounds().coordinates().get(0))
    points       = ee_points.getInfo()
    points       = map(functools.partial(apply, ee.Geometry.Point), points)
    highResModis = ee.ImageCollection('MOD09GQ').filterDate(start_date, end_date).filterBounds(points[0]).filterBounds(points[1]).filterBounds(points[2]).filterBounds(points[3])
    lowResModis  = ee.ImageCollection('MOD09GA').filterDate(start_date, end_date).filterBounds(points[0]).filterBounds(points[1]).filterBounds(points[2]).filterBounds(points[3])
    
    # This set of code is needed to merge the low and high res MODIS bands
    def merge_bands(element):
        # A function to merge the bands together.
        # After a join, results are in 'primary' and 'secondary' properties.       
        return ee.Image.cat(element.get('primary'), element.get('secondary'))
    join          = ee.Join.inner()
    f             = ee.Filter.equals('system:time_start', None, 'system:time_start')
    modisJoined   = ee.ImageCollection(join.apply(lowResModis, highResModis, f));
    roughJoined   = modisJoined.map(merge_bands);
    # Clean up the joined band names
    band_names_in = ['num_observations_1km','state_1km','SensorZenith','SensorAzimuth','Range','SolarZenith','SolarAzimuth','gflags','orbit_pnt',
                     'num_observations_500m','sur_refl_b03','sur_refl_b04','sur_refl_b05','sur_refl_b06','sur_refl_b07',
                     'QC_500m','obscov_500m','iobs_res','q_scan','num_observations', 'sur_refl_b01_1','sur_refl_b02_1','QC_250m','obscov']
    band_names_out = ['num_observations_1km','state_1km','SensorZenith','SensorAzimuth','Range','SolarZenith','SolarAzimuth','gflags','orbit_pnt',
                      'num_observations_500m','sur_refl_b03','sur_refl_b04','sur_refl_b05','sur_refl_b06','sur_refl_b07',
                      'QC_500m','obscov_500m','iobs_res','q_scan','num_observations_250m', 'sur_refl_b01','sur_refl_b02','QC_250m','obscov']
    collection    = roughJoined.select(band_names_in, band_names_out)
    return collection


def get_image_date(image_info):
    '''Extract the (text format) date from EE image.getInfo() - look for it in several locations'''
    
    if 'DATE_ACQUIRED' in image_info['properties']: # Landsat 5
        this_date = image_info['properties']['DATE_ACQUIRED']
    else:
        # MODIS: The date is stored in the 'id' field in this format: 'MOD09GA/MOD09GA_005_2004_08_15'
        text       = image_info['id']
        dateStart1 = text.rfind('MOD09GA_') + len('MOD09GA_')
        dateStart2 = text.find('_', dateStart1) + 1
        this_date  = text[dateStart2:].replace('_', '-')

    return this_date

def getCloudPercentage(image, bounds):
    '''Estimates the cloud percentage in an image'''
    
    likelihood = ee.Algorithms.Landsat.simpleCloudScore(image)
    LANDSAT_RESOLUTION = 30
    CLOUD_THRESHOLD    = 80
    
    #print '=================='
    #pprint.pprint(likelihood.getInfo())
    
    oneMask    = ee.Image(1.0)
    areaCount  = oneMask.reduceRegion(  ee.Reducer.sum(), bounds, LANDSAT_RESOLUTION)
    cloudArea  = likelihood.select('cloud').gte(CLOUD_THRESHOLD)
    cloudCount = cloudArea.reduceRegion(ee.Reducer.sum(), bounds, LANDSAT_RESOLUTION)
    
    #miscUtilities.downloadEeImage(likelihood.select('cloud'), bounds, 16, 'clouds.tif')
    #miscUtilities.downloadEeImage(cloudArea, bounds, 16, 'clouds2.tif')
    
    #print '=================='
    #pprint.pprint(cloudCount.getInfo())
    
    percentage = ((miscUtilities.safe_get_info(cloudCount)['cloud']) /
                  miscUtilities.safe_get_info(areaCount)['constant']       )
    
    print 'Percentage clouds = ' + str(percentage)
    
    return percentage



# List of image sources we will use, in order.
#NUM_SENSOR_OPTIONS = 6
#SENSOR_LANDSAT_5 = 1
#SENSOR_LANDSAT_8 = 0
#SENSOR_LANDSAT_7 = 2
#SENSOR_LANDSAT_4 = 3
#SENSOR_LANDSAT_3 = 4
#SENSOR_LANDSAT_2 = 5

## Indices match the constants above
#sensorStringNames = ['LC8_L1T', 'LT5_L1T', 'LE7_L1T', 'LM4_L1T', 'LM3_L1T', 'LM2_L1T']

LANDSAT_SENSORS = [
    {'name': 'LC8_L1T',  'rgbBands': ['B4', 'B3', 'B2']},
    {'name': 'LT5_L1T',  'rgbBands': ['B3', 'B2', 'B1']},
    {'name': 'LE7_L1T',  'rgbBands': ['B3', 'B2', 'B1']}#,
    #{'name': 'LM4_L1T',  'rgbBands': ['B3', 'B2', 'B1']},
    #{'name': 'LM3_L1T',  'rgbBands': ['B3', 'B2', 'B1']},
    #{'name': 'LM2_L1T',  'rgbBands': ['B3', 'B2', 'B1']}
]




def fetchSensorSeason(sensorName, bounds, date, bigRange=False):
    ''''''
       
    if bigRange: # Grab all the data we can!
        dateStart = ee.Date.fromYMD(1970, 1,  01)
        dateEnd   = ee.Date.fromYMD(2015, 10, 15)
        collection = ee.ImageCollection(sensorName).filterDate(dateStart, dateEnd).filterBounds(bounds)
        return collection
    
    # Otherwise grab nearby portions of the year across several years
    fullCollection = None    
    monthRange = 3.0
    for i in [-2, -1, 0, 1, 2]: # Year offsets

        yearDate   = date.advance(-1.0*i, 'year')
        dateStart  = yearDate.advance(-1.0*monthRange, 'month')
        dateEnd    = yearDate.advance(     monthRange,  'month')
        #print 'Looking in range: '
        #print dateStart.format().getInfo()
        #print dateEnd.format().getInfo()
        collection = ee.ImageCollection(sensorName).filterDate(dateStart, dateEnd).filterBounds(bounds)
        if fullCollection:
            fullCollection = fullCollection.merge(collection)
        else:
            fullCollection = collection
        #print fullCollection.size().getInfo()
        
    return fullCollection


def findClearImage(bounds, date):
    '''Find a suitable reference image at a location'''
    
    MAX_CLOUD_PERCENTAGE = 0.00

    # Needed to change EE formats for later function calls
    rectBounds = bounds

    # TODO: Any use for the water mask?
    ## Get the permanent water mask
    ## - We change the band name to make this work with the evaluation function call further down
    #waterMask = ee.Image("MODIS/MOD44W/MOD44W_005_2000_02_24").select(['water_mask'], ['b1'])

    
    DESIRED_NUM_IMAGES = 10
    bestNumImages = 0
    bestSensor    = None
    
    # Keep trying sensors until we get a good image
    # - The sensors are in order of decreasing desireability
    for sensor in LANDSAT_SENSORS:
        requestString = sensor['name']
    
        #print 'Looking for sensor: ' + requestString
    
        #refImageCollection = ee.ImageCollection(requestString).filterDate(dateStart, dateEnd).filterBounds(bounds)
        refImageCollection = fetchSensorSeason(requestString, bounds, date)
        numRefImagesFound  = refImageCollection.size().getInfo()
        if (numRefImagesFound > bestNumImages):
            bestNumImages = numRefImagesFound
            bestSensor    = sensor
        print 'Found ' + str(numRefImagesFound) + ' landsat images in this region using sensor ' + requestString
        
        if numRefImagesFound < DESIRED_NUM_IMAGES:
            continue # Skip sensors without enough image data
    
        percentile = 50 # Default values
        cloudScoreRange = 10
        maxDepth = 40
        composite = ee.Algorithms.Landsat.simpleComposite(refImageCollection,
                                percentile, cloudScoreRange, maxDepth, asFloat=True)
        
        #cloudPercentage = getCloudPercentage(composite, rectBounds)
        #print 'Cloud percentage in composite = ' + str(cloudPercentage)
        
        return (composite, sensor)

    if (bestNumImages > 0):
        requestString = bestSensor['name']
        # We did not get as many images as we wanted, but we still got something with one sensor
        #refImageCollection = ee.ImageCollection(sensorStringNames[bestSensor]).filterDate(dateStart, dateEnd).filterBounds(bounds)
        refImageCollection = fetchSensorSeason(requestString, bounds, date, bigRange=True)
        composite = ee.Algorithms.Landsat.simpleComposite(refImageCollection, asFloat=True)
        return (composite, bestSensor)
        

    # If we made it here then we failed to find any images!
    
    raise Exception('Did not find enough landsat images in the requested region: ' + str(bounds.getInfo()))

    
    # TODO: A last check for cloud percentage?
    
    #refImageList       = refImageCollection.toList(100)
    #refImageListInfo   = refImageList.getInfo()
    ## Find the first image with a low cloud percentage
    #refImage = None
    #for i in range(len(refImageListInfo)):
    #    thisImage       = ee.Image(refImageList.get(i))
    #    #pprint.pprint(thisImage.getInfo())
    #    cloudPercentage = getCloudPercentage(thisImage, rectBounds)
    #    if cloudPercentage < MAX_CLOUD_PERCENTAGE:
    #        refImage = thisImage
    #        break
    #if not refImage:
    #    raise Exception('Could not find a reference image for location' + str(bounds.getInfo()))
    #return refImage


def fetchReferenceImage(longitude, latitude, metersPerPixel, date, outputPath):
    '''Fetch a reference Earth image for a given location and save it to disk'''
    # Try to get an image this size at the requested resolution.
    #DESIRED_IMAGE_SIZE = 2000
    #bufferSizeMeters = (DESIRED_IMAGE_SIZE / 2.0) * metersPerPixel

    # Cap the requested image resolution at the resolution of the input images.
    # - TODO: Vary this with the data source that is used.
    BEST_MPP = 25
    mppToUse = metersPerPixel
    if mppToUse < BEST_MPP:
        mppToUse = BEST_MPP

    MIN_IMAGE_SIZE  = 2000  # Don't fetch an image smaller than this
    MAX_IMAGE_SIZE  = 3000
    MAX_ERROR_RANGE = 100000 # 50km possible error handled by this amount
    
    # Default calculation is based on the max error range, but it is capped by pixel size
    bufferSizeMeters = MAX_ERROR_RANGE / 2.0
    estPixelSize     = MAX_ERROR_RANGE / mppToUse
    if estPixelSize < MIN_IMAGE_SIZE:
        bufferSizeMeters = (MIN_IMAGE_SIZE*mppToUse) / 2.0
    if estPixelSize > MAX_IMAGE_SIZE:
        print 'Warning: capping image size below ' + str(estPixelSize)
        bufferSizeMeters = (MAX_IMAGE_SIZE*mppToUse) / 2.0
        # TODO: Lower the image resolution in this case?

    
    # TODO: Check for a max size too!
    
    center = ee.Geometry.Point(longitude, latitude)
    circle = center.buffer(bufferSizeMeters)
    bounds = circle.bounds()

    # Also need to convert from MPP to Google's weird scale value
    metersPerDegree = miscUtilities.getMetersPerDegree(longitude, latitude)
    #print 'Requested MPP = ' + str(mppToUse)
    #print 'Meters per degree = ' + str(metersPerDegree)
    scale = miscUtilities.computeScale(metersPerDegree, mppToUse)
    
    #print 'Computed scale = ' + str(scale)

    #print date
    eeDate = ee.Date.parse('YYYY.MM.dd', date)
    #print 'Input date:'
    #print eeDate.format().getInfo()


    #try:
    #image = findClearImage(bounds, dateStart, dateEnd)
    (image, sensor) = findClearImage(bounds, eeDate)
    #except:
    #    print 'Failed to find reference image, trying again with larger boundary.'
    #    center = ee.Geometry.Point(longitude, latitude)
    #    circle = center.buffer(2*bufferSizeMeters)
    #    bounds = circle.bounds()
    #    image = findClearImage(bounds, dateStart, dateEnd)

    percentValid = image.mask().reduceRegion(ee.Reducer.mean(), bounds, scale*10).getInfo()['B1']
    print 'Percent valid = ' + str(percentValid)
    
    # Dynamically estimating the search range seems like more trouble than it is worth at the moment
    
    #print image.select(sensor['rgbBands']).reduceRegion(ee.Reducer.mean(), bounds, 400).getInfo()
    #minVals = image.select(sensor['rgbBands']).reduceRegion(ee.Reducer.min(), bounds, 400).getInfo()
    #maxVals = image.select(sensor['rgbBands']).reduceRegion(ee.Reducer.max(), bounds, 400).getInfo()
    #minVal  = min(minVals.itervalues())
    #maxVal  = max(maxVals.itervalues())
    #print minVals
    #print maxVals
    #print minVal
    #print maxVal
    
    # TODO: Tweak these by sensor or location!
    #landsatVisParams = {'bands': sensor['rgbBands'], 'min': 0, 'max': 128}
    landsatVisParams = {'bands': sensor['rgbBands'], 'min': 0, 'max': 0.4}
    #landsatVisParams = {'bands': sensor['rgbBands'], 'min': minVal, 'max': maxVal}
    #landsatVisParams = {'bands': sensor['rgbBands'], 'gain': '1.8, 1.5, 1.0'}

    # Download the image and return percent valid pixels and the resolution we used.
    # - Earth Engine sometimes fails so try a few times before giving up.
    
    NUM_RETRIES = 6
    SLEEP_TIME  = 10
    numTries = 0
    while True:
        if numTries < (NUM_RETRIES-1):
            try:
                miscUtilities.downloadEeImage(image, bounds, scale, outputPath, landsatVisParams)
                return (percentValid, mppToUse)
            except Exception: # After the first failures, wait and try again.
                print 'Caught exception downloading reference image, will wait and retry.'
                time.sleep(SLEEP_TIME)
            numTries += 1
        else: # Last pass, don't catch the exception.
            miscUtilities.downloadEeImage(image, bounds, scale, outputPath, landsatVisParams)
            return (percentValid, mppToUse)
    

#======================================================================================================
def main():

    # TODO: Command line interface

    #fetchReferenceImage(-109.276799, -27.125795, 'ref_image.tif')
    #fetchReferenceImage(-91.13, 33.00, 50, '2002.06.06', 'ref_image.tif')
    #fetchReferenceImage(-74.01283, 40.70338, 25, '2015.04.11', 'ref_image.tif')
    fetchReferenceImage(59.5, 46, 25, '2005.06.03', 'ref_image.tif')

    # TODO: Return code


if __name__ == "__main__":
    sys.exit(main())


