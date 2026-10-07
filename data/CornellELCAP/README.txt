Cornell ELCAP data root for LesionSizingToolkit (TEST_CORNELL_DATA_ROOT)

LesionSizingToolkit's test/CMakeLists.txt gates nine tests on
find_path(TEST_CORNELL_DATA_ROOT README.txt ...). Those nine tests read only
the module's bundled Data/Input/PartSolidLesionCropped.mha, so this directory
needs nothing but this file for them to be registered. The forest passes this
directory as TEST_CORNELL_DATA_ROOT (bin/setup-itk-downstream-testbed.sh,
LesionSizingToolkit arm).

The full collection (TEST_CORNELL_COLLECTION=ON, test/CornellCollectionTests.cmake)
reads DICOM series from the VIA/I-ELCAP Public Lung Image Database,
https://www.via.cornell.edu/databases/lungdb.html. That site requires an
interactive, self-certified login, so the series cannot be fetched by script.
To enable it, download the series the tests name and place them here with the
layout CornellCollectionTests.cmake expects, for example

  CornellPartSolid3/SL0074-20000101/SL0074/20000101-134856-2-1/*.dcm
  SM0052-20000101/SM0052/20000101-154701-2-1/*.dcm

The forest turns TEST_CORNELL_COLLECTION on when the SL0074 series is present.
DICOM and image files under data/ are git-ignored.
