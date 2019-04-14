The Image Registration module is intended to help automate the process of registering
images to the correct location on the ground.  It consists of two main components:
A - Fetching RGB satellite imagery of Earth to use for comparison.
B - Searching for the correct image registration parameters.


Step A is performed using Google's Earth Engine platform.
To install Earth Engine, follow these steps:
1 - Apply for a beta signup: https://docs.google.com/forms/d/17-LSoJQcBUGIwfplrBFLv0ULYhOahHJs2MwRF2XkrcM/viewform
  - Your application should be accepted quickly.
2 - Follow the steps for Python installation of Earth Engine: https://developers.google.com/earth-engine/python_install
  - If using Conda: conda install -c conda-forge earthengine-api
  - On older machines like the geocam servers probably need to compile your own python
    and make a new VirtualEnv environment from scratch following the Google instructions above.
    - Make sure to compile with sqlite3 support: http://binfcentral.blogspot.com/2012/06/compiling-python-with-sqlite3-support.html
  - Also need django, numpy, pillow, mysqlclient, and piexif
3 - Make sure the path in imageregistration/ImageFetcher/ee_authenticate.py is pointed to the credentials file created in step 2.


Step B is performed using a C++ program relying on OpenCV 3.0
To install, follow these steps:
1 - Build OpenCV 3.0 with the contributor modules package.
	(follow tutorial here: http://www.pyimagesearch.com/2015/06/22/install-opencv-3-0-and-python-2-7-on-ubuntu/)
  - Use the below cmake (assumes opencv_contrib is in /usr/local/lib/opencv_contrib)
	sudo cmake -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/local -D INSTALL_C_EXAMPLES=ON -D INSTALL_PYTHON_EXAMPLES=ON -D OPENCV_EXTRA_MODULES_PATH=/usr/local/lib/opencv_contrib/modules -D BUILD_EXAMPLES=ON ..
	And make sure to do "make install" as well as "make"!!!

  - Building OpenCV may not go smoothly, so we will have to update this file with more specific instructions as we go.
  - Sample install instructions here may be useful: http://www.pyimagesearch.com/2015/06/22/install-opencv-3-0-and-python-2-7-on-ubuntu/
  
2 - Build the ImageRegistration C++ code.
  - I used the following CMake line to do this:
    cmake ..  -DOPENCV_INSTALL_DIR=/home/smcmich1/programs/opencv_install/
    (for grace it's: cmake ..  -DOPENCV_INSTALL_DIR=/usr/local/)
  - Once this is built, everything should be ready to use.

==============================
Grace's notes:
Two step process A&B
A: center point + zoom level are used to fetch new images
B: Tries to align the images together and returns a transformation matrix (image to lat lon)

Also gives a three part confidence estimate (I should take the "high" and ignore the others)

Takes optional fields (referencedImagePath and referencedGeoTransform), which take the similar image and the transform. If you do this step, it will use the given image as a reference image and will skip the first step. 
This is good when there are sequence of images of the same area.

registerImage.py is the main function.

==============================

Offline processing TODO:

---- How to connect to georef on the stage machine -----

ssh -L 1234:127.0.0.1:443  geocam-stage.jsc.nasa.gov
In web browser: https://localhost:1234 (add exception if needed)


DB change requests:
    - Make issMRF a unique value in all tables where we use it.
    - Do something with the registration info in the overlays table.
        - Move simple numbers out of the extras field (size, rotation, focal length, center, nadir, bounds, etc).
        - Add a "writtenToFile" field.
        - By mirroring our existing registration table fields we can make searches easier using joins.

- Add UNIQUE flag if not already done.

- Disable GUI writing of gtiff files.  ---> Go ahead and start running the tools, ignoring this step!
- Verify offline tools output folder.
- Set up automatic offline tools.
    - How should they be running?
- Verify that offline tools are running.
- Test out the GUI, make sure everything works properly.

- Switch from prints to logging


Verify local is working:
iss027 - 005051, 50

No local:
MISSION	-->	TOTAL	NONE	LOW	HIGH	HIGH_FRACTION
ISS027	-->	1710	638 	499	573 	0.34
Local: 
MISSION	-->	TOTAL	NONE	LOW	HIGH	HIGH_FRACTION
ISS027	-->	1710	990	    15	705	    0.41



Examples for demo:
43-122588 = -22.2, -67.8  --> Dist = 4000m
44-903    = -15.5, 123.2  --> Dist = 3600m
44-868    = -21.7, 115.1  --> Dist = 5600m
44-1998   =  34.7,  10.8  --> Dist = 6600m



--> Final idealized design
    = Multiple asynchronous processes that all feed into the same SQL database.
        - Image detector = Add new images to the DB.
        - Metadata fetcher = Fetch ISS metadata.
        - Geosense fetcher = Add Geosense metadata.
        - Image matcher = Perform image alignment, generate GCP list.
        - Output generator = Use GCPs to generate final output image.
        --> The georef GUI will only edit SQL rows and flag the output generator.

-> Use a common info fetching function for frame, similar to what we have now.
    - Each tool can access just the info it needs.


- File describing the input data system?

- Handle overwrite options better, including re-fetch


- IP registration improvements:    
    - Small amounts of clouds cause all the match image IP to fall on them!
      What can we do to alleviate this effect?
    - Snow covered images have a similar effect.
    - Large cities and some other detailed regions fail because the IP are scattered around the entire image
      and we don't have enough density to find the small ISS image without a massive run time.
      - Could just use a huge amount of IP...
      - Try a first-pass registration at a lower resolution?
      - Try a second-pass registration based on an initial low-confidence registration?

    - Check image saturation and re-process if too much white?  
  
    - Performance is MUCH better on images which have similar lighting/color
      conditions.  Could possibly get significant improvements by improving
      our image preprocessing steps.
  

- Double check batch local matching
- Verify that we can process from each mission














