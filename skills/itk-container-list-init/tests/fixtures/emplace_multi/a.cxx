#include <cstddef>
#include <utility>
#include <vector>

using PairVec = std::vector<std::pair<int, int>>;

std::size_t
use_a()
{
  std::vector<std::pair<int, int>> p;
  p.emplace_back(1, 2);
  p.emplace_back(3, 4);
  PairVec q;
  q.emplace_back(5, 6);
  return p.size() + q.size();
}
