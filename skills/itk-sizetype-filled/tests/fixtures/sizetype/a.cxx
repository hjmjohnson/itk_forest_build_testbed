#include "itkStandIn.h"

using SizeType = itk::Size<2>;
using IndexType = itk::Index<2>;
using OffsetType = itk::Offset<2>;
using PointType = itk::Point<double, 2>;

long
use_a(double spacing)
{
  IndexType start;
  start.Fill(0);

  SizeType size;
  size.Fill(2);

  SizeType grown;
  grown.Fill(2);
  grown[1] = 3;

  OffsetType step; // neighbor step
  step.Fill(1);

  PointType origin;
  origin.Fill(spacing); // half a voxel

  SizeType self;
  self.Fill(self[0]);

  return start.m_Data[0] + static_cast<long>(size.m_Data[0] + grown.m_Data[1] + self.m_Data[0]) + step.m_Data[0] +
         static_cast<long>(origin[0]);
}
