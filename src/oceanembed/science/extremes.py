"""Subsurface thermal extremes (PREREGISTRATION §8).

Not called a marine heatwave: the formal Hobday et al. (2016) definition expects
a climatological baseline of preferably 30 years, and this record holds six
training years. The structure (seasonally varying 90th percentile, 11-day window,
31-day smoothing, >= 5 days, gaps <= 2 days bridged) follows Hobday; the name
does not claim it.
"""
from __future__ import annotations

import numpy as np

NAME = "SUBSURFACE THERMAL EXTREME"
MHW_DECISION = (
    "Formal marine-heatwave protocol not adopted: Hobday et al. (2016) recommend a "
    "baseline of at least 30 years of daily data; this record holds 6 training years "
    "(2015-2020) of reconstructions, and subsurface MHW definitions are not "
    "standardised. The feature is therefore named SUBSURFACE THERMAL EXTREME.")
BASELINE_START = "2015-01-01"
BASELINE_END = "2020-12-31"
EXTREME_DEPTHS = (0, 50, 75, 100, 125, 150)
PERCENTILE = 90
HALF_WINDOW = 5          # +/-5 days -> 11-day window
SMOOTH_DAYS = 31
MIN_DURATION = 5
MAX_GAP = 2
TRAILING_DAYS = 60
RULE = (f"exceedance above the day-of-year {PERCENTILE}th percentile of frozen-L2 "
        f"reconstructions {BASELINE_START}..{BASELINE_END} (+/-{HALF_WINDOW}-day window, "
        f"{SMOOTH_DAYS}-day smoothing); active when the exceedance run ending on the date "
        f"lasts >= {MIN_DURATION} days; an earlier >= {MIN_DURATION}-day run separated by "
        f"<= {MAX_GAP} days is part of the same event; only days up to the date are used")


def smooth_circular(values: np.ndarray, window: int) -> np.ndarray:
    """NaN-aware circular moving mean along axis 0 (day of year)."""
    if window % 2 == 0:
        raise ValueError("window must be odd")
    h = window // 2
    n = values.shape[0]
    finite = np.isfinite(values)
    v = np.where(finite, values, 0.0).astype("float64")
    c = finite.astype("float64")
    pad_v = np.concatenate([v[-h:], v, v[:h]], axis=0)
    pad_c = np.concatenate([c[-h:], c, c[:h]], axis=0)
    cs_v = np.concatenate([np.zeros_like(pad_v[:1]), np.cumsum(pad_v, axis=0)], axis=0)
    cs_c = np.concatenate([np.zeros_like(pad_c[:1]), np.cumsum(pad_c, axis=0)], axis=0)
    total = cs_v[window:window + n] - cs_v[:n]
    count = cs_c[window:window + n] - cs_c[:n]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(count > 0, total / count, np.nan)
    return out.astype(values.dtype)


def trailing_events(exceed: np.ndarray, valid: np.ndarray | None = None) -> dict:
    """Event state on the LAST day of ``exceed`` (n_days, ...), using past days only.

    Returns ``active``, ``duration`` (days, merged event start .. last day),
    ``censored`` (the event already ran at the first day of the window, so the
    true duration is at least ``duration``) and ``run`` (current exceedance run).
    A day without a valid value breaks a run: it is never assumed to exceed.
    """
    ex = np.asarray(exceed, dtype=bool)
    if valid is not None:
        ex = ex & np.asarray(valid, dtype=bool)
    n = ex.shape[0]
    shape = ex.shape[1:]
    run = np.zeros(shape, dtype="int32")
    run_start = np.zeros(shape, dtype="int32")
    last_end = np.full(shape, -10_000, dtype="int32")
    last_start = np.zeros(shape, dtype="int32")
    for t in range(n):
        e = ex[t]
        starting = e & (run == 0)
        run_start = np.where(starting, t, run_start)
        ended = ~e & (run >= MIN_DURATION)
        if ended.any():
            gap = run_start - last_end - 1
            merged = np.where(gap <= MAX_GAP, last_start, run_start)
            last_start = np.where(ended, merged, last_start)
            last_end = np.where(ended, t - 1, last_end)
        run = np.where(e, run + 1, 0)
    active = run >= MIN_DURATION
    gap = run_start - last_end - 1
    start = np.where(gap <= MAX_GAP, last_start, run_start)
    duration = np.where(active, (n - 1) - start + 1, 0)
    censored = active & (start == 0)
    return {"active": active, "duration": duration.astype("int32"),
            "censored": censored, "run": run}


# ------------------------------------------------------------------ runtime
from collections import OrderedDict  # noqa: E402
from functools import lru_cache  # noqa: E402

import pandas as pd  # noqa: E402

from ..config import REPO_ROOT  # noqa: E402

BASELINE_DIR = REPO_ROOT / "outputs" / "science" / "cache" / "extreme_baseline"
_RESULTS: "OrderedDict[tuple, dict]" = OrderedDict()


class BaselineUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def baseline():
    import json
    try:
        meta = json.loads((BASELINE_DIR / "meta.json").read_text(encoding="utf-8"))
        thr = np.load(BASELINE_DIR / "p90_threshold.npy", mmap_mode="r")
        recon = np.load(BASELINE_DIR / "recon.npy", mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise BaselineUnavailable(
            "thermal-extreme baseline not built: run "
            "scripts/science/build_thermal_extreme_baseline.py") from exc
    dates = pd.date_range(meta["baseline"][0], meta["baseline"][1], freq="D")
    return thr, recon, dates, meta


def cell_area_km2(lat: np.ndarray, dlat: float = 0.25, dlon: float = 0.25) -> np.ndarray:
    r = 6371.0088
    rad = np.pi / 180
    return r * r * dlon * rad * np.abs(np.sin((lat + dlat / 2) * rad) - np.sin((lat - dlat / 2) * rad))


def evaluate(engine, date, depth_m: int) -> dict:
    """Trailing-window thermal-extreme state for one historical date and depth."""
    from ..diagnostics.bathymetry import depth_physically_valid, local_water_depth
    from ..ml.metrics import BASINS
    from ..replay.engine import DEPTHS
    from . import frozen

    if depth_m not in EXTREME_DEPTHS:
        raise ValueError(f"depth must be one of {EXTREME_DEPTHS}")
    when = engine._normalise_date(date)
    key = (engine.l2_state_dict_sha256, str(when.date()), int(depth_m))
    if key in _RESULTS:
        _RESULTS.move_to_end(key)
        return _RESULTS[key]
    thr, recon, bdates, meta = baseline()
    di = EXTREME_DEPTHS.index(depth_m)
    k = DEPTHS.index(depth_m)
    start = max(when - pd.Timedelta(days=TRAILING_DAYS - 1), engine._normalise_date("2015-01-01"))
    days = pd.date_range(start, when, freq="D")
    exceed, valid = [], []
    temp = None
    for d in days:
        field, siv, w = frozen.historical_inputs(engine, d)
        t = frozen.forward_field(engine, field, siv, w)[:, :, k]
        th = np.asarray(thr[d.dayofyear - 1, di], dtype="float64")
        ok = siv & np.isfinite(t) & np.isfinite(th)
        exceed.append(ok & (t > th))
        valid.append(ok)
        temp = t
    ev = trailing_events(np.stack(exceed), np.stack(valid))
    water = local_water_depth(strict=False)
    support = valid[-1] & depth_physically_valid(depth_m, water)
    th_today = np.asarray(thr[when.dayofyear - 1, di], dtype="float64")
    excess = np.where(support, temp - th_today, np.nan)
    dist = np.abs(bdates.dayofyear.to_numpy() - when.dayofyear)
    idx = np.flatnonzero(np.minimum(dist, 366 - dist) <= HALF_WINDOW)
    samples = np.asarray(recon[idx, di], dtype="float64")
    with np.errstate(invalid="ignore"):
        pct = np.where(support, (samples < temp[None]).mean(axis=0) * 100, np.nan)
    active = ev["active"] & support
    area = cell_area_km2(engine.lat)[:, None] * np.ones_like(active, dtype="float64")
    la, lo = np.meshgrid(engine.lat, engine.lon, indexing="ij")
    extent = {"nio": float(area[active].sum())}
    for name, box in BASINS.items():
        sel = (la >= box["lat"][0]) & (la <= box["lat"][1]) & (lo >= box["lon"][0]) & (lo <= box["lon"][1])
        extent[name] = float(area[active & sel].sum())
    result = {
        "date": str(when.date()), "depth_m": int(depth_m), "name": NAME, "rule": RULE,
        "window": [str(days[0].date()), str(days[-1].date())], "window_days": len(days),
        "active": active, "duration": np.where(active, ev["duration"], 0),
        "censored": ev["censored"] & active, "excess": excess, "percentile": pct,
        "support": support, "extent_km2": extent,
        "n_active_cells": int(active.sum()), "baseline_meta": meta,
        "mhw_decision": MHW_DECISION,
    }
    _RESULTS[key] = result
    while len(_RESULTS) > 6:
        _RESULTS.popitem(last=False)
    return result
