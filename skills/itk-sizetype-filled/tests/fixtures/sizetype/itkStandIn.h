#pragma once

namespace itk
{
template <typename TContainer>
constexpr TContainer
MakeFilled(typename TContainer::const_reference value)
{
  TContainer container{};
  static_assert(container.size() > 0, "MakeFilled requires TContainer with constant non-zero size!");
  container.Fill(value);
  return container;
}

template <typename T, unsigned int N>
class FixedArray
{
public:
  using const_reference = const T &;
  constexpr FixedArray() = default;
  static constexpr unsigned int
  size()
  {
    return N;
  }
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

template <typename T>
class RGBPixel : public FixedArray<T, 3>
{
public:
  using Superclass = FixedArray<T, 3>;
  constexpr RGBPixel()
    : Superclass(Superclass())
  {}
};

template <unsigned int N>
struct Size
{
  using const_reference = const unsigned long &;
  static constexpr unsigned int
  size()
  {
    return N;
  }
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
  using const_reference = const long &;
  static constexpr unsigned int
  size()
  {
    return N;
  }
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
  using const_reference = const long &;
  static constexpr unsigned int
  size()
  {
    return N;
  }
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
  using const_reference = const T &;
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
  using const_reference = const T &;
  Matrix() = default;
  constexpr unsigned int
  size() const
  {
    return 9;
  }
  void
  Fill(const T & value)
  {
    m_Value = value;
  }
  T m_Value;
};
} // namespace itk
