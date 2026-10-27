#include <cstddef>
#include <vector>

std::size_t
use_a()
{
  std::vector<double> v;
  v.push_back(1.5);
#if 1
  v.push_back(2.5);
#endif
  return v.size();
}
