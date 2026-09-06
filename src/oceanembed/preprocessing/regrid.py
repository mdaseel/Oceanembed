"""Horizontal regridding onto the canonical 0.25 deg grid, and vertical
interpolation of the GLORYS target onto requested depths.

First-pass method for the Phase 6A smoke test: xarray/scipy linear
interpolation. Two rules are enforced rather than assumed:

  * land is never filled - ``fill_value=None`` keeps NaN where the source is
    NaN, and no extrapolation is done beyond the source footprint;
  * vertical interpolation always uses the two bracketing native levels and
    reports them, so a nearest-neighbour snap can never happen silently.
"""
from __future__ import annotations

import numpy as np
import xarray as xr

from ..grid import canonical_lat, canonical_lon


def regrid_horizontal(ds: xr.Dataset, method: str = "linear") -> xr.Dataset:
    """Interpolate a lat/lon dataset onto the canonical grid.

    NaNs propagate: a target cell whose source neighbours include NaN (land,
    retrieval gap) becomes NaN. This is deliberate - see STEP 8, "do NOT
    extrapolate values across land simply to make the grid complete".
    """
    lat, lon = canonical_lat(), canonical_lon()
    out = ds.interp(lat=lat, lon=lon, method=method,
                    kwargs={"bounds_error": False, "fill_value": np.nan})
    out.attrs = dict(ds.attrs)
    out.attrs["regrid_method"] = f"xarray.interp({method}), no land fill, no extrapolation"
    return out


def bracketing_levels(native: np.ndarray, target: float) -> tuple[float, float]:
    """Return the two native levels straddling ``target``.

    If ``target`` lies outside the native range, the nearest single level is
    returned twice - the caller must report that as clamping, not silently
    treat it as interpolation.
    """
    native = np.asarray(native, dtype="float64")
    if target <= native.min():
        return float(native.min()), float(native.min())
    if target >= native.max():
        return float(native.max()), float(native.max())
    below = float(native[native <= target].max())
    above = float(native[native >= target].min())
    return below, above


def interp_depths(da: xr.DataArray, depths: list[float],
                  depth_dim: str = "depth") -> tuple[xr.DataArray, dict]:
    """Linearly interpolate a depth-resolved DataArray onto ``depths``.

    Returns (interpolated, provenance) where provenance maps each requested
    depth to the native levels used and whether it was clamped.
    """
    native = np.asarray(da[depth_dim].values, dtype="float64")
    lo_native, hi_native = float(native.min()), float(native.max())

    provenance = {}
    for d in depths:
        lo, hi = bracketing_levels(native, d)
        provenance[float(d)] = {
            "native_below_m": lo,
            "native_above_m": hi,
            "clamped": bool(lo == hi),
            "method": "nearest-level clamp (target outside native range)"
            if lo == hi else "linear between bracketing levels",
        }

    # A target outside the native range (0 m sits above GLORYS's shallowest
    # level, 0.494 m) must CLAMP to the nearest level, not silently become NaN.
    # Interpolate at the clipped positions, then relabel to what was asked for.
    # The clamp is already recorded in ``provenance`` so it can never pass
    # unnoticed as though it were interpolation.
    clipped = [float(np.clip(d, lo_native, hi_native)) for d in depths]
    out = da.interp({depth_dim: clipped}, method="linear",
                    kwargs={"bounds_error": False, "fill_value": np.nan})
    out = out.assign_coords({depth_dim: [float(d) for d in depths]})
    return out, provenance
