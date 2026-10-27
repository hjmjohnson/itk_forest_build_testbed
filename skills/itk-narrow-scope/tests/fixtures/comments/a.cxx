int
above(int c)
{
  // The running total.
  int total = 0;
  if (c > 0)
  {
    total = c * 2;
    return total;
  }
  return 0;
}

int
trailing(int c)
{
  int total = 1; // starts at one
  if (c > 0)
  {
    total += c;
    return total;
  }
  return 0;
}

int
doxygen(int c)
{
  /** The scale.
   *  Applied once. */
  double scale = 3.0;
  if (c > 0)
  {
    return static_cast<int>(scale * c);
  }
  return 0;
}
