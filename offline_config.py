

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


GEOREF_DB_HOST="localhost"
GEOREF_DB_USER="root"
GEOREF_DB_PASS="vagrant"
GEOREF_DB_NAME="georef"

# ==================================================
# Output paths

# The location of the results database
OUTPUT_DATABASE_PATH = '/home/smcmich1/log_db_test.sqlt'

# Top level folder where we write our output files
OUTPUT_IMAGE_FOLDER  = '/home/smcmich1/georef_images'


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

