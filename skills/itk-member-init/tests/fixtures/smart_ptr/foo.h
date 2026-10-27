#include <memory>

namespace itk
{
template <typename T>
class SmartPointer
{
public:
  SmartPointer() = default;

private:
  T * m_Pointer = nullptr;
};
} // namespace itk

class Reader
{};

class Foo
{
public:
  Foo();

private:
  using ReaderPointer = Reader *;
  ReaderPointer                m_Reader;
  std::unique_ptr<Reader>      m_Owned;
  itk::SmartPointer<Reader>    m_Smart;
  int                          m_Count;
};
