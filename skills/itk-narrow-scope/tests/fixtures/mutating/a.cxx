void
use(int);

void
branch(int c, int n)
{
  int x = n++;
  use(n);
  if (c)
  {
    x = 1;
    use(x);
  }
}

void
loop(int m, int n)
{
  int x = n++;
  for (int i = 0; i < m; ++i)
  {
    x = i;
    use(x);
  }
}
