void
F(const std::string & x)
{
  std::ofstream f;
  f.open(x, std::ios::binary);
  std::ifstream g;
  g.open(x);
  std::fstream h;
  h.open(x.c_str(), std::ios::in | std::ios::out);
}
