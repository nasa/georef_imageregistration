#__BEGIN_LICENSE__
# Copyright (c) 2015, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All rights reserved.
#
# The xGDS platform is licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#__END_LICENSE__

import os
import datetime
from io import BytesIO
from PIL import Image, ExifTags

"""
Exif utility Functions
referenced: https://gist.github.com/erans/983821
"""
def getExifData(filename):
    pilImageObj = Image.open(filename)
    exifData = {}
    try: 
        pilExif = pilImageObj._getexif()
        for tag,value in pilExif.items():
            decoded = ExifTags.TAGS.get(tag, tag)
            if tag in ExifTags.TAGS:
                if decoded == "GPSInfo":
                    gpsData = {}
                    for t in value:
                        gpsDecoded = ExifTags.GPSTAGS.get(t, t)
                        gpsData[gpsDecoded] = value[t]
                    exifData[decoded] = gpsData
                else: 
                    exifData[ExifTags.TAGS[tag]] = value
    except: 
        pass
    return exifData