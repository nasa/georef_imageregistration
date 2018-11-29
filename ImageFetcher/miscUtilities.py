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

import ee
import os
import math
import json
import threading
import time
import xml.etree.cElementTree as ET
import tempfile
import zipfile
import urllib2
try:
    from registration_common import TemporaryDirectory
except:
    import sys
    import os.path
    sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    from registration_common import TemporaryDirectory


def safe_get_info(ee_object, max_num_attempts=None):
    '''Keep trying to call getInfo() on an Earth Engine object until it succeeds.'''
    num_attempts = 0
    while True:
        try:
            return ee_object.getInfo()
        except Exception as e:
            print 'Earth Engine Error: %s. Waiting 10s and then retrying.' % (e)
            time.sleep(10)
            num_attempts += 1
        if max_num_attempts and (num_attempts >= max_num_attempts):
            raise Exception('safe_get_info failed to succeed after ' +str(num_attempts)+ ' attempts!')


class waitForEeResult(threading.Thread):
    '''Starts up a thread to run a pair of functions in series'''

    def __init__(self, function, finished_function = None):
        threading.Thread.__init__(self)
        self.function          = function # Main function -> Run this!
        self.finished_function = finished_function # Run this after the main function is finished
        self.setDaemon(True) # Don't hold up the program on this thread
        self.start()
    def run(self):
        self.finished_function(self.function())

def prettyPrintEE(eeObjectInfo):
    '''Convenient function for printing an EE object with tabbed formatting (pass in result of .getInfo())'''
    print(json.dumps(eeObjectInfo, sort_keys=True, indent=2))

def get_permanent_water_mask():
    '''Returns the global permanent water mask'''
    return ee.Image("MODIS/MOD44W/MOD44W_005_2000_02_24").select(['water_mask'], ['b1'])


def regionIsInUnitedStates(region):
        '''Returns true if the current region is inside the US.'''
        
        # Extract the geographic boundary of the US.
        nationList = ee.FeatureCollection('ft:1tdSwUL7MVpOauSgRzqVTOwdfy17KDbw-1d9omPw')
        nation     = ee.Feature(nationList.filter(ee.Filter.eq('Country', 'United States')).first())
        nationGeo  = ee.Geometry(nation.geometry())
        result     = nationGeo.contains(region, 10)

        return (str(result.getInfo()) == 'True')
    
    
    
def unComputeRectangle(eeRect):
    '''"Decomputes" an ee Rectangle object so more functions will work on it'''
    # This function is to work around some dumb EE behavior

    LON = 0 # Helper constants
    LAT = 1    
    rectCoords  = eeRect.getInfo()['coordinates']    # EE object -> dictionary -> string
    minLon      = rectCoords[0][0][LON]           # Exctract the numbers from the string
    minLat      = rectCoords[0][0][LAT]
    maxLon      = rectCoords[0][2][LON]
    maxLat      = rectCoords[0][2][LAT]
    bbox        = [minLon, minLat, maxLon, maxLat]   # Pack in order
    eeRectFixed = apply(ee.Geometry.Rectangle, bbox) # Convert back to EE rectangle object
    return eeRectFixed
    
    
    
def which(program):
    '''Tests if a given command line tool is available, replicating the "which" function'''
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def getMetersPerDegree(lon, lat):
    '''Returns the approximate meters per pixel at the current location/zoom'''

    # Formula to compute the length of a degree at this latitude
    m1 = 111132.92
    m2 = -559.82
    m3 = 1.175
    m4 = -0.0023
    p1 = 111412.84
    p2 = -93.5
    p3 = 0.118
    lat_len_meters  = m1 + (m2 * math.cos(2 * lat)) + (m3 * math.cos(4 * lat)) + (m4 * math.cos(6 * lat))
    long_len_meters = (p1 * math.cos(lat)) + (p2 * math.cos(3 * lat)) + (p3 * math.cos(5 * lat))

    # Just take the average of the vertical and horizontal size
    meters_per_degree = (lat_len_meters + long_len_meters) / 2
    return meters_per_degree
    
def computeScale(metersPerDegree, metersPerPixel):
    '''Compute the scale for the getDownloadUrl function'''

    pixels_per_degree = metersPerDegree / metersPerPixel
    #print 'pixelsPerDegree = ' + str(pixels_per_degree)

    mercator_range = 256.0
    # pixels_per_degree = (mercator_range / 360.0) * scale
    #scale = pixels_per_degree / (mercator_range / 360.0)
    
    scale = metersPerPixel
    
    return scale


def downloadEeImage(eeObject, bbox, scale, file_path, vis_params=None):
    '''Downloads an Earth Engine image object to the specified path'''

    with TemporaryDirectory() as workDir:

        # For now we require a GDAL installation in order to save images
        if not(which('gdalbuildvrt') and which('gdal_translate')):
            print 'ERROR: Must have GDAL installed in order to save images!'
            return False
    
        # Get a list of all the band names in the object
        band_names = []
        if vis_params and ('bands' in vis_params): # Band names were specified
            band_names = vis_params['bands']
            if ',' in band_names: # If needed, convert from string to list
                band_names = band_names.replace(' ', '').split(',')
        else: # Grab the first three band names
            if len(eeObject.getInfo()['bands']) > 3:
                print 'Warning: Limiting recorded file to first three band names!'
            for b in eeObject.getInfo()['bands']:
                band_names.append(b['id'])
                if len(band_names) == 3:
                    break
                
        if (len(band_names) != 3) and (len(band_names) != 1):
            raise Exception('Only 1 and 3 channel output images supported!')
        
        # Handle selected visualization parameters
        if vis_params and ('min' in vis_params) and ('max' in vis_params): # User specified scaling
            download_object = eeObject.visualize(band_names, min=vis_params['min'], max=vis_params['max'])
        elif vis_params and ('gain' in vis_params):
            # Extract the floating point gain values
            gain_text       = vis_params['gain'].replace(' ', '').split(',')
            gain_vals       = [float(x) for x in gain_text]
            download_object = eeObject.visualize(band_names, gain_vals)
        else:
            download_object = eeObject.visualize(band_names)
        
        # Handle input bounds as string or a rect object
        if isinstance(bbox, basestring) or isinstance(bbox, list): 
            eeRect = apply(ee.Geometry.Rectangle, bbox)
        else:
            eeRect = bbox
        eeGeom = unComputeRectangle(eeRect).toGeoJSONString()
        
        # Retrieve a download URL from Earth Engine
        dummy_name = 'EE_image'
        url = download_object.getDownloadUrl({'name' : dummy_name, 'scale': scale,
                                              'crs': 'EPSG:4326', 'region': eeGeom})
        #crsTransform = [scale, 0, eeRect.]
        #url = download_object.getDownloadUrl({'name' : dummy_name, 'crs_transform': crsTransform,
        #                                    'crs': 'EPSG:4326', 'region': eeGeom})
          
        
        # Generate a temporary path for the packed download file
        temp_prefix = 'CMT_temp_download_' + dummy_name
        zip_name    = temp_prefix + '.zip'
        zip_path    = os.path.join(workDir, zip_name) 
        
        # Download the packed file
        print 'Downloading image...'
        data = urllib2.urlopen(url)
        with open(zip_path, 'wb') as fp:
            while True:
                chunk = data.read(16 * 1024)
                if not chunk:
                    break
                fp.write(chunk)
        print 'Download complete!'
        
        # Each band get packed seperately in the zip file.
        z = zipfile.ZipFile(zip_path, 'r')
        
        ## All the transforms should be the same so we only read the first one.
        ## - The transform is the six numbers that make up the CRS matrix (pixel to lat/lon conversion)
        #transform_file = z.open(dummy_name + '.' + band_names[0] + '.tfw', 'r')
        #transform = [float(line) for line in transform_file]
        
        # Extract each of the band images into a temporary file
        # - Eventually the download function is supposed to pack everything in to one file!  https://groups.google.com/forum/#!topic/google-earth-engine-developers/PlgCvJz2Zko
        temp_band_files = []
        band_files_string = ''
        #print 'Extracting...'
        if len(band_names) == 1:
            color_names = ['vis-gray']
        else:
            color_names = ['vis-red', 'vis-green', 'vis-blue']
        for b in color_names:
            band_filename  = dummy_name + '.' + b + '.tif'
            extracted_path = os.path.join(workDir, band_filename)
            #print band_filename
            #print extracted_path
            z.extract(band_filename, workDir)
            temp_band_files.append(extracted_path)
            band_files_string += ' ' + extracted_path
            
        # Generate an intermediate vrt file
        vrt_path = os.path.join(workDir, temp_prefix + '.vrt')
        cmd = 'gdalbuildvrt -separate -resolution highest ' + vrt_path +' '+ band_files_string
        #print cmd
        os.system(cmd)
        if not os.path.exists(vrt_path):
            raise Exception('Failed to create VRT file!')
        
        # Convert to the output file
        cmd = 'gdal_translate -ot byte '+ vrt_path + ' ' +file_path
        #print cmd
        os.system(cmd)
        
        # Check for output file
        if not os.path.exists(file_path):
            raise Exception('Failed to create output image file!')
        
        print 'Finished saving ' + file_path
        return True
    
