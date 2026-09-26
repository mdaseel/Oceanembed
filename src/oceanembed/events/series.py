"""Generic event series and comparison metrics.

The corridor and the per-day quantities are exactly those of the frozen Phase 7D
``/api/event/series`` for Mocha (a cell is in the corridor when it lies within
``CORRIDOR_DEG`` in latitude and longitude of any observed track point), extended
with the 50/75/125 m levels. Each row is one independent reconstruction; every
comparison is a subtraction between rows. No recovery class and no severity
ranking is produced.
"""
from __future__ import annotations

import numpy as np

from ..diagnostics import PhysicalSupport
from ..diagnostics.hazard import ThermalSupport

CORRIDOR_DEG = 1.5
LEVELS = (50, 75, 100, 125)


def corridor_mask(track_points, lat, lon, deg: float = CORRIDOR_DEG) -> np.ndarray:
    mask = np.zeros((lat.size, lon.size), dtype=bool)
    for p in track_points:
        mask |= ((np.abs(lat[:, None] - p["lat"]) <= deg)
                 & (np.abs(lon[None, :] - p["lon"]) <= deg))
    return mask


def _mean(values: np.ndarray, mask: np.ndarray):
    selected = values[mask]
    selected = selected[np.isfinite(selected)]
    return float(selected.mean()) if selected.size else None


def _max(values: np.ndarray, mask: np.ndarray):
    selected = values[mask]
    selected = selected[np.isfinite(selected)]
    return float(selected.max()) if selected.size else None


def series_row(ctx, corridor: np.ndarray) -> dict:
    """One day. The first seven keys equal the frozen Mocha series definition."""
    view, diag = ctx.view, ctx.diag
    usable = (corridor & view.ocean_mask & view.surface_input_valid
              & (ctx.tchp_phys == PhysicalSupport.SUPPORTED))
    depths = list(view.depths)
    row = {
        "date": view.date,
        "n_cells": int(usable.sum()),
        "sst_nominal_0m_c": _mean(view.temperature[:, :, 0], usable),
        "temp_100m_c": _mean(view.temperature[:, :, depths.index(100)], usable),
        "anomaly_100m_c": _mean(view.anomaly[:, :, depths.index(100)], usable),
        "d26_m": _mean(diag.d26, usable),
        "tchp_kj_cm2": _mean(diag.tchp, usable),
        "category_counts": {c.name: int((ctx.category[usable] == c).sum())
                            for c in ThermalSupport},
    }
    for depth in LEVELS:
        k = depths.index(depth)
        row[f"temp_{depth}m_c"] = _mean(view.temperature[:, :, k], usable)
        row[f"anomaly_{depth}m_c"] = _mean(view.anomaly[:, :, k], usable)
    row["max_anomaly_100m_c"] = _max(view.anomaly[:, :, depths.index(100)], usable)
    return row


def _in(rows, segment):
    return [r for r in rows if segment["start"] <= r["date"] <= segment["end"]]


def _segment_mean(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return float(np.mean(values)) if values else None


def _segment(segments, short):
    for s in segments:
        if s["label"].split("/")[0].strip().upper() == short:
            return s
    return None


def _diff(a, b):
    return None if a is None or b is None else a - b


def event_metrics(rows: list[dict], segments: list[dict]) -> dict:
    """Comparison numbers, each defined in ``definitions`` and derived from rows only."""
    rows = sorted(rows, key=lambda r: r["date"])
    pre = _in(rows, segments[0]) if segments else []
    event = _in(rows, _segment(segments, "EVENT")) if _segment(segments, "EVENT") else []
    wake = _in(rows, _segment(segments, "WAKE")) if _segment(segments, "WAKE") else []

    def minimum(group, key):
        best = None
        for r in group:
            if r.get(key) is not None and (best is None or r[key] < best["value"]):
                best = {"value": r[key], "date": r["date"]}
        return best

    pre_tchp = _segment_mean(pre, "tchp_kj_cm2")
    wake_min = minimum(wake, "tchp_kj_cm2")
    final = next((r for r in reversed(rows) if r.get("tchp_kj_cm2") is not None), None)
    tchp_change = _diff(wake_min["value"] if wake_min else None, pre_tchp)
    pre_max_anomaly = [r["max_anomaly_100m_c"] for r in pre
                       if r.get("max_anomaly_100m_c") is not None]
    temperature_change = {
        str(d): _diff(_segment_mean(wake, f"temp_{d}m_c"), _segment_mean(pre, f"temp_{d}m_c"))
        for d in LEVELS}
    sst_min = minimum(wake, "sst_nominal_0m_c")
    d26_min = minimum(wake, "d26_m")
    return {
        "pre_event_tchp": pre_tchp,
        "event_tchp": _segment_mean(event, "tchp_kj_cm2"),
        "wake_min_tchp": wake_min,
        "tchp_change": tchp_change,
        "tchp_change_pct": (tchp_change / pre_tchp * 100
                            if tchp_change is not None and pre_tchp else None),
        "temperature_change_c": temperature_change,
        "sst_change_c": _diff(sst_min["value"] if sst_min else None,
                              _segment_mean(pre, "sst_nominal_0m_c")),
        "d26_change_m": _diff(d26_min["value"] if d26_min else None,
                              _segment_mean(pre, "d26_m")),
        "max_pre_event_anomaly_100m_c": max(pre_max_anomaly) if pre_max_anomaly else None,
        "final": ({"date": final["date"], "tchp": final["tchp_kj_cm2"]} if final else None),
        "final_vs_pre_tchp": _diff(final["tchp_kj_cm2"] if final else None, pre_tchp),
        "final_vs_wake_min_tchp": _diff(final["tchp_kj_cm2"] if final else None,
                                        wake_min["value"] if wake_min else None),
        "definitions": {
            "pre_event_tchp": "mean of daily corridor-mean TCHP over the Pre-event segment",
            "event_tchp": "mean of daily corridor-mean TCHP over the Event segment",
            "wake_min_tchp": "lowest daily corridor-mean TCHP in the Wake segment",
            "tchp_change": "wake minimum minus pre-event mean",
            "temperature_change_c": "Wake-segment mean minus Pre-event mean of the corridor-mean temperature at each depth",
            "sst_change_c": "lowest Wake-segment corridor-mean nominal 0 m temperature minus the Pre-event mean",
            "d26_change_m": "lowest Wake-segment corridor-mean D26 minus the Pre-event mean",
            "max_pre_event_anomaly_100m_c": "largest single-cell 100 m anomaly inside the corridor on any Pre-event day",
            "final_vs_pre_tchp": "last replayed day's corridor-mean TCHP minus the pre-event mean",
        },
    }
