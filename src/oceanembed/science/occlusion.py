"""Inference-time channel occlusion over the frozen L2 (PREREGISTRATION §2).

For each of the seven channels separately, its standardised data plane is set to
the training mean and the frozen whole-field forward is run again. Every result
is a difference against the unmodified forward on the same field. Nothing here is
a production field: results are returned to the caller and cached only under
outputs/science/cache/.
"""
from __future__ import annotations

from collections import OrderedDict

import numpy as np

from ..diagnostics.bathymetry import depth_physically_valid, local_water_depth
from ..diagnostics.thermal import D26Status, d26_tchp
from ..replay.engine import DEPTHS
from . import frozen
from .channels import CHANNELS, LABELS, NEUTRAL_RULE, SHORT, neutralize

VERSION = "science-occlusion-1"
WORDING = ("Occlusion sensitivity of the frozen model: how much the reconstruction "
           "changes when one channel is replaced by its training mean. It measures what "
           "the frozen network uses, not what information is physically required.")
_FIELDS: "OrderedDict[tuple, dict]" = OrderedDict()


def occluded_fields(engine, field: np.ndarray, siv: np.ndarray, when, key=None) -> dict:
    """{'base': T, channel: T_occluded} for the whole domain (nlat, nlon, 15)."""
    if key is not None and key in _FIELDS:
        _FIELDS.move_to_end(key)
        return _FIELDS[key]
    out = {"base": frozen.forward_field(engine, field, siv, when)}
    for ch in CHANNELS:
        out[ch] = frozen.forward_field(engine, neutralize(field, [ch]), siv, when)
    if key is not None:
        _FIELDS[key] = out
        while len(_FIELDS) > 2:
            _FIELDS.popitem(last=False)
    return out


def _tchp(profile: np.ndarray, water: float | None) -> tuple[float | None, str]:
    r = d26_tchp(profile, DEPTHS)
    status = D26Status(int(r.status))
    if not bool(r.tchp_defined):
        return None, status.name
    if status == D26Status.OK and (water is None or not np.isfinite(water) or r.d26 > water):
        return None, "INSUFFICIENT_WATER_COLUMN_SUPPORT" if water is not None else "UNVERIFIED"
    return float(r.tchp), status.name


def domain_summary(fields: dict, siv: np.ndarray) -> dict:
    """Median and 90th-percentile |dT| per depth over display-valid cells."""
    water = local_water_depth(strict=False)
    base = fields["base"]
    rows = {}
    for ch in CHANNELS:
        d = np.abs(fields[ch] - base)
        med, p90, n = [], [], []
        for k, depth in enumerate(DEPTHS):
            ok = siv & depth_physically_valid(depth, water)
            vals = d[:, :, k][ok]
            vals = vals[np.isfinite(vals)]
            med.append(round(float(np.median(vals)), 5) if vals.size else None)
            p90.append(round(float(np.percentile(vals, 90)), 5) if vals.size else None)
            n.append(int(vals.size))
        rows[ch] = {"median_abs_delta_c": med, "p90_abs_delta_c": p90, "n_cells": n}
    return rows


def point_summary(fields: dict, row: int, col: int) -> dict:
    water = local_water_depth(strict=False)
    w = None if water is None else float(water[row, col])
    base = fields["base"][row, col]
    tchp0, status0 = _tchp(base, w)
    out = {}
    for ch in CHANNELS:
        prof = fields[ch][row, col]
        delta = prof - base
        supported = [bool(w is not None and np.isfinite(w) and w >= d) for d in DEPTHS]
        tchp1, status1 = _tchp(prof, w)
        out[ch] = {
            "delta_c": [None if not np.isfinite(x) else round(float(x), 4) for x in delta],
            "depth_supported": supported,
            "tchp_original": None if tchp0 is None else round(tchp0, 2),
            "tchp_occluded": None if tchp1 is None else round(tchp1, 2),
            "delta_tchp": None if (tchp0 is None or tchp1 is None) else round(tchp1 - tchp0, 2),
            "tchp_status_original": status0, "tchp_status_occluded": status1,
        }
    return out


def occlusion_payload(engine, field, siv, when, row, col, source="historical") -> dict:
    date = str(np.datetime_as_string(np.datetime64(when, "D")))
    fields = occluded_fields(engine, field, siv, when,
                             key=(engine.l2_state_dict_sha256, source, date, VERSION))
    if not bool(siv[row, col]):
        raise ValueError("the selected cell has no valid surface input on this date")
    return {
        "date": date, "source": source, "row": int(row), "col": int(col),
        "lat": float(engine.lat[row]), "lon": float(engine.lon[col]),
        "depths_m": list(DEPTHS), "channels": list(CHANNELS),
        "channel_labels": [LABELS[c] for c in CHANNELS],
        "channel_short": [SHORT[c] for c in CHANNELS],
        "original_c": [None if not np.isfinite(x) else round(float(x), 4)
                       for x in fields["base"][row, col]],
        "point": point_summary(fields, row, col),
        "domain": domain_summary(fields, siv),
        "method": {"neutral_value": NEUTRAL_RULE, "one_channel_per_run": True,
                   "tchp": "Phase 7C d26_tchp recomputed from the occluded profile only, "
                           "with ETOPO water-column support",
                   "domain_population": "surface input valid AND local water depth >= level"},
        "wording": WORDING, "version": VERSION,
        "model_sha256": engine.l2_state_dict_sha256,
        "production_field": False,
    }
