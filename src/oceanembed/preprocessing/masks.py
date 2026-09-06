"""Validity masks.

Two concepts are kept strictly separate, because conflating them silently
throws away shallow-water data:

  ocean_mask          - "is this cell ocean at all?"  Defined by whether the
                        GLORYS target exists at the SURFACE. A shelf cell with
                        valid temperature at 0-50 m but nothing at 1000 m is
                        still ocean.
  target_valid_<d>m   - "does a training target exist at THIS depth here?"
                        One mask per requested depth.

Nothing below the seafloor is ever invented, and no vertical extrapolation is
performed beyond valid water depth: a depth with no bracketing native GLORYS
data simply stays NaN and its validity mask is False.
"""
from __future__ import annotations

import numpy as np
import xarray as xr

SURFACE_CHANNELS = ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]


def ocean_mask(temp_surface: xr.DataArray) -> xr.DataArray:
    """Ocean = the GLORYS target is defined at the shallowest level.

    Deliberately NOT defined by deep-water validity - using a 1000 m mask as
    the definition of "ocean" would discard the entire continental shelf.
    """
    m = np.isfinite(temp_surface)
    m.name = "ocean_mask"
    m.attrs = {
        "long_name": "ocean cell (GLORYS target defined at the surface level)",
        "definition": "isfinite(temp_0m); NOT dependent on deep-water validity",
        "flag_values": "0 = land or inland water, 1 = ocean",
    }
    return m


def surface_input_valid(ds: xr.Dataset) -> xr.DataArray:
    """True where ALL seven surface predictor channels are present."""
    m = xr.ones_like(ds[SURFACE_CHANNELS[0]], dtype=bool)
    for v in SURFACE_CHANNELS:
        m = m & np.isfinite(ds[v])
    m.name = "surface_input_valid"
    m.attrs = {
        "long_name": "all seven surface predictor channels present",
        "channels": ", ".join(SURFACE_CHANNELS),
    }
    return m


def target_valid(ds: xr.Dataset, depths: list[int]) -> dict[str, xr.DataArray]:
    """One validity mask per requested depth.

    Future training must be able to mask the loss per depth, so a cell that is
    valid at 30 m but not at 300 m still contributes at 30 m.
    """
    out = {}
    for d in depths:
        name = f"temp_{int(d)}m"
        m = np.isfinite(ds[name])
        key = f"target_valid_{int(d)}m"
        m.name = key
        m.attrs = {
            "long_name": f"GLORYS target available at {d} m",
            "note": "False below the seafloor; no value is invented there",
        }
        out[key] = m
    return out


def add_all_masks(ds: xr.Dataset, depths: list[int]) -> xr.Dataset:
    """Attach ocean_mask, surface_input_valid and per-depth target masks."""
    ds = ds.copy()
    ds["ocean_mask"] = ocean_mask(ds["temp_0m"])
    ds["surface_input_valid"] = surface_input_valid(ds)
    for k, v in target_valid(ds, depths).items():
        ds[k] = v
    return ds
