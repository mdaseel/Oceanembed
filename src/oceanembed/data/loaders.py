"""Per-product loaders. One function per product, deliberately NOT merged into
a single generic reader - each source has its own coordinate quirks and each
needs its own documented handling.

Every loader returns an xarray.Dataset with:
  dims/coords : time (daily, 00:00 UTC), lat (ascending), lon ([-180,180) asc)
  variables   : canonical OceanEmbed names
  attrs       : ``source_product``, ``source_files``, and any unit conversion

Loaders return data on the *native* horizontal grid, subset to the padded
domain. Regridding onto the canonical grid is a separate, explicit step.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import xarray as xr

from ..config import EAST, NORTH, REPO_ROOT, SOUTH, WEST
from ..preprocessing import standardize as st

PAD = 1.0  # degrees of halo kept so interpolation has neighbours at the edge


def _finish(ds: xr.Dataset, product: str, files: list[str], notes: dict) -> xr.Dataset:
    ds = st.rename_coords(ds)
    ds, flipped = st.ensure_ascending_lat(ds)
    ds, lon_conv = st.normalise_longitude(ds)
    ds = st.normalise_time_daily(ds)
    ds = ds.sortby("time")
    ds = st.subset_domain(ds, SOUTH, NORTH, WEST, EAST, pad=PAD)
    st.check_no_duplicate_coords(ds)
    ds.attrs = {
        "source_product": product,
        "source_files": "; ".join(Path(f).name for f in files),
        "n_source_files": len(files),
        "latitude_flipped_to_ascending": str(flipped),
        "longitude_converted_from_0_360": str(lon_conv),
        **{k: str(v) for k, v in notes.items()},
    }
    return ds


def _paths(pattern: str) -> list[str]:
    files = sorted(glob.glob(str(REPO_ROOT / pattern)))
    if not files:
        raise FileNotFoundError(f"no files matched {pattern}")
    return files


# --------------------------------------------------------------------- SST
def load_ostia(pattern: str = "data/raw/ostia/*.nc") -> xr.Dataset:
    """OSTIA L4 REP SST (DOI 10.48670/moi-00168). Kelvin -> degC."""
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    out = xr.Dataset({"sst": st.kelvin_to_celsius(ds["analysed_sst"])})
    out = out.assign_coords(ds.coords)
    return _finish(out, "OSTIA L4 REP (METOFFICE-GLO-SST-L4-REP-OBS-SST)", files,
                   {"doi": "10.48670/moi-00168", "native_resolution_deg": 0.05,
                    "unit_conversion": "K -> degC"})


def load_avhrr_oi(pattern: str = "data/raw/_extracted/Ocean_embed_datas/sst/*.nc") -> xr.Dataset:
    """NOAA/NCEI OISST v2.1 (AVHRR-OI) - the SST actually supplied in the
    archive. Kept as a documented fallback / cross-check against OSTIA."""
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords")
    out = xr.Dataset({"sst": st.kelvin_to_celsius(ds["analysed_sst"])})
    out = out.assign_coords({c: ds[c] for c in ("lat", "lon", "time")})
    return _finish(out, "NOAA/NCEI OISST v2.1 (AVHRR-OI)", files,
                   {"doi": "10.5067/GHAAO-4BC21", "native_resolution_deg": 0.25,
                    "unit_conversion": "K -> degC",
                    "caveat": "substitute for the PS-mandated OSTIA"})


# --------------------------------------------------------------------- SSS
def load_smap_sss(pattern: str = "data/raw/_extracted/Ocean_embed_datas/sss/SMAP_L3_SSS_*_8DAYS_V5.0.nc") -> xr.Dataset:
    """SMAP JPL L3 CAP v5.0, 8-day running mean stamped daily.

    Each file carries a scalar time; they are concatenated along a new time
    axis. Latitude is descending in the source and is flipped.
    """
    files = _paths(pattern)
    parts = []
    for f in files:
        d = xr.open_dataset(f)
        sss = d["smap_sss"]
        if "time" not in sss.dims:
            sss = sss.expand_dims(time=np.atleast_1d(d["time"].values))
        parts.append(xr.Dataset({"sss": sss}))
        d.close()
    ds = xr.concat(parts, dim="time")
    ds["sss"].attrs["units"] = "PSU"
    ds["sss"].attrs["original_units"] = "1e-3"
    ds["sss"].attrs["unit_conversion"] = "none (1e-3 is numerically PSU)"
    return _finish(ds, "SMAP JPL L3 CAP v5.0 8-day running mean", files,
                   {"doi": "10.5067/SMP50-3TPCS", "native_resolution_deg": 0.25,
                    "temporal_caveat": "8-day trailing mean stamped daily, NOT a true daily field"})


def load_multiobs_sss(pattern: str = "data/raw/sss_multiobs/*/*.nc") -> xr.Dataset:
    """Copernicus Multi-Observation Global Ocean SSS (DOI 10.48670/moi-00051).

    Dataset ``cmems_obs-mob_glo_phy-sss_my_multi_P1D``, 0.125 deg, genuinely
    daily L4 multi-observation analysis. This REPLACES the Phase 6A smoke-test
    SMAP 8-day running mean as the model-ready SSS.

    The salinity variable is ``sos``; the product also carries ``dos`` (sea
    surface density), which is deliberately not requested or used.
    """
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    out = ds[["sos"]].rename({"sos": "sss"})
    # The product carries a singleton depth axis at 0.0 m. Drop it so the
    # channel is (time, lat, lon) like every other surface variable.
    if "depth" in out.dims:
        assert out.sizes["depth"] == 1, f"unexpected depth size {out.sizes['depth']}"
        out = out.squeeze("depth", drop=True)
    out["sss"].attrs["units"] = "PSU"
    out["sss"].attrs["original_name"] = "sos"
    out["sss"].attrs["original_units"] = ".001"
    return _finish(out, "CMEMS MULTIOBS SSS (cmems_obs-mob_glo_phy-sss_my_multi_P1D)", files,
                   {"doi": "10.48670/moi-00051", "native_resolution_deg": 0.125,
                    "temporal_resolution": "daily (true daily L4 analysis)",
                    "unit_conversion": "none",
                    "replaces": "SMAP JPL L3 CAP v5.0 8-day running mean (Phase 6A smoke test)"})


# --------------------------------------------------------------------- SLA
def load_duacs_sla(pattern: str = "data/raw/duacs/*.nc") -> xr.Dataset:
    """DUACS L4 sea level anomaly (DOI 10.48670/moi-00145), 0.25 deg daily."""
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    out = xr.Dataset({"sla": ds["sla"]})
    return _finish(out, "DUACS L4 C3S two-sat 0.25deg daily", files,
                   {"doi": "10.48670/moi-00145", "native_resolution_deg": 0.25,
                    "unit_conversion": "none (m)"})


# ---------------------------------------------------------------- CURRENTS
def load_oscar(pattern: str = "data/raw/_extracted/Ocean_embed_datas/OSCAR/oscar_currents_final_*.nc") -> xr.Dataset:
    """OSCAR L4_OC_FINAL v2.0 total surface currents.

    Three quirks handled here:
      * dims are ``longitude``/``latitude`` while the coord variables attached
        to them are named ``lat``/``lon``;
      * longitude uses the 0-360 convention;
      * time uses a cftime Julian calendar.
    ``u``/``v`` (total) are taken, not ``ug``/``vg`` (geostrophic only).
    """
    files = _paths(pattern)
    parts = []
    for f in files:
        d = xr.open_dataset(f)
        # Attach the lat/lon coord variables to their actual dims, then drop
        # the mismatched originals.
        lat = np.asarray(d["lat"].values).ravel()
        lon = np.asarray(d["lon"].values).ravel()
        sub = d[["u", "v"]].drop_vars([c for c in ("lat", "lon") if c in d.coords])
        sub = sub.assign_coords(latitude=("latitude", lat), longitude=("longitude", lon))
        sub = sub.transpose("time", "latitude", "longitude")
        parts.append(sub.rename({"u": "current_u", "v": "current_v"}))
        d.close()
    ds = xr.concat(parts, dim="time")
    for v in ("current_u", "current_v"):
        ds[v].attrs["units"] = "m s-1"
    return _finish(ds, "OSCAR L4_OC_FINAL v2.0 (total currents u,v)", files,
                   {"doi": "10.5067/OSCAR-25F20", "native_resolution_deg": 0.25,
                    "variables_used": "u,v (total) - NOT ug,vg (geostrophic)",
                    "depth_caveat": "represents the average of the top ~30 m",
                    "calendar_conversion": "cftime Julian -> proleptic datetime64"})


# ------------------------------------------------------------------- WINDS
def load_ccmp(pattern: str = "data/raw/_extracted/Ocean_embed_datas/ccmp/CCMP_Wind_Analysis_*_V03.1_L4.nc") -> xr.Dataset:
    """CCMP v3.1 6-hourly L4 winds, aggregated to daily.

    U and V are averaged independently over the four 6-hourly analyses of each
    day. Wind speed magnitude is deliberately NOT used - averaging speed would
    destroy direction, and averaging components preserves the daily-mean vector
    stress that the model needs.
    """
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords")
    out = ds[["uwnd", "vwnd"]].rename({"uwnd": "wind_u", "vwnd": "wind_v"})
    # 6-hourly -> daily mean of the vector components, done BEFORE the time
    # coordinate is floored so the four sub-daily steps are actually grouped.
    n_before = out.sizes["time"]
    out = out.resample(time="1D").mean(skipna=True)
    for v in ("wind_u", "wind_v"):
        out[v].attrs["units"] = "m s-1"
    return _finish(out, "CCMP v3.1 6-hourly L4 (daily vector mean)", files,
                   {"doi": "10.5067/CCMP-6HW10M-L4V31", "native_resolution_deg": 0.25,
                    "temporal_aggregation":
                        f"{n_before} x 6-hourly -> daily mean of U and V independently "
                        "(magnitude NOT used)"})


# ------------------------------------------------------------------ TARGET
def load_glorys(pattern: str = "data/raw/glorys/*.nc") -> xr.Dataset:
    """GLORYS12V1 daily potential temperature (DOI 10.48670/moi-00021)."""
    files = _paths(pattern)
    ds = xr.open_mfdataset(files, combine="by_coords") if len(files) > 1 else xr.open_dataset(files[0])
    out = ds[["thetao"]]
    out = st.rename_coords(out)
    out, flipped = st.ensure_ascending_lat(out)
    out, lon_conv = st.normalise_longitude(out)
    out = st.normalise_time_daily(out).sortby("time")
    out = st.subset_domain(out, SOUTH, NORTH, WEST, EAST, pad=PAD)
    st.check_no_duplicate_coords(out)
    out.attrs = {
        "source_product": "GLORYS12V1 (cmems_mod_glo_phy_my_0.083deg_P1D-m)",
        "source_files": "; ".join(Path(f).name for f in files),
        "doi": "10.48670/moi-00021",
        "native_resolution_deg": 0.0833333,
        "latitude_flipped_to_ascending": str(flipped),
        "longitude_converted_from_0_360": str(lon_conv),
        "n_native_depth_levels": int(out.sizes.get("depth", 0)),
    }
    return out
