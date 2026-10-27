int
f();

int
use()
{
  int near = f();
  int total = near;
  total += 1;




  int far = f();
  return total + far;
}
