"""Spatial patch construction for the L2 satellite embedding engine.

Design notes that matter scientifically:

* MISSING IS NOT ZERO. Surface channels are standardised with the frozen
  train scaler, then missing cells are set to 0.0 - which after
  standardisation means "the training mean", a neutral value - and an
  explicit validity mask channel is carried alongside so the CNN can always
  tell "land / unavailable" from "a real value that happens to be near the
  mean". Channels are therefore 7 data + 1 mask = 8.

* DOMAIN EDGES ARE PADDED, NOT DROPPED. A 17x17 patch centred within 8 cells
  of the boundary would run off the domain. The field is zero-padded by
  HALF = patch//2 with mask=0 in the padding, so every one of the 101x241
  cells gets a deterministic patch and the model can see that the padding is
  not observation. No reflection or replication is used: those would fabricate
  plausible-looking ocean where none was observed.
"""
from __future__ import annotations

import numpy as np
import xarray as xr

from .features import SURFACE

N_DATA_CHANNELS = len(SURFACE)        # 7
N_CHANNELS = N_DATA_CHANNELS + 1      # + validity mask


def day_field(ds: xr.Dataset, t: int, scaler, patch: int) -> np.ndarray:
    """Build the padded (8, nlat+2h, nlon+2h) standardised field for one day."""
    half = patch // 2
    nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]
    raw = np.empty((N_DATA_CHANNELS, nlat, nlon), dtype="float32")
    for k, v in enumerate(SURFACE):
        raw[k] = ds[v].isel(time=t).values

    valid = np.isfinite(raw).all(axis=0)
    flat = raw.reshape(N_DATA_CHANNELS, -1).T.astype("float64")
    # standardise with the FROZEN train scaler (first 7 entries are the
    # surface channels, in the same order as SURFACE)
    z = (flat - scaler.mean[:N_DATA_CHANNELS]) / scaler.std[:N_DATA_CHANNELS]
    z = z.T.reshape(N_DATA_CHANNELS, nlat, nlon).astype("float32")
    z = np.where(valid[None, :, :], z, 0.0).astype("float32")

    out = np.zeros((N_CHANNELS, nlat + 2 * half, nlon + 2 * half), dtype="float32")
    out[:N_DATA_CHANNELS, half:half + nlat, half:half + nlon] = z
    out[N_DATA_CHANNELS, half:half + nlat, half:half + nlon] = valid.astype("float32")
    return out


def extract_patch(field: np.ndarray, i: int, j: int, patch: int) -> np.ndarray:
    """Patch centred on domain cell (i, j) of a field padded by patch//2.

    The centre of the returned patch is exactly domain cell (i, j): with the
    padding offset, field[:, i:i+patch, j:j+patch] has its middle element at
    padded index (i+half, j+half), which is domain (i, j).
    """
    return field[:, i:i + patch, j:j + patch]


def centre_value(patch_stack: np.ndarray, patch: int) -> np.ndarray:
    """The centre pixel of each patch - used to verify orientation/indexing."""
    h = patch // 2
    return patch_stack[..., h, h]
