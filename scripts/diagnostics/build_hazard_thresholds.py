"""Execute the frozen hazard threshold rule — once, on the TRAIN split only.

The rule is fixed by ``outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md``, written
before any threshold number existed:

    quantity   TCHP from the frozen Phase 7C diagnostic
    period     TRAIN split only, 2015-01-01 .. 2020-12-31, every 5th day
    region     the PoC domain, one distribution (not per basin), all seasons
    cells      TCHP defined AND physically supported - exactly the cells that
               can ever carry a category
    output     p50 -> MODERATE, p75 -> ELEVATED, p90 -> HIGH

Using the TRAIN split keeps test-period information out of the category
definition. Using the model's own distribution keeps the measured reconstruction
bias out of the labels.

    python scripts/diagnostics/build_hazard_thresholds.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import (D26Status, PhysicalSupport,  # noqa: E402
                                    bathymetry_provenance, d26_tchp,
                                    local_water_depth, qualify)
from oceanembed.diagnostics.hazard import THRESHOLDS_PATH  # noqa: E402
from oceanembed.replay.engine import ReplayEngine  # noqa: E402

TRAIN_START, TRAIN_END, STRIDE = "2015-01-01", "2020-12-31", 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="smoke-test only")
    args = ap.parse_args()

    dates = list(pd.date_range(TRAIN_START, TRAIN_END, freq="D")[::STRIDE])
    planned = len(dates)
    if args.limit:
        dates = dates[:args.limit]
    print(f"reference period {TRAIN_START}..{TRAIN_END} stride {STRIDE}d "
          f"-> {planned} dates, running {len(dates)}")

    engine = ReplayEngine()
    water = local_water_depth()
    stores: dict[int, xr.Dataset] = {}
    values: list[np.ndarray] = []
    used, failures = 0, []
    t0 = time.perf_counter()

    for date in dates:
        try:
            year = date.year
            if year not in stores:
                stores[year] = xr.open_zarr(
                    ROOT / "data" / "processed" / "model_ready" /
                    f"oceanembed_{year}.zarr", consolidated=True)
            store = stores[year]
            times = pd.DatetimeIndex(store.time.values).normalize()
            hit = np.flatnonzero(times == date)
            if not hit.size:
                failures.append({"date": str(date.date()), "reason": "absent from store"})
                continue
            t = int(hit[0])
            ocean = np.asarray(store["ocean_mask"].isel(time=t).values, dtype=bool)
            siv = np.asarray(store["surface_input_valid"].isel(time=t).values, dtype=bool)

            view = engine.replay_field(date)
            res = d26_tchp(view.temperature, view.depths)
            _, tchp_phys = qualify(res, water)
            # Exactly the population that can ever carry a category.
            keep = (ocean & siv
                    & (tchp_phys == PhysicalSupport.SUPPORTED)
                    & ((res.status == D26Status.OK)
                       | (res.status == D26Status.SURFACE_BELOW_26))
                    & np.isfinite(res.tchp))
            values.append(res.tchp[keep].astype("float32"))
            used += 1
        except Exception as exc:  # noqa: BLE001 - a failed date is reported
            failures.append({"date": str(date.date()),
                             "reason": f"{type(exc).__name__}: {exc}"})
        if used and used % 50 == 0:
            print(f"  {used}/{len(dates)} dates "
                  f"({(time.perf_counter()-t0)/used:.2f}s/date)")

    pooled = np.concatenate(values)
    p50, p75, p90 = (float(np.percentile(pooled, q)) for q in (50, 75, 90))

    record = {
        "protocol": "outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md",
        "indicator": "Ocean Thermal Support for Cyclone Intensification",
        "quantity": "tchp_kj_cm2",
        "reference_period": f"{TRAIN_START}..{TRAIN_END} (TRAIN split only)",
        "stride_days": STRIDE,
        "n_dates_planned": planned,
        "n_dates": used,
        "failed_dates": failures,
        "n_samples": int(pooled.size),
        "population": "TCHP defined AND PhysicalSupport.SUPPORTED, over the "
                      "whole PoC domain, all seasons, one distribution",
        "boundaries": {"p50": p50, "p75": p75, "p90": p90},
        "category_rule": "TCHP < p50 LOW; >= p50 MODERATE; >= p75 ELEVATED; "
                         ">= p90 HIGH",
        "distribution_context": {
            "min": float(pooled.min()), "max": float(pooled.max()),
            "mean": float(pooled.mean()),
            "p05": float(np.percentile(pooled, 5)),
            "p25": float(np.percentile(pooled, 25)),
            "p95": float(np.percentile(pooled, 95)),
            "fraction_below_50_kJ_cm2": float((pooled < 50.0).mean()),
        },
        "literature_anchor": {
            "value_kj_cm2": 50.0,
            "role": "DISCLOSURE ONLY - not used to set any boundary",
            "source": "Shay et al. 2000; Mainelli et al. 2008; AOML practice",
            "percentile_of_this_distribution":
                float((pooled < 50.0).mean() * 100.0),
        },
        "model": {"l2_state_dict_sha256": engine.l2_state_dict_sha256,
                  "l2_encoder_sha256": engine.l2_encoder_sha256},
        "bathymetry": {k: bathymetry_provenance()[k]
                       for k in ("dataset", "depth_sha256", "rule")},
        "argo_used": False,
        "argo_2024_status": "PROTECTED - not read by this phase",
        "wall_clock_seconds": round(time.perf_counter() - t0, 1),
    }
    THRESHOLDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLDS_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"\n{len(failures)} failed dates · {pooled.size:,} samples")
    print(f"  p50 (MODERATE) = {p50:8.2f} kJ/cm2")
    print(f"  p75 (ELEVATED) = {p75:8.2f} kJ/cm2")
    print(f"  p90 (HIGH)     = {p90:8.2f} kJ/cm2")
    print(f"  literature 50 kJ/cm2 sits at the "
          f"{record['literature_anchor']['percentile_of_this_distribution']:.1f}"
          f"th percentile of this distribution")
    print(f"wrote {THRESHOLDS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
