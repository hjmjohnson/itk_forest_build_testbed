int
f();

int
use_a()
{
  int n = f();
  int m = 0;
  m += n;
  return m;
}
