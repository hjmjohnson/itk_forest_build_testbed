#include "itkStandIn.h"

void
use(const double *);

void
decay(int c)
{
  double         buf[3];
  const double * p = nullptr;
  if (c)
  {
    buf[0] = 1.0;
    p = buf;
  }
  use(p);
}

void
member(int c)
{
  itk::Point<double, 3> pt;
  const double *        p = nullptr;
  if (c)
  {
    pt[0] = 1.0;
    p = pt.GetDataPointer();
  }
  use(p);
}
