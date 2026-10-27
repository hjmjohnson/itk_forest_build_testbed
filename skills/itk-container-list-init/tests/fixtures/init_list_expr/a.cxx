#include <vector>

int
f();

int
use_a()
{
  int              n = f();
  std::vector<int> v;
  v.push_back(n + 1);
  return v[0];
}
