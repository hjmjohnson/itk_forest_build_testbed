#include "itkImageRegionIterator.h"

using IteratorType = itk::ImageRegionIterator<ImageType>;

void
fill(ImageType * output, ImageType * image, PixelType outputPixel, RegionType crop)
{
  // Clear the output.
  for (IteratorType outIt(output, output->GetBufferedRegion()); !outIt.IsAtEnd(); ++outIt)
  {
    outIt.Set(outputPixel);
  }

  itk::ImageRegionIterator<ImageType> it(image, image->GetLargestPossibleRegion());
  it.GoToBegin();
  while (!it.IsAtEnd())
  {
    it.Set(static_cast<PixelType>(0));
    ++it;
  }

  for (IteratorType idx(image, image->GetBufferedRegion()); !idx.IsAtEnd(); ++idx)
  {
    idx.Set(idx.GetIndex()[0]);
  }

  for (IteratorType sub(image, crop); !sub.IsAtEnd(); ++sub)
  {
    sub.Set(outputPixel);
  }
}
