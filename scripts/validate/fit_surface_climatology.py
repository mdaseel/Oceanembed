"""Fit a TRAIN-ONLY seasonal climatology of the seven surface channels.

Used only as a non-learned fallback for a missing input channel in the
Phase 6C-B stress baseline. Nothing is fitted on evaluation data.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import pandas as pd
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.surface_climatology import SurfaceClimatology

OUT = REPO_ROOT / "outputs" / "baselines" / "phase6cb_surface_climatology.nc"
t0 = time.time()
ds = splits.open_split("train")
tt = pd.DatetimeIndex(ds.time.values)
assert not splits.contains_test_dates(tt), "LEAK: test dates in surface climatology"
print(f"TRAIN ONLY {tt[0].date()}..{tt[-1].date()} ({len(tt)} days)")
c = SurfaceClimatology.fit(ds)
c.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB) in {time.time()-t0:.0f}s")
back = SurfaceClimatology.load(OUT)
import numpy as np
a = c.predict_channel("sst", tt[10]); b = back.predict_channel("sst", tt[10])
print("save/reload identical:", bool(np.allclose(a, b, equal_nan=True)))
print("meta:", back.meta)
