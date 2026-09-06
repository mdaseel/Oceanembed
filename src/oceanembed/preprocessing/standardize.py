"""Coordinate / time / unit standardisation primitives.

Every product loader routes through these so that the conventions are applied
in exactly one place. Nothing here silently repairs data values - it only
normalises *representation* (names, axis order, longitude convention, time
stamps) and performs unit conversions that are declared explicitly by the
caller and recorded in the output attributes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

# Common aliases seen across OSTIA / SMAP / OSCAR / CCMP / DUACS / GLORYS.
_LAT_ALIASES = ("lat", "latitude", "LATITUDE", "Latitude", "nav_lat", "y")
_LON_ALIASES = ("lon", "longitude", "LONGITUDE", "Longitude", "nav_lon", "x")
_TIME_ALIASES = ("time", "TIME", "Time", "t")


def _pick(ds: xr.Dataset, aliases: tuple[str, ...]) -> str | None:
    for a in aliases:
        if a in ds.dims or a in ds.coords or a in ds.variables:
            return a
    return None


def rename_coords(ds: xr.Dataset) -> xr.Dataset:
    """Rename latitude/longitude/time (dims *and* coords) to lat/lon/time.

    Handles the OSCAR case where the dimension is called ``latitude`` but the
    coordinate variable attached to it is called ``lat``.
    """
    ds = ds.copy()

    # 1. Dimensions first.
    dim_map = {}
    for d in list(ds.dims):
        if d in _LAT_ALIASES and d != "lat":
            dim_map[d] = "lat"
        elif d in _LON_ALIASES and d != "lon":
            dim_map[d] = "lon"
        elif d in _TIME_ALIASES and d != "time":
            dim_map[d] = "time"
    if dim_map:
        # A dim rename collides if a *coord* of the target name already exists
        # on a different dim; drop-and-reattach handles that.
        for old, new in list(dim_map.items()):
            if new in ds.coords and new not in ds.dims:
                vals = ds[new].values
                ds = ds.drop_vars(new)
                ds = ds.rename({old: new})
                ds = ds.assign_coords({new: (new, np.asarray(vals).ravel())})
                dim_map.pop(old)
        if dim_map:
            ds = ds.rename(dim_map)

    # 2. Any remaining coord-name aliases.
    coord_map = {}
    for c in list(ds.coords):
        if c in _LAT_ALIASES and c != "lat" and "lat" not in ds.coords:
            coord_map[c] = "lat"
        elif c in _LON_ALIASES and c != "lon" and "lon" not in ds.coords:
            coord_map[c] = "lon"
        elif c in _TIME_ALIASES and c != "time" and "time" not in ds.coords:
            coord_map[c] = "time"
    if coord_map:
        ds = ds.rename(coord_map)
    return ds


def ensure_ascending_lat(ds: xr.Dataset) -> tuple[xr.Dataset, bool]:
    """Flip latitude to ascending (south -> north) if needed."""
    lat = ds["lat"].values
    if lat.size > 1 and lat[0] > lat[-1]:
        return ds.isel(lat=slice(None, None, -1)), True
    return ds, False


def normalise_longitude(ds: xr.Dataset) -> tuple[xr.Dataset, bool]:
    """Convert longitude to [-180, 180) and re-sort ascending.

    Returns (dataset, converted) where ``converted`` says whether the source
    used the 0-360 convention.
    """
    lon = ds["lon"].values.astype("float64")
    was_0_360 = bool(np.nanmax(lon) > 180.0)
    if was_0_360:
        lon = ((lon + 180.0) % 360.0) - 180.0
        ds = ds.assign_coords(lon=("lon", lon))
    ds = ds.sortby("lon")
    return ds, was_0_360


def normalise_time_daily(ds: xr.Dataset) -> xr.Dataset:
    """Coerce the time coordinate to datetime64 floored to 00:00 UTC.

    Products stamp the same calendar day differently (OISST 00:00, SMAP 12:00,
    OSCAR cftime-Julian 00:00, CCMP 6-hourly). Flooring to the day is what makes
    them joinable; it is a *labelling* change, not a resampling.
    """
    t = ds["time"].values
    # cftime (OSCAR uses a Julian calendar) -> proleptic Gregorian datetime64
    if t.dtype == object:
        t = np.array([np.datetime64(f"{x.year:04d}-{x.month:02d}-{x.day:02d}") for x in t])
    idx = pd.DatetimeIndex(pd.to_datetime(t)).floor("D")
    return ds.assign_coords(time=("time", idx.values))


def subset_domain(ds: xr.Dataset, south: float, north: float,
                  west: float, east: float, pad: float = 0.0) -> xr.Dataset:
    """Slice to the domain (optionally padded) assuming ascending lat/lon."""
    return ds.sel(lat=slice(south - pad, north + pad),
                  lon=slice(west - pad, east + pad))


def kelvin_to_celsius(da: xr.DataArray) -> xr.DataArray:
    """Explicit, recorded K -> degC conversion."""
    out = da - 273.15
    out.attrs = dict(da.attrs)
    out.attrs["units"] = "degC"
    out.attrs["unit_conversion"] = "kelvin -> degC (subtracted 273.15)"
    out.attrs["original_units"] = da.attrs.get("units", "kelvin")
    return out


def check_no_duplicate_coords(ds: xr.Dataset) -> None:
    """Raise if any coordinate axis contains repeated values."""
    for c in ("time", "lat", "lon"):
        if c not in ds.coords:
            continue
        v = ds[c].values
        if len(np.unique(v)) != len(v):
            raise ValueError(f"duplicate values on coordinate {c!r}")
