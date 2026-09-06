"""Feature assembly for the pointwise baselines.

Eleven inputs, deliberately pointwise: seven surface channels at the cell, the
cell's own coordinates, and a cyclic day-of-year encoding. No neighbouring
cells, no previous or future days - the L1 model is spatially and temporally
blind by construction, so any skill it shows is attributable to the
surface->subsurface mapping itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SURFACE = ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]
FEATURE_NAMES = SURFACE + ["lat", "lon", "doy_sin", "doy_cos"]
N_FEATURES = len(FEATURE_NAMES)
PERIOD_DAYS = 365.25


def day_of_year(times) -> np.ndarray:
    return pd.DatetimeIndex(np.atleast_1d(times)).dayofyear.to_numpy().astype("float64")


def cyclic_doy(times) -> tuple[np.ndarray, np.ndarray]:
    """sin/cos day-of-year.

    A raw day-of-year integer would tell the model that 31 Dec and 1 Jan are
    364 units apart. The sin/cos pair makes the encoding continuous across the
    year boundary, which is what a seasonal signal actually is.
    """
    ang = 2.0 * np.pi * day_of_year(times) / PERIOD_DAYS
    return np.sin(ang), np.cos(ang)


def harmonic_design(times, n_harmonics: int = 3) -> np.ndarray:
    """Design matrix [1, cos(k.t), sin(k.t) ...] for climatology regression."""
    doy = day_of_year(times)
    cols = [np.ones_like(doy)]
    for k in range(1, n_harmonics + 1):
        ang = 2.0 * np.pi * k * doy / PERIOD_DAYS
        cols += [np.cos(ang), np.sin(ang)]
    return np.column_stack(cols)


def n_harmonic_terms(n_harmonics: int = 3) -> int:
    return 2 * n_harmonics + 1
