
#===============================================================================
# Project information


project( GeocamSpace_ImageRegistration )
cmake_minimum_required(VERSION 2.8)

# Add path for custom modules
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_CURRENT_SOURCE_DIR}" )



#===============================================================================
# Configuration options


set(OPENCV_INSTALL_DIR "" CACHE FILEPATH "Path to OpenCV installation directory")
if(NOT OPENCV_INSTALL_DIR)
  message(SEND_ERROR "You need to set OPENCV_INSTALL_DIR: ${OPENCV_INSTALL_DIR}")
endif()

message("OpenCV install path   = ${OPENCV_INSTALL_DIR}")


# --- Custom options ---
option(BUILD_SHARED_LIBS "Produce shared libraries." TRUE)

# --- Fixed options ---
set(CMAKE_CXX_FLAGS ${CMAKE_CXX_FLAGS})



#==================================================================================
# Find dependencies


#--- Find OpenCV

#find_package( OpenCV 3.0.0 REQUIRED )

# Manually force it to find the correct path!
set(OpenCV_FOUND True)
set(OpenCV_LIBS "${OPENCV_INSTALL_DIR}/lib/libopencv_core.so" 
                "${OPENCV_INSTALL_DIR}/lib/libopencv_highgui.so" 
                "${OPENCV_INSTALL_DIR}/lib/libopencv_stitching.so"
                "${OPENCV_INSTALL_DIR}/lib/libopencv_features2d.so"
                "${OPENCV_INSTALL_DIR}/lib/libopencv_imgproc.so"
                "${OPENCV_INSTALL_DIR}/lib/libopencv_imgcodecs.so"
                "${OPENCV_INSTALL_DIR}/lib/libopencv_calib3d.so"
                "${OPENCV_INSTALL_DIR}/lib/libopencv_xfeatures2d.so")
set(OpenCV_INCLUDE_DIR "${OPENCV_INSTALL_DIR}/include"
                       "${OPENCV_INSTALL_DIR}/include/opencv"
                       "${OPENCV_INSTALL_DIR}/include/opencv2")
set(OpenCV_INCLUDE_DIRS "${OpenCV_INCLUDE_DIR}")

message("Found OpenCV ${OpenCV_INCLUDE_DIRS}")



include_directories( ${OpenCV_INCLUDE_DIRS} )
include_directories(${CMAKE_CURRENT_SOURCE_DIR})



#==================================================================================
# Executables


add_executable( registerGeocamImage registerGeocamImage.cpp )
target_link_libraries( registerGeocamImage ${OpenCV_LIBS})

add_executable( computeImageRms computeImageRms.cpp )
target_link_libraries( computeImageRms ${OpenCV_LIBS})

add_executable( detectImageTag detectImageTag.cpp )
target_link_libraries( detectImageTag ${OpenCV_LIBS})




