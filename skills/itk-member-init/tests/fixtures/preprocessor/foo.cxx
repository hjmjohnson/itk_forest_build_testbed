#include "foo.h"

Foo::Foo()
  : m_A(0)
#if defined(X)
  , m_B(1)
#endif
{
  m_C = 2;
}

Foo::Foo(int a)
  : m_A(a)
{}
