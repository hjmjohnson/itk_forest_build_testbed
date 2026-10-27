void
F(bool x)
{
  Foo * p = nullptr;
  if (x)
    p = MakeFoo();
  Use(p);
}
