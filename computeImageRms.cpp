

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








