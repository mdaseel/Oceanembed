"""Controlled leave-one-group-out channel ablation (Experiment D).

The ablation is applied AFTER the frozen ``day_field`` has already built the
standardised, masked, zero-padded field. The ablated group's planes are set to
zero, which in standardised space is the training mean; every other channel and
the validity-mask channel are untouched.

Why this is the controlled version and not an outage simulation:

* the sample population is unchanged - validity still comes from the ORIGINAL
  complete seven-channel field, so no cell is added or removed;
* the architecture, input width and parameter count are unchanged;
* the preprocessing is unchanged;
* only the information content of one group changes.

An operational missing-channel event is a different thing entirely: there the
joint mask collapses and the cell disappears. That case is Phase 6C-B/6C-C
work and nothing here should be read as a statement about it.
"""
from __future__ import annotations

import numpy as np

from ..ml.features import SURFACE
from ..ml.patches import N_DATA_CHANNELS

ABLATION_GROUPS = {
    "SST": ["sst"],
    "SSS": ["sss"],
    "SLA": ["sla"],
    "CURRENTS": ["current_u", "current_v"],
    "WINDS": ["wind_u", "wind_v"],
}


def group_channel_indices(group: str) -> list[int]:
    if group not in ABLATION_GROUPS:
        raise KeyError(f"unknown ablation group {group!r}; "
                       f"expected one of {sorted(ABLATION_GROUPS)}")
    return [SURFACE.index(v) for v in ABLATION_GROUPS[group]]


def ablate_field(field: np.ndarray, group: str | None) -> np.ndarray:
    """Zero one group's data planes in standardised space; mask untouched.

    ``group=None`` returns the field unchanged, which is the full-input control.
    """
    if group is None:
        return field
    if field.shape[0] != N_DATA_CHANNELS + 1:
        raise ValueError(f"expected {N_DATA_CHANNELS + 1} channels, "
                         f"got {field.shape[0]}")
    out = field.copy()
    for k in group_channel_indices(group):
        out[k] = 0.0
    return out
