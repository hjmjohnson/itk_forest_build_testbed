#ifndef foo_h
#define foo_h

template <typename T>
class Tpl
{
public:
  Tpl();

private:
  T   m_X;
  int m_N;
};

#include "foo.hxx"
#endif
