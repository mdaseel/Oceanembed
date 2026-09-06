"""Fit feature and per-depth target normalisation on the TRAIN split only."""
from __future__ import annotations

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np, pandas as pd, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.dataset import PointwiseSampler
from oceanembed.ml.features import FEATURE_NAMES
from oceanembed.ml.scaler import RunningMoments, ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]

def main() -> int:
    t0 = time.time()
    ds = splits.open_split("train")
    tt = pd.DatetimeIndex(ds.time.values)
    assert not splits.contains_test_dates(tt), "LEAK: test dates in scaler fit"
    print(f"TRAIN ONLY: {tt[0].date()} .. {tt[-1].date()} ({len(tt)} days)")

    smp = PointwiseSampler(ds, DEPTHS, chunk_days=64)
    fm = RunningMoments(len(FEATURE_NAMES))
    tm = RunningMoments(len(DEPTHS))
    n = 0
    for X, Y, M, *_ in smp.blocks():
        fm.update(X)
        tm.update(Y, valid=M)          # masked: absent depths never contribute
        n += len(X)
        print(f"  {n/1e6:6.2f} M samples", end="\r")
    print(f"\nstreamed {n:,} training samples in {time.time()-t0:.0f}s")

    fs = ZScoreScaler(fm.mean, fm.std, FEATURE_NAMES, "train",
                      {"n_samples": int(n), "split": "train",
                       "start": str(tt[0].date()), "end": str(tt[-1].date())})
    ts = ZScoreScaler(tm.mean, tm.std, [f"temp_{d}m" for d in DEPTHS], "train",
                      {"n_valid_per_depth": tm.n.tolist(),
                       "purpose": "per-depth target standardisation; makes the "
                                  "masked loss weight each depth by its own "
                                  "variability instead of raw degC variance"})
    fs.to_json(BASE / "phase6b_feature_scaler.json")
    ts.to_json(BASE / "phase6b_target_scaler.json")

    print("\nFEATURES (train-only):")
    for nm, m, s in zip(FEATURE_NAMES, fs.mean, fs.std):
        print(f"  {nm:11s} mean={m:9.4f}  std={s:8.4f}")
    print("\nTARGETS (train-only, per depth):")
    for nm, m, s, c in zip(ts.names, ts.mean, ts.std, tm.n):
        print(f"  {nm:11s} mean={m:8.4f}  std={s:7.4f}  n={int(c):,}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
