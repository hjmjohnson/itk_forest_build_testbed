#include "itkStandIn.h"

double
use(int m, const itk::Point<double, 3> & origin)
{
  double                value;
  itk::Point<double, 3> p;
  double                sum = 0.0;
  for (int i = 0; i < m; ++i)
  {
    value = i * 0.5;
    p = origin;
    sum += p[0] + value;
  }
  return sum;
}
