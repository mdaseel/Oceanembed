"""STEP 6 - scientific sanity checks.

Policy: this module NEVER modifies data. It computes statistics, locates
extremes, and raises typed flags. Any correction is a separate, documented
decision made downstream.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

# Physically plausible envelopes for the North Indian Ocean, open water.
# Values outside these are flagged for inspection, not clipped.
PLAUSIBLE = {
    "sst":       (15.0, 33.0, "degC"),
    "sss":       (30.0, 41.0, "PSU"),
    "sla":       (-1.0, 1.0, "m"),
    "current_u": (-3.0, 3.0, "m s-1"),
    "current_v": (-3.0, 3.0, "m s-1"),
    "wind_u":    (-40.0, 40.0, "m s-1"),
    "wind_v":    (-40.0, 40.0, "m s-1"),
}
for _d in (0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000):
    PLAUSIBLE[f"temp_{_d}m"] = (0.0, 33.0, "degC")


def _locate(da: xr.DataArray, which: str) -> dict:
    """Return the coordinates of the min or max of a DataArray."""
    arr = da.values.astype("float64")
    if not np.isfinite(arr).any():
        return {}
    flat = np.nanargmin(arr) if which == "min" else np.nanargmax(arr)
    idx = np.unravel_index(flat, arr.shape)
    return {d: (str(da[d].values[i])[:19] if d == "time" else float(da[d].values[i]))
            for d, i in zip(da.dims, idx) if d in da.coords}


def stats(ds: xr.Dataset, variables: list[str] | None = None) -> pd.DataFrame:
    """Per-variable min/max/mean/std/%missing plus the location of extremes."""
    rows = []
    for v in (variables or list(ds.data_vars)):
        da = ds[v]
        a = da.values.astype("float64")
        finite = np.isfinite(a)
        lo, hi, units = PLAUSIBLE.get(v, (None, None, da.attrs.get("units", "")))
        row = {
            "variable": v,
            "units": da.attrs.get("units", units),
            "min": float(np.nanmin(a)) if finite.any() else np.nan,
            "max": float(np.nanmax(a)) if finite.any() else np.nan,
            "mean": float(np.nanmean(a)) if finite.any() else np.nan,
            "std": float(np.nanstd(a)) if finite.any() else np.nan,
            "pct_missing": float(100.0 * (1.0 - finite.mean())),
            "n_finite": int(finite.sum()),
        }
        if lo is not None:
            n_below = int((a < lo).sum())
            n_above = int((a > hi).sum())
            row["plausible_range"] = f"[{lo}, {hi}]"
            row["n_below_range"] = n_below
            row["n_above_range"] = n_above
            row["pct_out_of_range"] = float(100.0 * (n_below + n_above) / max(finite.sum(), 1))
        row["argmin"] = _locate(da, "min")
        row["argmax"] = _locate(da, "max")
        rows.append(row)
    return pd.DataFrame(rows)


def flags(ds: xr.Dataset) -> list[str]:
    """Structured checks for the specific failure modes named in STEP 6."""
    out: list[str] = []

    for v in ds.data_vars:
        a = ds[v].values.astype("float64")
        finite = np.isfinite(a)
        if not finite.any():
            out.append(f"ALL-NaN: {v} contains no finite values")
            continue

        # Celsius / Kelvin confusion
        if v.startswith(("sst", "temp_")) and np.nanmin(a) > 100.0:
            out.append(f"UNIT: {v} min={np.nanmin(a):.1f} looks like kelvin, not degC")

        # m/s vs cm/s confusion
        if v.startswith(("current_", "wind_")) and np.nanmax(np.abs(a)) > 50.0:
            out.append(f"UNIT: {v} |max|={np.nanmax(np.abs(a)):.1f} may be cm/s not m/s")

        # all-zero field
        if finite.sum() and np.nanmax(np.abs(a)) == 0.0:
            out.append(f"ALL-ZERO: {v} is identically zero")

        # impossible salinity
        if v == "sss" and (np.nanmin(a) < 0.0 or np.nanmax(a) > 45.0):
            out.append(f"RANGE: sss spans [{np.nanmin(a):.2f}, {np.nanmax(a):.2f}] - outside 0-45 PSU")

        # out-of-envelope values
        lo, hi, _ = PLAUSIBLE.get(v, (None, None, None))
        if lo is not None:
            n_out = int(((a < lo) | (a > hi)).sum())
            if n_out:
                out.append(
                    f"RANGE: {v} has {n_out} finite values outside the plausible "
                    f"open-ocean envelope [{lo}, {hi}] (min={np.nanmin(a):.3f}, max={np.nanmax(a):.3f})")

    # coordinate integrity
    for c in ("time", "lat", "lon"):
        if c not in ds.coords:
            continue
        vals = ds[c].values
        if len(np.unique(vals)) != len(vals):
            out.append(f"COORD: duplicate values on {c}")
        if c in ("lat", "lon") and vals.size > 1 and not np.all(np.diff(vals) > 0):
            out.append(f"COORD: {c} is not strictly ascending")
    if "lon" in ds.coords and float(ds.lon.max()) > 180.0:
        out.append("COORD: longitude exceeds 180 - 0-360 convention not normalised")

    return out
