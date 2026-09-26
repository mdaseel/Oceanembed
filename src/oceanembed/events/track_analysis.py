"""Track x ocean thermal state: reading an EXISTING OceanEmbed field along a path.

The path may be an observed best track, an external advisory track, or a
user-drawn scenario. In every case it is geometry only. It never enters a
reconstruction, never selects a model input and never modifies a field: this
module receives a field that already exists (a ``replay_field`` result or a
latest-qualified field) and the frozen Phase 7C/7D diagnostics derived from it.

Nothing here runs the model, interpolates between model depths, cells or dates,
invents a threshold, or produces a score or probability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..diagnostics import (PhysicalSupport, depth_physically_valid,
                           field_diagnostics, local_water_depth, qualify)
from ..diagnostics.hazard import ThermalSupport, categorize, load_thresholds

EARTH_RADIUS_KM = 6371.0088
STEP_KM = 10.0
SAMPLE_DEPTHS = (50, 75, 100, 125)
FOOTPRINT_DEPTHS = (0, 50, 75, 100)
CATEGORY_RANK = {"LOW": 0, "MODERATE": 1, "ELEVATED": 2, "HIGH": 3}
MAX_POINTS = 200

SAMPLING_RULE = (
    "The path is resampled every 10 km along great-circle arcs between consecutive "
    "positions, and each sample reads the nearest 0.25-degree grid cell of the "
    "selected OceanEmbed field. The resampling places points on the path only; no "
    "OceanEmbed value is interpolated between cells, depths or dates.")
DISTANCE_RULE = (
    "Each sample represents half the distance to its neighbours along the path; a "
    "category distance is the sum of those lengths. Approximate: resolution is set "
    "by the 10 km step and the 0.25-degree grid.")
STRONGEST_SEGMENT_RULE = (
    "Take the highest thermal-support category present along the path; the strongest "
    "segment is the contiguous run of samples in that category containing the "
    "highest TCHP sample (earliest on ties). No weights and no composite score.")
SECTION_NOTE = (
    "Values exist only at OceanEmbed's 15 depths and at the sampled grid cells. Any "
    "smoothing in the drawing is display only, never new model output. Blank cells "
    "lie below the local ETOPO seafloor or have no surface input.")
COMPOSITE_RULE = (
    "A composite is the mean of the independent daily reconstructions inside one "
    "frozen segment. A cell is blank unless every day in the segment has a value, "
    "so coverage is never mixed across days.")


@dataclass
class FieldContext:
    """One authoritative field and the frozen diagnostics derived from it."""

    view: object
    diag: object
    d26_phys: np.ndarray
    tchp_phys: np.ndarray
    category: np.ndarray
    water: np.ndarray | None
    withheld: tuple
    thresholds: object


def field_context(view, withheld: tuple = ()) -> FieldContext:
    diag = field_diagnostics(view)
    water = local_water_depth(strict=False)
    d26_phys, tchp_phys = qualify(diag, water)
    thresholds = load_thresholds(strict=False)
    category = categorize(diag.tchp, diag.status, tchp_phys, thresholds)
    return FieldContext(view, diag, d26_phys, tchp_phys, category, water,
                        tuple(withheld), thresholds)


def _f(x) -> float | None:
    x = float(x)
    return x if math.isfinite(x) else None


# ------------------------------------------------------------------ geometry
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _along(lat1, lon1, lat2, lon2, f: float) -> tuple[float, float]:
    """Point a fraction ``f`` along the great-circle arc (geometry only)."""
    d = haversine_km(lat1, lon1, lat2, lon2) / EARTH_RADIUS_KM
    if d < 1e-12:
        return lat1, lon1
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a, b = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def validate_points(points) -> list[dict]:
    clean = []
    for p in points or []:
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("every position needs numeric lat and lon") from exc
        if not (math.isfinite(lat) and math.isfinite(lon)) or not -90 <= lat <= 90 \
                or not -180 <= lon <= 360:
            raise ValueError(f"invalid position {lat}, {lon}")
        clean.append({**p, "lat": lat, "lon": lon})
    if not clean:
        raise ValueError("a path needs at least one position")
    if len(clean) > MAX_POINTS:
        raise ValueError(f"a path may have at most {MAX_POINTS} positions")
    return clean


def resample(points, step_km: float = STEP_KM) -> tuple[list[dict], float]:
    pts = validate_points(points)
    samples: list[dict] = []
    total = 0.0

    def when(p):
        return p.get("valid_time") or p.get("time")

    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
        n = max(1, math.ceil(seg / step_km))
        for k in range(n):
            lat, lon = _along(a["lat"], a["lon"], b["lat"], b["lon"], k / n)
            samples.append({"distance_km": total + seg * k / n, "lat": lat, "lon": lon,
                            "segment": i,
                            "point_type": (a if k == 0 else b).get("point_type"),
                            "from_time": when(a), "to_time": when(b)})
        total += seg
    last = pts[-1]
    samples.append({"distance_km": total, "lat": last["lat"], "lon": last["lon"],
                    "segment": max(0, len(pts) - 2), "point_type": last.get("point_type"),
                    "from_time": when(last), "to_time": None})
    for i, s in enumerate(samples):
        before = samples[i - 1]["distance_km"] if i else s["distance_km"]
        after = samples[i + 1]["distance_km"] if i + 1 < len(samples) else s["distance_km"]
        s["length_km"] = (after - before) / 2
    return samples, total


def nearest_cell(view, lat: float, lon: float) -> tuple[int, int] | None:
    """Nearest canonical cell, first index on ties; None outside the domain."""
    la, lo = np.asarray(view.lat), np.asarray(view.lon)
    if not (la[0] <= lat <= la[-1] and lo[0] <= lon <= lo[-1]):
        return None
    return int(np.argmin(np.abs(la - lat))), int(np.argmin(np.abs(lo - lon)))


# ------------------------------------------------------------------ sampling
def cell_values(ctx: FieldContext, row: int, col: int) -> dict:
    v = ctx.view
    ocean = bool(v.ocean_mask[row, col])
    has_input = bool(v.surface_input_valid[row, col])
    usable = ocean and has_input
    tchp = d26 = None
    if usable and "tchp" not in ctx.withheld and \
            ctx.tchp_phys[row, col] == PhysicalSupport.SUPPORTED:
        tchp = _f(ctx.diag.tchp[row, col])
    if usable and "d26" not in ctx.withheld and \
            ctx.d26_phys[row, col] == PhysicalSupport.SUPPORTED:
        d26 = _f(ctx.diag.d26[row, col])
    water = None if ctx.water is None else _f(ctx.water[row, col])
    levels = {}
    for depth in SAMPLE_DEPTHS:
        k = list(v.depths).index(depth)
        ok = usable and water is not None and water >= depth
        levels[str(depth)] = {
            "temperature": _f(v.temperature[row, col, k]) if ok else None,
            "anomaly": _f(v.anomaly[row, col, k]) if ok else None,
        }
    return {"ocean": ocean, "input_valid": has_input,
            "category": ThermalSupport(int(ctx.category[row, col])).name,
            "tchp": tchp, "d26": d26, "water_depth_m": water, "levels": levels}


def _empty_cell() -> dict:
    return {"row": None, "col": None, "grid_lat": None, "grid_lon": None,
            "ocean": False, "input_valid": False, "category": None, "tchp": None,
            "d26": None, "water_depth_m": None,
            "levels": {str(d): {"temperature": None, "anomaly": None}
                       for d in SAMPLE_DEPTHS}}


def sample_path(ctx: FieldContext, points, step_km: float = STEP_KM):
    samples, total = resample(points, step_km)
    for s in samples:
        cell = nearest_cell(ctx.view, s["lat"], s["lon"])
        s["in_domain"] = cell is not None
        if cell is None:
            s.update(_empty_cell())
        else:
            r, c = cell
            s.update({"row": r, "col": c, "grid_lat": float(ctx.view.lat[r]),
                      "grid_lon": float(ctx.view.lon[c]), **cell_values(ctx, r, c)})
    return samples, total


def _extreme(samples, getter, largest: bool) -> dict | None:
    best = None
    for s in samples:
        value = getter(s)
        if value is None:
            continue
        if best is None or (value > best["value"] if largest else value < best["value"]):
            best = {"value": value, "distance_km": s["distance_km"],
                    "lat": s["grid_lat"], "lon": s["grid_lon"], "category": s["category"]}
    return best


def strongest_segment(samples: list[dict], highest: str | None) -> dict | None:
    if highest is None:
        return None
    runs, current = [], []
    for i, s in enumerate(samples):
        if s["category"] == highest:
            current.append(i)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    def peak(run):
        values = [(samples[i]["tchp"], i) for i in run if samples[i]["tchp"] is not None]
        return max(values, key=lambda t: (t[0], -t[1])) if values else (float("-inf"), run[0])

    best = max(runs, key=lambda run: (peak(run)[0], -run[0]))
    _, pi = peak(best)
    seg = [samples[i] for i in best]
    p = samples[pi]
    return {"category": highest,
            "start_km": seg[0]["distance_km"], "end_km": seg[-1]["distance_km"],
            "length_km": sum(s["length_km"] for s in seg),
            "lat_range": [min(s["grid_lat"] for s in seg), max(s["grid_lat"] for s in seg)],
            "lon_range": [min(s["grid_lon"] for s in seg), max(s["grid_lon"] for s in seg)],
            "peak_tchp": p["tchp"], "peak_lat": p["grid_lat"], "peak_lon": p["grid_lon"],
            "peak_distance_km": p["distance_km"],
            "peak_anomaly_100m": p["levels"]["100"]["anomaly"],
            "n_samples": len(seg), "rule": STRONGEST_SEGMENT_RULE}


def summarize(samples: list[dict], total: float, ctx: FieldContext) -> dict:
    tchps = [s["tchp"] for s in samples if s["tchp"] is not None]
    distance = {c: 0.0 for c in CATEGORY_RANK}
    cells = {c: set() for c in CATEGORY_RANK}
    for s in samples:
        if s["category"] in CATEGORY_RANK:
            distance[s["category"]] += s["length_km"]
            cells[s["category"]].add((s["row"], s["col"]))
    present = [c for c in CATEGORY_RANK if cells[c]]
    highest = max(present, key=CATEGORY_RANK.get) if present else None
    anomaly = {str(d): {"max": _extreme(samples, lambda s, d=d: s["levels"][str(d)]["anomaly"], True),
                        "min": _extreme(samples, lambda s, d=d: s["levels"][str(d)]["anomaly"], False)}
               for d in SAMPLE_DEPTHS}
    if "d26" in ctx.withheld:
        d26 = {"withheld": True}
    else:
        d26s = [s["d26"] for s in samples if s["d26"] is not None]
        d26 = {"withheld": False,
               "median": float(np.median(d26s)) if d26s else None,
               "min": min(d26s) if d26s else None, "max": max(d26s) if d26s else None}
    return {
        "length_km": total,
        "length_in_domain_km": sum(s["length_km"] for s in samples if s["in_domain"]),
        "n_samples": len(samples),
        "n_in_domain": sum(1 for s in samples if s["in_domain"]),
        "n_with_tchp": len(tchps),
        "tchp": {"max": _extreme(samples, lambda s: s["tchp"], True),
                 "median": float(np.median(tchps)) if tchps else None},
        "d26": d26,
        "anomaly": anomaly,
        "category_distance_km": distance,
        "category_cells": {c: len(v) for c, v in cells.items()},
        "highest_category": highest,
        "intersects": {"HIGH": bool(cells["HIGH"]), "ELEVATED": bool(cells["ELEVATED"])},
        "strongest_segment": strongest_segment(samples, highest),
    }


def analyze(ctx: FieldContext, points, step_km: float = STEP_KM) -> dict:
    samples, total = sample_path(ctx, points, step_km)
    return {"date": ctx.view.date, "samples": samples,
            "summary": summarize(samples, total, ctx),
            "withheld": list(ctx.withheld), "sample_depths_m": list(SAMPLE_DEPTHS),
            "rules": {"sampling": SAMPLING_RULE, "distance": DISTANCE_RULE,
                      "strongest_segment": STRONGEST_SEGMENT_RULE}}


def section(ctx: FieldContext, points, mode: str = "temperature",
            step_km: float = STEP_KM) -> dict:
    """Distance-along-path x the 15 model depths, blank where unsupported."""
    if mode not in ("temperature", "anomaly"):
        raise ValueError("mode must be 'temperature' or 'anomaly'")
    samples, total = resample(points, step_km)
    v = ctx.view
    depths = list(v.depths)
    values = [[None] * len(samples) for _ in depths]
    source = v.temperature if mode == "temperature" else v.anomaly
    floor: list[float | None] = []
    for i, s in enumerate(samples):
        cell = nearest_cell(v, s["lat"], s["lon"])
        if cell is None:
            floor.append(None)
            continue
        r, c = cell
        water = None if ctx.water is None else _f(ctx.water[r, c])
        floor.append(water)
        if water is None or not (v.ocean_mask[r, c] and v.surface_input_valid[r, c]):
            continue
        for k, depth in enumerate(depths):
            if water >= depth:
                values[k][i] = _f(source[r, c, k])
    return {"date": v.date, "mode": mode, "depths_m": depths,
            "distance_km": [s["distance_km"] for s in samples],
            "lat": [s["lat"] for s in samples], "lon": [s["lon"] for s in samples],
            "values": values, "water_depth_m": floor, "length_km": total,
            "bathymetry_available": ctx.water is not None, "note": SECTION_NOTE}


# ------------------------------------------------------------------ change
class CompositeAccumulator:
    """Mean of independent daily fields, built one day at a time.

    NaN propagates: a cell with no value on any day stays blank, so the composite
    never mixes coverage across days.
    """

    def __init__(self):
        self._t = self._tchp = self._siv = self._ocean = None
        self._n = 0
        self.dates: list[str] = []
        self._depths = self._lat = self._lon = None

    def add(self, ctx: FieldContext) -> None:
        v = ctx.view
        tchp = np.where((ctx.tchp_phys == PhysicalSupport.SUPPORTED) & np.isfinite(ctx.diag.tchp),
                        ctx.diag.tchp, np.nan)
        if self._n == 0:
            self._t = np.array(v.temperature, dtype="float64", copy=True)
            self._tchp = np.array(tchp, dtype="float64", copy=True)
            self._siv = np.array(v.surface_input_valid, dtype=bool, copy=True)
            self._ocean = np.array(v.ocean_mask, dtype=bool, copy=True)
            self._depths, self._lat, self._lon = list(v.depths), v.lat, v.lon
        else:
            self._t += v.temperature
            self._tchp += tchp
            self._siv &= v.surface_input_valid.astype(bool)
        self._n += 1
        self.dates.append(v.date)

    def result(self) -> dict:
        if not self._n:
            raise ValueError("a composite needs at least one day")
        return {"temperature": self._t / self._n, "tchp": self._tchp / self._n,
                "input_valid": self._siv, "ocean": self._ocean, "dates": list(self.dates),
                "depths": self._depths, "lat": self._lat, "lon": self._lon}


def composite(contexts: list[FieldContext]) -> dict:
    acc = CompositeAccumulator()
    for ctx in contexts:
        acc.add(ctx)
    return acc.result()


def change_stats(delta: np.ndarray, valid: np.ndarray, lat, lon) -> dict:
    values = np.where(valid & np.isfinite(delta), delta, np.nan)
    if not np.isfinite(values).any():
        return {"n_cells": 0, "min": None, "max": None, "median": None}
    lo = np.unravel_index(np.nanargmin(values), values.shape)
    hi = np.unravel_index(np.nanargmax(values), values.shape)
    return {"n_cells": int(np.isfinite(values).sum()),
            "min": {"value": float(values[lo]), "lat": float(lat[lo[0]]), "lon": float(lon[lo[1]])},
            "max": {"value": float(values[hi]), "lat": float(lat[hi[0]]), "lon": float(lon[hi[1]])},
            "median": float(np.nanmedian(values))}


def difference(a: dict, b: dict, water: np.ndarray | None, depth_m: int | None = None,
               include_tchp_grid: bool = False) -> dict:
    """``b`` minus ``a`` between two composites, at real model depths only."""
    depths, lat, lon = a["depths"], a["lat"], a["lon"]
    ocean = a["ocean"] & b["ocean"]
    has_input = a["input_valid"] & b["input_valid"]
    temperature = {}
    for depth in FOOTPRINT_DEPTHS:
        k = depths.index(depth)
        valid = depth_physically_valid(depth, water, ocean) & has_input
        temperature[str(depth)] = change_stats(
            b["temperature"][:, :, k] - a["temperature"][:, :, k], valid, lat, lon)
    d_tchp = b["tchp"] - a["tchp"]
    tchp_valid = ocean & has_input & np.isfinite(d_tchp)
    out = {"from_dates": a["dates"], "to_dates": b["dates"], "rule": COMPOSITE_RULE,
           "footprint": {"temperature": temperature,
                         "tchp": change_stats(d_tchp, tchp_valid, lat, lon)}}
    if depth_m is not None:
        if depth_m not in depths:
            raise ValueError(f"depth {depth_m} m is not one of the 15 model depths")
        k = depths.index(depth_m)
        valid = depth_physically_valid(depth_m, water, ocean) & has_input
        grid = np.where(valid, b["temperature"][:, :, k] - a["temperature"][:, :, k], np.nan)
        out["grid"] = {"depth_m": depth_m, "values": _grid(grid)}
    if include_tchp_grid:
        out["tchp_grid"] = _grid(np.where(tchp_valid, d_tchp, np.nan))
    return out


def _grid(values: np.ndarray) -> list:
    return [[_f(x) for x in row] for row in values]
