"""Harmonise an NRT product onto the FROZEN OceanEmbed input contract.

The rules are copied from the Phase 6A.5 pipeline deliberately, not re-invented:
same 1 degree download pad, same ascending-latitude and [-180,180) conventions,
same xarray linear regridding onto the canonical 101x241 grid, NaN propagated,
no land fill, no extrapolation. The frozen feature scaler is applied later and
is never refitted - measuring training-serving shift is the entire point, so
normalising NRT data by NRT statistics would erase the thing being measured.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..preprocessing.regrid import regrid_horizontal
from ..preprocessing.standardize import (ensure_ascending_lat, normalise_longitude,
                                         normalise_time_daily)


def to_canonical(ds: xr.Dataset, method: str = "linear") -> xr.Dataset:
    """Exactly the training regridding path - the same function, not a copy.

    Calling ``regrid_horizontal`` rather than reimplementing it is deliberate:
    if the NRT path and the training path ever diverged, every compatibility
    number in this phase would silently be measuring that divergence instead of
    the product difference.
    """
    ds, _ = ensure_ascending_lat(ds)
    ds, _ = normalise_longitude(ds)
    out = regrid_horizontal(ds, method=method)
    # OSCAR arrives (time, lon, lat); the contract is (time, lat, lon) and a
    # silently transposed field would compare cleanly against nothing.
    return out.transpose("time", "lat", "lon", missing_dims="ignore")


def rename_coords(ds: xr.Dataset) -> xr.Dataset:
    ren = {}
    for a, b in (("latitude", "lat"), ("longitude", "lon"), ("nav_lat", "lat"),
                 ("nav_lon", "lon")):
        if a in ds.coords or a in ds.dims:
            ren[a] = b
    return ds.rename(ren) if ren else ds


def harmonise_sst(ds: xr.Dataset) -> xr.Dataset:
    """OSTIA NRT: kelvin -> degC, identical to the training conversion."""
    ds = rename_coords(ds)
    out = ds[["analysed_sst"]].rename({"analysed_sst": "sst"})
    out["sst"] = out["sst"] - 273.15
    out["sst"].attrs = {"units": "degC", "original_units": "kelvin",
                        "unit_conversion": "minus 273.15"}
    return to_canonical(normalise_time_daily(out))


def harmonise_sla(ds: xr.Dataset) -> xr.Dataset:
    ds = rename_coords(ds)
    out = ds[["sla"]]
    out["sla"].attrs = {"units": "m", "unit_conversion": "none"}
    return to_canonical(normalise_time_daily(out))


def harmonise_smos_sss(ds: xr.Dataset, use_rain_corrected: bool = False,
                       require_good_qc: bool = True) -> xr.Dataset:
    """SMOS CATDS L3: apply provider QC BEFORE anything else.

    QC flag 0 marks the qualified retrievals; anything else is dropped rather
    than repaired. True missingness is preserved - this product is gappy by
    construction and pretending otherwise would be the error.
    """
    ds = rename_coords(ds)
    var = ("Sea_Surface_Salinity_Rain_Corrected" if use_rain_corrected
           else "Sea_Surface_Salinity")
    sss = ds[var]
    if require_good_qc and "Sea_Surface_Salinity_QC" in ds:
        sss = sss.where(ds["Sea_Surface_Salinity_QC"] == 0)
    sss = sss.where((sss > 2.0) & (sss < 45.0))     # physical envelope
    out = xr.Dataset({"sss": sss})
    out["sss"].attrs = {"units": "PSU", "original_units": "0.001",
                        "qc": "Sea_Surface_Salinity_QC == 0 retained",
                        "source_variable": var}
    return to_canonical(normalise_time_daily(out))


def harmonise_wind_hourly(ds: xr.Dataset) -> xr.Dataset:
    """Copernicus NRT wind: hourly -> DAILY MEAN OF U AND V INDEPENDENTLY.

    Averaging speed and direction instead would bias the daily mean whenever the
    wind veers, which is exactly what happens across a monsoon transition. The
    training CCMP aggregation used the same U/V rule.
    """
    ds = rename_coords(ds)
    out = ds[["eastward_wind", "northward_wind"]].rename(
        {"eastward_wind": "wind_u", "northward_wind": "wind_v"})
    out = out.resample(time="1D").mean(skipna=True)
    for v in ("wind_u", "wind_v"):
        out[v].attrs = {"units": "m s-1",
                        "temporal_aggregation": "daily mean of the hourly component; "
                                                "U and V averaged independently"}
    return to_canonical(normalise_time_daily(out))


def harmonise_oscar(ds: xr.Dataset) -> xr.Dataset:
    """OSCAR NRT: total u/v, 0-360 longitude, cftime calendar - as in training."""
    if "lat" in ds.dims and "latitude" in ds.dims:
        ds = ds.rename({"latitude": "lat_dim"}) if "latitude" in ds.dims else ds
    ren = {}
    for d in list(ds.dims):
        if d == "latitude" and "lat" in ds.coords:
            ren[d] = "lat"
        if d == "longitude" and "lon" in ds.coords:
            ren[d] = "lon"
    if ren:
        ds = ds.rename(ren)
    out = ds[["u", "v"]].rename({"u": "current_u", "v": "current_v"})
    for v in ("current_u", "current_v"):
        out[v].attrs = {"units": "m s-1", "unit_conversion": "none"}
    out = normalise_time_daily(out)
    return to_canonical(out)


def compare_fields(ref: np.ndarray, nrt: np.ndarray) -> dict:
    """Distribution and error statistics on the COMMON valid support only."""
    both = np.isfinite(ref) & np.isfinite(nrt)
    n = int(both.sum())
    if n < 2:
        return {"n_common": n}
    a, b = ref[both].astype("float64"), nrt[both].astype("float64")
    d = b - a
    out = {
        "n_common": n,
        "ref_missing_frac": float(1 - np.isfinite(ref).mean()),
        "nrt_missing_frac": float(1 - np.isfinite(nrt).mean()),
        "common_support_frac": float(both.mean()),
        "ref_mean": float(a.mean()), "nrt_mean": float(b.mean()),
        "ref_std": float(a.std()), "nrt_std": float(b.std()),
        "bias": float(d.mean()), "rmse": float(np.sqrt((d ** 2).mean())),
        "mae": float(np.abs(d).mean()),
        "correlation": float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else np.nan,
        "std_ratio": float(b.std() / a.std()) if a.std() > 0 else np.nan,
        "ref_p01": float(np.percentile(a, 1)), "nrt_p01": float(np.percentile(b, 1)),
        "ref_p50": float(np.percentile(a, 50)), "nrt_p50": float(np.percentile(b, 50)),
        "ref_p99": float(np.percentile(a, 99)), "nrt_p99": float(np.percentile(b, 99)),
    }
    return out


def gradient_stats(field: np.ndarray) -> dict:
    """Spatial gradient magnitude - sensitive to effective resolution."""
    f = np.where(np.isfinite(field), field, np.nan)
    gy, gx = np.gradient(f)
    g = np.sqrt(gy ** 2 + gx ** 2)
    ok = np.isfinite(g)
    if not ok.any():
        return {"mean_gradient": np.nan, "p95_gradient": np.nan}
    return {"mean_gradient": float(np.nanmean(g)),
            "p95_gradient": float(np.nanpercentile(g[ok], 95))}
