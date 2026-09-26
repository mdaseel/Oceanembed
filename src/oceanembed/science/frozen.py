"""The frozen L2 forward, exposed for experiments that need a modified INPUT.

``forward_field`` is the same computation as ``ReplayEngine._infer`` - same
``day_field``, same frozen scalers, same whole-field encoder pass, same decoder
context - but it accepts an already-built standardised field so an experiment
can neutralise a channel first. A test pins that, on an unmodified field, it
reproduces ``_infer`` exactly. It never writes the replay cache.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
import xarray as xr

from ..ml.features import SURFACE, cyclic_doy
from ..ml.patches import N_DATA_CHANNELS, day_field


def context(engine, rows: np.ndarray, cols: np.ndarray, when: pd.Timestamp) -> np.ndarray:
    s, c = cyclic_doy(pd.DatetimeIndex([when]))
    raw = np.column_stack([engine.lat[rows], engine.lon[cols],
                           np.full(rows.size, s[0]), np.full(rows.size, c[0])])
    fs = engine.feature_scaler
    return ((raw.astype("float64") - fs.mean[N_DATA_CHANNELS:])
            / fs.std[N_DATA_CHANNELS:]).astype("float32")


def historical_inputs(engine, date):
    """(standardised padded field, surface_input_valid, timestamp) for a record date."""
    when = engine._normalise_date(date)
    ds = engine._store(when.year)
    t = engine._time_index(ds, when)
    siv = np.asarray(ds["surface_input_valid"].isel(time=t).values, dtype=bool)
    return day_field(ds, t, engine.feature_scaler, engine.patch), siv, when


def inputs_from_arrays(engine, arrays: dict, siv: np.ndarray, day) -> np.ndarray:
    """Standardised padded field from raw surface arrays (latest qualified states)."""
    when = pd.Timestamp(day).normalize()
    shim = xr.Dataset({v: (("time", "lat", "lon"), np.asarray(arrays[v])[None])
                       for v in SURFACE},
                      coords={"time": [np.datetime64(when)], "lat": engine.lat,
                              "lon": engine.lon})
    field = day_field(shim, 0, engine.feature_scaler, engine.patch)
    # the joint mask actually used by the qualified run defines the mask plane
    h = engine.patch // 2
    field[N_DATA_CHANNELS, h:h + siv.shape[0], h:h + siv.shape[1]] = siv.astype("float32")
    return field


def forward_field(engine, field: np.ndarray, siv: np.ndarray, when) -> np.ndarray:
    """Physical temperature (nlat, nlon, 15) at supported cells; NaN elsewhere."""
    when = pd.Timestamp(when).normalize()
    rows, cols = np.nonzero(siv)
    ctx = context(engine, rows, cols, when)
    with torch.no_grad():
        z = engine.model.embed_field(torch.from_numpy(np.ascontiguousarray(field))[None])[0]
        std = engine.model.forward_from_z(z[:, rows, cols].T,
                                          torch.from_numpy(ctx)).numpy().astype("float64")
    pred = engine.target_scaler.inverse_transform(std)
    out = np.full((engine.lat.size, engine.lon.size, pred.shape[1]), np.nan)
    out[rows, cols, :] = pred
    return out
