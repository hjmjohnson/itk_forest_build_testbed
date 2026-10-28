void
F()
{
  Foo * p = nullptr;
  p = MakeFoo();
  int n = 0;
  n = Count();
  std::string s = "";
  s = Name();
  double d = 0.0;
  d = Value() * 2.0;
  double d0 = NAN;
  double d1 = NAN;
  double dist = NAN;
  d0 = pow(a - b, 2);
  d1 = pow(a + b, 2);
  dist = sqrt(d0 + d1);
}
