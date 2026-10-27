#include <cstddef>
#include <vector>

std::size_t
use_b()
{
  std::vector<double> w; // the w
  w.push_back(1.5);      // first
  w.push_back(2.5);
  return w.size();
}
