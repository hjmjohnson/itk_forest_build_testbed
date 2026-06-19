// Standalone replica of FrequencyIterators.{Even,Odd}{2,3}D: band-filter [0,0.25]
// a real image in frequency space via the full-complex layout and via the
// half-Hermitian layout, inverse-FFT both, and report the max reconstruction
// difference (the gtest asserts every pixel agrees within 1e-5). Links only
// ITKFFT/ITKImageFrequency/ITKImageGrid (no IO/jpeg), so it builds where the
// bundled test driver cannot. Toggle ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS.
#include "itkImage.h"
#include "itkForwardFFTImageFilter.h"
#include "itkInverseFFTImageFilter.h"
#include "itkRealToHalfHermitianForwardFFTImageFilter.h"
#include "itkHalfHermitianToRealInverseFFTImageFilter.h"
#include "itkFrequencyBandImageFilter.h"
#include "itkFrequencyFFTLayoutImageRegionIteratorWithIndex.h"
#include "itkFrequencyHalfHermitianFFTLayoutImageRegionIteratorWithIndex.h"
#include "itkImageRegionIteratorWithIndex.h"
#include "itkImageRegionConstIterator.h"
#include "itkRandomImageSource.h"
#include "itkCastImageFilter.h"
#include <cstdio>

template <typename ImageType>
typename ImageType::Pointer
fullBand(typename ImageType::Pointer image)
{
  using FwdT = itk::ForwardFFTImageFilter<ImageType>;
  using CplxT = typename FwdT::OutputImageType;
  using ItT = itk::FrequencyFFTLayoutImageRegionIteratorWithIndex<CplxT>;
  auto fwd = FwdT::New();
  fwd->SetInput(image);
  auto band = itk::FrequencyBandImageFilter<CplxT, ItT>::New();
  band->SetInput(fwd->GetOutput());
  band->SetFrequencyThresholds(0.0, 0.25);
  auto inv = itk::InverseFFTImageFilter<CplxT, ImageType>::New();
  inv->SetInput(band->GetOutput());
  inv->Update();
  return inv->GetOutput();
}

template <typename ImageType>
typename ImageType::Pointer
hermitianBand(typename ImageType::Pointer image)
{
  using FwdT = itk::RealToHalfHermitianForwardFFTImageFilter<ImageType>;
  using CplxT = typename FwdT::OutputImageType;
  using InvT = itk::HalfHermitianToRealInverseFFTImageFilter<CplxT, ImageType>;
  using ItT = itk::FrequencyHalfHermitianFFTLayoutImageRegionIteratorWithIndex<CplxT>;
  auto fwd = FwdT::New();
  fwd->SetInput(image);
  fwd->Update();
  auto band = itk::FrequencyBandImageFilter<CplxT, ItT>::New();
  band->SetInput(fwd->GetOutput());
  band->SetFrequencyThresholds(0.0, 0.25);
  band->SetActualXDimensionIsOdd(fwd->GetActualXDimensionIsOdd());
  auto inv = InvT::New();
  inv->SetInput(band->GetOutput());
  inv->SetActualXDimensionIsOdd(fwd->GetActualXDimensionIsOdd());
  inv->Update();
  return inv->GetOutput();
}

template <unsigned D>
int
run(const char * tag, unsigned s)
{
  using ImageType = itk::Image<float, D>;
  // Match the gtest's CreateImage exactly: random signed-char, 1 work unit
  // for reproducibility, cast to float.
  using CharImage = itk::Image<signed char, D>;
  auto rnd = itk::RandomImageSource<CharImage>::New();
  rnd->SetNumberOfWorkUnits(1);
  rnd->SetSize(CharImage::SizeType::Filled(s));
  auto cast = itk::CastImageFilter<CharImage, ImageType>::New();
  cast->SetInput(rnd->GetOutput());
  cast->Update();
  typename ImageType::Pointer img = cast->GetOutput();
  auto full = fullBand<ImageType>(img);
  auto herm = hermitianBand<ImageType>(img);
  itk::ImageRegionConstIterator<ImageType> a(full, full->GetLargestPossibleRegion());
  itk::ImageRegionConstIterator<ImageType> b(herm, herm->GetLargestPossibleRegion());
  double   maxdiff = 0;
  unsigned over1e5 = 0;
  for (a.GoToBegin(), b.GoToBegin(); !a.IsAtEnd(); ++a, ++b)
  {
    double dd = std::abs(a.Get() - b.Get());
    maxdiff = std::max(maxdiff, dd);
    if (dd > 1e-5)
      ++over1e5;
  }
  std::printf("  %-8s size=%u^%u  max|full-herm|=%.3e  pixels>1e-5=%u  %s\n",
              tag, s, D, maxdiff, over1e5, over1e5 == 0 ? "PASS" : "FAIL");
  return over1e5 == 0 ? 0 : 1;
}

int
main()
{
  int rc = 0;
  rc |= run<2>("Even2D", 16);
  rc |= run<3>("Even3D", 16);
  rc |= run<3>("Odd3D", 15);
  return rc;
}
