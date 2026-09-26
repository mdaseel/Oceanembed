"""Subsurface thermal-extreme baseline (PREREGISTRATION §8).

Reconstructs every day 2015-01-01..2020-12-31 with the frozen L2 (no replay-cache
writes), keeps depths 0, 50, 75, 100, 125, 150 m, and derives per cell, depth and
day of year the 90th percentile of all baseline values within +/-5 days, smoothed
with a 31-day circular moving mean. Outputs live under
outputs/science/cache/extreme_baseline/ (gitignored, regenerable).

Before any baseline day is written, the experiment forward is checked against the
engine's own inference on the first date; a mismatch aborts.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd

from oceanembed.config import REPO_ROOT
from oceanembed.replay.engine import DEPTHS, ReplayEngine
from oceanembed.science import frozen
from oceanembed.science.extremes import (BASELINE_END, BASELINE_START, EXTREME_DEPTHS,
                                         HALF_WINDOW, PERCENTILE, SMOOTH_DAYS,
                                         smooth_circular)

OUT = REPO_ROOT / "outputs" / "science" / "cache" / "extreme_baseline"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    engine = ReplayEngine()
    dates = pd.date_range(BASELINE_START, BASELINE_END, freq="D")

    # equivalence with the production inference, before anything is stored
    when = dates[0]
    ds = engine._store(when.year)
    t = engine._time_index(ds, when)
    ref, siv_ref = engine._infer(ds, t, when)
    field, siv, _ = frozen.historical_inputs(engine, when)
    t0 = time.time()
    mine = frozen.forward_field(engine, field, siv, when)
    one = time.time() - t0
    assert np.array_equal(siv, siv_ref)
    diff = np.nanmax(np.abs(mine - ref))
    assert np.array_equal(np.isnan(mine), np.isnan(ref)) and diff == 0.0, diff
    print(f"forward_field == engine._infer on {when.date()} (max |diff| {diff}); "
          f"{one:.2f}s per day", flush=True)

    k = [DEPTHS.index(d) for d in EXTREME_DEPTHS]
    shape = (len(dates), len(k), engine.lat.size, engine.lon.size)
    path = OUT / "recon.npy"
    progress = OUT / "recon_progress.json"
    start = json.loads(progress.read_text())["next"] if (progress.exists() and path.exists()) else 0
    recon = np.lib.format.open_memmap(path, mode="r+" if start else "w+",
                                      dtype="float32", shape=shape)
    t0 = time.time()
    for i in range(start, len(dates)):
        field, siv, when = frozen.historical_inputs(engine, dates[i])
        temp = frozen.forward_field(engine, field, siv, when)
        recon[i] = np.moveaxis(temp[:, :, k], -1, 0).astype("float32")
        if (i + 1) % 50 == 0 or i + 1 == len(dates):
            recon.flush()
            progress.write_text(json.dumps({"next": i + 1}))
            print(f"  {i + 1}/{len(dates)} ({time.time() - t0:.0f}s)", flush=True)
    recon.flush()
    del recon

    recon = np.load(path, mmap_mode="r")
    doy = dates.dayofyear.to_numpy()
    thr = np.full((366, len(k), engine.lat.size, engine.lon.size), np.nan, dtype="float32")
    counts = np.zeros(366, dtype="int32")
    for d in range(1, 367):
        dist = np.abs(doy - d)
        dist = np.minimum(dist, 366 - dist)
        idx = np.flatnonzero(dist <= HALF_WINDOW)
        counts[d - 1] = idx.size
        samples = np.asarray(recon[idx], dtype="float32")
        thr[d - 1] = np.nanpercentile(samples, PERCENTILE, axis=0).astype("float32")
        if d % 60 == 0:
            print(f"  percentile doy {d}/366", flush=True)
    thr = smooth_circular(thr, SMOOTH_DAYS)
    np.save(OUT / "p90_threshold.npy", thr)
    sha = hashlib.sha256((OUT / "p90_threshold.npy").read_bytes()).hexdigest()
    meta = {"protocol": "outputs/science/PREREGISTRATION.md §8",
            "baseline": [str(dates[0].date()), str(dates[-1].date())],
            "n_days": len(dates), "depths_m": list(EXTREME_DEPTHS),
            "percentile": PERCENTILE, "half_window_days": HALF_WINDOW,
            "smoothing_days": SMOOTH_DAYS,
            "samples_per_doy_min": int(counts.min()), "samples_per_doy_max": int(counts.max()),
            "l2_state_dict_sha256": engine.l2_state_dict_sha256,
            "threshold_sha256": sha,
            "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "source": "frozen-L2 reconstructions via science.frozen.forward_field "
                      "(verified identical to engine._infer); replay cache not written"}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
