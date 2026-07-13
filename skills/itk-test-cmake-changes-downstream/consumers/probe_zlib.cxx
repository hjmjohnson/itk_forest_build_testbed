// Default probe for ITK ThirdParty/ZLIB export-CMake changes.
// Forces the consumer to resolve BOTH the zlib include directory (via
// itk_zlib.h -> zlib.h) and the zlib link symbol (zlibVersion), so a broken
// exported include path or link interface fails the build, not just silently
// links nothing.
#include "itk_zlib.h"
#include <cstdio>
int
main()
{
  std::printf("zlib version via ITK: %s\n", zlibVersion());
  return 0;
}
