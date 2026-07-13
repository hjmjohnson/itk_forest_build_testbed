# ASAN Build Notes for ITK v5.4.2

## Why ASAN requires a feature suffix

AddressSanitizer instrumentation changes the ABI: every memory allocation
gains a shadow-memory red zone, and the runtime library must be linked into
every binary. A consumer built against the default (non-ASAN) ITK install
cannot safely link against ASAN-instrumented libraries. Therefore the skill
requires the `_asan` suffix, producing separate `bld_v5.4.2_asan/` and
`installed_v5.4.2_asan/` directories.

## ASAN-specific CMake flags

| Variable | Value | Purpose |
|----------|-------|---------|
| `CMAKE_CXX_FLAGS` | `-fsanitize=address -fno-omit-frame-pointer -fno-optimize-sibling-calls` | ASAN instrumentation + full stack traces |
| `CMAKE_C_FLAGS` | Same as above | C sources need same instrumentation |
| `CMAKE_EXE_LINKER_FLAGS` | `-fsanitize=address` | Links ASAN runtime into executables |
| `CMAKE_SHARED_LINKER_FLAGS` | `-fsanitize=address` | Links ASAN runtime into shared libraries |
| `CMAKE_MODULE_LINKER_FLAGS` | `-fsanitize=address` | Links ASAN runtime into loadable modules |

## Compiler

Default Apple Clang (`/usr/bin/clang++`) is used. No compiler-specific
suffix is needed because Apple Clang is the system default on macOS.

## Consumer project usage

The consumer **must also** be built with `-fsanitize=address` flags --
mixing ASAN and non-ASAN object code in the same binary is undefined behavior.
