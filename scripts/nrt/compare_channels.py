"""Phase 6C-D Steps 9-10: RAW channel-level compatibility, no calibration.

The NRT products are compared to the reference products exactly as delivered.
No affine correction, no quantile mapping, no learned adjustment - a raw
baseline has to exist before anyone can argue for an adapter.

Only surface input channels are opened from the reference archive. The target
variables are never read; a guard enforces it, because the overlap window falls
inside the locked test split (see the pre-registration, section 1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import xarray as xr

from oceanembed.config import REPO_ROOT
from oceanembed.ml.features import SURFACE
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.nrt.compatibility import (PREREGISTERED, channel_stats, classify,
                                          pooled_from_daily, region_masks)

MR = REPO_ROOT / "data" / "processed" / "model_ready"
NRT = REPO_ROOT / "data" / "processed" / "nrt"
TAB = REPO_ROOT / "outputs" / "tables"
OUTD = REPO_ROOT / "outputs" / "nrt"

ALLOWED_REFERENCE_VARS = set(SURFACE) | {"ocean_mask", "surface_input_valid"}

# channel -> (reference variable, nrt file key, nrt variable)
CHANNEL_SOURCES = [
    ("sst", "sst", "sst_nrt", "sst"),
    ("sss", "sss", "sss_nrt_smos", "sss"),
    ("sss", "sss", "sss_nrt_smap", "sss"),
    ("sla", "sla", "sla_nrt", "sla"),
    ("current_u", "current_u", "currents_nrt", "current_u"),
    ("current_v", "current_v", "currents_nrt", "current_v"),
    ("wind_u", "wind_u", "wind_nrt", "wind_u"),
    ("wind_v", "wind_v", "wind_nrt", "wind_v"),
]


def open_reference(year: int = 2024) -> xr.Dataset:
    ds = xr.open_zarr(MR / f"oceanembed_{year}.zarr", consolidated=True)
    keep = [v for v in ds.data_vars if v in ALLOWED_REFERENCE_VARS]
    opened = set(keep)
    assert not any(v.startswith(("temp_", "target_valid_")) for v in opened), \
        "LEAK: a target variable was selected from the reference archive"
    return ds[keep]


def main() -> int:
    fs = ZScoreScaler.from_json(REPO_ROOT / "outputs" / "baselines"
                                / "phase6b_feature_scaler.json")
    assert fs.fitted_on == "train"
    sigma = dict(zip(fs.names, fs.std))

    ref = open_reference(2024)
    ocean = np.asarray(ref["ocean_mask"].values, dtype=bool)
    if ocean.ndim == 3:
        ocean = ocean[0]
    regions = region_masks(ref.lat.values, ref.lon.values)
    print(f"reference variables opened: {sorted(ref.data_vars)}")
    print(f"ocean cells: {int(ocean.sum())} of {ocean.size}\n")

    daily_rows, pooled_rows = [], []
    for channel, rvar, key, nvar in CHANNEL_SOURCES:
        path = NRT / f"{key}_canonical.nc"
        if not path.exists():
            print(f"{key}/{nvar}: SKIPPED (not downloaded)")
            continue
        nrt = xr.open_dataset(path)
        times = pd.DatetimeIndex(nrt.time.values).normalize()
        rtimes = pd.DatetimeIndex(ref.time.values).normalize()
        common = times.intersection(rtimes)
        print(f"{key}/{nvar}: {len(common)} common days "
              f"({common.min().date()}..{common.max().date()})")

        rsel = ref[rvar].sel(time=common).values
        nsel = nrt[nvar].sel(time=common).values
        for i, t in enumerate(common):
            for rname, rmask in regions.items():
                s = channel_stats(rsel[i], nsel[i], rmask, ocean)
                s.update({"channel": channel, "nrt_key": key, "region": rname,
                          "date": str(t.date())})
                daily_rows.append(s)
        nrt.close()

        d = pd.DataFrame([r for r in daily_rows
                          if r["nrt_key"] == key and r["channel"] == channel])
        for rname in regions:
            sub = d[d["region"] == rname]
            pooled = pooled_from_daily(sub)
            rec = classify(pooled, float(sigma[channel]))
            rec.update({"channel": channel, "nrt_key": key, "region": rname,
                        "n_days_available": int(len(sub))})
            pooled_rows.append(rec)
            if rname == "full_nio":
                print(f"    full_nio: {rec.get('compatibility_band')}  "
                      f"{rec.get('band_reason')}  "
                      f"cov ref={rec.get('ref_coverage', float('nan')):.3f} "
                      f"nrt={rec.get('nrt_coverage', float('nan')):.3f}")

    TAB.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(daily_rows).to_csv(TAB / "phase6cd_channel_daily.csv", index=False)
    pooled = pd.DataFrame(pooled_rows)
    cols = ["channel", "nrt_key", "region", "n_days", "n_common", "ref_coverage",
            "nrt_coverage", "common_coverage", "bias", "rmsd", "mae",
            "correlation_daily_median", "std_ratio", "grad_ratio", "sigma_train",
            "rmsd_over_sigma", "abs_bias_over_sigma", "compatibility_band",
            "band_reason", "n_days_available"]
    pooled = pooled.reindex(columns=[c for c in cols if c in pooled.columns]
                            + [c for c in pooled.columns if c not in cols])
    pooled.to_csv(TAB / "phase6cd_channel_compatibility.csv", index=False)
    json.dump({"preregistered_bands": PREREGISTERED,
               "calibration_applied": "NONE - raw products as delivered",
               "reference_variables_opened": sorted(ref.data_vars),
               "targets_opened": []},
              open(OUTD / "compatibility_meta.json", "w"), indent=2)
    print(f"\n-> {TAB / 'phase6cd_channel_compatibility.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
