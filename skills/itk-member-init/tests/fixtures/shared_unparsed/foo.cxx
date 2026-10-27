#include "foo.h"

Foo::Foo()
  : m_A(0)
{}

Foo::Foo(const Foo & other) noexcept
  : m_A(0)
{}
