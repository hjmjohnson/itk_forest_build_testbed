void
F(int c)
{
  bool a = false;
  if (c > 0)
  {
    a = true;
  }
  else
  {
    Other();
  }
  use(a);
}
