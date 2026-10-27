#include "itkStandIn.h"

using ArrayType = itk::Array<double>;
using MatrixType = itk::Matrix<double>;
using RGBPixelType = itk::RGBPixel<unsigned char>;

template <typename TImage>
unsigned long
first_size()
{
  typename TImage::SizeType size;
  size.Fill(3);
  return size[0];
}

struct FakeImage
{
  using SizeType = itk::Size<3>;
};

unsigned int
use_b()
{
  ArrayType weights;
  weights.Fill(7);

  MatrixType m;
  m.Fill(0);

  RGBPixelType color;
  color.Fill(0);

  return weights.size() + static_cast<unsigned int>(m.m_Value + first_size<FakeImage>() + color[0]);
}
