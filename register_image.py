

import os
import sys
import argparse
import subprocess
import traceback

import ImageFetcher.fetchReferenceImage


# TODO: Copy required functions from the test file once they are ready.

#======================================================================================
# Main interface function


def register_image(imagePath, centerLon, centerLat, focalLength, imageDate):
    '''Attempts to geo-register the provided image.
       Returns a transform from image coordinates to lonlat coordinates.
       Also returns an evaluation of how likely the registration is to be correct.'''

    # TODO: Do the work!

    transform = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    
    return (transform, confidence)







