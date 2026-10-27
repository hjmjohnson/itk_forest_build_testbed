#include "itkImageRegionIterator.h"

void
fill(ImageType * output, PixelType value)
{
  for (itk::ImageRegionIterator<ImageType> it(output, output->GetBufferedRegion()); !it.IsAtEnd(); ++it)
  {
    it.Set(value); // background
  }
}
