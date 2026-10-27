void
F(int c, int d, int e)
{
  const bool a = c > 0;
  const bool b = d > 0;
  const bool g = !(e > 0);
  use(a, b, g);
}
