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

'''
Main config file that stores settings needed by the offline
registration tools.
'''


# ==================================================
# Input paths

# Path to the input database
DB_PATH = '/home/smcmich1/db.sqlt'

# Path to the DCRAW tool used to convert from raw images to tiffs
DCRAW_PATH = '/home/smcmich1/repo/dcraw/dcraw'

# Top level folder containing the input RAW images
RAW_IMAGE_FOLDER = '/media/network/ImagesDrop/RawESC'

# We can either process the RAW file or an already converted JPEG file
USE_RAW = False

GEOREF_DB_HOST = "localhost"
GEOREF_DB_USER = "root"
GEOREF_DB_PASS = "vagrant"
GEOREF_DB_NAME = "georef"

MS_DB_USER   = "georef"
MS_DB_PASS   = "TODO"
MS_DB_SERVER = "TODO"
MS_DB_NAME   = "Photos"



# ==================================================
# Output paths

# The location of the results database
OUTPUT_DATABASE_PATH = '/home/smcmich1/log_db_test.sqlt'

# Top level folder where we write our output files
OUTPUT_IMAGE_FOLDER  = '/media/network/GeoRef/auto/'
#OUTPUT_IMAGE_FOLDER = '/tmp/sourceFiles'

OUTPUT_ZIP_FOLDER = '/media/network/GeoRef/export'

# ==================================================
# Input image filters

# Maximum tilt angle of images that we will try to process
MAX_TILT_ANGLE = 70

# Maximum cloud percentage that we will try to process.
# - For convenience, convert it to an integer here.
MAX_CLOUD_PERCENTAGE     = 0.34
MAX_CLOUD_PERCENTAGE_INT = int(MAX_CLOUD_PERCENTAGE*100)



# ==================================================
# ==================================================
# Processing settings


# ==================================================
# "Local" alignment settings

# Only try to match a certain number of times
LOCAL_ALIGNMENT_MAX_ATTEMPTS = 4

# Limit to the frame count that we can match to in each direction
LOCAL_ALIGNMENT_MAX_FRAME_RANGE = 20

# How far the center point can differ in lat or lon
# - TODO: This should differ by the resolution
LOCAL_ALIGNMENT_MAX_DIST = 0.5

