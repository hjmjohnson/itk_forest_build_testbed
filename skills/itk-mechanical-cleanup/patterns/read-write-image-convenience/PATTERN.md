---
pattern: read-write-image-convenience
itk_main_status: none
scope: all
---

## Overview

ITK ships free-function convenience wrappers `itk::ReadImage<ImageType>(fileName)`
and `itk::WriteImage(image, fileName)` (declared in `itkImageFileReader.h` /
`itkImageFileWriter.h`). For one-shot I/O — read a file into an image, or write
an image/filter output to a file — they collapse a 4-6 line
`New()`/`SetFileName()`/`SetInput()`/`Update()` SmartPointer chain to a single
call.

Core principle: **only collapse a reader/writer that is used once for plain
I/O.** If the reader/writer object is reused, has extra configuration
(`SetImageIO`, `SetUseStreaming`, `SetNumberOfStreamDivisions`, observers), or
the code inspects it after `Update()` (e.g. `reader->GetImageIO()`), the helper
does not apply.

## When to use / when NOT

Use when, on a single SmartPointer variable:

- **Writer:** `New()` + `SetInput(src)` + `SetFileName(fn)` + `Update()`
  (the `SetInput`/`SetFileName` order varies) → `itk::WriteImage(src, fn);`
- **Reader:** `New()` + `SetFileName(fn)` + `Update()`, output consumed via
  `reader->GetOutput()` → `auto img = itk::ReadImage<ImageType>(fn);`

Do NOT use when:

- The reader/writer is reused for a second file or re-`Update()`d.
- Extra setup is present: `SetImageIO`, `SetUseStreaming`, `SetNumberOfStreamDivisions`,
  `SetUseCompression` (WriteImage has an optional `compress` arg — case by case),
  AddObserver, `UpdateLargestPossibleRegion`, region/IORegion clipping.
- The object is queried after Update (`GetImageIO()`, `GetMetaDataDictionary()`).
- The `GetOutput()` pointer is captured and the reader kept alive deliberately
  (the helper returns a fresh image; lifetime semantics differ).

This is **review-only**: the match spans multiple (possibly try/catch-wrapped)
lines with order-insensitive setters and frequent variable reuse, so a blind
sed/regex rewrite is unsafe. `detect.sh` is the deliverable; a human applies the
edit per site.

## Before / after

```cpp
// before
using WriterType = itk::ImageFileWriter<ImageType>;
WriterType::Pointer ImageWriter = WriterType::New();
ImageWriter->SetInput(imageFilter->GetOutput());
ImageWriter->SetFileName(argv[1]);
ImageWriter->Update();
// after
itk::WriteImage(imageFilter->GetOutput(), argv[1]);
```

```cpp
// before
using ReaderType = itk::ImageFileReader<ImageType>;
auto reader = ReaderType::New();
reader->SetFileName(argv[1]);
reader->Update();
ImageType::Pointer image = reader->GetOutput();
// after
auto image = itk::ReadImage<ImageType>(argv[1]);
```

## Detection

`detect.sh <repo-path>` (default `.`) git-greps for `ImageFileReader<` /
`ImageFileWriter<` declarations outside `ThirdParty/`, prints `file:line` plus a
small context window so a reviewer can confirm the New/SetFileName/Update chain,
and reports a candidate count. Context-only — it does not assert the full chain
(that judgement is the review step).

```bash
bash skills/itk-read-write-image-convenience/detect.sh /path/to/ITK
```

## Transformation approach

No safe automatic transform is provided. Per confirmed site:

1. Replace the `using`/`New()`/setters/`Update()` block with the single helper
   call. Writer: `itk::WriteImage(<input-expr>, <filename-expr>);`. Reader:
   `auto <var> = itk::ReadImage<ImageType>(<filename-expr>);` and retarget later
   `reader->GetOutput()` uses to `<var>`.
2. Drop the surrounding `try { ... Update(); } catch (...)` only when the
   function has no other reason to catch — `ReadImage`/`WriteImage` still throw
   `itk::ExceptionObject`, so keep the handler if the test expects it.
3. The `itkImageFileReader.h` / `itkImageFileWriter.h` include is already present
   (it declared the class) and also declares the helper — no include change.

## Verification (pattern-specific)

For tests with baseline comparison, the test must still pass (`ctest -R`).
Confirm no `reader->`/`writer->` references remain dangling.

## Common mistakes

- Collapsing a reader whose object is queried after `Update()` (e.g.
  `GetImageIO()`) — the helper discards the reader.
- Dropping a try/catch a test relies on to report I/O failure as a test failure.
- Forcing `WriteImage` where `SetUseCompression`/streaming was set — pass the
  optional `compress` arg or leave the site alone.
- Assuming setter order — match the *set* of calls (`SetInput`+`SetFileName`),
  not a fixed sequence.
