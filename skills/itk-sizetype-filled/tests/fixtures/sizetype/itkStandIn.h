#pragma once

namespace itk
{
template <typename TContainer, typename TValue>
constexpr TContainer
MakeFilled(const TValue & value)
{
  TContainer container{};
  container.Fill(value);
  return container;
}

template <typename T, unsigned int N>
class FixedArray
{
public:
  constexpr FixedArray() = default;
  constexpr void
  Fill(const T & value)
  {
    for (auto & e : m_Data)
    {
      e = value;
    }
  }
  static constexpr FixedArray
  Filled(const T & value)
  {
    return MakeFilled<FixedArray>(value);
  }
  T &
  operator[](unsigned int i)
  {
    return m_Data[i];
  }
  T m_Data[N]{};
};

template <typename T, unsigned int N>
class Point : public FixedArray<T, N>
{
public:
  constexpr Point() = default;
};

template <unsigned int N>
struct Size
{
  constexpr void
  Fill(unsigned long value)
  {
    for (auto & e : m_Data)
    {
      e = value;
    }
  }
  static constexpr Size
  Filled(unsigned long value)
  {
    return MakeFilled<Size>(value);
  }
  unsigned long &
  operator[](unsigned int i)
  {
    return m_Data[i];
  }
  constexpr unsigned long
  operator[](unsigned int i) const
  {
    return m_Data[i];
  }
  unsigned long m_Data[N];
};

template <unsigned int N>
struct Index
{
  constexpr void
  Fill(long value)
  {
    for (auto & e : m_Data)
    {
      e = value;
    }
  }
  static constexpr Index
  Filled(long value)
  {
    return MakeFilled<Index>(value);
  }
  long m_Data[N];
};

template <unsigned int N>
struct Offset
{
  constexpr void
  Fill(long value)
  {
    for (auto & e : m_Data)
    {
      e = value;
    }
  }
  long m_Data[N];
};

template <typename T>
class Array
{
public:
  Array() = default;
  void
  Fill(const T &)
  {}
  unsigned int
  size() const
  {
    return 0;
  }
};

template <typename T>
class Matrix
{
public:
  Matrix() {}
  void
  Fill(const T & value)
  {
    m_Value = value;
  }
  T m_Value;
};
} // namespace itk
