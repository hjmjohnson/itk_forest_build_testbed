#include "itkImageBase.h"

void
make(ImagePointer image, Image & ref)
{
  image->Allocate(true);
  ref.Allocate( true ); // zeroed
  image->Allocate(false);
  image->Allocate();
  // image->Allocate(true) stays in a comment
  const char * s = "->Allocate(true)";
  image->Allocate(true);
}
