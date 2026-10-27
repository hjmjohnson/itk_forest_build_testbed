void
F()
{
  int a = ComputeA();
  int b;
#if defined(X)
  int c = 3;
#endif
  b = c;
}
