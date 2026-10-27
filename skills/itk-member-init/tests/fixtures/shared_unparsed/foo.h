class Foo
{
public:
  Foo();
  Foo(const Foo & other) noexcept;

private:
  int m_A;
};
