int
use(int k)
{
  int r = 0;
  switch (k)
  {
    case 1:
    {
      r = 5;
      return r;
    }
    default:
      break;
  }
  return 0;
}

int
jump(int k)
{
  int r = 1;
  if (k < 0)
  {
    goto done;
  }
done:
{
  r += k;
  return r;
}
}
