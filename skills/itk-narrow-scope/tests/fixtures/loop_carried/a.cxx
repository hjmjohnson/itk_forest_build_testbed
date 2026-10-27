int
use(int m)
{
  int last = 0;
  for (int i = 0; i < m; ++i)
  {
    if (i > last)
    {
      last = i + 1;
    }
  }
  return m;
}
