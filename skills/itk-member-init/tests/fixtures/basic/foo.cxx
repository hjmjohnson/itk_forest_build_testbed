#include "foo.h"

Foo::Foo()
{
  m_C = 0.5;
  m_A = 0;
  m_B = 0;
}

Foo::Foo(int a)
{
  m_A = 1;
  m_B = 2; // the B
  m_C = a * 2.0;
}
