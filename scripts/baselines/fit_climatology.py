"""Fit the L0 climatology on the TRAINING split only, and freeze it."""
from __future__ import annotations

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np, pandas as pd, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
NH = CFG["climatology"]["n_harmonics"]
OUT = REPO_ROOT / CFG["paths"]["baselines"] / "phase6b_climatology.nc"

def main() -> int:
    t0 = time.time()
    ds = splits.open_split("train")           # test split cannot be opened here
    tt = pd.DatetimeIndex(ds.time.values)
    print(f"TRAIN ONLY: {tt[0].date()} .. {tt[-1].date()}  ({len(tt)} days)")
    assert not splits.contains_test_dates(tt), "LEAK: test dates in climatology fit"
    print(f"fitting harmonic climatology, {NH} harmonics, {len(DEPTHS)} depths")
    clim = HarmonicClimatology.fit(ds, DEPTHS, n_harmonics=NH, fitted_on="train")
    clim.meta["split_start"], clim.meta["split_end"] = splits.split_bounds("train")
    clim.save(OUT)
    print(f"\nwrote {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)  in {time.time()-t0:.0f}s")

    back = HarmonicClimatology.load(OUT)
    a = clim.predict(tt[:3]); b = back.predict(tt[:3])
    print("save/reload identical:", bool(np.allclose(a, b, equal_nan=True)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
