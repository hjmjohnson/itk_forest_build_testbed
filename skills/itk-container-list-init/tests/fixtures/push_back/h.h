#include <cstddef>
#include <vector>

inline std::size_t
use_h()
{
  std::vector<double> u;
  u.push_back(0.5);
  u.push_back(1.5);
  return u.size();
}
