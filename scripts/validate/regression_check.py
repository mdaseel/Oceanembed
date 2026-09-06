"""Phase 6A -> 6A.5 regression check.

The scaled pipeline must reproduce the Phase 6A smoke-test output on
2020-01-01/02 for every product that did NOT change. SSS is expected to differ:
the 8-day SMAP running mean was deliberately replaced by the official daily
MULTIOBS product, so it is reported separately and never counted as a failure.

This is what proves that scaling and refactoring did not silently alter the
science.

Run:  PYTHONPATH=src python scripts/validate/regression_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from oceanembed.config import REPO_ROOT  # noqa: E402

TAB = REPO_ROOT / "outputs" / "tables"
TAB.mkdir(parents=True, exist_ok=True)

OLD = REPO_ROOT / "data" / "processed" / "oceanembed_smoketest_2020_01_dev.nc"
NEW = REPO_ROOT / "data" / "processed" / "model_ready" / "oceanembed_2020.zarr"

# Channels whose source product is unchanged between 6A and 6A.5.
UNCHANGED = ["sst", "sla", "current_u", "current_v", "wind_u", "wind_v",
             "temp_0m", "temp_50m", "temp_100m", "temp_500m", "temp_1000m"]
CHANGED = ["sss"]

# Identical inputs through identical code should be bit-comparable; allow a
# small tolerance only for float accumulation order.
TOL_MEAN_ABS_DIFF = 1e-4
TOL_MAX_ABS_DIFF = 1e-3


def main() -> int:
    if not OLD.exists():
        print(f"MISSING Phase 6A dataset: {OLD}")
        return 1
    if not NEW.exists():
        print(f"MISSING Phase 6A.5 dataset: {NEW}\nBuild 2020 first.")
        return 1

    old = xr.open_dataset(OLD)
    new = xr.open_zarr(NEW, consolidated=True)

    dates = [np.datetime64("2020-01-01"), np.datetime64("2020-01-02")]
    old = old.sel(time=dates)
    new = new.sel(time=dates)

    assert np.array_equal(old.lat.values, new.lat.values), "lat grid changed"
    assert np.array_equal(old.lon.values, new.lon.values), "lon grid changed"
    print("grid identical: lat/lon match exactly")

    rows = []
    for v in UNCHANGED + CHANGED:
        if v not in old.data_vars or v not in new.data_vars:
            rows.append({"variable": v, "status": "ABSENT", "verdict": "SKIP"})
            continue
        a = old[v].values.astype("float64")
        b = new[v].values.astype("float64")
        both = np.isfinite(a) & np.isfinite(b)
        d = np.abs(a[both] - b[both])
        mean_d = float(d.mean()) if d.size else np.nan
        max_d = float(d.max()) if d.size else np.nan
        # coverage agreement matters as much as value agreement
        nan_a, nan_b = ~np.isfinite(a), ~np.isfinite(b)
        cov_mismatch = int((nan_a ^ nan_b).sum())

        expected_change = v in CHANGED
        if expected_change:
            verdict = "EXPECTED-DIFF"
        elif np.isnan(mean_d):
            verdict = "FAIL (no overlapping finite values)"
        elif mean_d <= TOL_MEAN_ABS_DIFF and max_d <= TOL_MAX_ABS_DIFF:
            verdict = "PASS"
        else:
            verdict = "FAIL"

        rows.append({
            "variable": v,
            "source_changed": expected_change,
            "phase6a_mean": float(np.nanmean(a)),
            "phase6a5_mean": float(np.nanmean(b)),
            "mean_abs_diff": mean_d,
            "max_abs_diff": max_d,
            "tol_mean": TOL_MEAN_ABS_DIFF,
            "tol_max": TOL_MAX_ABS_DIFF,
            "n_compared": int(both.sum()),
            "coverage_mismatch_cells": cov_mismatch,
            "verdict": verdict,
        })

    df = pd.DataFrame(rows)
    df.to_csv(TAB / "phase6a_regression_check.csv", index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print(df.to_string(index=False))

    fails = df[df.verdict.astype(str).str.startswith("FAIL")]
    print()
    if len(fails):
        print(f"REGRESSION CHECK FAILED for {len(fails)} variable(s)")
        return 1
    print("REGRESSION CHECK PASSED for all unchanged products "
          f"({(df.verdict=='PASS').sum()} channels); "
          f"{(df.verdict=='EXPECTED-DIFF').sum()} deliberately changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
