#include <string>

std::string
g();
void
use(const char *);

void
probe(int c)
{
  std::string  s;
  const char * p = nullptr;
  if (c)
  {
    s = g();
    p = s.c_str();
  }
  use(p);
}
