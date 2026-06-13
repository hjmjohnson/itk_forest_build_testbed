// Side test: does SAVING the FFT plan pay off when many same-size transforms
// run? PocketFFT's plan cache is gated by POCKETFFT_CACHE_SIZE (0 = reconstruct
// the plan every call; >0 = save/reuse by length). N3/N4 bias correction runs
// thousands of identical-size 1-D histogram FFTs, so this is the relevant knob.
//
// Build twice and compare per-call cost:
//   c++ -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE=0  ... -o probe_nocache
//   c++ -O3 -std=c++17 -DPOCKETFFT_CACHE_SIZE=16 ... -o probe_cache
//
// Prints: backend, transform length, repeats, ns/transform.
#include "pocketfft_hdronly.h"
#include <chrono>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <vector>

int
main(int argc, char ** argv)
{
  const size_t N = (argc > 1) ? std::strtoul(argv[1], nullptr, 10) : 256; // padded histogram-ish
  const size_t reps = (argc > 2) ? std::strtoul(argv[2], nullptr, 10) : 200000;

  std::vector<std::complex<double>> buf(N);
  for (size_t i = 0; i < N; ++i)
    buf[i] = { double(i % 7) - 3.0, 0.0 };

  const pocketfft::shape_t  shape{ N };
  const pocketfft::stride_t stride{ ptrdiff_t(sizeof(std::complex<double>)) };
  const pocketfft::shape_t  axes{ 0 };

  // Warm once (populates the cache when POCKETFFT_CACHE_SIZE>0).
  pocketfft::c2c(shape, stride, stride, axes, true, buf.data(), buf.data(), 1.0);

  auto t0 = std::chrono::steady_clock::now();
  for (size_t r = 0; r < reps; ++r)
    pocketfft::c2c(shape, stride, stride, axes, (r & 1) == 0, buf.data(), buf.data(), 1.0);
  auto t1 = std::chrono::steady_clock::now();

  double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / double(reps);
#ifdef POCKETFFT_CACHE_SIZE
  const int cs = POCKETFFT_CACHE_SIZE;
#else
  const int cs = -1; // header default
#endif
  std::printf("pocketfft  N=%zu  reps=%zu  cache=%d  %.1f ns/transform\n", N, reps, cs, ns);
  return 0;
}
