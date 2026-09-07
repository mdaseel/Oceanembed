"""Phase 7A verification: uncached timing + an isolated no-target sanity run.

Two things the Phase 7A gate needs that a unit test does not give directly:

1. the wall-clock cost of one UNCACHED ``replay_field(date)``, which Phase 7B
   needs in order to decide loading/caching behaviour and whether an interactive
   3D depth-scrub can be driven live;

2. a manual isolated-environment run proving there is no hidden target
   dependency. A temporary model-ready store is built containing ONLY the seven
   surface channels and the two masks - the GLORYS ``temp_*`` and
   ``target_valid_*`` variables are physically absent from it. If replay still
   produces a full 15-depth profile there, no target path can be hiding.

NON-DESTRUCTIVE: the temporary store is written to a scratch directory. No real
project file is deleted, renamed, moved, corrupted or overwritten.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import xarray as xr

from oceanembed.config import REPO_ROOT
from oceanembed.replay import ReplayEngine
from oceanembed.replay.contract import ALLOWED_STORE_VARS

OUT = REPO_ROOT / "outputs" / "phase7"
TIMING_DATES = ["2021-06-15", "2021-06-16", "2021-06-17", "2022-11-20",
                "2023-05-14"]
ISOLATION_DATE = "2021-06-15"
ISOLATION_YEAR = 2021
LAT, LON = 15.25, 87.75


def measure_uncached(reps: int = 5) -> dict:
    eng = ReplayEngine(use_cache=False)
    print("timing uncached replay_field() — cache disabled entirely\n")
    # one warm-up so lazy Zarr metadata and torch kernels are not counted as
    # scientific cost; it is reported separately rather than discarded silently
    t0 = time.perf_counter()
    eng.replay_field(TIMING_DATES[0])
    warm = time.perf_counter() - t0
    print(f"  warm-up (includes first store open) : {warm:.3f} s")

    rows = []
    for i in range(reps):
        d = TIMING_DATES[i % len(TIMING_DATES)]
        t0 = time.perf_counter()
        v = eng.replay_field(d)
        wall = time.perf_counter() - t0
        rows.append({"date": d, "wall_seconds": wall,
                     "compute_seconds": v.provenance["compute_seconds"],
                     "n_supported_cells": v.provenance["n_supported_cells"]})
        print(f"  {d}  wall {wall:6.3f} s   inference+L0 {v.provenance['compute_seconds']:6.3f} s")
    eng.close()

    wall = np.array([r["wall_seconds"] for r in rows])
    comp = np.array([r["compute_seconds"] for r in rows])
    summary = {
        "reps": reps,
        "warmup_seconds": warm,
        "wall_seconds_median": float(np.median(wall)),
        "wall_seconds_min": float(wall.min()),
        "wall_seconds_max": float(wall.max()),
        "compute_seconds_median": float(np.median(comp)),
        "per_call": rows,
        "note": "cache disabled; every call is a real frozen-L2 whole-field run",
    }
    print(f"\n  median uncached wall-clock: {summary['wall_seconds_median']:.3f} s "
          f"(min {summary['wall_seconds_min']:.3f}, max {summary['wall_seconds_max']:.3f})")
    return summary


def build_target_free_store(dest: Path, year: int, dates: list[str]) -> Path:
    """A model-ready store with the targets PHYSICALLY ABSENT."""
    src = REPO_ROOT / "data" / "processed" / "model_ready" / f"oceanembed_{year}.zarr"
    ds = xr.open_zarr(src, consolidated=True)
    keep = [v for v in ds.data_vars if v in ALLOWED_STORE_VARS]
    sub = ds[keep].sel(time=pd.DatetimeIndex(dates))
    out = dest / "model_ready" / f"oceanembed_{year}.zarr"
    out.parent.mkdir(parents=True, exist_ok=True)
    sub.load().to_zarr(out, mode="w", consolidated=True)
    ds.close()
    return out


def isolated_run() -> dict:
    print("\nisolated no-target sanity run")
    tmp = Path(tempfile.mkdtemp(prefix="oceanembed_phase7a_"))
    try:
        store = build_target_free_store(tmp, ISOLATION_YEAR, [ISOLATION_DATE])
        with xr.open_zarr(store, consolidated=True) as check:
            present = sorted(map(str, check.data_vars))
        leaked = [v for v in present if v.startswith(("temp_", "target_valid_"))]
        print(f"  isolated store variables: {present}")
        print(f"  target variables present: {leaked or 'NONE'}")
        assert not leaked, "the isolated store still contains a target variable"

        eng = ReplayEngine(model_ready=tmp / "model_ready",
                           cache_root=tmp / "cache", use_cache=False)
        res = eng.replay_point(ISOLATION_DATE, LAT, LON)
        view = eng.replay_field(ISOLATION_DATE)
        eng.close()

        n_finite = sum(1 for r in res.profile if r["prediction_c"] is not None)
        print(f"  replay_point returned {len(res.profile)} depths, "
              f"{n_finite} finite predictions")
        print(f"  replay_field shape {view.temperature.shape}, "
              f"{view.provenance['n_supported_cells']:,} supported cells")
        print("  RESULT: replay ran with the targets physically absent")
        return {
            "result": "PASS",
            "isolated_store_variables": present,
            "target_variables_present": leaked,
            "n_depths_returned": len(res.profile),
            "n_finite_predictions": n_finite,
            "field_shape": list(view.temperature.shape),
            "n_supported_cells": int(view.provenance["n_supported_cells"]),
            "method": "temporary Zarr store built with targets dropped; no real "
                      "project file was deleted, renamed, moved or overwritten",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    timing = measure_uncached()
    isolation = isolated_run()
    doc = {"generated": str(pd.Timestamp.utcnow().tz_localize(None)),
           "uncached_replay_field_timing": timing,
           "isolated_no_target_run": isolation}
    path = OUT / "phase7a_verification.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
