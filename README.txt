The Image Registration module is intended to help automate the process of registering
images to the correct location on the ground.  It consists of two main components:
A - Fetching RGB satellite imagery of Earth to use for comparison.
B - Searching for the correct image registration parameters.


Step A is performed using Google's Earth Engine platform.
To install Earth Engine, follow these steps:
1 - Apply for a beta signup: https://docs.google.com/forms/d/17-LSoJQcBUGIwfplrBFLv0ULYhOahHJs2MwRF2XkrcM/viewform
  - Your application should be accepted quickly.
2 - Follow the steps for Python installation of Earth Engine: https://developers.google.com/earth-engine/python_install
3 - Make sure the path in imageregistration/ImageFetcher/ee_authenticate.py is pointed to the credentials file created in step 2.

Step B is performed using a C++ program relying on OpenCV 3.0
To install, follow these steps:
1 - Build OpenCV 3.0 with the contributor modules package.
	(follow tutorial here: http://www.pyimagesearch.com/2015/06/22/install-opencv-3-0-and-python-2-7-on-ubuntu/)
  - Use the below cmake (assumes opencv_contrib is in /usr/local/lib/opencv_contrib)
	sudo cmake -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/local -D INSTALL_C_EXAMPLES=ON -D INSTALL_PYTHON_EXAMPLES=ON -D OPENCV_EXTRA_MODULES_PATH=/usr/local/lib/opencv_contrib/modules -D BUILD_EXAMPLES=ON ..
	And make sure to do "make install" as well as "make"!!!
		  
  - Building OpenCV may not go smoothly, so we will have to update this file with more specific instructions
    as we go.
  - Sample install instructions here may be useful: http://www.pyimagesearch.com/2015/06/22/install-opencv-3-0-and-python-2-7-on-ubuntu/
  
2 - Build the ImageRegistration C++ code.
  - I used the following CMake line to do this:
    cmake ..  -DOPENCV_INSTALL_DIR=/home/smcmich1/programs/opencv_install/
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


- File describing the input data system?

- Integration with the GUI

- Import to DB
    - Partially done.

- Handle overwrite options better, including re-fetch

- Test new uncertainty description once ImageMagick is installed
    
    
- Small amounts of clouds cause all the match image IP to fall on them!
  What can we do to alleviate this effect?
- Snow covered images have a similar effect.
- Some LANDSAT processed images look like snow, but maybe we are preprocessing
  them incorrectly.
  
--> Check image saturation and re-process if too much white?  
  
- Performance is MUCH better on images which have similar lighting/color
  conditions.  Could possibly get significant improvements by improving
  our image preprocessing steps.
  
- Set up cron job.
    - How do new images come in?
        - When they get added to the database?
    - Where are they going to be located?
    - If there is not a consistent pattern, how do we find them?


- Double check batch local matching
- Verify that we can process one from each mission

- Eventually re-run everything to improve worse results we may have.
  - Landsat images also need to be re-fetched.


024881 local match?
071138















