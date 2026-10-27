#include <array>

int
use_a()
{
  int                i = 0;
  std::array<int, 2> a;
  a[1] = i++;
  a[0] = i++;
  int                x = 0;
  std::array<int, 2> b;
  b[1] = x += 1;
  b[0] = x += 1;
  return a[0] + b[0];
}
