#include <cstddef>
#include <vector>

std::size_t
use_a()
{
  std::vector<std::size_t> v;
  v.push_back(3);
  return v.size();
}
