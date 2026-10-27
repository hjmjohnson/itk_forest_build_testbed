int
use(int c)
{
  static int calls = 0;
  if (c > 0)
  {
    ++calls;
    return calls;
  }
  return 0;
}

int
per_thread(int c)
{
  thread_local int seen = 0;
  if (c > 0)
  {
    seen += c;
    return seen;
  }
  return 0;
}
