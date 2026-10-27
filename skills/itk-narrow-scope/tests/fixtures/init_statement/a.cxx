int
f();

int
use()
{
  const auto n = f();
  if (n > 0)
  {
    return n;
  }
  return 0;
}

int
count(int m)
{
  int i = 0;
  for (; i < m; ++i)
  {
    m -= 1;
  }
  return m;
}

int
pick(int k)
{
  const int v = k * 2;
  switch (v)
  {
    case 0:
      return 1;
    default:
      return v;
  }
}
