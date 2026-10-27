void
F(const std::string & x)
{
  std::ofstream f(x, std::ios::binary);
  std::ifstream g(x);
  std::fstream h(x.c_str(), std::ios::in | std::ios::out);
}
