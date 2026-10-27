void
F(int c, int d)
{
  bool a = false;
  if (c > 0)
    a = true;
  if (d > 0)
  {
    a = false;
  }
  use(a);
}
