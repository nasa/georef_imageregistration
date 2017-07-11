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
//#include "opencv2/features2d.hpp"
//#include "opencv2/calib3d.hpp"
#include "opencv2/imgproc.hpp"

//#include "opencv2/xfeatures2d.hpp"

#include <Common.h>

/// Convenience function for applying a transform to one point
cv::Point2f transformPoint(const cv::Point2f &pointIn, const cv::Mat &transform)
{
  // OpenCV makes us pach the function arguments in to vectors.
  std::vector<cv::Point2f> ptIn(1);
  std::vector<cv::Point2f> ptOut(1);
  ptIn[0] = pointIn;
  cv::perspectiveTransform(ptIn, ptOut, transform);
  return ptOut[0];
}


void writeOverlayImage(const cv::Mat &refImage, const cv::Mat &warpImage,
                       const cv::Mat &transform, const std::string &outputPath)
{
// DEBUG - Paste the match image on top of the reference image
  cv::Mat warpedImage, mergedImage;
  cv::Size warpSize(refImage.rows, refImage.cols);
  //typedef unsigned char PixelType;
  typedef cv::Vec3b PixelType;
  PixelType fillerPixel(0, 0, 0);
  cv::warpPerspective(warpImage, warpedImage, transform, warpSize);//, cv::WARP_INVERSE_MAP);
  mergedImage = refImage.clone();
  double opacity = 0.5;
  const int NUM_CHANNELS = 3;
  for (int r=0; r<refImage.rows; ++r)
  {
    for (int c=0; c<refImage.cols; ++c)
    {
      PixelType newPixel;
      PixelType refPixel  = refImage.at<PixelType>(r, c);
      PixelType warpPixel = warpedImage.at<PixelType>(r, c);
      
      if (warpPixel == fillerPixel)
        newPixel = refPixel;
      else
      {
        for (int i=0; i<NUM_CHANNELS; ++i)
          newPixel[i] = (warpPixel[i]*opacity + refPixel[i]*(1.0-opacity));
        //newPixel = (warpPixel*opacity + refPixel*(1.0-opacity));
      }
      mergedImage.at<PixelType>(r, c) = newPixel;
    }  
  }
  cv::imwrite(outputPath, mergedImage);
}

void intensityStretch(const cv::Mat &inputImage, cv::Mat &outputImage)
{
  const double LOW_PERCENTILE  = 0.02;
  const double HIGH_PERCENTILE = 0.98;


  // Not as good, but so much less code!
  //cv::equalizeHist(inputImage, outputImage);
  //return;
    
  // Compute a regular histogram
  cv::Mat hist;
  int numBins = 256;
  float range[] = { 0, 256 } ;
  const float* histRange = { range };
  bool uniform    = true;
  bool accumulate = false;
  calcHist(&inputImage, 1, 0, cv::Mat(), hist, 1, &numBins, &histRange,
           uniform, accumulate);

  // Compute a cumulative histogram
  float numPixels = inputImage.rows * inputImage.cols;
  std::vector<double> cumulativeHist(numBins);
  double sum = 0.0;
  int lowStretch = -1, highStretch = -1;
  for (int i=0; i<numBins; ++i)
  {
    
    sum += (double)(hist.at<float>(i) / numPixels);
    cumulativeHist[i] = sum;
    //printf("%d = %f --> %lf\n", i, hist.at<float>(i), sum);
    if ((lowStretch == -1) && (sum > LOW_PERCENTILE))
      lowStretch = i;
    if ((highStretch == -1) && (sum > HIGH_PERCENTILE))
      highStretch = i;
  }
  //printf("Computed stretch %d to %d\n", lowStretch, highStretch);
  
  double gain   = 256.0 / (highStretch - lowStretch);
  double offset = -lowStretch*gain;
  //printf("Computed vals %lf to %lf\n", gain, offset);
  inputImage.convertTo(outputImage, CV_8UC1, gain, offset);
}



int findPeak(const std::vector<size_t> &accumulator)
{
  const double KERNEL_SIZE = 5;
  const double SEPERATION  = 0.9;

  // Copy the input vector into a float matrix
  // - Need to manually pad the edges because the BORDER_WRAP option does not work!
  const size_t numBins    = accumulator.size();
  const size_t padAmount  = (KERNEL_SIZE-1) / 2;
  const size_t paddedSize = numBins + 2*padAmount;
  const size_t copyEndPos = numBins + padAmount;
  cv::Mat wrapper(paddedSize, 1, CV_32FC1);
  for (size_t i=0; i<numBins; ++i) // Copy the main vector
    wrapper.at<float>(i+padAmount) = static_cast<float>(accumulator[i]);
  for (size_t i=0; i<padAmount; ++i) // Fill in the padded values
  {
    wrapper.at<float>(padAmount-1-i) = static_cast<float>(accumulator[numBins-1-i]);
    wrapper.at<float>(copyEndPos +i) = static_cast<float>(accumulator[i]);
  }
    
  // Smooth the input values
  cv::Mat smoothed;
  cv::GaussianBlur(wrapper, smoothed, cv::Size(KERNEL_SIZE,KERNEL_SIZE), 0, 0, cv::BORDER_REPLICATE);
  
  // Find the two highest values in the vector
  size_t peak1=0,    peak2=0;
  float  peakVal1=0, peakVal2=0;
  for (size_t i=padAmount; i<copyEndPos; ++i) // Loop through non-padding
  {
    float smoothedVal = smoothed.at<float>(i);
    //printf("%f <> %f\n", wrapper.at<float>(i), smoothedVal);
    if (smoothedVal > peakVal1)
    {
      // Highest value
      peak2    = peak1;
      peakVal2 = peakVal1;
      peak1    = i;
      peakVal1 = smoothedVal;
    }
    else // Second highest value
      if (smoothedVal > peakVal2)
      {
        peak2    = i;
        peakVal2 = smoothedVal;
      }
  }

  // Only return a peak index if the first and second best values have adequate seperation  
  if (peakVal2 <= peakVal1*SEPERATION)
    return static_cast<int>(peak1 - padAmount); // Don't forget the padding!

  return -1; // Failed to find a good peak
}

/// Using detected features, attempt to compute a rotation to help align two images.
bool estimateImageRotation(const std::vector<cv::KeyPoint> &keypointsA,
                           const std::vector<cv::KeyPoint> &keypointsB,
                           const std::vector<cv::DMatch  > &matches,
                           double &rotationB)
{
  const double NUM_ANGLE_BINS = 180;
  const double PI = 3.14159265359;

  rotationB = 0;
  
  const size_t numPointsA = keypointsA.size();
  const size_t numPointsB = keypointsB.size();
  const size_t numMatches = matches.size();
  
  std::vector<size_t> accumulatorAngle(NUM_ANGLE_BINS);
  
  // TODO: Also accumulate scale
  
  // Loop through each pair of matches and accumulate angles
  const double radiansToBin = NUM_ANGLE_BINS / (2*PI);
  const double binToDegrees = 360/NUM_ANGLE_BINS;
  int bin;
  double dx, dy;
  for (size_t i=0; i<numMatches; ++i)
  {
    const cv::Point2f kpAi = keypointsA[matches[i].queryIdx].pt;
    const cv::Point2f kpBi = keypointsB[matches[i].trainIdx].pt;
    
    for (size_t j=0; j<numMatches; ++j)
    {
      if (i == j)
        continue;
    
      const cv::Point2f kpAj = keypointsA[matches[j].queryIdx].pt;
      const cv::Point2f kpBj = keypointsB[matches[j].trainIdx].pt;
      
      // TODO: Add some filtering as to which points are used
      
      // Compute angle from kpAi to kpAj
      dx = kpAj.x - kpAi.x;
      dy = kpAj.y - kpAi.y;
      double angleA = atan2(dy, dx);
      if (angleA < 0)
        angleA += 2*PI;
      //printf("A: Angle = %lf, bin = %d\n", angle, bin);
      
      // Compute angle from kpBi to kpBj
      dx    = kpBj.x - kpBi.x;
      dy    = kpBj.y - kpBi.y;
      double angleB = atan2(dy, dx);
      if (angleB < 0)
        angleB += 2*PI;
      //printf("B: Angle = %lf, bin = %d\n", angle, bin);
      
      double diffAngle = angleA - angleB;
      if (diffAngle < 0)
        diffAngle += 2*PI;
      bin = diffAngle * radiansToBin;
      
      ++accumulatorAngle[bin];
    }
  }
  
  int peak = findPeak(accumulatorAngle);
  
  // Quit if we did not get a solid rotation for the two images
  if (peak <0)
    return false;

  // Otherwise compute the correcting rotation angle
  rotationB = peak * binToDegrees;
  printf("Diff rotation = %lf\n", rotationB);
  
  return true;
}


/// Apply RootSift process to SIFT outputs
/// - This is supposed to improve the matching performance of SIFT features.
void applyRootSift(cv::Mat &descriptors)
{
  const size_t descriptorSize = descriptors.cols;

  // Loop through each descriptor
  for (size_t r=0; r<5/*descriptors.rows*/; ++r)
  {
    // Compute L1 norm of the vector 
    double norm1 = 0.0, norm2=0.0;
    for (size_t i=0; i<descriptorSize; ++i)
    {
      float thisVal = descriptors.at<float>(r, i) / 512.0f;
      //printf("%f, ", thisVal);
      norm1 += thisVal; // Abs not needed because all values are positive
      norm2 += thisVal*thisVal;
    }
    if (norm1 == 0) // Avoid divide by zero
      norm1 = 0.00000001;
    
    //printf("\nNorm1 = %f\n", norm1);
    //printf("Norm2 = %f\n", sqrt(norm2));
    
    // Divide each element by L1 norm and also compute sqrt
    norm2 = 0;
    for (size_t i=0; i<descriptorSize; ++i) 
    {
      float thisVal = descriptors.at<float>(r, i) / 512.0f;
      float newVal  = sqrt( thisVal / norm1); // No negative inputs!
      descriptors.at<float>(r, i) = newVal;// * 512.0f; // TODO: Should this be multiplied??
      norm2 += newVal*newVal;
      //printf("%f, ", newVal);
    }
    //printf("\nNorm2 = %f\n", sqrt(norm2));
    //printf("\n");
  } // End row loop
}

