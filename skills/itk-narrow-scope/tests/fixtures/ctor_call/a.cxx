struct Obj
{
  explicit Obj(int v)
    : m_V(v)
  {}
  int m_V;
};

void
use(const Obj &);

void
probe(int c)
{
  Obj o(c);
  int z = 0;
  if (c)
  {
    o = Obj(2);
    use(o);
  }
}
