#include "foo.h"

Foo::Foo(int a)
{
  m_Count = 0; // reset on construction
  m_Scale = 1.5;
  m_Size = a; // from the caller
}
