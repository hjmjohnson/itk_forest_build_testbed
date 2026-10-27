void
F(int c, int d, int e, Foo * ptr)
{
  const bool a = c > 0;
  const bool b = d > 0;
  const bool g = !(e > 0);
  const bool found = static_cast<bool>(ptr);
  const bool missing = !ptr;
  consume(a && b && g && found && missing);
}
