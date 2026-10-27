int
f();

int
caught()
{
  int v = 0;
  try
  {
    v = f();
  }
  catch (...)
  {
    return v;
  }
  return 0;
}

int
after()
{
  int v = 0;
  try
  {
    v = f();
  }
  catch (...)
  {}
  return v;
}
