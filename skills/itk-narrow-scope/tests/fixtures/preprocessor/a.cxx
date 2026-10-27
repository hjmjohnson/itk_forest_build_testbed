int
use(int c)
{
  int total = 0;
#ifdef FOO
  c += 1;
#endif
  if (c > 0)
  {
    total = c;
    return total;
  }
  return 0;
}
