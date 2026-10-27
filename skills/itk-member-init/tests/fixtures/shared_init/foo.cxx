#include "foo.h"

Foo::Foo()
  : m_B(1)
  , m_A(0)
{}

Foo::Foo(const Foo & other)
  : m_B(other.m_B)
  // a copy starts from zero
  , m_A(0)
{}
