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
#include "opencv2/features2d.hpp"
#include "opencv2/calib3d.hpp"
#include "opencv2/imgproc.hpp"

#include "opencv2/xfeatures2d.hpp"

//#include <Common.h>
#include "processingFunctions.h"

enum DetectorType {DETECTOR_TYPE_BRISK = 0, 
                   DETECTOR_TYPE_ORB   = 1,
                   DETECTOR_TYPE_SIFT  = 2,
                   DETECTOR_TYPE_AKAZE = 3};

enum ModeType {MODE_FAST     = 0,
               MODE_ACCURATE = 1};


/// Write the transform parameters and the confidence to a file on disk
bool writeOutput(const std::string &outputPath, const cv::Mat &transform,
                 const std::vector<cv::Point2f> &refInlierCoords, 
                 const std::vector<cv::Point2f> &matchInlierCoords,
                 std::string confidenceString, bool print=false)
{
  // Error checks
  const size_t numInliers = refInlierCoords.size();
  if (matchInlierCoords.size() != numInliers)
  {
    printf("Logic error - number of inliers do not match!");
    return false;
  }

  // Open the file and write out a confidence measure
  std::ofstream file(outputPath.c_str());
  file << confidenceString << std::endl;
  
  // Write out the computed transform between the two images
  file << "TRANSFORM:" << std::endl;
  for (size_t r=0; r<transform.rows; ++r)
  {
    for (size_t c=0; c<transform.cols-1; ++c)
    {
      file << transform.at<double>(r,c) << ", ";
      if (print)
        printf("%lf    ", transform.at<double>(r,c));
    }
    file << transform.at<double>(r,transform.cols-1) << std::endl;
    if (print)
        printf("%lf\n", transform.at<double>(r,transform.cols-1));
  }
  
  // Write out the list of interest point pairs.
  file << "INLIERS:" << std::endl;
  for (size_t i=0; i<numInliers; ++i)
  {
    file << refInlierCoords  [i].x << ", " << refInlierCoords  [i].y << ", " 
         << matchInlierCoords[i].x << ", " << matchInlierCoords[i].y << std::endl;
  }
  
  
  
  file.close();
  
  return (!file.fail());
}

void preprocess(const cv::Mat &inputImage, cv::Mat &outputImage)
{
  // No preprocessing, just operate on the grayscale images.
  //outputImage = inputImage;
  
  // TODO: Utilize color information
  // Convert from color to grayscale
  cv::Mat grayImage;
  cvtColor(inputImage, grayImage, CV_BGR2GRAY);
  
  // Intensity Stretching
  cv::Mat normImage;
  intensityStretch(grayImage, normImage);
  
  
  outputImage = normImage;
  return; // TODO: Experiment with other preprocessing
  
  
  int kernelSize = 9;
  cv::Mat temp;
  
  
  
  // Simple Edge detection
  const int scale = 1;
  const int delta = 0;
  cv::Laplacian( normImage, temp, CV_32S, kernelSize, scale, delta, cv::BORDER_DEFAULT );
  cv::convertScaleAbs( temp, outputImage, 0.001);
  return;
  
  
  // Canny edge detection
  cv::Mat small;
  double kScaleFactor = 1.0/1.0;
  cv::resize(inputImage, small, cvSize(0, 0), kScaleFactor, kScaleFactor);
  
  const int cannyLow  = 200;
  const int cannyHigh = 300;
  cv::blur(small, temp, cv::Size(kernelSize, kernelSize));
  cv::Canny(temp, outputImage, cannyLow, cannyHigh, kernelSize);
  
}


/// Compute an affine transform for N points, no outlier handling.
cv::Mat getAffineTransformOverdetermined( const std::vector<cv::Point2f> &src,
                                          const std::vector<cv::Point2f> &dst)
{
  // TODO: Replace this C style code
  size_t n = src.size();
  cv::Mat M(2, 3, CV_64F), X(6, 1, CV_64F, M.data); // output
  double* a = (double*)malloc(12*n*sizeof(double));
  double* b = (double*)malloc(2*n*sizeof(double));
  cv::Mat A(2*n, 6, CV_64F, a), B(2*n, 1, CV_64F, b); // input

  for( int i = 0; i < n; i++ )
  {
    int j = i*12;   // 2 equations (in x, y) with 6 members: skip 12 elements
    int k = i*12+6; // second equation: skip extra 6 elements
    a[j] = a[k+3] = src[i].x;
    a[j+1] = a[k+4] = src[i].y;
    a[j+2] = a[k+5] = 1;
    a[j+3] = a[j+4] = a[j+5] = 0;
    a[k] = a[k+1] = a[k+2] = 0;
    b[i*2] = dst[i].x;
    b[i*2+1] = dst[i].y;
  }
  cv::solve( A, B, X, cv::DECOMP_SVD );
  delete a;
  delete b;
  return M;
}


/// See how well all the final points fit into an affine transform
void affineInlierPrune(std::vector<cv::Point2f> &ptsA, std::vector<cv::Point2f> &ptsB)
{
  // Eliminate at most this many points
  const size_t MAX_PRUNING = 10;
    
  size_t numPoints = ptsA.size();
  size_t numPointsRemoved = 0;
  double currentError = 0;
  while (numPointsRemoved < MAX_PRUNING)
  {
    // Compute an affine transform using all the points
    //cv::Mat affineTransform = cv::getAffineTransform(ptsA, ptsB);
    cv::Mat affineTransform = getAffineTransformOverdetermined(ptsA, ptsB);
    
    // Apply the transform to the points
    std::vector<cv::Point2f> warpedPtsA;
    cv::transform(ptsA, warpedPtsA, affineTransform);
    
    // Compute the per-point error
    std::vector<double> error(warpedPtsA.size());
    double maxError = 0;
    size_t maxErrorIndex = 0;
    for (size_t i=0; i<warpedPtsA.size(); ++i)
    {
      error[i] = sqrt( pow((ptsB[i].x - warpedPtsA[i].x), 2.0) +
                       pow((ptsB[i].y - warpedPtsA[i].y), 2.0) );
      if (error[i] > maxError)
      {
        maxError      = error[i];
        maxErrorIndex = i;
      }
    }
    printf("Computed max error %lf at index %lu\n", maxError, maxErrorIndex);
    std::cout << ptsB[maxErrorIndex] << std::endl;
    break; // TODO: Do something with this information!
  }
}


/// Returns the number of inliers
/// - Computed transform is from MATCH (second) to REF (first).
int computeImageTransform(const cv::Mat &refImageIn, const cv::Mat &matchImageIn,
                          cv::Mat &transform,
                          std::vector<cv::Point2f> &refInlierCoords, 
                          std::vector<cv::Point2f> &matchInlierCoords,
                          const std::string debugFolder,
                          const int          kernelSize  =5, 
                          const DetectorType detectorType=DETECTOR_TYPE_ORB,
                          bool debug=true)
{
  
  // Preprocess the images to improve feature detection
  cv::Mat refImage, matchImage;
  preprocess(refImageIn,   refImage);
  preprocess(matchImageIn, matchImage);
  
  if (debug)
  {
    printf("Writing preprocessed images...\n");
    cv::imwrite( debugFolder+"basemapProcessed.jpeg", refImage );
    cv::imwrite( debugFolder+"geocamProcessed.jpeg",  matchImage );
  }
    
  std::vector<cv::KeyPoint> keypointsA, keypointsB;
  cv::Mat descriptorsA, descriptorsB;  

  const int numPixelsRef   = refImage.rows   * refImage.cols;
  const int numPixelsMatch = matchImage.rows * matchImage.cols;

  // Adaptively set the number of features
  int nfeaturesRef   = numPixelsRef   / 850;
  int nfeaturesMatch = numPixelsMatch / 850;
  const int MIN_FEATURES =  3000;
  const int MAX_FEATURES = 15000;
  if (nfeaturesRef   < MIN_FEATURES) nfeaturesRef   = MIN_FEATURES;
  if (nfeaturesMatch < MIN_FEATURES) nfeaturesMatch = MIN_FEATURES;
  if (nfeaturesRef   > MAX_FEATURES) nfeaturesRef   = MAX_FEATURES;
  if (nfeaturesMatch > MAX_FEATURES) nfeaturesMatch = MAX_FEATURES;

  printf("Using %d reference features.\n", nfeaturesRef);
  printf("Using %d match features.\n",     nfeaturesMatch);
  
  cv::Ptr<cv::FeatureDetector    > detectorRef,  detectorMatch;
  cv::Ptr<cv::DescriptorExtractor> extractorRef, extractorMatch;
  if (detectorType == DETECTOR_TYPE_BRISK)
  {
    detectorRef    = cv::BRISK::create();
    detectorMatch  = cv::BRISK::create();
    extractorRef   = cv::BRISK::create();
    extractorMatch = cv::BRISK::create();
  }
  if (detectorType == DETECTOR_TYPE_ORB)
  {
    //nfeatures         = 2000; // ORB is pretty fast to try more features
    float scaleFactor = 1.2f; // 1.2 is  default
    int nlevels       = 8; // 8 is default
    detectorRef    = cv::ORB::create(nfeaturesRef  );
    detectorMatch  = cv::ORB::create(nfeaturesMatch);
    extractorRef   = cv::ORB::create(nfeaturesRef  );
    extractorMatch = cv::ORB::create(nfeaturesMatch);
    printf("Using the ORB feature detector\n");
  }
  if (detectorType == DETECTOR_TYPE_SIFT)
  {
    int nOctaveLayers        = 6; // Output seems very sensitive to this value!
    double contrastThreshold = 0.04;
    double edgeThreshold     = 15;
    double sigma             = 1.2;
    detectorRef    = cv::xfeatures2d::SIFT::create(nfeaturesRef,   nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    detectorMatch  = cv::xfeatures2d::SIFT::create(nfeaturesMatch, nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    extractorRef   = cv::xfeatures2d::SIFT::create(nfeaturesRef,   nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    extractorMatch = cv::xfeatures2d::SIFT::create(nfeaturesMatch, nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    printf("Using the SIFT feature detector\n");
  }
  if (detectorType == DETECTOR_TYPE_AKAZE)
  {
    int   descriptorType     = cv::AKAZE::DESCRIPTOR_MLDB;
    //int   descriptorType     = cv::AKAZE::DESCRIPTOR_KAZE;
    int   descriptorSize     = 0; // Max
    int   descriptorChannels = 3;
    float threshold          = 0.0015f; // Controls number of points found
    int   numOctaves         = 8;
    int   numOctaveLayers    = 5; // Num sublevels per octave
    detectorRef    = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
    detectorMatch  = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
    extractorRef   = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
    extractorMatch = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
  }
  
  printf("detect...\n");
  detectorRef->detect(  refImage, keypointsA); // Basemap
  printf("extract...\n");
  extractorRef->compute(refImage, keypointsA, descriptorsA);

  // TODO: Try out a cloud masking algorithm for the ISS image!
  // - Handle clouds in the reference image using Earth Engine.
  //cv::Mat keypointMask(matchImage.size(), CV_8U)
  
  printf("detect...\n");
  //detector->detect(  matchImage, keypointsB, keypointMask); // ISS image
  detectorMatch->detect(  matchImage, keypointsB); // ISS image
  printf("extract...\n");
  extractorMatch->compute(matchImage, keypointsB, descriptorsB);

  if ( (keypointsA.size() == 0) || (keypointsB.size() == 0) )
  {
    std::cout << "Failed to find any features in an image!\n";
    return 0;
  }
  printf("Detected %lu and %lu keypoints\n", keypointsA.size(), keypointsB.size());

  // TODO: Does not seem to make a difference...
  //if ( (detectorType == DETECTOR_TYPE_SIFT) || (detectorType == DETECTOR_TYPE_AKAZE))
  if (detectorType == DETECTOR_TYPE_SIFT)
  {
    applyRootSift(descriptorsA);
    applyRootSift(descriptorsB);
  }
  
  if (debug)
  {
    cv::Mat keypointImageA, keypointImageB;
    cv::drawKeypoints(refImageIn, keypointsA, keypointImageA,
                      cv::Scalar::all(-1), cv::DrawMatchesFlags::DRAW_RICH_KEYPOINTS);
    cv::drawKeypoints(matchImageIn, keypointsB, keypointImageB,
                      cv::Scalar::all(-1), cv::DrawMatchesFlags::DRAW_RICH_KEYPOINTS);
    cv::imwrite( debugFolder+"refKeypoints.tif", keypointImageA);
    cv::imwrite( debugFolder+"matchKeypoints.tif", keypointImageB);
  }
  
  // Find the closest match for each feature
  //cv::FlannBasedMatcher matcher;
  cv::Ptr<cv::DescriptorMatcher> matcher;
  if (detectorType == DETECTOR_TYPE_SIFT)
    matcher = cv::DescriptorMatcher::create("BruteForce");
  else // Hamming distance is used for binary descriptors
    matcher = cv::DescriptorMatcher::create("BruteForce-Hamming");
  std::vector<std::vector<cv::DMatch> > matches;
  const size_t N_BEST_MATCHES = 2;
  matcher->knnMatch(descriptorsA, descriptorsB, matches, N_BEST_MATCHES);
  printf("Initial matching finds %lu matches.\n", matches.size());
  
  const float  SEPERATION_RATIO = 0.8; // Min seperation between top two matches
  std::vector<cv::DMatch> seperatedMatches;
  seperatedMatches.reserve(matches.size());// * N_BEST_MATCHES);
  for (int i = 0; i < matches.size(); ++i)
  {
    //// Accept multiple matches for each feature
    //for (size_t j=0; j<N_BEST_MATCHES; ++j)
    //  seperatedMatches.push_back(matches[i][j]);
      
    // Only accept matches which stand out
    if (matches[i][0].distance < SEPERATION_RATIO * matches[i][1].distance)
    {
      seperatedMatches.push_back(matches[i][0]);
    }
  }
  printf("After match seperation have %lu out of %lu points remaining\n",
         seperatedMatches.size(), matches.size());
  const size_t MIN_LEGAL_MATCHES = 3;
  if (seperatedMatches.size() < MIN_LEGAL_MATCHES)
    return 0;

  //// TODO: If this ever works, try to use it!
  //printf("Attempting to compute aligning image rotation...\n");
  //double calcRotation=0;
  //if (!estimateImageRotation(keypointsA, keypointsB, seperatedMatches, calcRotation))
  //  printf("Failed to compute a rotation alignment between the images!\n"); 
  
  //-- Quick calculation of max and min distances between keypoints
  double max_dist = 0; double min_dist = 9999999;
  for (size_t i=0; i<seperatedMatches.size(); i++)
  { 
    if ((seperatedMatches[i].queryIdx < 0) || (seperatedMatches[i].trainIdx < 0))
      continue;
    double dist = seperatedMatches[i].distance;
    //std::cout << matches[i].queryIdx <<", "<< matches[i].trainIdx << ", " << dist <<  std::endl;
    if (dist < min_dist) 
      min_dist = dist;
    if (dist > max_dist) 
      max_dist = dist;
  }
  //printf("-- Max dist : %f \n", max_dist );
  //printf("-- Min dist : %f \n", min_dist );
  
  if (debug)
  {
    cv::Mat matches_image1;
    cv::drawMatches(refImageIn, keypointsA, matchImageIn, keypointsB,
                    seperatedMatches, matches_image1, cv::Scalar::all(-1), cv::Scalar::all(-1),
                    std::vector<char>(),cv::DrawMatchesFlags::NOT_DRAW_SINGLE_POINTS);
    cv::imwrite(debugFolder+"seperated_matches.tif", matches_image1);
  }
  
  
  //-- Pick out "good" matches
  float goodDist = max_dist;//(min_dist + max_dist) / 2.0;
  //if (argc > 3)
  //  goodDist = atof(argv[3]);
  const size_t DUPLICATE_CUTOFF = 3;
  std::vector< cv::DMatch > good_matches;
  for (int i=0; i<seperatedMatches.size(); i++)
  { 
    // First verify that the match is valid
    if ( (seperatedMatches[i].queryIdx < 0) ||
         (seperatedMatches[i].trainIdx < 0) ||  
         (seperatedMatches[i].queryIdx >= keypointsA.size()) || 
         (seperatedMatches[i].trainIdx >= keypointsB.size()) )
      continue;
    
    // Throw out matches that match to the same point as other matches
    size_t duplicateCount = 0;
    for (int j=0; j<seperatedMatches.size(); j++)
    {
      if (i == j) continue;
      if ( (seperatedMatches[i].queryIdx == seperatedMatches[j].queryIdx) ||
           (seperatedMatches[i].trainIdx == seperatedMatches[j].trainIdx)  )
      ++duplicateCount;
    }
    //printf("Count = %d\n", duplicateCount);
    if (duplicateCount >= DUPLICATE_CUTOFF)
      continue;
    
    // Now check the distance
    if (seperatedMatches[i].distance <= goodDist)
      good_matches.push_back( seperatedMatches[i]);
    
    //good_matches.push_back( seperatedMatches[i]);
  }
  printf("After additional filtering have %lu out of %lu points remaining\n",
         good_matches.size(), seperatedMatches.size());
  if (good_matches.size() < MIN_LEGAL_MATCHES)
    return 0;

  if (debug)
  {
    cv::Mat matches_image2;
    cv::drawMatches(refImageIn, keypointsA, matchImageIn, keypointsB,
                    good_matches, matches_image2, cv::Scalar::all(-1), cv::Scalar::all(-1),
                    std::vector<char>(),cv::DrawMatchesFlags::NOT_DRAW_SINGLE_POINTS);
    cv::imwrite(debugFolder+"good_matches.tif", matches_image2);
  }
  
  // Get the coordinates from the remaining good matches  
  std::vector<cv::Point2f> refPts;
  std::vector<cv::Point2f> matchPts;
  for(size_t i = 0; i < good_matches.size(); i++ )
  {
    refPts.push_back  (keypointsA[good_matches[i].queryIdx].pt);
    matchPts.push_back(keypointsB[good_matches[i].trainIdx].pt);
  }
  printf("Computing homography...\n");
  
  // Compute a transform between the images using RANSAC
  // - Start with a small error acceptance threshold, but increase it if we don't find a solution.
  const int MIN_INLIER_DIST_PIXELS = 5;
  const int MAX_INLIER_DIST_PIXELS = 20;
  const int INC_INLIER_DIST_PIXELS = 3;
  cv::Mat inlierMask;
  size_t numInliers = 0;
  for (int d=MIN_INLIER_DIST_PIXELS; d<MAX_INLIER_DIST_PIXELS; d+=INC_INLIER_DIST_PIXELS)
  {
    numInliers = 0;
    printf("Searching for homography with inlier distance = %d\n", d);
    transform = cv::findHomography( matchPts, refPts, cv::RHO, d, inlierMask );
    if (inlierMask.rows == 0)
      continue; // Special case for no inliers!
    for (size_t i=0; i<refPts.size(); ++i)
    {  // Count the number of inliers
      if (inlierMask.at<unsigned char>(i, 0) > 0)
        ++numInliers;
    }
    // Stop increasing the match distance when we get the minimum legal number of inliers
    if (numInliers > MIN_LEGAL_MATCHES)
      break;
  }
  printf("Finished computing homography.\n");
  
  // TODO: Use some sort of affine based check to throw out bad points?
  //       Often, but not always, an affine based transform works ok.
  //       This would help alleviate cases where one bad match messes up
  //       an otherwise good transform.
  
  if (inlierMask.rows == 0)
  {
    printf("Failed to find any inliers!\n");
    return 0;
  }
  
  // Convert from OpenCV inlier mask to vector of inlier indices
  std::vector<size_t    > inlierIndices;
  std::vector<cv::DMatch> inlierMatches;
  inlierMatches.reserve(numInliers);
  inlierIndices.reserve(numInliers);
  for (size_t i=0; i<refPts.size(); ++i)
  {
    if (inlierMask.at<unsigned char>(i, 0) > 0)
    {
      inlierIndices.push_back(i);
      inlierMatches.push_back(good_matches[i]);
    }
  }
  printf("Obtained %lu inliers.\n", inlierIndices.size());

  for(size_t i = 0; i < inlierIndices.size(); i++ )
  {
    // Get the keypoints from the used matches
    refInlierCoords.push_back  (refPts  [inlierIndices[i]]);
    matchInlierCoords.push_back(matchPts[inlierIndices[i]]);
  }

  // A function to help filter results but it is not currently used
  //affineInlierPrune(matchInlierCoords, refInlierCoords);
  
  if (debug)
  {
    cv::Mat matches_image3;
    cv::drawMatches(refImageIn, keypointsA, matchImageIn, keypointsB,
                    inlierMatches, matches_image3, cv::Scalar::all(-1), cv::Scalar::all(-1),
                    std::vector<char>(),cv::DrawMatchesFlags::NOT_DRAW_SINGLE_POINTS);
                       
    cv::imwrite(debugFolder+"match_debug_image.tif", matches_image3);
  }



  // Return the number of inliers found
  return static_cast<int>(numInliers);
}

/// Calls computImageTransform with multiple parameters until one succeeds
int computeImageTransformRobust(const cv::Mat &refImageIn, const cv::Mat &matchImageIn,
                                cv::Mat &transform,
                                std::vector<cv::Point2f> &refInlierCoords, 
                                std::vector<cv::Point2f> &matchInlierCoords,
                                const ModeType mode,
                                const std::string &debugFolder,
                                bool debug)
{
  // Try not to accept solutions with fewer outliers
  const int DESIRED_NUM_INLIERS  = 20;
  const int REQUIRED_NUM_INLIERS = 10;
  cv::Mat bestTransform;
  int bestNumInliers = 0;
  int numInliers;
  
  if (mode == MODE_FAST)
  {
    int kernelSize   = 5;
    int detectorType = DETECTOR_TYPE_ORB;
    printf("Attempting transform with kernel size = %d and detector type = %d\n",
           kernelSize, detectorType);
    numInliers = computeImageTransform(refImageIn, matchImageIn, transform, 
                                       refInlierCoords, matchInlierCoords,
                                       debugFolder,
                                       kernelSize, static_cast<DetectorType>(detectorType), debug);
    return numInliers;
  }
  if (mode == MODE_ACCURATE)
  {
    int kernelSize   = 5;
    int detectorType = DETECTOR_TYPE_SIFT;
    printf("Attempting transform with kernel size = %d and detector type = %d\n",
           kernelSize, detectorType);
    numInliers = computeImageTransform(refImageIn, matchImageIn, transform, 
                                       refInlierCoords, matchInlierCoords,
                                       debugFolder,
                                       kernelSize, static_cast<DetectorType>(detectorType), debug);
    return numInliers;
  } 
  printf("ERROR: Did not recognize the execution mode!");
  return 0; 
  
  // To improve run speed, this function is currently set up to try only a single
  //  parameter configuration.
  // - If this changes, we need to make sure that the best set of inliers make it to the output variables.
/*  
  // Keep trying transform parameter combinations until we get a good
  //   match as determined by the inlier count
  for (int kernelSize=5; kernelSize<6; kernelSize += 20)
  {
    for (int detectorType=2; detectorType<4; detectorType+=10)
    {
      printf("Attempting transform with kernel size = %d and detector type = %d\n",
             kernelSize, detectorType);
      numInliers = computeImageTransform(refImageIn, matchImageIn, transform, 
                                         refInlierCoords, matchInlierCoords,
                                         debugFolder,
                                         kernelSize, static_cast<DetectorType>(detectorType), debug);
      
      
      return numInliers; // DEBUG!!!!!!!!!
      
      if (numInliers >= DESIRED_NUM_INLIERS)
        return numInliers; // This transform is good enough, return it.

      if (numInliers > bestNumInliers)
      {
        // This is the best transform yet.
        bestTransform  = transform;
        bestNumInliers = numInliers;
      }
    } // End detector type loop
  } // End kernel size loop

  if (bestNumInliers < REQUIRED_NUM_INLIERS)
    return 0; // Did not get an acceptable transform!

  // Use the best transform we got
  transform = bestTransform;
  return bestNumInliers;
*/
}

/// Try to estimate the accuracy of the computed registration
std::string evaluateRegistrationAccuracy(int numInliers, const cv::Mat &transform)
{
  // Make some simple decisions based on the inlier count
  if (numInliers < 5)
    return "CONFIDENCE_NONE";
  if (numInliers > 25)
    return "CONFIDENCE_HIGH";

  return "CONFIDENCE_LOW";
}


//=============================================================




int main(int argc, char** argv )
{
  
  if (argc < 4)
  {
    printf("usage: registerGeocamImage <Base map path> <New image path> <Output path> [debug (y or n)] [slow method? (y or n)]\n");
    return -1;
  }
  std::string refImagePath   = argv[1];
  std::string matchImagePath = argv[2];
  std::string outputPath     = argv[3];
  bool debug = false;
  if (argc > 4) // Set debug option
  {
    char lcase = tolower(argv[4][0]);
    debug = ((lcase == 'y') || (lcase == '1'));
  }
  ModeType mode = MODE_FAST;
  if (argc > 5) // Set debug option
  {
    char lcase = tolower(argv[5][0]);
    if ((lcase == 'y') || (lcase == '1'))
      mode = MODE_ACCURATE;
  }
  
  // TODO: Experiment with color processing
  const int LOAD_GRAY = 0;
  const int LOAD_RGB  = 1;
  
  // Load the input image
  cv::Mat refImageIn = cv::imread(refImagePath, LOAD_RGB);
  if (!refImageIn.data)
  {
    printf("Failed to load reference image\n");
    return -1;
  }

  cv::Mat matchImageIn = cv::imread(matchImagePath, LOAD_RGB);
  if (!matchImageIn.data)
  {
    printf("Failed to load match image\n");
    return -1;
  }

  // Write any debug files to this folder
  size_t stop = outputPath.rfind("/");
  std::string debugFolder = outputPath.substr(0,stop+1);

  // First compute the transform between the two images
  // - The transform is from MATCH (second input) to REF (first input)
  cv::Mat transform(3, 3, CV_32FC1);
  std::vector<cv::Point2f> refInlierCoords, matchInlierCoords;
  int numInliers = computeImageTransformRobust(refImageIn, matchImageIn, transform, 
                                               refInlierCoords, matchInlierCoords,
                                               mode, debugFolder, debug);
  if (!numInliers)
  {
    printf("Failed to compute image transform!\n");
    return -1;
  }
   
  std::string confString = evaluateRegistrationAccuracy(numInliers, transform);
  printf("Computed %s transform with %d inliers.\n", confString.c_str(), numInliers);

  // Write the output to a file
  writeOutput(outputPath, transform, refInlierCoords, matchInlierCoords, confString, debug);
  
  if (!debug) // Only debug stuff beyond this point
    return 0;
  
  // DEBUG - Paste the match image on top of the reference image
  writeOverlayImage(refImageIn, matchImageIn, transform, debugFolder+"warped.tif");
  
  
  return 0;
}








