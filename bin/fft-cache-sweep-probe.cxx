// Sweep helper: per-transform cost as a function of POCKETFFT_CACHE_SIZE for a
// workload that interleaves K distinct FFT lengths. Two regimes matter for the
// ITK default:
//   * K=1 (N3/N4 histogram FFT, fixed length 512): shows the lookup/mutex
//     overhead a larger cache adds when only one plan is ever needed.
//   * K>1 (general image-domain pipelines: separable axes, multi-resolution):
//     shows thrashing when cache < number of concurrently-live distinct sizes.
//
//   build: c++ -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE=<n> -I<inc> probe.cxx
//   run:   ./probe <reps> <len1,len2,...>
#include "pocketfft_hdronly.h"
#include <chrono>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

int
main(int argc, char ** argv)
{
  const size_t reps = (argc > 1) ? std::strtoul(argv[1], nullptr, 10) : 100000;
  std::vector<size_t> lens;
  if (argc > 2)
  {
    char * s = argv[2];
    for (char * tok = std::strtok(s, ","); tok; tok = std::strtok(nullptr, ","))
      lens.push_back(std::strtoul(tok, nullptr, 10));
  }
  if (lens.empty())
    lens.push_back(512);

  // One buffer per distinct length.
  std::vector<std::vector<std::complex<double>>> bufs;
  for (size_t L : lens)
  {
    std::vector<std::complex<double>> b(L);
    for (size_t i = 0; i < L; ++i)
      b[i] = { double(i % 7) - 3.0, 0.0 };
    bufs.push_back(std::move(b));
  }
  auto one = [&](size_t k, bool fwd) {
    const size_t            L = lens[k];
    const pocketfft::shape_t  shape{ L };
    const pocketfft::stride_t stride{ ptrdiff_t(sizeof(std::complex<double>)) };
    const pocketfft::shape_t  axes{ 0 };
    pocketfft::c2c(shape, stride, stride, axes, fwd, bufs[k].data(), bufs[k].data(), 1.0);
  };
  for (size_t k = 0; k < lens.size(); ++k)
    one(k, true); // warm

  auto t0 = std::chrono::steady_clock::now();
  for (size_t r = 0; r < reps; ++r)
    one(r % lens.size(), (r & 1) == 0);
  auto t1 = std::chrono::steady_clock::now();

  double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / double(reps);
  std::printf("cache=%-3d distinct=%zu  %.1f ns/transform\n",
              POCKETFFT_CACHE_SIZE, lens.size(), ns);
  return 0;
}
