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
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/highgui.hpp>

typedef unsigned short MASK_DATA_TYPE;
typedef unsigned char  BINARY_MASK_DATA_TYPE;

//const unsigned char MASK_MAX = 255; // UINT8
const unsigned short MASK_MAX = 1023; // UINT16 - This is equal to the grassfire distance!


/*
/// Constrain an OpenCV ROI to lie within an image
/// - Returns false if there is no overlap
bool constrainCvRoi(cv::Rect &roi, const int imageWidth, const int imageHeight)
{
  //std::cout << "roi    = " << roi << std::endl;
  //std::cout << "width  = " << imageWidth << std::endl;
  //std::cout << "height = " << imageHeight << std::endl;
  cv::Rect imageRoi(0, 0, imageWidth, imageHeight);
  roi &= imageRoi;
  return (roi.area() > 0);
}

/// As constrainCvRoi, but also resizes roi2 to match the changes to roi1.
bool constrainMatchedCvRois(cv::Rect &roi, const int imageWidth, const int imageHeight,
                            cv::Rect &roi2)
{
  // Constrain the first ROI
  cv::Rect roiIn = roi;
  if (!constrainCvRoi(roi, imageWidth, imageHeight))
    return false;
  // Detect the changes
  cv::Point tlDiff = roi.tl()   - roiIn.tl(); // TL corner can only have increased
  //cv::Point brDiff = roiIn.br() - roi.br();
  
  //std::cout << "tlDiff  = " << tlDiff << std::endl;
  
  roi2 = cv::Rect(roi2.tl() + tlDiff, roi.size()); // Use the new size
  //std::cout << "roi2  = " << roi2<< std::endl;
  return true;
}
*/

std::string itoa(const int i)
{
  std::stringstream s;
  s << i;
  return s.str();
}
/*
void affineTransform(const cv::Mat &transform, float xIn, float yIn, float &xOut, float &yOut)
{
  xOut = xIn*transform.at<float>(0,0) + yIn*transform.at<float>(0,1) + transform.at<float>(0,2);
  yOut = xIn*transform.at<float>(1,0) + yIn*transform.at<float>(1,1) + transform.at<float>(1,2);
}
*/
/// Single channel image interpolation
template <typename T>
T interpPixel(const cv::Mat& img, const cv::Mat& mask, float xF, float yF, bool &gotValue)
{
  const int BORDER_SIZE = 1; // Stay away from border artifacts

  gotValue = false;
  int x = (int)xF;
  int y = (int)yF;

  // Get the bordering pixel coordinates, replacing out of bounds with zero.
  int minX = BORDER_SIZE; // Max legal pixel boundaries with the specified border.
  int minY = BORDER_SIZE;
  int maxX = img.cols-BORDER_SIZE;
  int maxY = img.rows-BORDER_SIZE;
  int x0 = x;   // The coordinates of the four bordering pixels
  int x1 = x+1;
  int y0 = y;
  int y1 = y+1;
  if ((x0 < minX) || (x0 >= maxX)) return 0; // Quit if we exceed any of the borders.
  if ((x1 < minX) || (x1 >= maxX)) return 0;
  if ((y0 < minY) || (y0 >= maxY)) return 0;
  if ((y1 < minY) || (y1 >= maxY)) return 0;
  
  // - Don't interpolate if any mask inputs are zero, this might indicate 
  //    that we are at a projection border.
  unsigned char i00 = mask.at<MASK_DATA_TYPE>(y0, x0);
  unsigned char i01 = mask.at<MASK_DATA_TYPE>(y0, x1);
  unsigned char i10 = mask.at<MASK_DATA_TYPE>(y1, x0);
  unsigned char i11 = mask.at<MASK_DATA_TYPE>(y1, x1);
  if ((i00 == 0) || (i01 == 0) || (i10 == 0) || (i11 == 0))
    return 0;


  float a = xF - (float)x;
  float c = yF - (float)y;
  
  float v00 = static_cast<float>(img.at<T>(y0, x0));
  float v01 = static_cast<float>(img.at<T>(y0, x1));
  float v10 = static_cast<float>(img.at<T>(y1, x0));
  float v11 = static_cast<float>(img.at<T>(y1, x1));

  T val = static_cast<T>( v00*(1-a)*(1-c)  + v10*a*(1-c) + v01*(1-a)*c + v11*a*c );

  gotValue = true;
  return val;
}

/// As interpPixel but specialized for RGB
cv::Vec3b interpPixelRgb(const cv::Mat& img, float xF, float yF, bool &gotValue)
{
  const size_t NUM_RGB_CHANNELS = 3;
  const int    BORDER_SIZE      = 1; // Stay away from border artifacts

  gotValue = false;
  int x = (int)xF;
  int y = (int)yF;

  // Get the bordering pixel coordinates, replacing out of bounds with zero.
  int minX = BORDER_SIZE;
  int minY = BORDER_SIZE;
  int maxX = img.cols-BORDER_SIZE;
  int maxY = img.rows-BORDER_SIZE;
  int x0 = x;
  int x1 = x+1;
  int y0 = y;
  int y1 = y+1;
  if ((x0 < minX) || (x0 >= maxX)) return 0;
  if ((x1 < minX) || (x1 >= maxX)) return 0;
  if ((y0 < minY) || (y0 >= maxY)) return 0;
  if ((y1 < minY) || (y1 >= maxY)) return 0;

  // Now interpolate each pixel channel

  float a = xF - (float)x;
  float c = yF - (float)y;
  
  cv::Vec3b outputPixel;
  for (size_t i=0; i<NUM_RGB_CHANNELS; ++i)
  {
    float v00 = static_cast<float>(img.at<cv::Vec3b>(y0, x0)[i]);
    float v01 = static_cast<float>(img.at<cv::Vec3b>(y0, x1)[i]);
    float v10 = static_cast<float>(img.at<cv::Vec3b>(y1, x0)[i]);
    float v11 = static_cast<float>(img.at<cv::Vec3b>(y1, x1)[i]);

    outputPixel[i] = static_cast<unsigned char>( v00*(1-a)*(1-c)  + v10*a*(1-c) + v01*(1-a)*c + v11*a*c );

  }

  gotValue = true;
  return outputPixel;
}

/// As interpPixelRgb but with pixels near the edges handled by mirroring
template <typename MASK_T>
cv::Vec3b interpPixelMirrorRgb(const cv::Mat& img,  const cv::Mat& mask,
                               float xF, float yF, bool &gotValue)
{
  const size_t NUM_RGB_CHANNELS = 3;

  // Get the bounding pixel coordinates
  gotValue = false;
  int x = (int)xF;
  int y = (int)yF;
  int x0 = x;
  int x1 = x+1;
  int y0 = y;
  int y1 = y+1;
  /*
  // Mirror a border of one by adjusting the bounding coordinates
  if (x0 == -1)       x0 = 0;
  if (y0 == -1)       y0 = 0;
  if (x1 == img.cols) x1 = img.cols-1;
  if (y1 == img.rows) y1 = img.rows-1;
  */
  // Pixels past the border are still rejected
  if ((x0 < 0) || (x0 >= img.cols)) return 0;
  if ((x1 < 0) || (x1 >= img.cols)) return 0;
  if ((y0 < 0) || (y0 >= img.rows)) return 0;
  if ((y1 < 0) || (y1 >= img.rows)) return 0;

  // Check the mask
  // - Don't interpolate if any mask inputs are zero, this might indicate 
  //    that we are at a projection border.
  unsigned char i00 = mask.at<MASK_T>(y0, x0);
  unsigned char i01 = mask.at<MASK_T>(y0, x1);
  unsigned char i10 = mask.at<MASK_T>(y1, x0);
  unsigned char i11 = mask.at<MASK_T>(y1, x1);
  if ((i00 == 0) || (i01 == 0) || (i10 == 0) || (i11 == 0))
    return 0;
  
  // Now interpolate each pixel channel

  float a = xF - (float)x;
  float c = yF - (float)y;
  
  cv::Vec3b outputPixel;
  for (size_t i=0; i<NUM_RGB_CHANNELS; ++i)
  {
    float v00 = static_cast<float>(img.at<cv::Vec3b>(y0, x0)[i]);
    float v01 = static_cast<float>(img.at<cv::Vec3b>(y0, x1)[i]);
    float v10 = static_cast<float>(img.at<cv::Vec3b>(y1, x0)[i]);
    float v11 = static_cast<float>(img.at<cv::Vec3b>(y1, x1)[i]);  
    outputPixel[i] = static_cast<unsigned char>( v00*(1.0f-a)*(1.0f-c)  + v10*a*(1.0f-c) + v01*(1.0f-a)*c + v11*a*c );
  }
  
  gotValue = true;
  return outputPixel;
}

/*
/// Computes the ROI of one image in another given the transform with bounds checking.
cv::Rect_<int> getboundsInOtherImage(const cv::Mat &imageA, const cv::Mat &imageB, const cv::Mat &transB_to_A)
{
  // Transform the four corners of imageB
  float x[4], y[4];
  affineTransform(transB_to_A, 0,             0,             x[0], y[0]);
  affineTransform(transB_to_A, imageB.cols-1, 0,             x[1], y[1]);
  affineTransform(transB_to_A, imageB.cols-1, imageB.rows-1, x[2], y[2]);
  affineTransform(transB_to_A, 0,             imageB.rows-1, x[3], y[3]);
  
  // Get the bounding box of the transformed points
  float xMin = x[0];
  float xMax = x[0];
  float yMin = y[0];
  float yMax = y[0];
  for (size_t i=0; i<4; ++i)
  {
    if (x[i] < xMin) xMin = x[i];
    if (x[i] > xMax) xMax = x[i];
    if (y[i] < yMin) yMin = y[i];
    if (y[i] > yMax) yMax = y[i];
  }
  
  if (xMin < 0) xMin = 0;
  if (yMin < 0) yMin = 0;
  if (xMax > imageA.cols-1) xMax = imageA.cols-1;
  if (yMax > imageA.rows-1) yMax = imageA.rows-1;

  // Return the results expanded to the nearest integer
  cv::Rect_<int> boundsInA(static_cast<int>(floor(xMin)), 
                           static_cast<int>(floor(yMin)),
                           static_cast<int>(ceil(xMax-xMin)), 
                           static_cast<int>(ceil(yMax-yMin)));
  return boundsInA;
}

/// Write a small matrix to a text file
bool writeTransform(const std::string &outputPath, const cv::Mat &transform)
{
  std::ofstream file(outputPath.c_str());
  file << transform.rows << ", " << transform.cols << std::endl;
  for (size_t r=0; r<transform.rows; ++r)
  {
    for (size_t c=0; c<transform.cols-1; ++c)
    {
      file << transform.at<double>(r,c) << ", ";
    }
    file << transform.at<double>(r,transform.cols-1) << std::endl;
  }
  file.close();
  
  return (!file.fail());
}

// Read a small matrix from a text file
bool readTransform(const std::string &inputPath, cv::Mat &transform)
{
  //printf("Reading transform: %s\n", inputPath.c_str());
  std::ifstream file(inputPath.c_str());
  if (!file.fail())
  {
    char   comma;
    size_t numRows, numCols;
    file >> numRows >> comma >> numCols;
    transform.create(numRows, numCols, CV_32FC1);
    for (size_t r=0; r<transform.rows; ++r)
    {
      for (size_t c=0; c<transform.cols-1; ++c)
      {
        file >> transform.at<float>(r,c) >> comma;
      }
      file >> transform.at<float>(r,transform.cols-1);
    }
    file.close();
  }
  if (file.fail())
  {
    std::cout << "Failed to load transform file: " << inputPath << std::endl;
    return false;
  }
  return true;
}
*/
/// Try to load the image and then make sure we got valid data.
/// - The type must by 0 (gray) or 1 (RGB)
bool readOpenCvImage(const std::string &imagePath, cv::Mat &image, const int imageType)
{
  //printf("Reading image file: %s\n", imagePath.c_str());
  image = cv::imread(imagePath, imageType);
  if (!image.data)
  {
    printf("Failed to load image %s!\n", imagePath.c_str());
    return false;
  }
  return true;
}



/*
/// Converts a single RGB pixel to YCbCr
cv::Vec3b rgb2ycbcr(cv::Vec3b rgb)
{
  // Convert
  double temp[3];
  temp[0] =         0.299   *rgb[0] + 0.587   *rgb[1] + 0.114   *rgb[2];
  temp[1] = 128.0 - 0.168736*rgb[0] - 0.331264*rgb[1] + 0.5     *rgb[2];
  temp[2] = 128.0 + 0.5     *rgb[0] - 0.418688*rgb[1] - 0.081312*rgb[2];
  // Copy and constrain
  cv::Vec3b ycbcr;
  for (int i=0; i<3; ++i)
  {
    ycbcr[i] = temp[i];
    if (temp[i] < 0.0  ) ycbcr[i] = 0;
    if (temp[i] > 255.0) ycbcr[i] = 255;
  }
  return ycbcr;
}
    
/// Converts a single YCbCr pixel to RGB
cv::Vec3b ycbcr2rgb(cv::Vec3b ycbcr)
{
  double temp[3];
  temp[0] = ycbcr[0]                                + 1.402   * (ycbcr[2] - 128.0);
  temp[1] = ycbcr[0] - 0.34414 * (ycbcr[1] - 128.0) - 0.71414 * (ycbcr[2] - 128.0);
  temp[2] = ycbcr[0] + 1.772   * (ycbcr[1] - 128.0);
  
  // Copy and constrain
  cv::Vec3b rgb;
  for (int i=0; i<3; ++i)
  {
    rgb[i] = temp[i];
    if (temp[i] < 0.0  ) rgb[i] = 0;
    if (temp[i] > 255.0) rgb[i] = 255;
  }
  return rgb;
}
*/






