int
f();

int
use()
{
  static int s = f();
  return s;
}
