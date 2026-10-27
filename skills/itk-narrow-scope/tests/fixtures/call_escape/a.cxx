struct Holder
{
  void
  Set(int & v);
  void
  Use(const double * p);
};

struct Buffer
{
  double         m_Data[3];
  const double *
  Data() const;
};

int
byref(int c, Holder & h)
{
  int x = 0;
  if (c > 0)
  {
    h.Set(x);
  }
  return c;
}

int
member(int c, Holder & h)
{
  Buffer buf;
  if (c > 0)
  {
    h.Use(buf.Data());
  }
  return c;
}

int
value(int c)
{
  int x = 0;
  if (c > 0)
  {
    x = c;
    return static_cast<int>(x) + 1;
  }
  return c;
}
