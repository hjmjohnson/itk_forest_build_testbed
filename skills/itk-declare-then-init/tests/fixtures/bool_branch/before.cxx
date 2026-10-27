void
F(int c, int d, int e, Foo * ptr)
{
  bool a = false;
  if (c > 0) { a = true; }
  bool b = false;
  if (d > 0)
    b = true;
  bool g = true;
  if (e > 0)
  {
    g = false;
  }
  bool found = false;
  if (ptr) found = true;
  bool missing = true;
  if (ptr)
    missing = false;
  consume(a && b && g && found && missing);
}
