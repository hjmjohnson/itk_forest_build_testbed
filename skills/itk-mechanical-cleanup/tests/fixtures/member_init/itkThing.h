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

class Holder
{
  Pointer                  m_Self;
  std::unique_ptr<int>     m_Owned;
  itk::SmartPointer<Thing> m_Ptr;
  std::shared_ptr<int>     m_Shared;
};
