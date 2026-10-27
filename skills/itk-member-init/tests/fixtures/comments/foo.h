class Foo
{
public:
  Foo(int a);

private:
  /** Number of reads since construction. */
  int    m_Count;
  double m_Scale;
  int    m_Size;
};
