#include "h.h"
#include <cstddef>
#include <vector>

std::size_t
use_a()
{
  std::vector<int> v;
  v.push_back(1);
  v.push_back(2);
  v.push_back(3);
  std::vector<double> w;
  w.push_back(1.5);
  w.push_back(w[0]);
  return v.size() + w.size() + use_h();
}
