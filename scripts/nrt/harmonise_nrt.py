"""Harmonise every downloaded NRT product onto the frozen input contract.

Each output is a canonical-grid (101 x 241) daily netCDF in the contract's own
units and variable names, ready to be dropped into the frozen ``day_field``.
Native-resolution coverage is recorded alongside post-regrid coverage so that a
gappy product's missingness is never confused with a regridding artefact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import xarray as xr

from oceanembed.config import REPO_ROOT
from oceanembed.nrt.harmonize import (harmonise_oscar, harmonise_sla,
                                      harmonise_smos_sss, harmonise_sst,
                                      harmonise_wind_hourly)

RAW = REPO_ROOT / "data" / "raw" / "nrt"
OUT = REPO_ROOT / "data" / "processed" / "nrt"


def native_coverage(da: xr.DataArray) -> float:
    v = np.isfinite(np.asarray(da.values, dtype="float64"))
    return float(v.mean())


def run(key: str, src: Path, fn, native_var: str) -> dict:
    dst = OUT / f"{key}_canonical.nc"
    with xr.open_dataset(src) as raw:
        nat = native_coverage(raw[native_var]) if native_var in raw else np.nan
        out = fn(raw)
        out.load()
    out.to_netcdf(dst)
    cov = {v: float(np.isfinite(out[v].values).mean()) for v in out.data_vars}
    print(f"  {key}: {dict(out.sizes)} native_cov={nat:.4f} "
          f"regrid_cov={ {k: round(v,4) for k,v in cov.items()} }")
    return {"key": key, "source": str(src), "output": str(dst),
            "native_valid_fraction": None if np.isnan(nat) else nat,
            "regridded_valid_fraction": cov,
            "n_times": int(out.sizes["time"]),
            "grid": [int(out.sizes["lat"]), int(out.sizes["lon"])]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    log = []

    jobs = [
        ("sst_nrt", RAW / "sst_nrt" / "sst_nrt_2024-07-01_2024-12-15.nc",
         harmonise_sst, "analysed_sst"),
        ("sla_nrt", RAW / "sla_nrt" / "sla_nrt_2024-07-01_2024-12-15.nc",
         harmonise_sla, "sla"),
        ("sss_nrt_smos", RAW / "sss_nrt_smos" / "sss_nrt_smos_2024-07-01_2024-12-15.nc",
         harmonise_smos_sss, "Sea_Surface_Salinity"),
        ("wind_nrt", RAW / "wind_nrt" / "wind_nrt_2024-07-01_2024-12-15.nc",
         harmonise_wind_hourly, "eastward_wind"),
        ("currents_nrt", RAW / "currents_nrt" / "oscar_nrt_2024-07-01_2024-12-13.nc",
         harmonise_oscar, "u"),
        ("currents_nrt_lag3", RAW / "currents_nrt" / "oscar_nrt_2024-06-28_2024-12-10.nc",
         harmonise_oscar, "u"),
    ]
    for key, src, fn, nv in jobs:
        if not src.exists():
            print(f"  {key}: MISSING {src}")
            log.append({"key": key, "error": f"missing {src}"})
            continue
        log.append(run(key, src, fn, nv))

    # SMAP is already binned onto the canonical grid by the ingest script; it is
    # copied through unchanged so that no second gridding step can touch it.
    smap = RAW / "sss_nrt_smap" / "smap_nrt_binned_daily.nc"
    if smap.exists():
        with xr.open_dataset(smap) as d:
            d.load().to_netcdf(OUT / "sss_nrt_smap_canonical.nc")
            cov = float(np.isfinite(d["sss"].values).mean())
        print(f"  sss_nrt_smap: copied, regrid_cov={cov:.4f} (binned, not interpolated)")
        log.append({"key": "sss_nrt_smap", "source": str(smap),
                    "output": str(OUT / "sss_nrt_smap_canonical.nc"),
                    "native_valid_fraction": None,
                    "regridded_valid_fraction": {"sss": cov},
                    "note": "binned from L2 swath; never interpolated"})
    else:
        print("  sss_nrt_smap: MISSING")
        log.append({"key": "sss_nrt_smap", "error": "not downloaded"})

    json.dump(log, open(REPO_ROOT / "outputs" / "nrt" / "harmonisation_log.json", "w"),
              indent=2)
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
