

#include <stdio.h>
#include <Common.h>
#include "opencv2/core.hpp"
#include "opencv2/features2d.hpp"
#include "opencv2/calib3d.hpp"
#include "opencv2/imgproc.hpp"

#include "opencv2/xfeatures2d.hpp"

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

enum DetectorType {DETECTOR_TYPE_BRISK = 0, 
                   DETECTOR_TYPE_ORB   = 1,
                   DETECTOR_TYPE_SIFT  = 2,
                   DETECTOR_TYPE_AKAZE = 3};


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



/// Returns the number of inliers
int computeImageTransform(const cv::Mat &refImageIn, const cv::Mat &matchImageIn,
                          cv::Mat &transform,
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
    cv::imwrite( debugFolder+"geocamProcessed.jpeg", matchImage );
  }
    
  std::vector<cv::KeyPoint> keypointsA, keypointsB;
  cv::Mat descriptorsA, descriptorsB;  

  int nfeatures = 2000;
  
  cv::Ptr<cv::FeatureDetector    > detector;
  cv::Ptr<cv::DescriptorExtractor> extractor;
  if (detectorType == DETECTOR_TYPE_BRISK)
  {
    detector  = cv::BRISK::create();
    extractor = cv::BRISK::create();
  }
  if (detectorType == DETECTOR_TYPE_ORB)
  {
    detector  = cv::ORB::create(nfeatures);
    extractor = cv::ORB::create(nfeatures);
  }
  if (detectorType == DETECTOR_TYPE_SIFT)
  {
    int nOctaveLayers        = 6; // Output seems very sensitive to this value!
    double contrastThreshold = 0.04;
    double edgeThreshold     = 15;
    double sigma             = 1.2;
    detector  = cv::xfeatures2d::SIFT::create(nfeatures, nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    extractor = cv::xfeatures2d::SIFT::create(nfeatures, nOctaveLayers, contrastThreshold, edgeThreshold, sigma);
    printf("Using the SIFT feature detector\n");
  }
  if (detectorType == DETECTOR_TYPE_AKAZE)
  {
    int   descriptorType     = cv::AKAZE::DESCRIPTOR_MLDB;
    //int   descriptorType     = cv::AKAZE::DESCRIPTOR_KAZE;
    int   descriptorSize     = 0; // Max
    int   descriptorChannels = 3;
    float threshold          = 0.003f; // Controls number of points found
    int   numOctaves         = 8;
    int   numOctaveLayers    = 5; // Num sublevels per octave
    detector  = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
    extractor = cv::AKAZE::create(descriptorType, descriptorSize, descriptorChannels, threshold, numOctaves, numOctaveLayers);
  }
  
  detector->detect(  refImage, keypointsA); // Basemap
  extractor->compute(refImage, keypointsA, descriptorsA);

  detector->detect(  matchImage, keypointsB); // HRSC
  extractor->compute(matchImage, keypointsB, descriptorsB);

  if ( (keypointsA.size() == 0) || (keypointsB.size() == 0) )
  {
    std::cout << "Failed to find any features in an image!\n";
    return 0;
  }

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
  matcher->knnMatch(descriptorsA, descriptorsB, matches, 2);
  printf("Initial matching finds %d matches.\n", matches.size());
  
  const float SEPERATION_RATIO = 0.8; // Min seperation between top two matches
  std::vector<cv::DMatch> seperatedMatches;
  seperatedMatches.reserve(matches.size());
  for (int i = 0; i < matches.size(); ++i)
  {
    if (matches[i][0].distance < SEPERATION_RATIO * matches[i][1].distance)
    {
      seperatedMatches.push_back(matches[i][0]);
    }
  }
  printf("After match seperation have %d out of %d points remaining\n",
         seperatedMatches.size(), matches.size());
  const size_t MIN_LEGAL_MATCHES = 3;
  if (seperatedMatches.size() < MIN_LEGAL_MATCHES)
    return 0;

  // TODO: If this ever works, try to use it!
  printf("Attempting to compute aligning image rotation...\n");
  double calcRotation=0;
  if (!estimateImageRotation(keypointsA, keypointsB, seperatedMatches, calcRotation))
    printf("Failed to compute a rotation alignment between the images!\n"); 

  
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
  const size_t DUPLICATE_CUTOFF = 2;
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
  }
  printf("After score filtering have %u out of %u points remaining\n",
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
  const double MAX_INLIER_DIST_PIXELS = 30;
  cv::Mat inlierMask;
  transform = cv::findHomography( matchPts, refPts, cv::RHO, MAX_INLIER_DIST_PIXELS, inlierMask );
  printf("Finished computing homography.\n");
  
  if (inlierMask.rows == 0)
  {
    printf("Failed to find any inliers!\n");
    return 0;
  }
  
  // Convert from OpenCV inlier mask to vector of inlier indices
  std::vector<size_t    > inlierIndices;
  std::vector<cv::DMatch> inlierMatches;
  inlierMatches.reserve(refPts.size());
  inlierIndices.reserve(refPts.size());
  for (size_t i=0; i<refPts.size(); ++i) {
    if (inlierMask.at<unsigned char>(i, 0) > 0)
    {
      inlierIndices.push_back(i);
      inlierMatches.push_back(good_matches[i]);
    }
  }
  printf("Obtained %d inliers.\n", inlierIndices.size());

  
  std::vector<cv::Point2f> usedPtsRef, usedPtsMatch;
  for(size_t i = 0; i < inlierIndices.size(); i++ )
  {
    // Get the keypoints from the used matches
    usedPtsRef.push_back  (refPts  [inlierIndices[i]]);
    usedPtsMatch.push_back(matchPts[inlierIndices[i]]);
  }

  if (debug)
  {
    cv::Mat matches_image3;
    cv::drawMatches(refImageIn, keypointsA, matchImageIn, keypointsB,
                    inlierMatches, matches_image3, cv::Scalar::all(-1), cv::Scalar::all(-1),
                    std::vector<char>(),cv::DrawMatchesFlags::NOT_DRAW_SINGLE_POINTS);
                       
    cv::imwrite(debugFolder+"match_debug_image.tif", matches_image3);
  }

  // Return the number of inliers found
  return static_cast<int>(inlierIndices.size());
}

/// Calls computImageTransform with multiple parameters until one succeeds
int computeImageTransformRobust(const cv::Mat &refImageIn, const cv::Mat &matchImageIn,
                                const std::string &debugFolder,
                                cv::Mat &transform,
                                bool debug)
{
  // Try not to accept solutions with fewer outliers
  const int DESIRED_NUM_INLIERS  = 20;
  const int REQUIRED_NUM_INLIERS = 10;
  cv::Mat bestTransform;
  int bestNumInliers = 0;
  int numInliers;
  
  // Keep trying transform parameter combinations until we get a good
  //   match as determined by the inlier count
  for (int kernelSize=5; kernelSize<6; kernelSize += 20)
  {
    for (int detectorType=3; detectorType<4; detectorType+=10)
    {
      printf("Attempting transform with kernel size = %d and detector type = %d\n",
             kernelSize, detectorType);
      numInliers = computeImageTransform(refImageIn, matchImageIn, transform, debugFolder,
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
}

//=============================================================




int main(int argc, char** argv )
{
  
  if (argc < 4)
  {
    printf("usage: registerGeocamImage <Base map path> <New image path> <Output path> [debug]\n");
    return -1;
  }
  std::string refImagePath   = argv[1];
  std::string matchImagePath = argv[2];
  std::string outputPath     = argv[3];
  bool debug = false;
  if (argc > 4) // Set debug option
    debug = true;
  
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
  cv::Mat transform(3, 3, CV_32FC1);
  int numInliers = computeImageTransformRobust(refImageIn, matchImageIn, debugFolder, transform, debug);
  if (!numInliers)
  {
    printf("Failed to compute image transform!\n");
    return -1;
  }
  printf("Computed transform with %d inliers.\n", numInliers);

  // The output transform is from the HRSC image to the base map
  writeTransform(outputPath, transform);

  if (!debug) // Only debug stuff beyond this point
    return 0;
 
  // Print the transform
  for (int r=0; r<3; ++r)
  {
    for (int c=0; c<3; ++c)
    {
      printf("%lf    ", transform.at<double>(r,c));
    }
    printf("\n");
  }
  
  // DEBUG - Paste the match image on top of the reference image
  writeOverlayImage(refImageIn, matchImageIn, transform, debugFolder+"warped.tif");
  
  
  return 0;
}








