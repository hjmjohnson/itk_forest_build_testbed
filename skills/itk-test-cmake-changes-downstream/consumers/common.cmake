# Shared knobs for every fake consumer. Override on the cmake command line to
# retarget this family at a different ThirdParty module (HDF5, PNG, TIFF, ...).
#
#   PROBE_SRC          absolute path to the .cxx that forces the dependency
#   ITK_MODULE_TARGET  the ITK interface target a modern consumer links
#   THIRDPARTY_TARGET  the bare upstream imported target a "naive" consumer
#                      references expecting find_package(ITK) to have provided it
#   FIND_COMPONENTS    a COMPONENTS list that transitively needs the dependency
set(PROBE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/../probe_zlib.cxx" CACHE FILEPATH "")
set(ITK_MODULE_TARGET "ITK::ITKZLIBModule" CACHE STRING "")
set(THIRDPARTY_TARGET "ZLIB::ZLIB" CACHE STRING "")
set(FIND_COMPONENTS "ITKIOPNG" CACHE STRING "")
