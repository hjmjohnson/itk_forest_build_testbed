#include "foo.h"

int
Get();
void
Use(int);

Foo::Foo()
{
  m_A = Get();
  m_B = Get();
  Use(m_A);
}
