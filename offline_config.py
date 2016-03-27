

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



# ==================================================
# Output paths

# The location of the results database
OUTPUT_DATABASE_PATH = '/home/smcmich1/log_db_test.sqlt'

# Top level folder where we write our output files
OUTPUT_IMAGE_FOLDER  = '/home/smcmich1/georef_images'


# ==================================================
# Input image filters

# Maximum tilt angle of images that we will try to process
MAX_TILT_ANGLE = 50

# Maximum cloud percentage that we will try to process.
# - For convenience, convert it to an integer here.
MAX_CLOUD_PERCENTAGE     = 0.20
MAX_CLOUD_PERCENTAGE_INT = int(MAX_CLOUD_PERCENTAGE*100)



# ==================================================
# Processing settings