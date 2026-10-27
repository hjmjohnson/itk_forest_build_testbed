int
use(int c)
{
  int t = 0;
  if (c > 0)
  {
    t = 1;
    return t;
  }
  else
  {
    t = 2;
    return t;
  }
}

int
two(int c)
{
  int t = 0;
  {
    t = c;
    c += t;
  }
  {
    t = 2 * c;
    c += t;
  }
  return c;
}
