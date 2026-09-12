"""Local UI and additive transport over the unchanged Phase 7A replay API."""
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
import xarray as xr
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from ..config import REPO_ROOT
from ..diagnostics import (CONVENTION, D26Status, DISPLAY_VALID_RULE,
                           PHYSICAL_SUPPORT_RULE, PhysicalSupport,
                           bathymetry_provenance, depth_physically_valid,
                           display_valid, field_diagnostics, local_water_depth,
                           qualify)
from ..diagnostics.hazard import (INDICATOR_NAME, NON_PREDICTION_STATEMENT,
                                  PROTOCOL_PATH, TCHP_ERROR_KJ_CM2,
                                  ThermalSupport, categorize, load_thresholds)
from ..nrt.latest import LatestRefused
from ..replay import api as replay_api
from ..replay.contract import OutsideDomain
from ..replay.engine import _PRODUCTS, _UNITS

TABLES = {
    "grid": "outputs/tables/phase6b_l2_metrics_by_depth_test.csv",
    "argo": "outputs/tables/phase6c_argo_metrics_by_depth.csv",
    "basins": "outputs/tables/phase6b_l2_basin_summary_test.csv",
    "ablation": "outputs/tables/architecture_closure/channel_ablation_depth_groups.csv",
    "noise": "outputs/tables/architecture_closure/ablation_noise_floor.csv",
    "architecture": "outputs/tables/architecture_closure/architecture_review_matrix.csv",
}
DOCUMENTS = {
    "closure": "ARCHITECTURE_CLOSURE_REPORT.md",
    "architecture": "ARCHITECTURE_REVIEW.md",
    "l2": "PHASE6B_L2_REPORT.md",
    "argo": "PHASE6C_ARGO_VALIDATION_REPORT.md",
}
CREDITS = (
    "Surface inputs: OSTIA, CMEMS MULTIOBS and DUACS / Copernicus Marine; "
    "OSCAR Final v2.0 and CCMP v3.1 / NASA PO.DAAC. "
    "Training reference: GLORYS12V1 / Copernicus Marine."
)


async def _warm_latest_states() -> None:
    """Pre-produce the recent qualified states so the tab opens instantly.

    Runs in the background at startup: the provider downloads happen off the
    event loop and outside the engine lock, so Historical Replay is never made
    to wait for them. Each date is still fully qualified; this only fills the
    immutable per-date cache ahead of the user.
    """
    from ..nrt import latest as LQ
    try:
        summary = await run_in_threadpool(LQ.qualification_summary)
        if not summary.get("qualified"):
            return
        engine = await run_in_threadpool(replay_api.engine)
        await run_in_threadpool(LQ.reference_cells, engine)
        await run_in_threadpool(LQ.warm_recent_states, engine, 7)
    except Exception:  # noqa: BLE001 - warm-up must never break startup
        pass


@asynccontextmanager
async def lifespan(application):
    application.state.engine_lock = asyncio.Lock()
    application.state.warm_task = asyncio.create_task(_warm_latest_states())
    yield
    task = getattr(application.state, "warm_task", None)
    if task is not None and not task.done():
        task.cancel()


app = FastAPI(title="OceanEmbed Historical PoC", version="7B", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=3)


#: Endpoints that must NOT take the shared engine lock. Live telemetry can take
#: tens of seconds against a remote provider, and Historical Replay must never
#: be blocked by it — a slow or dead network cannot be allowed to take the
#: offline science down with it. These touch no xarray store and no replay cache.
UNLOCKED_PREFIXES = ("/api/latest",)


@app.middleware("http")
async def local_transport(request, call_next):
    # xarray/netCDF and the shared replay cache are serialized in one process.
    if request.url.path.startswith(UNLOCKED_PREFIXES):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    if request.url.path.startswith("/api/"):
        lock = getattr(app.state, "engine_lock", None)
        if lock is None:
            app.state.engine_lock = lock = asyncio.Lock()
        async with lock:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def get_view(date: str, force_recompute: bool = False):
    try:
        if pd.isna(pd.Timestamp(date)):
            raise ValueError("Date is required")
        return replay_api.engine().replay_field(date, force_recompute=force_recompute)
    except (OutsideDomain, ValueError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from exc


def view_payload(view) -> dict:
    """Lossless JSON transport: one field call, no extra point/model calls."""
    e = replay_api.engine()
    when = pd.Timestamp(view.date)
    ds = e._store(when.year)
    t = e._time_index(ds, when)
    surface = {
        name: {"values": replay_api._nan_to_none(ds[name].isel(time=t).values),
               "units": _UNITS[name], "product": _PRODUCTS[name]}
        for name in view.provenance["surface_inputs"]
    }
    return field_payload(view, surface)


def field_payload(view, surface_inputs: dict, withheld: tuple = (),
                  qualification: dict | None = None,
                  hazard_scope: str | None = None) -> dict:
    """The one field-view transport, whatever the source of the field.

    Historical Replay and the Phase 8B latest mode both go through here, so the
    frontend receives the same schema from both and adapts both with the same
    adapter. ``withheld`` names diagnostics the source may not show; a withheld
    diagnostic is transported with no value at all.
    """
    # Derived on the server from the SAME authoritative field the map and the
    # profile use, so a D26 shown on the map and a D26 shown for a clicked cell
    # cannot come from two different calculations.
    diag = field_diagnostics(view)
    # Physical water-column support: the SAME ETOPO artifact the 3D view reads.
    # It qualifies the presentation; it never edits a raw model value.
    water = local_water_depth(strict=False)
    d26_phys, tchp_phys = qualify(diag, water)
    blank = np.full(diag.d26.shape, np.nan)
    return {
        "schema": "oceanembed.field-view.v1",
        "date": view.date,
        "shape": list(view.temperature.shape),
        "lat": view.lat.tolist(), "lon": view.lon.tolist(),
        "depths_m": view.depths,
        **{key: replay_api._nan_to_none(getattr(view, key))
           for key in ("temperature", "climatology", "anomaly")},
        "ocean_mask": view.ocean_mask.tolist(),
        "surface_input_valid": view.surface_input_valid.tolist(),
        "climatology_defined": view.climatology_defined.tolist(),
        "surface_inputs": surface_inputs,
        "diagnostics": {
            "d26_m": replay_api._nan_to_none(blank if "d26" in withheld else diag.d26),
            "tchp_kj_cm2": replay_api._nan_to_none(
                blank if "tchp" in withheld else diag.tchp),
            "withheld": list(withheld),
            "qualification": qualification,
            "status": diag.status.astype(int).tolist(),
            "status_labels": {int(s): s.name for s in D26Status},
            "status_counts": diag.counts(),
            "convention": CONVENTION,
            "d26_physical_status": d26_phys.astype(int).tolist(),
            "tchp_physical_status": tchp_phys.astype(int).tolist(),
            "physical_status_labels": {int(s): s.name for s in PhysicalSupport},
            "physical_status_counts": {
                s.name: int((d26_phys == s).sum()) for s in PhysicalSupport},
        },
        "bathymetry": {
            **bathymetry_provenance(),
            "local_water_depth_m": (replay_api._nan_to_none(water)
                                    if water is not None else None),
            # Two orthogonal counts, never one merged number: how much ocean is
            # deep enough, and how much of that also has surface input today.
            "depth_physically_valid_counts": {
                str(int(d)): int(depth_physically_valid(
                    d, water, view.ocean_mask).sum())
                for d in view.depths},
            "display_valid_counts": {
                str(int(d)): int(display_valid(
                    d, water, view.ocean_mask, view.surface_input_valid).sum())
                for d in view.depths},
        },
        "hazard": hazard_block(diag, d26_phys, tchp_phys,
                               view.ocean_mask & view.surface_input_valid,
                               scope_note=hazard_scope),
        "provenance": view.provenance,
        "credits": CREDITS,
    }


HISTORICAL_HAZARD_SCOPE = (
    "Historical only. Not connected to live or near-real-time data. No "
    "numeric cyclone probability is produced.")


def hazard_block(diag, d26_phys, tchp_phys, population,
                 scope_note: str | None = None) -> dict:
    """Ocean Thermal Support, derived from the SAME diagnostics shown elsewhere.

    No second inference path and no client-side recomputation. A category exists
    only where TCHP is defined and physically supported; every other cell is
    NOT_CATEGORIZED with its reason left readable from the Phase 7C status
    arrays already in this payload.
    """
    thresholds = load_thresholds(strict=False)
    category = categorize(diag.tchp, diag.status, tchp_phys, thresholds)
    return {
        "indicator": INDICATOR_NAME,
        "available": thresholds is not None,
        "category": category.astype(int).tolist(),
        "category_labels": {int(c): c.name for c in ThermalSupport},
        # Counted over the population only. Including land would make
        # NOT_CATEGORIZED look like a huge uncategorised ocean when most of
        # those cells are simply not sea.
        "category_counts": {c.name: int((category[population] == c).sum())
                            for c in ThermalSupport},
        "population_cells": int(population.sum()),
        "thresholds": thresholds.as_dict() if thresholds else None,
        "protocol": PROTOCOL_PATH,
        "reconstruction_error_kj_cm2": TCHP_ERROR_KJ_CM2,
        "non_prediction_statement": NON_PREDICTION_STATEMENT,
        "uncertainty_note": (
            "The category summarises a reconstruction, not a measurement. The "
            "Phase 7C TCHP error is comparable to a category width, so adjacent "
            "categories are not distinguishable at a single cell."),
        "scope_note": scope_note or HISTORICAL_HAZARD_SCOPE,
    }


@app.get("/api/replay/view")
def complete_field(date: str, force_recompute: bool = False):
    return JSONResponse(view_payload(get_view(date, force_recompute)))


#: Fixed by outputs/phase7/EVENT_SELECTION.md, written before any event-specific
#: OceanEmbed output existed. Not chosen here and not tunable at runtime.
EVENT = {
    "name": "Cyclone Mocha (2023)",
    "basin": "Bay of Bengal",
    "window_start": "2023-05-05",
    "window_end": "2023-05-22",
    "peak": "2023-05-13",
    "landfall": "2023-05-14",
    "selection": "outputs/phase7/EVENT_SELECTION.md",
    "segments": [
        {"label": "Pre-event", "start": "2023-05-05", "end": "2023-05-08"},
        {"label": "Approach / intensification", "start": "2023-05-09", "end": "2023-05-12"},
        {"label": "Event", "start": "2023-05-13", "end": "2023-05-14"},
        {"label": "Wake", "start": "2023-05-15", "end": "2023-05-18"},
        {"label": "Recovery", "start": "2023-05-19", "end": "2023-05-22"},
    ],
    "independence_note": (
        "Every date is an independent replay_field call. No temporal model, no "
        "sequence input, and no state carried between days. This is a strip of "
        "independent daily reconstructions, never a forecast."),
    "claim_note": (
        "OceanEmbed reconstructs the subsurface ocean thermal state the cyclone "
        "encountered. It did not predict the storm's genesis, track, landfall, "
        "category or intensity."),
}
TRACK_PATH = REPO_ROOT / "web" / "public" / "assets" / "event" / "track.json"
#: Corridor half-width around the track, in degrees, for the cold-wake average.
CORRIDOR_DEG = 1.5


@app.get("/api/event")
def event() -> dict:
    """The pre-registered event and its bundled offline best track."""
    track = None
    if TRACK_PATH.is_file():
        track = json.loads(TRACK_PATH.read_text(encoding="utf-8"))
    return {**EVENT, "track": track,
            "track_available": track is not None}


@app.get("/api/event/series")
def event_series() -> dict:
    """Cold wake and thermal recovery across the pre-registered window.

    Each date is an INDEPENDENT replay_field call; the series is a sequence of
    separate reconstructions differenced afterwards, never a modelled evolution.
    Values are averaged over a fixed corridor around the observed track so the
    signal comes from the water the storm actually crossed.
    """
    if not TRACK_PATH.is_file():
        raise HTTPException(503, "Bundled event track unavailable")
    track = json.loads(TRACK_PATH.read_text(encoding="utf-8"))
    engine = replay_api.engine()
    lat, lon = engine.lat, engine.lon

    # Fixed corridor: any canonical cell within CORRIDOR_DEG of any track point.
    corridor = np.zeros((lat.size, lon.size), dtype=bool)
    for point in track["points"]:
        corridor |= ((np.abs(lat[:, None] - point["lat"]) <= CORRIDOR_DEG)
                     & (np.abs(lon[None, :] - point["lon"]) <= CORRIDOR_DEG))

    water = local_water_depth(strict=False)
    thresholds = load_thresholds(strict=False)
    dates = pd.date_range(EVENT["window_start"], EVENT["window_end"], freq="D")
    rows = []
    for date in dates:
        view = get_view(str(date.date()))
        diag = field_diagnostics(view)
        _, tchp_phys = qualify(diag, water)
        usable = (corridor & view.ocean_mask & view.surface_input_valid
                  & (tchp_phys == PhysicalSupport.SUPPORTED))
        category = categorize(diag.tchp, diag.status, tchp_phys, thresholds)

        def mean_of(values, mask):
            selected = values[mask]
            selected = selected[np.isfinite(selected)]
            return float(selected.mean()) if selected.size else None

        rows.append({
            "date": view.date,
            "n_cells": int(usable.sum()),
            "sst_nominal_0m_c": mean_of(view.temperature[:, :, 0], usable),
            "temp_100m_c": mean_of(view.temperature[:, :, view.depths.index(100)], usable),
            "anomaly_100m_c": mean_of(view.anomaly[:, :, view.depths.index(100)], usable),
            "d26_m": mean_of(diag.d26, usable),
            "tchp_kj_cm2": mean_of(diag.tchp, usable),
            "category_counts": {c.name: int((category[usable] == c).sum())
                                for c in ThermalSupport},
        })
    return {
        "event": EVENT["name"],
        "window": [EVENT["window_start"], EVENT["window_end"]],
        "corridor_deg": CORRIDOR_DEG,
        "corridor_cells": int(corridor.sum()),
        "corridor_note": "cells within %.1f degrees of any observed track point; "
                         "the track is static context and never enters inference"
                         % CORRIDOR_DEG,
        "independence_note": EVENT["independence_note"],
        "series": rows,
    }


@app.get("/api/latest/cached")
def latest_cached() -> dict:
    """Instant: the last SUCCESSFUL telemetry, or nothing. Never a live fetch.

    Lets the tab render immediately while the live attempt runs, without ever
    presenting the cache as fresh — it is returned under its own state and
    label, with the staleness measured now.
    """
    from ..nrt import telemetry as T
    cached = T.load_snapshot()
    if not cached:
        return {"mode": "LATEST_INPUTS", "phase": "8A", "is_cached": True,
                "state": T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE.value,
                "sources": [], "has_snapshot": False,
                "unavailable_label": "DATA SOURCE CURRENTLY UNAVAILABLE",
                "subsurface_reconstruction": T.NOT_CERTIFIED,
                "why_these_inputs": T.WHY_THESE_INPUTS}
    generated = cached.get("generated_utc")
    staleness = None
    if generated:
        staleness = round((pd.Timestamp.utcnow().tz_localize(None)
                           - pd.Timestamp(generated)).total_seconds() / 3600.0, 2)
    return {**cached, "is_cached": True, "has_snapshot": True,
            "state": T.OverallState.CACHED_TELEMETRY_NOT_CURRENT.value,
            "cached_generated_utc": generated,
            "cached_staleness_hours": staleness,
            "cache_label": "LAST SUCCESSFUL TELEMETRY - NOT CURRENT",
            "subsurface_reconstruction": T.NOT_CERTIFIED,
            "why_these_inputs": T.WHY_THESE_INPUTS}


@app.get("/api/latest")
def latest(region: bool = True) -> dict:
    """Attempt a real live fetch of the two NRT inputs. Telemetry only.

    Defined as a sync endpoint so FastAPI runs it in a worker thread: a slow
    provider must not block the event loop, and it never takes the engine lock.
    No model is run here and no subsurface field is produced.
    """
    from ..nrt import telemetry as T
    return T.telemetry_payload(with_region=region)


# ------------------------------------------------------------------ Phase 8B
LATEST_HAZARD_SCOPE = (
    "Latest qualified mode. Qualified by transfer from the frozen TCHP rule; not "
    "observationally validated as a cyclone forecast. The Phase 7D indicator logic "
    "and thresholds are unchanged; its transfer to the operational stack was "
    "qualified under the Phase 8B protocol (section 9) because TCHP was. It "
    "describes the ocean "
    "thermal environment on the effective date. No numeric cyclone probability "
    "is produced.")


def _engine_lock():
    lock = getattr(app.state, "engine_lock", None)
    if lock is None:
        app.state.engine_lock = lock = asyncio.Lock()
    return lock


def latest_state_payload(result, state: str, summary: dict,
                         label: str | None = None, live_attempt: dict | None = None,
                         newest_date: str | None = None) -> dict:
    """A latest field in the SAME field-view transport as Historical Replay."""
    from ..nrt import latest as LQ
    from ..nrt.registry import PRODUCTS
    by_channel = {ch: s for s in result.sources for ch in s["channels"]}
    surface = {
        ch: {"values": replay_api._nan_to_none(result.surface[ch]),
             "units": _UNITS[ch],
             "product": (f"{PRODUCTS[by_channel[ch]['product_key']]['product_id']} "
                         f"(NRT, valid {result.view.date})")}
        for ch in result.view.provenance["surface_inputs"]
    }
    withheld = tuple(k for k in ("d26", "tchp")
                     if summary.get(f"{k}_category") != "QUALIFIED")
    field = field_payload(
        result.view, surface, withheld=withheld,
        qualification={"d26": summary.get("d26_category"),
                       "tchp": summary.get("tchp_category")},
        hazard_scope=LATEST_HAZARD_SCOPE)
    if summary.get("latest_hazard_indicators") != "QUALIFIED":
        field.pop("hazard", None)
    return {"mode": "LATEST_QUALIFIED_OCEAN_STATE", "phase": "8B", "state": state,
            "label": label, "qualification": summary,
            "effective_date": result.view.date,
            "selected_date": result.view.date,
            "newest_qualified_date": newest_date,
            "is_newest": bool(newest_date is not None
                              and result.view.date == newest_date),
            "served_from": result.view.provenance.get("inference_source"),
            "sources": result.sources,
            "meta": result.meta, "live_attempt": live_attempt,
            "policy": LQ.POLICY, "field": field}


def _latest_fallback(engine, summary: dict, live_attempt: dict) -> dict:
    from ..nrt import latest as LQ
    snap = LQ.load_snapshot(engine)
    if snap is not None:
        return latest_state_payload(snap, LQ.SNAPSHOT_STATE, summary,
                                    LQ.SNAPSHOT_LABEL, live_attempt)

    return {"mode": "LATEST_QUALIFIED_OCEAN_STATE", "phase": "8B",
            "state": LQ.UNAVAILABLE_STATE, "label": LQ.UNAVAILABLE_LABEL,
            "qualification": summary, "live_attempt": live_attempt,
            "policy": LQ.POLICY, "field": None}


def _not_qualified(summary: dict) -> dict:
    from ..nrt import latest as LQ
    return {"mode": "LATEST_QUALIFIED_OCEAN_STATE", "phase": "8B",
            "state": LQ.NOT_QUALIFIED_STATE, "label": LQ.NOT_QUALIFIED_LABEL,
            "qualification": summary, "field": None}


@app.get("/api/latest/qualification")
def latest_qualification() -> dict:
    """What the UI may claim, read from the frozen decision artifact only."""
    from ..nrt import latest as LQ
    return LQ.qualification_summary()


@app.get("/api/latest/qualified/cached")
async def latest_qualified_cached():
    """Instant: the last qualified snapshot, labelled NOT CURRENT, or nothing."""
    from ..nrt import latest as LQ
    summary = LQ.qualification_summary()
    if not summary["qualified"]:
        return JSONResponse(_not_qualified(summary))
    async with _engine_lock():
        payload = await run_in_threadpool(
            _latest_fallback, replay_api.engine(), summary,
            {"attempted": False, "reason": "cached view requested"})
    return JSONResponse(payload)


@app.get("/api/latest/prewarm")
async def latest_prewarm(days: int = 7):
    """Start (or report) the background warm-up of the recent qualified states.

    Returns immediately; it never blocks the page that asked for it.
    """
    from ..nrt import latest as LQ
    summary = LQ.qualification_summary()
    if not summary["qualified"]:
        return JSONResponse({"started": False, "reason": "not qualified"})
    task = getattr(app.state, "warm_task", None)
    if task is None or task.done():
        app.state.warm_task = asyncio.create_task(_warm_latest_states())
        started = True
    else:
        started = False
    return JSONResponse({"started": started, "running": True,
                         "status": dict(LQ.WARM_STATUS)})


@app.get("/api/latest/available-dates")
async def latest_available_dates(days: int = 7, refresh: bool = False):
    """Which recent dates the COMPLETE seven-channel stack can actually supply.

    Read from the providers' own time axes and granule catalogue, so an
    unavailable day names the channel that is missing rather than being
    silently skipped. Nothing is inferred here.
    """
    from ..nrt import latest as LQ
    summary = LQ.qualification_summary()
    if not summary["qualified"]:
        return JSONResponse({**_not_qualified(summary), "days": []})
    if refresh:
        LQ.refresh_discovery()
    try:
        window = await run_in_threadpool(LQ.available_window, days)
    except Exception as exc:  # noqa: BLE001 - discovery failure is not a crash
        return JSONResponse({"qualification": summary, "days": [],
                             "newest_qualified_date": None,
                             "error": f"{type(exc).__name__}: {exc}"})
    # A window served from the persisted fast path says so, and a refresh is
    # started behind it so the newest date cannot stay stale.
    age = dict(LQ.DISCOVERY_AGE)
    if age.get("from_disk"):
        task = getattr(app.state, "warm_task", None)
        if task is None or task.done():
            app.state.warm_task = asyncio.create_task(_warm_latest_states())
    return JSONResponse({**window, "qualification": summary,
                         "warm_status": dict(LQ.WARM_STATUS),
                         "discovery_age_seconds": round(age.get("seconds", 0.0)),
                         "discovery_refreshing": bool(age.get("from_disk"))})


@app.get("/api/latest/qualified")
async def latest_qualified(date: str | None = None, refresh: bool = False):
    """Attempt a new latest qualified reconstruction from the complete stack.

    Retrieval and the L1-L5 checks run WITHOUT the engine lock, so a slow or
    dead provider never blocks Historical Replay. Only the frozen inference
    itself takes the lock. Any refusal returns the last qualified snapshot,
    labelled NOT CURRENT, or the unavailable state - never a partial stack.
    """
    from ..nrt import latest as LQ
    summary = LQ.qualification_summary()
    if not summary["qualified"]:
        return JSONResponse(_not_qualified(summary))
    engine = replay_api.engine()
    if refresh:
        LQ.refresh_discovery()
    async with _engine_lock():
        await run_in_threadpool(LQ.reference_cells, engine)

    # Discovery first, so a requested date can be checked against what the
    # providers actually hold before anything is retrieved or inferred. When the
    # in-memory answer is cold, the last persisted one is used rather than making
    # the page wait for every provider: it only decides WHICH date to ask for,
    # and the retrieval itself still verifies that each channel really carries
    # that date (assemble -> NOT_ON_COMMON_DATE) before any inference runs.
    try:
        dates, errors = await run_in_threadpool(LQ.channel_dates)
    except Exception as exc:  # noqa: BLE001
        dates, errors = {}, {"discovery": f"{type(exc).__name__}: {exc}"}
    newest, _ = LQ.resolve_common_date(dates, errors)
    newest_date = None if newest is None else str(newest.date())
    try:
        day = pd.Timestamp(date).normalize() if date else newest
    except (ValueError, TypeError):
        day = None
    if date and day is None:
        return JSONResponse({"mode": "LATEST_QUALIFIED_OCEAN_STATE", "phase": "8B",
                             "state": LQ.DATE_UNAVAILABLE_STATE,
                             "label": LQ.DATE_UNAVAILABLE_LABEL,
                             "qualification": summary, "selected_date": date,
                             "newest_qualified_date": newest_date,
                             "reason": "unparseable date", "field": None})
    if day is not None and day not in LQ.common_dates(dates):
        miss = LQ.missing_channels(day, dates, errors)
        return JSONResponse({
            "mode": "LATEST_QUALIFIED_OCEAN_STATE", "phase": "8B",
            "state": LQ.DATE_UNAVAILABLE_STATE, "label": LQ.DATE_UNAVAILABLE_LABEL,
            "qualification": summary, "selected_date": str(day.date()),
            "newest_qualified_date": newest_date, "missing_channels": miss,
            "reason": "no usable field for " + ", ".join(miss),
            "note": "No inference was run for this date and no channel was "
                    "carried forward from another day.",
            "field": None})

    # An immutable field already produced for this exact date and provenance.
    if day is not None:
        cached = await run_in_threadpool(LQ.load_daily, engine, day)
        if cached is not None:
            state = LQ.LIVE_STATE if str(day.date()) == newest_date else LQ.DATED_STATE
            payload = await run_in_threadpool(latest_state_payload, cached, state,
                                              summary, None, None, newest_date)
            return JSONResponse(payload)

    try:
        prepared = await run_in_threadpool(LQ.prepare_stack, engine, None, dates,
                                           None, None, day)
    except LatestRefused as exc:
        async with _engine_lock():
            payload = await run_in_threadpool(
                _latest_fallback, engine, summary,
                {"attempted": True, "reasons": exc.reasons, "sources": exc.sources,
                 "effective_date": exc.effective_date})
        return JSONResponse(payload)
    except Exception as exc:  # noqa: BLE001 - an unexpected failure is still a refusal
        async with _engine_lock():
            payload = await run_in_threadpool(
                _latest_fallback, engine, summary,
                {"attempted": True, "reasons": [f"{type(exc).__name__}: {exc}"],
                 "sources": []})
        return JSONResponse(payload)
    async with _engine_lock():
        result = await run_in_threadpool(LQ.run_prepared, engine, prepared)
        # The per-date cache is immutable; the single "last successful" snapshot
        # is the offline fallback and may only ever hold the newest state.
        LQ.save_snapshot(result, LQ.daily_cache_dir(result.view.date))
        is_newest = result.view.date == newest_date
        if is_newest:
            LQ.save_snapshot(result)
        payload = await run_in_threadpool(
            latest_state_payload, result,
            LQ.LIVE_STATE if is_newest else LQ.DATED_STATE, summary, None, None,
            newest_date)
    return JSONResponse(payload)


@app.get("/api/evidence")
def evidence():
    tables = {}
    for name, relative in TABLES.items():
        path = REPO_ROOT / relative
        if not path.is_file():
            tables[name] = {"source": relative, "rows": [], "error": "Artifact unavailable"}
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        tables[name] = {"source": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "rows": rows}
    manifest = REPO_ROOT / "outputs/phase7/final_core_manifest.json"
    return {"tables": tables, "manifest": json.loads(manifest.read_text(encoding="utf-8")),
            "inference_statement": "Only surface inputs at inference; no GLORYS target or Argo observations are read by replay.",
            "argo_note": "External Argo observational check, 2022–2023. GLORYS assimilates in-situ observations; this is not perfectly independent truth.",
            "ablation_note": "SST and SLA showed clear incremental predictive value above measured run-to-run noise; SSS/currents/winds showed no detectable incremental contribution under this architecture/dataset/validation setup."}


@app.get("/api/evidence/document/{name}")
def document(name: str):
    if name not in DOCUMENTS:
        raise HTTPException(404, "Unknown evidence document")
    path = REPO_ROOT / DOCUMENTS[name]
    if not path.is_file():
        raise HTTPException(404, "Evidence document unavailable")
    return {"source": DOCUMENTS[name], "markdown": path.read_text(encoding="utf-8")}


@app.get("/api/export/field.nc")
def netcdf(date: str):
    view = get_view(date)
    diag = field_diagnostics(view)
    water = local_water_depth(strict=False)
    d26_phys, tchp_phys = qualify(diag, water)
    # Raw model output is exported unchanged; physical support travels beside it
    # as its own variable so a consumer can qualify without losing the raw value.
    # Bathymetric existence only - `surface_input_valid` is already its own
    # exported variable, so the two stay separable rather than pre-merged.
    valid_by_depth = np.stack(
        [depth_physically_valid(d, water, view.ocean_mask)
         for d in view.depths], axis=-1).astype("int8")
    dims = ("lat", "lon", "depth")
    ds = xr.Dataset(
        {**{name: (dims, getattr(view, name), {"units": "degree_Celsius"})
            for name in ("temperature", "climatology", "anomaly")},
         "ocean_mask": (("lat", "lon"), view.ocean_mask.astype("int8")),
         "surface_input_valid": (("lat", "lon"), view.surface_input_valid.astype("int8")),
         "climatology_defined": (dims, view.climatology_defined.astype("int8"),
                                  {"description": "L0 coefficient availability; not bathymetry"}),
         "d26": (("lat", "lon"), diag.d26,
                 {"units": "m", "long_name": "depth of the 26 degC isotherm",
                  "description": CONVENTION["d26"]}),
         "tchp": (("lat", "lon"), diag.tchp,
                  {"units": "kJ cm-2", "long_name": "tropical cyclone heat potential",
                   "description": CONVENTION["tchp"]}),
         "d26_status": (("lat", "lon"), diag.status.astype("int8"),
                        {"flag_values": [int(s) for s in D26Status],
                         "flag_meanings": " ".join(s.name for s in D26Status),
                         "description": "NaN in d26/tchp means undefined, never zero"}),
         "local_water_depth": (
             ("lat", "lon"),
             water if water is not None else np.full(view.ocean_mask.shape, np.nan),
             {"units": "m", "long_name": "local water depth from ETOPO 2022",
              "description": "static physical context; not a model input, not a "
                             "prediction, and not climatology_defined"}),
         "depth_physically_valid": (
             dims, valid_by_depth,
             {"long_name": "water column reaches this mandated depth",
              "description": PHYSICAL_SUPPORT_RULE +
                             ". Bathymetric existence only: a deep cell whose "
                             "surface input is missing stays 1 here and is "
                             "excluded by surface_input_valid instead. "
                             "display_valid = " + DISPLAY_VALID_RULE +
                             ". Raw temperature is exported unchanged regardless"}),
         "d26_physical_status": (
             ("lat", "lon"), d26_phys.astype("int8"),
             {"flag_values": [int(s) for s in PhysicalSupport],
              "flag_meanings": " ".join(s.name for s in PhysicalSupport),
              "description": "additional qualification; the Phase 7C d26 value "
                             "and d26_status are unchanged"}),
         "tchp_physical_status": (
             ("lat", "lon"), tchp_phys.astype("int8"),
             {"flag_values": [int(s) for s in PhysicalSupport],
              "flag_meanings": " ".join(s.name for s in PhysicalSupport),
              "description": "TCHP integrates to D26, so it inherits D26's "
                             "verdict; SURFACE_BELOW_26 stays a real zero"})},
        coords={"lat": ("lat", view.lat, {"units": "degrees_north"}),
                "lon": ("lon", view.lon, {"units": "degrees_east"}),
                "depth": ("depth", view.depths, {"units": "m", "positive": "down"})},
        attrs={"date": view.date, "credits": CREDITS,
               "provenance_json": json.dumps(view.provenance),
               "nominal_zero_m_note": view.provenance["nominal_zero_m_note"],
               "deep_skill_note": view.provenance["deep_skill_note"]})
    return Response(bytes(ds.to_netcdf(engine="scipy")), media_type="application/x-netcdf",
                    headers={"Content-Disposition": f'attachment; filename="OceanEmbed-{view.date}.nc"'})


# All original Phase 7A endpoints remain available, unchanged.
app.include_router(replay_api.app.router, prefix="/api")
DIST = REPO_ROOT / "web/dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if not (DIST / "index.html").is_file():
        raise HTTPException(503, "Frontend build unavailable. Run npm ci and npm run build in web/.")
    return FileResponse(DIST / "index.html")
