class ImageBase
{
public:
  void
  Allocate(bool initialize = false);
  void
  AllocateInitialized()
  {
    return this->Allocate(true);
  }
};
