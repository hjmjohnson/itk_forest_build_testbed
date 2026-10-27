class Thing
{
public:
  int
  Count() const
  {
    return m_Count;
  }

private:
  int        m_Count;
  double     m_Scale; // pixels
  static int m_Shared;
  bool       m_Ready{ false };
};
