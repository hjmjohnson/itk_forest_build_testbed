int
use(int c)
{
  int total = 0;
  if (c > 0)
  {
    total += c;
    total *= 2;
    c = total;
  }
  return c;
}

int
keep(int c)
{
  int total = 0;
  if (c > 0)
  {
    total = c;
  }
  return total;
}

int
deep(int c)
{
  double scale = 2.0;
  if (c > 0)
  {
    if (c > 1)
    {
      scale *= c;
      return static_cast<int>(scale);
    }
  }
  return 0;
}
