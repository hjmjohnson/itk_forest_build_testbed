#include <limits>

template <unsigned int D>
struct Size
{
  unsigned long m_Size[D];
  static constexpr Size
  Filled(unsigned long v)
  {
    Size s{};
    for (auto & e : s.m_Size)
    {
      e = v;
    }
    return s;
  }
};
using SizeType = Size<2>;

int
f();

double
use()
{
  SizeType size = SizeType::Filled(2);
  int      lit = 3;
  int      n = f();
  double   big = std::numeric_limits<double>::max();
  int      arr[] = { 1, 2 };

  auto w = f();
  return size.m_Size[0] + lit + n + big + arr[1] + w;
}
