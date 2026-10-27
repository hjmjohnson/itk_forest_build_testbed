#include <memory>
#include <vector>

struct Filter
{
  static std::shared_ptr<Filter>
  New()
  {
    return std::make_shared<Filter>();
  }
  void
  Update()
  {}
};

void
use(int m)
{
  auto filter = Filter::New();
  for (int i = 0; i < m; ++i)
  {
    filter = Filter::New();
    filter->Update();
  }
}

int
sizes(int m)
{
  std::vector<int> values;
  for (int i = 0; i < m; ++i)
  {
    values = std::vector<int>(3, i);
    values.push_back(m);
  }
  return m;
}
