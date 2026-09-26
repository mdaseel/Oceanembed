"""Model Science and disaster-context endpoints.

Every endpoint reads a frozen field through the replay engine or a precomputed,
provenance-carrying artefact. None writes a production artefact, none serves an
experiment result as a production field, and none produces a probability.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..config import REPO_ROOT
from ..replay import api as replay_api
from . import attribution, coastal, extremes, integrity, occlusion, physical_qa
from . import validation_context as vc
from .channels import CHANNELS, LABELS, SHORT

router = APIRouter()
SCIENCE = REPO_ROOT / "outputs" / "science"
TABLES = REPO_ROOT / "outputs" / "tables"


def _read_json(path, missing: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, missing)


def _cell(engine, lat: float, lon: float):
    from ..replay.contract import OutsideDomain  # noqa: F401
    la, lo = engine.lat, engine.lon
    if not (la[0] - 0.125 <= lat <= la[-1] + 0.125 and lo[0] - 0.125 <= lon <= lo[-1] + 0.125):
        raise HTTPException(422, "location outside the OceanEmbed domain")
    return int(np.abs(la - lat).argmin()), int(np.abs(lo - lon).argmin())


def _inputs(engine, source: str, date: str | None):
    """Standardised input field for a historical date or a qualified latest state."""
    from . import frozen
    if source == "historical":
        if not date:
            raise HTTPException(422, "a historical analysis needs a date")
        try:
            field, siv, when = frozen.historical_inputs(engine, date)
        except Exception as exc:  # noqa: BLE001 - outside the record
            raise HTTPException(422, str(exc)) from exc
        return field, siv, when, {"source": "historical", "valid_date": str(when.date())}
    if source == "latest":
        from ..nrt import latest as LQ
        from ..poc.app import _qualified_latest_field
        result = LQ.load_daily(engine, date) if date else _qualified_latest_field(engine)[0]
        if result is None:
            raise HTTPException(503, "Latest OceanEmbed reconstruction unavailable. Historical "
                                     "Event Intelligence remains available.")
        view = result.view
        missing = [c for c in CHANNELS if c not in result.surface]
        if missing:
            raise HTTPException(503, f"qualified state lacks stored inputs: {missing}")
        field = frozen.inputs_from_arrays(engine, result.surface, view.surface_input_valid, view.date)
        return field, view.surface_input_valid.astype(bool), pd.Timestamp(view.date), \
            {"source": "latest qualified state", "valid_date": view.date}
    raise HTTPException(422, "source must be 'historical' or 'latest'")


# ------------------------------------------------------------------ attribution
@router.get("/api/science/attribution")
def science_attribution(lat: float, lon: float, date: str | None = None,
                        source: str = "historical", steps: int = attribution.STEPS):
    if not 16 <= steps <= 256:
        raise HTTPException(422, "steps must be between 16 and 256")
    engine = replay_api.engine()
    row, col = _cell(engine, lat, lon)
    field, siv, when, meta = _inputs(engine, source, date)
    if not siv[row, col]:
        raise HTTPException(422, "no valid surface input at this cell on this date")
    try:
        result = attribution.attribute_cell(engine, field, siv, when, row, col, steps,
                                            source=source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**result, "field": meta}


@router.get("/api/science/occlusion")
def science_occlusion(lat: float, lon: float, date: str | None = None,
                      source: str = "historical"):
    engine = replay_api.engine()
    row, col = _cell(engine, lat, lon)
    field, siv, when, meta = _inputs(engine, source, date)
    try:
        payload = occlusion.occlusion_payload(engine, field, siv, when, row, col, source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**payload, "field": meta}


@router.get("/api/science/retrained-ablation")
def science_retrained_ablation():
    """Display of Architecture Closure Experiment D and the SST-only experiment, if run."""
    groups = pd.read_csv(TABLES / "architecture_closure" / "channel_ablation_by_depth.csv")
    noise = pd.read_csv(TABLES / "architecture_closure" / "ablation_noise_floor.csv")
    out = {"experiment": "Architecture Closure Experiment D - retrained leave-one-group-out",
           "split": "validation 2021", "report": "ARCHITECTURE_CLOSURE_REPORT.md section 5",
           "noise_floor_percent": {"mean": round(float(noise.percent_difference.abs().mean()), 2),
                                   "max": round(float(noise.percent_difference.abs().max()), 2)},
           "groups": {}, "depths_m": sorted(int(d) for d in groups.depth_m.unique())}
    for g, sub in groups.groupby("group"):
        sub = sub.sort_values("depth_m")
        out["groups"][g] = {"rmse_change_percent": [round(float(x), 2) for x in sub.rmse_change_percent],
                            "anomaly_corr_change": [round(float(x), 3) for x in sub.anomaly_corr_change]}
    sst_path = TABLES / "science" / "sst_only_metrics_by_depth.csv"
    if sst_path.exists():
        m = pd.read_csv(sst_path)
        rows = {}
        for model, sub in m.groupby("model"):
            sub = sub.sort_values("depth_m")
            rows[model] = {"rmse_c": [round(float(x), 4) for x in sub.rmse],
                           "anomaly_correlation": [None if pd.isna(x) else round(float(x), 4)
                                                   for x in sub.get("anomaly_correlation", [])],
                           "skill_vs_l0_percent": [round(float(x), 2) for x in sub.skill_vs_L0_percent]}
        meta = _read_json(SCIENCE / "sst_only_eval_meta.json", "SST-only metadata missing")
        out["sst_only"] = {"status": "COMPLETED", "depths_m": sorted(int(d) for d in m.depth_m.unique()),
                           "models": rows, "meta": meta,
                           "protocol": "outputs/science/PREREGISTRATION.md section 3"}
    else:
        out["sst_only"] = {"status": "NOT_RUN",
                           "note": "SST-only experimental baseline has not completed on this machine"}
    return out


# ------------------------------------------------------------------ physical QA
@router.get("/api/science/physical-qa")
def science_physical_qa():
    return _read_json(SCIENCE / "physical_qa_summary.json",
                      "physical QA not computed: run scripts/science/run_physical_qa.py")


@router.get("/api/science/physical-qa/profile")
def science_physical_profile(lat: float, lon: float, date: str | None = None,
                             source: str = "historical"):
    from ..diagnostics.bathymetry import local_water_depth
    from ..replay.engine import DEPTHS
    engine = replay_api.engine()
    row, col = _cell(engine, lat, lon)
    if source == "historical":
        from ..poc.app import get_view
        view = get_view(date)
    else:
        from ..poc.app import _qualified_latest_field
        result = _qualified_latest_field(engine)[0]
        if result is None:
            raise HTTPException(503, "Latest OceanEmbed reconstruction unavailable.")
        view = result.view
    if not (view.ocean_mask[row, col] and view.surface_input_valid[row, col]):
        raise HTTPException(422, "no reconstructed column at this cell on this date")
    water = local_water_depth(strict=False)
    w = None if water is None else float(water[row, col])
    profile = physical_qa.single_profile(view.temperature[row, col], DEPTHS, w)
    summary = None
    try:
        summary = json.loads((SCIENCE / "physical_qa_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    context = None
    if summary:
        basin = vc.basin_for(float(engine.lat[row]), float(engine.lon[col])) or "nio"
        ref = summary["reference_glorys"].get(basin, summary["reference_glorys"]["nio"])
        rec = summary["reconstruction"].get(basin, summary["reconstruction"]["nio"])
        g = profile["strongest_gradient_c_per_m"]
        context = {"region": basin,
                   "reference_percentile": physical_qa.percentile_of(g, ref["strongest_gradient_quantiles"]),
                   "reconstruction_percentile": physical_qa.percentile_of(g, rec["strongest_gradient_quantiles"]),
                   "reference_inversion_frequency": {b: v["inversion_frequency"] for b, v in ref["bands"].items()},
                   "note": "percentile of this column's strongest cooling gradient within the "
                           "pre-registered QA sample (GLORYS reference and reconstruction)"}
    return {"date": view.date, "lat": float(engine.lat[row]), "lon": float(engine.lon[col]),
            "water_depth_m": w, "profile": profile, "context": context}


@router.get("/api/science/basin-physics")
def science_basin_physics():
    data = _read_json(SCIENCE / "basin_physics.json",
                      "basin comparison not computed: run scripts/science/run_physical_qa.py")
    attr = SCIENCE / "basin_attribution.json"
    if attr.exists():
        data["attribution"] = json.loads(attr.read_text(encoding="utf-8"))
    return data


# ------------------------------------------------------------------ validation / integrity
@router.get("/api/science/validation-context")
def science_validation_context(depth: int = 100, lat: float | None = None,
                               lon: float | None = None):
    return vc.context(depth, lat, lon)


@router.get("/api/science/integrity")
def science_integrity():
    return integrity.checks(replay_api.engine())


# ------------------------------------------------------------------ coastal
@router.get("/api/science/coastal")
def science_coastal(lat: float, lon: float):
    try:
        return coastal.lookup(lat, lon)
    except coastal.CoastalContextUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/api/science/coastal/batch")
def science_coastal_batch(body: dict):
    points = [p for p in (body.get("points") or []) if isinstance(p, dict)][:40]
    try:
        return {"results": coastal.lookup_many(points), "provenance": coastal.provenance()}
    except coastal.CoastalContextUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/api/science/coastal/provenance")
def science_coastal_provenance():
    return coastal.provenance()


# ------------------------------------------------------------------ thermal extremes
def _grid(a: np.ndarray, digits: int | None = None):
    out = []
    for row in a:
        if digits is None:
            out.append([int(v) for v in row])
        else:
            out.append([None if not np.isfinite(v) else round(float(v), digits) for v in row])
    return out


@router.get("/api/science/thermal-extremes")
def science_thermal_extremes(date: str, depth: int = 100, grid: bool = True):
    engine = replay_api.engine()
    try:
        r = extremes.evaluate(engine, date, depth)
    except extremes.BaselineUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload = {k: r[k] for k in ("date", "depth_m", "name", "rule", "window", "window_days",
                                 "extent_km2", "n_active_cells", "mhw_decision")}
    payload["baseline"] = {k: r["baseline_meta"][k] for k in
                           ("baseline", "percentile", "half_window_days", "smoothing_days",
                            "threshold_sha256", "l2_state_dict_sha256")}
    payload["extent_note"] = "latitude-aware cell areas of active, physically supported cells"
    if grid:
        payload["active"] = _grid(r["active"].astype(int))
        payload["excess_c"] = _grid(np.where(r["active"], r["excess"], np.nan), 2)
    return payload


@router.get("/api/science/thermal-extremes/point")
def science_thermal_extreme_point(date: str, lat: float, lon: float, depth: int = 100):
    engine = replay_api.engine()
    row, col = _cell(engine, lat, lon)
    try:
        r = extremes.evaluate(engine, date, depth)
    except extremes.BaselineUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    sup = bool(r["support"][row, col])

    def f(a, digits):
        v = float(a[row, col])
        return None if not (sup and np.isfinite(v)) else round(v, digits)
    return {"date": r["date"], "depth_m": r["depth_m"], "lat": float(engine.lat[row]),
            "lon": float(engine.lon[col]), "supported": sup,
            "active": bool(r["active"][row, col]),
            "duration_days": int(r["duration"][row, col]) if r["active"][row, col] else 0,
            "duration_at_least": bool(r["censored"][row, col]),
            "excess_over_threshold_c": f(r["excess"], 2),
            "percentile_in_baseline_window": f(r["percentile"], 1),
            "name": r["name"], "rule": r["rule"], "window": r["window"]}


# ------------------------------------------------------------------ RI study
@router.get("/api/science/ri-study")
def science_ri_study():
    return _read_json(SCIENCE / "ri_study" / "ri_summary.json",
                      "RI study not computed: run scripts/science/run_ri_study.py")


@router.get("/api/science/channels")
def science_channels():
    return {"channels": [{"key": c, "label": LABELS[c], "short": SHORT[c]} for c in CHANNELS],
            "n_channels": len(CHANNELS),
            "mask_note": "the encoder also reads a validity-mask plane; it is not a physical "
                         "channel and is never attributed or ablated"}
