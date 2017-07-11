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
  Simple tool to compute the RMS value of a float32 image.
*/

int main(int argc, char** argv )
{
  
  if (argc != 2)
  {
    printf("usage: computeImageRms <image path>\n");
    return -1;
  }
  std::string path = argv[1];
  
  const int LOAD_UNCHANGED = -1;
  
  // Load the input image
  cv::Mat image = cv::imread(path, LOAD_UNCHANGED);
  if (!image.data)
  {
    printf("Failed to load image\n");
    return -1;
  }

  double numPixels = static_cast<double>(image.rows*image.cols);
  double sum       = 0.0;
  for (size_t r=0; r<image.rows; ++r)
  {
    for (size_t c=0; c<image.cols; ++c)
    {
      double val = static_cast<double>(image.at<float>(r, c));
      sum += (val*val)/numPixels;
    }
  }
  double rms = sqrt(sum);

  std::cout << "RMS: " << rms << std::endl;
  
  return 0;
}








