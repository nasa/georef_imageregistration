//__BEGIN_LICENSE__
// Copyright (c) 2017, United States Government, as represented by the
// Administrator of the National Aeronautics and Space Administration.
// All rights reserved.
//
// The GeoRef platform is licensed under the Apache License, Version 2.0
// (the "License"); you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0.
//
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.
//__END_LICENSE__

#include <stdio.h>
#include <iostream>
#include <fstream>
#include <sstream>

#include "opencv2/core.hpp"
#include "opencv2/imgproc.hpp"
#include "opencv2/highgui.hpp"

/**
  Simple tool to determine if an ISS image has a white label tag at the bottom.
  
  The label is exactly 56 pixels in height and goes all the way across
  the image with the image name in black text.
  
*/

int main(int argc, char** argv )
{
  
  if (argc != 2)
  {
    printf("usage: detectImageTag <image path>\n");
    return -1;
  }
  std::string path = argv[1];
  
  const int LOAD_RGB = 1;
  
  // Load the input image
  cv::Mat image = cv::imread(path, LOAD_RGB);
  if (!image.data)
  {
    printf("Failed to load image\n");
    return -1;
  }

  // Set up constants
  const cv::Vec3b WHITE_VALUE(255, 255, 255);
  const int TAG_HEIGHT   = 55;
  const int imageHeight  = image.rows;
  const int tagTop       = imageHeight - TAG_HEIGHT - 1; // Row where the tag starts
  const int upperTop     = tagTop - TAG_HEIGHT; // One extra tag width above the tag
  
  const double pixelCount  = static_cast<double>(image.cols * (image.rows-tagTop-1));
  
  // Compute the pixel percentage in the tag region
  int whiteCount = 0;
  for (size_t r=tagTop; r<image.rows; ++r)
  {
    for (size_t c=0; c<image.cols; ++c)
    {
      if (image.at<cv::Vec3b>(r, c) == WHITE_VALUE)
        ++whiteCount;
    }
  }
  double bottomWhitePercentage = static_cast<double>(whiteCount) / pixelCount;
  
  // Compute the pixel percentage in an area above the tag region for comparison.
  whiteCount = 0;
  for (size_t r=upperTop; r<tagTop; ++r)
  {
    for (size_t c=0; c<image.cols; ++c)
    {
      if (image.at<cv::Vec3b>(r, c) == WHITE_VALUE)
        ++whiteCount;
    }
  }
  double upperWhitePercentage = static_cast<double>(whiteCount) / pixelCount;
  
  // DEBUG
  //std::cout << "Upper percentage = " << upperWhitePercentage << std::endl;
  //std::cout << "Bottom percentage = " << bottomWhitePercentage << std::endl;
  //std::cout << "pixel count = " << pixelCount << std::endl;
  //std::cout << "tagTop = " << tagTop << std::endl;
  //std::cout << "upperTop = " << upperTop<< std::endl;
  
  // See if the statistics suggest the label is there
  const double MIN_DISPARITY = 0.50;
  const double MIN_LEVEL     = 0.80; // Seems low, but we are asking for 
  if ((bottomWhitePercentage >= MIN_LEVEL) &&
      ((bottomWhitePercentage - upperWhitePercentage) > MIN_DISPARITY))
    std::cout << "LABEL\n";
  else
    std::cout << "NO_LABEL\n";
  
  return 0;
}








