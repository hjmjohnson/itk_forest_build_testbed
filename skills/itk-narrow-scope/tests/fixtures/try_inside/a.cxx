#include <string>

std::string
g();
void
use(const std::string &);

void
direct()
{
  std::string s;
  try
  {
    s = g();
    use(s);
  }
  catch (...)
  {}
}

void
nested(int c)
{
  std::string s;
  try
  {
    if (c > 0)
    {
      s = g();
      use(s);
    }
  }
  catch (...)
  {}
}
