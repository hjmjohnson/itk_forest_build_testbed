// Three-backend FFT benchmark: time a full 3-D complex forward+inverse FFT for
// whichever ITK backends this build provides (Vnl on main, PocketFFT on the
// branch, FFTW on both). Reports per-rep wall time so runs can be aggregated
// across backends and forests; also reports round-trip error as a correctness
// gate. Build once per forest (different ITK_DIR); the available backends are
// detected with __has_include.
//
//   bench-fft-backends <backend> <size> <reps>
//   backend in {vnl,fftw,pocketfft}; one transform direction pair per rep.
#include "itkImage.h"
#include "itkComplexToComplexFFTImageFilter.h"
#include "itkImageRegionIteratorWithIndex.h"
#include "itkImageRegionConstIterator.h"
#include <algorithm>
#include <complex>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#if __has_include("itkVnlComplexToComplexFFTImageFilter.h")
#  include "itkVnlComplexToComplexFFTImageFilter.h"
#  define HAVE_VNL 1
#endif
#if __has_include("itkPocketFFTComplexToComplexFFTImageFilter.h")
#  include "itkPocketFFTComplexToComplexFFTImageFilter.h"
#  define HAVE_POCKETFFT 1
#endif
#if defined(ITK_USE_FFTWD) && __has_include("itkFFTWComplexToComplexFFTImageFilter.h")
#  include "itkFFTWComplexToComplexFFTImageFilter.h"
#  define HAVE_FFTW 1
#endif

using PixelType = std::complex<double>;
using ImageType = itk::Image<PixelType, 3>;

static ImageType::Pointer
MakeImage(unsigned int s)
{
  auto img = ImageType::New();
  ImageType::SizeType sz;
  sz.Fill(s);
  img->SetRegions(ImageType::RegionType(sz));
  img->Allocate();
  itk::ImageRegionIteratorWithIndex<ImageType> it(img, img->GetLargestPossibleRegion());
  for (it.GoToBegin(); !it.IsAtEnd(); ++it)
  {
    auto i = it.GetIndex();
    it.Set(PixelType(double((i[0] + 2 * i[1] + 3 * i[2]) % 17) - 8.0, 0.0));
  }
  return img;
}

template <typename FilterType>
int
runBackend(const std::string & name, unsigned int s, unsigned int reps)
{
  auto input = MakeImage(s);
  double worstRoundTrip = 0.0;
  std::vector<double> fwdMs, invMs;
  for (unsigned int r = 0; r < reps; ++r)
  {
    auto fwd = FilterType::New();
    fwd->SetTransformDirection(FilterType::FORWARD);
    fwd->SetInput(input);
    auto t0 = std::chrono::steady_clock::now();
    fwd->Update();
    auto t1 = std::chrono::steady_clock::now();

    auto inv = FilterType::New();
    inv->SetTransformDirection(FilterType::INVERSE);
    inv->SetInput(fwd->GetOutput());
    inv->Update();
    auto t2 = std::chrono::steady_clock::now();

    fwdMs.push_back(std::chrono::duration<double, std::milli>(t1 - t0).count());
    invMs.push_back(std::chrono::duration<double, std::milli>(t2 - t1).count());

    // round-trip error: inverse(forward(x)) ~ x (filters normalize the inverse)
    itk::ImageRegionConstIterator<ImageType> a(input, input->GetLargestPossibleRegion());
    itk::ImageRegionConstIterator<ImageType> b(inv->GetOutput(), inv->GetOutput()->GetLargestPossibleRegion());
    double e = 0.0;
    for (a.GoToBegin(), b.GoToBegin(); !a.IsAtEnd(); ++a, ++b)
      e = std::max(e, std::abs(a.Get() - b.Get()));
    worstRoundTrip = std::max(worstRoundTrip, e);
  }
  auto med = [](std::vector<double> v) {
    std::sort(v.begin(), v.end());
    return v[v.size() / 2];
  };
  auto mn = [](const std::vector<double> & v) { return *std::min_element(v.begin(), v.end()); };
  std::cout << "  " << name << "  size=" << s << "^3  reps=" << reps
            << "  fwd_med=" << med(fwdMs) << "ms fwd_min=" << mn(fwdMs)
            << "  inv_med=" << med(invMs) << "ms inv_min=" << mn(invMs)
            << "  roundtrip_max=" << worstRoundTrip << "\n";
  return 0;
}

int
main(int argc, char ** argv)
{
  const std::string backend = (argc > 1) ? argv[1] : "list";
  const unsigned int s = (argc > 2) ? std::atoi(argv[2]) : 128;
  const unsigned int reps = (argc > 3) ? std::atoi(argv[3]) : 10;

  if (backend == "vnl")
  {
#ifdef HAVE_VNL
    return runBackend<itk::VnlComplexToComplexFFTImageFilter<ImageType>>("vnl", s, reps);
#else
    std::cerr << "vnl backend not built in this ITK\n";
    return 3;
#endif
  }
  if (backend == "pocketfft")
  {
#ifdef HAVE_POCKETFFT
    return runBackend<itk::PocketFFTComplexToComplexFFTImageFilter<ImageType>>("pocketfft", s, reps);
#else
    std::cerr << "pocketfft backend not built in this ITK\n";
    return 3;
#endif
  }
  if (backend == "fftw")
  {
#ifdef HAVE_FFTW
    return runBackend<itk::FFTWComplexToComplexFFTImageFilter<ImageType>>("fftw", s, reps);
#else
    std::cerr << "fftw backend not built in this ITK\n";
    return 3;
#endif
  }
  std::cout << "available:"
#ifdef HAVE_VNL
            << " vnl"
#endif
#ifdef HAVE_POCKETFFT
            << " pocketfft"
#endif
#ifdef HAVE_FFTW
            << " fftw"
#endif
            << "\n";
  return 0;
}
