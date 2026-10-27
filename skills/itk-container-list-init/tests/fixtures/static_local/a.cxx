#include <cstddef>
#include <vector>

std::size_t
use_a()
{
  static std::vector<double> v;
  v.push_back(1.5);
  v.push_back(2.5);
  thread_local std::vector<double> t;
  t.push_back(1.5);
  t.push_back(2.5);
  return v.size() + t.size();
}
