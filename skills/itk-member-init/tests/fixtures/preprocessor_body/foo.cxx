#include "foo.h"

Foo::Foo()
{
#ifndef X
  m_A = 1;
#endif
  m_C = 3;
  m_B = 2;
}

Foo::Foo(int a)
  : m_A(a)
  , m_B(a)
  , m_C(a)
{}
