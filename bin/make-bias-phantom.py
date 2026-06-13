#!/usr/bin/env python3
"""Generate a reproducible 3D phantom with a smooth multiplicative bias field.

A real N3/N4 workload: piecewise-constant tissue classes modulated by a
low-frequency bias and corrupted with noise. Deterministic (fixed seed) so the
same phantom drives every forest's executable. Output: NIfTI float32.
"""
import sys
import numpy as np
import nibabel as nib

size = int(sys.argv[2]) if len(sys.argv) > 2 else 128
out = sys.argv[1]
rng = np.random.default_rng(20260612)

z, y, x = np.mgrid[0:size, 0:size, 0:size].astype(np.float64) / size
# Three nested tissue blobs -> piecewise-constant anatomy.
r = np.sqrt((x - 0.5) ** 2 + (y - 0.5) ** 2 + (z - 0.5) ** 2)
tissue = np.select([r < 0.18, r < 0.32, r < 0.45], [800.0, 500.0, 300.0], 0.0)
# Smooth low-frequency multiplicative bias (1 +/- 0.4 across the volume).
bias = 1.0 + 0.4 * np.sin(2 * np.pi * x) * np.cos(2 * np.pi * y) * np.sin(np.pi * z)
img = tissue * bias + rng.normal(0, 8.0, tissue.shape)
img[tissue == 0] = 0.0

nib.save(nib.Nifti1Image(img.astype(np.float32), np.eye(4)), out)
print(f"wrote {out}  shape={img.shape}  nonzero={(tissue>0).mean():.2%}")
