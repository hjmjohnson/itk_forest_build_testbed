void
F(int c, int d, int e)
{
  bool a = false;
  if (c > 0) { a = true; }
  bool b = false;
  if (d > 0)
    b = true;
  bool g = true;
  if (e > 0)
  {
    g = false;
  }
  use(a, b, g);
}
