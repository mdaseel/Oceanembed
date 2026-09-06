"""Ocean-aware spatial collocation of gridded fields onto Argo positions.

One fixed method, declared before any metric was computed, so the choice cannot
drift toward whichever answer looks best:

  1. Bilinear interpolation over the four surrounding grid cells, using only
     cells that are WET for the field in question. Weights of dry cells are
     dropped and the remaining weights renormalised, so the interpolation never
     mixes land into an ocean value.
  2. If fewer than two of the four surrounding cells are wet, fall back to the
     nearest wet cell within one grid step.
  3. If neither succeeds, the profile is unmatched at that depth for every
     model alike.

The method is identical for L0, L1, L2 and GLORYS, and the accepted-sample
population is intersected across all four afterwards, so no model can gain
samples through more permissive missingness.
"""
from __future__ import annotations

import numpy as np

METHOD = "ocean_aware_bilinear_then_nearest_wet_within_1_cell"


def bracket_indices(axis: np.ndarray, value: float) -> tuple[int, int, float]:
    """Return (i0, i1, w) with axis[i0] <= value <= axis[i1] and weight w toward i1."""
    n = axis.size
    j = int(np.searchsorted(axis, value))
    if j <= 0:
        return 0, 0, 0.0
    if j >= n:
        return n - 1, n - 1, 0.0
    i0, i1 = j - 1, j
    span = axis[i1] - axis[i0]
    w = 0.0 if span == 0 else float((value - axis[i0]) / span)
    return i0, i1, w


def interp_point(field: np.ndarray, lat_axis: np.ndarray, lon_axis: np.ndarray,
                 lat: float, lon: float) -> tuple[float, str]:
    """Interpolate a single (lat, lon) from a 2-D field. NaN marks land/missing.

    Returns (value, how) where ``how`` records which rule fired.
    """
    if not (lat_axis[0] <= lat <= lat_axis[-1] and lon_axis[0] <= lon <= lon_axis[-1]):
        return np.nan, "outside_domain"

    i0, i1, wy = bracket_indices(lat_axis, lat)
    j0, j1, wx = bracket_indices(lon_axis, lon)

    corners = [(i0, j0, (1 - wy) * (1 - wx)),
               (i0, j1, (1 - wy) * wx),
               (i1, j0, wy * (1 - wx)),
               (i1, j1, wy * wx)]
    vals = np.array([field[i, j] for i, j, _ in corners], dtype="float64")
    wts = np.array([w for _, _, w in corners], dtype="float64")
    wet = np.isfinite(vals)

    if wet.sum() >= 2 and wts[wet].sum() > 1e-12:
        return float(np.sum(vals[wet] * wts[wet]) / wts[wet].sum()), "bilinear_wet"

    # fallback: nearest wet cell among the same four, by distance not weight
    if wet.any():
        d = [np.hypot(lat_axis[i] - lat, lon_axis[j] - lon)
             for (i, j, _), ok in zip(corners, wet) if ok]
        v = [vals[k] for k in range(4) if wet[k]]
        return float(v[int(np.argmin(d))]), "nearest_wet"
    return np.nan, "no_wet_neighbour"


def interp_profile_stack(stack: np.ndarray, lat_axis: np.ndarray, lon_axis: np.ndarray,
                         lat: float, lon: float):
    """Interpolate a (n_depth, nlat, nlon) stack at one position.

    Returns (values[n_depth], how[n_depth]).
    """
    n = stack.shape[0]
    out = np.full(n, np.nan)
    how = np.empty(n, dtype=object)
    for k in range(n):
        out[k], how[k] = interp_point(stack[k], lat_axis, lon_axis, lat, lon)
    return out, how


def nearest_grid_cell(lat_axis: np.ndarray, lon_axis: np.ndarray,
                      lat: float, lon: float) -> tuple[int, int, float]:
    """Nearest cell indices and the great-circle-ish offset in degrees."""
    i = int(np.abs(lat_axis - lat).argmin())
    j = int(np.abs(lon_axis - lon).argmin())
    return i, j, float(np.hypot(lat_axis[i] - lat, lon_axis[j] - lon))
