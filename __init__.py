

# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

"""
georef_imageregistration
"""

__version_info__ = {
    'major': 0,
    'minor': 1,
    'micro': 0,
    'releaselevel': 'final',
    'serial': 1
}


def get_version():
    """
    Return the formatted version information
    """
    vers = ["%(major)i.%(minor)i" % __version_info__, ]

    if __version_info__['micro']:
        vers.append(".%(micro)i" % __version_info__)
    if __version_info__['releaselevel'] != 'final':
        vers.append('%(releaselevel)s%(serial)i' % __version_info__)
    return ''.join(vers)

__version__ = get_version()

#MultiSettings = None
#try:
#    from geocamUtil.MultiSettings import MultiSettings
#except ImportError:
#    import sys
#    print >> sys.stderr, "warning: geocamUtil not installed, can't load defaultSettings.py"

#if MultiSettings:
#    import django.conf
#    import defaultSettings
#    settings = MultiSettings(django.conf.settings, defaultSettings)
#else:
#    from django.conf import settings
