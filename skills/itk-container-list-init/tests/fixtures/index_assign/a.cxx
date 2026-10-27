#include <array>

double
use_a()
{
  std::array<double, 3> a;
  a[0] = 1.0;
  a[1] = 2.0;
  a[2] = 3.0;
  std::array<double, 3> b;
  b[0] = 1.0;
  b[2] = 3.0;
  return a[0] + b[2];
}
