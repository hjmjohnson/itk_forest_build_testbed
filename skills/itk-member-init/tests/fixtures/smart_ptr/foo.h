class Reader
{};

class Foo
{
public:
  Foo();

private:
  using ReaderPointer = Reader *;
  ReaderPointer m_Reader;
  int           m_Count;
};
