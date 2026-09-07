"""Thin local HTTP wrapper over the Phase 7A replay primitives.

This is transport only. It contains NO inference, NO preprocessing and NO
scientific logic of its own — every endpoint delegates to the same
``ReplayEngine`` the CLI and the tests use, so an HTTP client and a Python
caller can never disagree.

It is deliberately local-first: no authentication, no database, no cloud
dependency, and it binds to localhost by default. Phase 7B consumes it; nothing
about the UI is built here.

    python -m uvicorn oceanembed.replay.api:app --port 8000
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from ..config import EAST, NORTH, SOUTH, WEST
from .contract import (DEEP_SKILL_NOTE, DEPTHS, LocationStatus,
                       NOMINAL_ZERO_M_NOTE, OutsideDomain)
from .engine import DATASET_END, DATASET_START, ReplayEngine

app = FastAPI(
    title="OceanEmbed Historical Replay API",
    version="7A",
    description="Authoritative frozen-L2 historical replay. Surface inputs "
                "only; no target, no Argo, no network.",
)

_engine: ReplayEngine | None = None


def engine() -> ReplayEngine:
    global _engine
    if _engine is None:
        _engine = ReplayEngine()
    return _engine


def _nan_to_none(a: np.ndarray) -> list:
    """JSON has no NaN. Missing stays missing rather than becoming a number."""
    return np.where(np.isfinite(a), a, None).astype(object).tolist()


@app.get("/health")
def health() -> dict:
    e = engine()
    return {
        "status": "ok",
        "mode": "HISTORICAL_REPLAY",
        "model": e.provenance["model_name"],
        "l2_state_dict_sha256": e.l2_state_dict_sha256,
        "l2_encoder_sha256": e.l2_encoder_sha256,
        "grid": {"shape": [int(e.lat.size), int(e.lon.size)],
                 "south": SOUTH, "north": NORTH, "west": WEST, "east": EAST},
        "depths_m": DEPTHS,
        "date_range": [str(DATASET_START.date()), str(DATASET_END.date())],
        "target_used_for_inference": False,
        "argo_used_for_inference": False,
    }


@app.get("/manifest")
def manifest() -> dict:
    return engine().provenance


@app.get("/replay/point")
def point(date: str, lat: float, lon: float,
          force_recompute: bool = False) -> dict:
    try:
        return engine().replay_point(date, lat, lon,
                                     force_recompute=force_recompute).as_dict()
    except OutsideDomain as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/replay/range")
def date_range(start: str, end: str, lat: float, lon: float,
               max_days: int = Query(90, ge=1, le=400)) -> dict:
    try:
        results = engine().replay_range(start, end, lat, lon)
    except OutsideDomain as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(results) > max_days:
        raise HTTPException(
            status_code=422,
            detail=f"{len(results)} days requested, max_days={max_days}. Each "
                   f"day is an independent replay_field call.")
    return {"mode": "HISTORICAL_REPLAY", "n_days": len(results),
            "results": [r.as_dict() for r in results]}


@app.get("/replay/field")
def field(date: str,
          layer: Literal["temperature", "climatology", "anomaly"] = "temperature",
          depth_m: int | None = None,
          force_recompute: bool = False) -> JSONResponse:
    """One depth slice, or the whole 101x241x15 canonical field-view.

    Omitting ``depth_m`` returns the full field. This is the payload the Phase
    7B 3D renderer consumes through its canonical field-view adapter (§7.0);
    arrays are row-major nested lists with ``null`` for missing.
    """
    try:
        view = engine().replay_field(date, force_recompute=force_recompute)
    except OutsideDomain as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    body: dict = {
        "mode": "HISTORICAL_REPLAY",
        "date": view.date,
        "layer": layer,
        "lat": view.lat.tolist(),
        "lon": view.lon.tolist(),
        "depths_m": view.depths,
        "ocean_mask": view.ocean_mask.tolist(),
        "surface_input_valid": view.surface_input_valid.tolist(),
        "nominal_zero_m_note": NOMINAL_ZERO_M_NOTE,
        "deep_skill_note": DEEP_SKILL_NOTE,
        "provenance": view.provenance,
    }
    if depth_m is None:
        body["shape"] = list(view.temperature.shape)
        body["field"] = _nan_to_none(getattr(view, layer))
        body["climatology_defined"] = view.climatology_defined.tolist()
    else:
        if int(depth_m) not in view.depths:
            raise HTTPException(
                status_code=422,
                detail=f"{depth_m} m is not a mandated depth; valid: {view.depths}")
        body["depth_m"] = int(depth_m)
        body["shape"] = [int(view.lat.size), int(view.lon.size)]
        body["field"] = _nan_to_none(view.layer(depth_m, layer))
        body["climatology_defined"] = view.climatology_defined[
            :, :, view.depth_index(depth_m)].tolist()
    return JSONResponse(body)
