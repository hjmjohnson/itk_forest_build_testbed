#include <array>

int
use_a()
{
  std::array<int, 2> a;
  a[1] = 2;
  a[0] = 1;
  std::array<int, 3> p;
  p[0] = 1;
  p[1] = 2;
  return a[0] + p[1];
}
