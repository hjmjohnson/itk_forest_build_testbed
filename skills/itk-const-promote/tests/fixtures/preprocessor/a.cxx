int
f();

int
use()
{
  int n = f();
#if defined(NEVER_DEFINED)
  n += 1;
#endif
  return n;
}

int
plain()
{
  int k = f();
  return k;
}
