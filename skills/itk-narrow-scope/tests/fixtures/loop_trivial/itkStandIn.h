#pragma once

namespace itk
{
template <typename T, unsigned int N>
class FixedArray
{
public:
  FixedArray() = default;
  T &
  operator[](unsigned int i)
  {
    return m_InternalArray[i];
  }

private:
  T m_InternalArray[N];
};

template <typename T, unsigned int N>
class Point : public FixedArray<T, N>
{
public:
  Point() = default;
};
} // namespace itk
