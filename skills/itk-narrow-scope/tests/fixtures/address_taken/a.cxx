void
sink(int *);

int
use(int m)
{
  int x;
  for (int i = 0; i < m; ++i)
  {
    x = i;
    sink(&x);
  }
  return m;
}

int
capture(int m)
{
  int y = 0;
  if (m > 0)
  {
    auto set = [&y](int v) { y = v; };
    set(m);
    return y;
  }
  return 0;
}
