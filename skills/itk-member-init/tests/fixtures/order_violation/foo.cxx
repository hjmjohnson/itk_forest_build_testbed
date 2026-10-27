#include "foo.h"

Foo::Foo()
  : m_A(m_B)
{
  m_B = 2;
}
