"""The seven surface channels and the two field transforms the experiments use.

Both transforms act AFTER the frozen ``day_field`` has built the standardised,
masked, padded field, and only on data planes. Setting a plane to 0 in
standardised space means "the training mean" - the same neutral value the frozen
pipeline already uses for missing input. The validity-mask plane (index 7) is
never touched, so the cell population is unchanged.
"""
from __future__ import annotations

import numpy as np

from ..ml.features import SURFACE
from ..ml.patches import N_DATA_CHANNELS

CHANNELS = tuple(SURFACE)
LABELS = {"sst": "SST", "sss": "SSS", "sla": "SLA", "current_u": "Current U",
          "current_v": "Current V", "wind_u": "Wind U", "wind_v": "Wind V"}
SHORT = {"sst": "SST", "sss": "SSS", "sla": "SLA", "current_u": "CU",
         "current_v": "CV", "wind_u": "WU", "wind_v": "WV"}
NEUTRAL_RULE = ("data plane set to 0 in standardised space (the frozen training "
                "mean); validity-mask plane and decoder context unchanged")


def _index(channel: str) -> int:
    if channel not in CHANNELS:
        raise KeyError(f"unknown channel {channel!r}; expected one of {CHANNELS}")
    return CHANNELS.index(channel)


def neutralize(field: np.ndarray, channels) -> np.ndarray:
    """Copy of ``field`` with the named data planes set to the training mean."""
    if field.shape[0] != N_DATA_CHANNELS + 1:
        raise ValueError(f"expected {N_DATA_CHANNELS + 1} planes, got {field.shape[0]}")
    out = field.copy()
    for ch in channels:
        out[_index(ch)] = 0.0
    return out


def keep_only(field: np.ndarray, keep) -> np.ndarray:
    """Copy of ``field`` with every data plane except ``keep`` neutralised."""
    keep = set(keep)
    for ch in keep:
        _index(ch)
    return neutralize(field, [c for c in CHANNELS if c not in keep])
