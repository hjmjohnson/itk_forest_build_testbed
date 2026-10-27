#include <cstddef>
#include <vector>

std::size_t
use_a()
{
  std::vector<double> v; // the v
  v.push_back(1.5);
  v.push_back(2.5);
  return v.size();
}
