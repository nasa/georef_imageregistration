
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
  - I used the following CMake line to do this:
    cmake ../CMakeLists.txt -DOPENCV_EXTRA_MODULES_PATH=/home/smcmich1/repo/opencv_contrib/modules -DBUILD_opencv_apps=OFF -DBUILD_opencv_gpu=OFF -DBUILD_opencv_video=OFF -DBUILD_opencv_ts=OFF -DBUILD_opencv_java=OFF -DWITH_FFMPEG=OFF -DWITH_DSHOW=OFF -DWITH_GSTREAMER=OFF -DBUILD_ANDROID_EXAMPLES=OFF -DBUILD_DOCS=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_WITH_DEBUG_INFO=OFF -DWITH_OPENGL=OFF
  - Building OpenCV may not go smoothly, so we will have to update this file with more specific instructions
    as we go.
  - Sample install instructions here may be useful: http://www.pyimagesearch.com/2015/06/22/install-opencv-3-0-and-python-2-7-on-ubuntu/
  
2 - Build the ImageRegistration C++ code.
  - I used the following CMake line to do this:
    cmake ..  -DOPENCV_INSTALL_DIR=/home/smcmich1/programs/opencv_install/
  - Once this is built, everything should be ready to use.

