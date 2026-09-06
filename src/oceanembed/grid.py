"""The ONE canonical OceanEmbed target grid.

0.25 deg x 0.25 deg, latitude 5N..30N inclusive, longitude 45E..105E inclusive.
Every product is regridded onto this and nothing else.

Conventions fixed here and enforced everywhere downstream:
  * latitude  ascending  (south -> north)
  * longitude ascending, [-180, 180) convention (the whole domain is positive
    east, so 45..105 is unchanged, but the convention still matters for
    normalising 0-360 sources such as OSCAR and CCMP).
"""
from __future__ import annotations

import numpy as np
import xarray as xr

from .config import EAST, NORTH, RESOLUTION, SOUTH, WEST


def _axis(start: float, stop: float, step: float) -> np.ndarray:
    """Inclusive-of-endpoint axis, built from an integer cell count.

    The count is *derived*, never hard-coded, then asserted to reproduce the
    requested endpoints exactly (to floating tolerance).
    """
    n = int(round((stop - start) / step)) + 1
    ax = start + step * np.arange(n, dtype="float64")
    assert abs(ax[0] - start) < 1e-9, (ax[0], start)
    assert abs(ax[-1] - stop) < 1e-9, (ax[-1], stop)
    return ax


def canonical_lat() -> np.ndarray:
    return _axis(SOUTH, NORTH, RESOLUTION)


def canonical_lon() -> np.ndarray:
    return _axis(WEST, EAST, RESOLUTION)


def canonical_grid() -> xr.Dataset:
    """Return an empty Dataset carrying only the canonical coordinates."""
    lat, lon = canonical_lat(), canonical_lon()
    ds = xr.Dataset(coords={"lat": ("lat", lat), "lon": ("lon", lon)})
    ds["lat"].attrs = {"units": "degrees_north", "standard_name": "latitude",
                       "axis": "Y", "long_name": "latitude"}
    ds["lon"].attrs = {"units": "degrees_east", "standard_name": "longitude",
                       "axis": "X", "long_name": "longitude"}
    ds.attrs = {
        "grid_name": "oceanembed_canonical_0p25",
        "resolution_deg": RESOLUTION,
        "lat_min": float(lat[0]), "lat_max": float(lat[-1]), "n_lat": int(lat.size),
        "lon_min": float(lon[0]), "lon_max": float(lon[-1]), "n_lon": int(lon.size),
        "n_cells": int(lat.size * lon.size),
        "lat_order": "ascending",
        "lon_convention": "-180_180",
    }
    return ds


def normalise_longitude(lon: np.ndarray) -> np.ndarray:
    """Map any longitude array to the [-180, 180) convention."""
    return ((np.asarray(lon, dtype="float64") + 180.0) % 360.0) - 180.0


def describe() -> dict:
    g = canonical_grid()
    return dict(g.attrs)


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(describe(), indent=2))
