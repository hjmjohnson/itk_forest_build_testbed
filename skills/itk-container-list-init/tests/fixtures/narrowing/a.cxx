#include <vector>

unsigned int
f();

int
use_a()
{
  unsigned int n = f();
  std::vector<int> v;
  v.push_back(n);
  v.push_back(2);
  return v[0];
}
