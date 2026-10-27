struct Guard
{
  ~Guard();
  int
  Get() const;
};

int
guard(int c)
{
  Guard g;
  if (c > 0)
  {
    return g.Get() + c;
  }
  return 0;
}
