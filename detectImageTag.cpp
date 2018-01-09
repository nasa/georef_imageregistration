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
  Simple tool to determine if an ISS image has a white label tag.
  
  The tags could be on any side of the image and have a black label
  on a white background.  This tool could get confused on some
  images but hopefully will work nearly every time.
*/


// Set up constants
const cv::Vec3b WHITE_VALUE(255, 255, 255);
const int MAX_TAG_HEIGHT = 180; // The narrow direction
const int MIN_TAG_HEIGHT = 30;

// Side codes
const int LEFT   = 0;
const int RIGHT  = 1;
const int TOP    = 2;
const int BOTTOM = 3;

const int NOT_FOUND = -1;

/// Search along a line from the outer edge of the image inwards
///  and record the index of the first drop from pure white to another color
int findLineDrop(const cv::Mat &image, int side, int place)
{
  const int height = image.rows;
  const int width  = image.cols;

  int start, stop, inc;
  switch(side)
  {
   case LEFT:  start = 0;         stop = MAX_TAG_HEIGHT;         inc =  1;  break;
   case RIGHT: start = width-1;   stop = width-MAX_TAG_HEIGHT;   inc = -1;  break;
   case TOP:   start = 0;         stop = MAX_TAG_HEIGHT;         inc =  1;  break;
   default:    start = height-1;  stop = height-MAX_TAG_HEIGHT;  inc = -1;  break;
  }

  if ((side == LEFT) || (side == RIGHT)) {
    if (image.at<cv::Vec3b>(place, start) != WHITE_VALUE)
      return NOT_FOUND; // No tag if first pixel is not white!
    start += inc;
    for (int i=start; i!=stop; i+=inc)
    {
      cv::Vec3b value = image.at<cv::Vec3b>(place, i);
      if (value != WHITE_VALUE)
      {
        //int mean = (value[0] + value[1] + value[2]) / 3.0;
        //int diff = 255 - mean;
        return i;
      }
    }
  }
  else // TOP and BOTTOM
  {
    if (image.at<cv::Vec3b>(start, place) != WHITE_VALUE)
      return NOT_FOUND; // No tag if first pixel is not white!
    start += inc;
    for (int i=start; i!=stop; i+=inc)
    {
      cv::Vec3b value = image.at<cv::Vec3b>(i, place);
      if (value != WHITE_VALUE)
      {
        //int mean = (value[0] + value[1] + value[2]) / 3.0;
        //int diff = 255 - mean;
        return i;
      }
    }
  }
  return NOT_FOUND;
}

// TODO: Need a simple histogram here!

// Returns the most likely tag side along with the location and the count
void get_best_count(const cv::Mat &image,
                    int &bestSide, int &bestCount, int &bestWidth)
{
  const int height = image.rows;
  const int width  = image.cols;
  
  const int lrSize = height + 1; // One extra value to store "NOT_FOUND" results
  const int tbSize = width  + 1;

  // Initialize all of the counts
  bestSide  = 0;
  bestCount = 0;
  bestWidth = 0;
    
  std::vector<int> leftCounts(lrSize), rightCounts (lrSize);
  std::vector<int> topCounts (tbSize), bottomCounts(tbSize);
  for (int r=0; r<lrSize; ++r) { leftCounts[r] = 0; rightCounts [r] = 0; }
  for (int c=0; c<tbSize; ++c) { topCounts [c] = 0; bottomCounts[c] = 0; }

  // Find all the index hits in each direction
  // - Add one to the results to NOT_FOUND(-1) goes into the first spot.
  int index;
  for (int r=0; r<height; ++r)
  {
    index = findLineDrop(image, LEFT,  r)+1;
    leftCounts [index] += 1;
    index = findLineDrop(image, RIGHT, r)+1;
    rightCounts[index] += 1;
  }
  for (int c=0; c<width; ++c)
  {
    index = findLineDrop(image, TOP,    c)+1;
    topCounts   [index] += 1;
    index = findLineDrop(image, BOTTOM, c)+1;
    bottomCounts[index] += 1;
  }
  
  // Find the highest hit total
  // - Skip the first entry which is for NOT_FOUND
  for (int r=1; r<lrSize; ++r) // Left and right sides
  {
    if (leftCounts[r] > bestCount) {
      bestCount = leftCounts[r];
      bestWidth = r;
      bestSide  = LEFT;
      std::cout << r << " L-> " << bestCount << std::endl;
    }
    if (rightCounts[r] > bestCount) {
      bestCount = rightCounts[r];
      bestWidth = r;
      bestSide  = RIGHT;
      std::cout << r << " R-> " << bestCount << std::endl;
    }
  }

  for (int c=1; c<tbSize; ++c) // Top and bottom sides
  {
    if (topCounts[c] > bestCount) {
      bestCount = topCounts[c];
      bestWidth = c;
      bestSide  = TOP;
      std::cout << c << " T-> " << bestCount << std::endl;
    }
    if (bottomCounts[c] > bestCount) {
      bestCount = bottomCounts[c];
      bestWidth = c;
      bestSide  = BOTTOM;
      std::cout << c << " B-> " << bestCount << std::endl;
    }  
  }
  return;
}


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
  
  // Require that at least 60 of pixels match the tag location.
  const double MIN_COUNT_PERCENT = 0.7;
  
  // The target number is larger for the longer edges.
  int lowThreshold  = floor(MIN_COUNT_PERCENT * static_cast<double>(image.rows));
  int highThreshold = floor(MIN_COUNT_PERCENT * static_cast<double>(image.cols));
  
  // Call function to find the side most likely to have a tag
  int bestSide, bestCount, bestWidth;
  get_best_count(image, bestSide, bestCount, bestWidth);
  
  // Debug info
  std::string side;
  int threshold;
  switch (bestSide)
  {
    case LEFT:  side = "LEFT";    threshold = lowThreshold;   break;
    case RIGHT: side = "RIGHT";   threshold = lowThreshold;   break;
    case TOP:   side = "TOP";     threshold = highThreshold;  break;
    default:    side = "BOTTOM";  threshold = highThreshold;  break;
  };
  std::cout << "best side = " << side << std::endl;
  std::cout << "best count = " << bestCount << std::endl;
  std::cout << "best width = " << bestWidth << std::endl;
  

  if (bestCount >= threshold)
    std::cout << "LABEL " << side << " " << bestWidth << std::endl;
  else
    std::cout << "NO_LABEL\n";
  
  return 0;
}








