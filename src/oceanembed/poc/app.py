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
from ..cyclones import gdacs
from ..events import library as event_library
from ..events import series as event_series_lib
from ..events import track_analysis as track_lib
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
UNLOCKED_PREFIXES = ("/api/latest", "/api/cyclones")


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


@app.get("/api/basins")
def basins() -> dict:
    """The existing named analysis basins, served so the UI keeps no copy of its own.

    These are the rectangular boxes already used by the Phase 6 and Phase 8
    evaluations (``oceanembed.ml.metrics.BASINS``). A location outside every box
    is named by its coordinates only; no informal region name is invented.
    """
    from ..ml.metrics import BASINS
    return {"basins": {name: {"lat": list(box["lat"]), "lon": list(box["lon"])}
                       for name, box in BASINS.items()},
            "source": "oceanembed.ml.metrics.BASINS"}


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


@app.get("/api/events")
def events_index() -> dict:
    """Enabled historical cyclone events, and every candidate with its exclusion reason."""
    return event_library.list_events()


EVENT_TRACK_LABEL = ("Track: external historical observation - IBTrACS v04r01 best track "
                     "(IMD / RSMC New Delhi agency values)")
THERMAL_LABEL = "Thermal state: OceanEmbed frozen-L2 reconstruction"
COMPARE_NOTE = (
    "Reconstructed ocean changes along each observed-track corridor. These numbers do "
    "not rank cyclone danger, and OceanEmbed does not explain differences in cyclone "
    "intensity by itself. External peak wind and pressure are IMD / RSMC New Delhi "
    "agency values carried by IBTrACS.")
EVENT_LIMITATIONS = [
    "OceanEmbed reconstructs subsurface temperature from surface satellite inputs; it "
    "does not forecast cyclone genesis, track, intensity or landfall.",
    "Corridor values average cells within 1.5 degrees of the observed best track.",
    "TCHP reconstruction error is comparable to a thermal-support category width at a "
    "single cell (Phase 7C).",
    "Changes between dates are differences between independent daily "
    "reconstructions; they may be consistent with cyclone-associated cooling or "
    "mixing, but OceanEmbed does not establish their cause.",
    "No recovery category, severity rank or probability is produced.",
]
_EVENT_BUNDLES: dict = {}
_BUNDLE_ORDER: list = []


def _event_or_404(event_id: str) -> dict:
    try:
        return event_library.get_event(event_id)
    except event_library.EventNotFound as exc:
        raise HTTPException(404, f"No enabled event {event_id!r}") from exc


def _resolve_segment(ev: dict, name: str) -> str:
    wanted = name.strip().upper()
    for seg in ev["segments"]:
        if seg["label"].upper() == wanted or \
                seg["label"].split("/")[0].strip().upper() == wanted:
            return seg["label"]
    raise HTTPException(422, f"event has no segment {name!r}")


def _event_bundle(event_id: str) -> dict:
    """Each window date replayed once: series rows and per-segment composites."""
    if event_id in _EVENT_BUNDLES:
        return _EVENT_BUNDLES[event_id]
    ev = _event_or_404(event_id)
    engine = replay_api.engine()
    corridor = event_series_lib.corridor_mask(ev["track"]["points"], engine.lat, engine.lon)
    accumulators = {seg["label"]: track_lib.CompositeAccumulator() for seg in ev["segments"]}
    rows = []
    for stamp in pd.date_range(ev["window_start"], ev["window_end"], freq="D"):
        day = str(stamp.date())
        ctx = track_lib.field_context(get_view(day))
        rows.append(event_series_lib.series_row(ctx, corridor))
        for seg in ev["segments"]:
            if seg["start"] <= day <= seg["end"]:
                accumulators[seg["label"]].add(ctx)
    bundle = {"rows": rows, "corridor_cells": int(corridor.sum()),
              "composites": {k: a.result() for k, a in accumulators.items()}}
    _EVENT_BUNDLES[event_id] = bundle
    _BUNDLE_ORDER.append(event_id)
    while len(_BUNDLE_ORDER) > 4:
        _EVENT_BUNDLES.pop(_BUNDLE_ORDER.pop(0), None)
    return bundle


def _event_points(ev: dict) -> list[dict]:
    return [{"lat": p["lat"], "lon": p["lon"], "time": p["time"], "point_type": "observed"}
            for p in ev["track"]["points"]]


def _event_date(ev: dict, date: str) -> str:
    if not (ev["window_start"] <= date <= ev["window_end"]):
        raise HTTPException(422, f"{date} is outside the {ev['name']} replay window")
    return date


def _basin_name(lat: float, lon: float) -> str | None:
    from ..ml.metrics import BASINS
    for name, box in BASINS.items():
        if box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]:
            return name.replace("_", " ").title().replace(" Of ", " of ")
    return None


@app.get("/api/events/compare")
def events_compare(ids: str) -> dict:
    chosen = [i for i in dict.fromkeys(x.strip() for x in ids.split(",")) if i]
    if not 2 <= len(chosen) <= 4:
        raise HTTPException(422, "Compare two to four enabled events")
    water = local_water_depth(strict=False)
    out = []
    for event_id in chosen:
        ev = _event_or_404(event_id)
        bundle = _event_bundle(event_id)
        change = track_lib.difference(
            bundle["composites"][ev["segments"][0]["label"]],
            bundle["composites"][_resolve_segment(ev, "WAKE")], water)
        out.append({
            "event_id": event_id, "name": ev["name"], "basin": ev["basin"],
            "season": ev["season"], "split": ev["split"], "in_sample": ev["in_sample"],
            "window": [ev["window_start"], ev["window_end"]],
            "metrics": event_series_lib.event_metrics(bundle["rows"], ev["segments"]),
            "pre_to_wake_footprint": change["footprint"],
            "external_metadata": ev["external_metadata"],
            "track_source": ev["track"]["dataset"]})
    return {"events": out, "note": COMPARE_NOTE,
            "corridor_deg": event_series_lib.CORRIDOR_DEG}


@app.get("/api/events/{event_id}")
def event_detail(event_id: str) -> dict:
    return _event_or_404(event_id)


@app.get("/api/events/{event_id}/series")
def event_detail_series(event_id: str) -> dict:
    ev = _event_or_404(event_id)
    bundle = _event_bundle(event_id)
    return {"event": ev["name"], "event_id": event_id,
            "window": [ev["window_start"], ev["window_end"]],
            "corridor_deg": event_series_lib.CORRIDOR_DEG,
            "corridor_cells": bundle["corridor_cells"],
            "corridor_note": "cells within 1.5 degrees of any observed track point; the "
                             "track is static context and never enters inference",
            "independence_note": ev["independence_note"],
            "series": bundle["rows"],
            "metrics": event_series_lib.event_metrics(bundle["rows"], ev["segments"])}


@app.get("/api/events/{event_id}/track-analysis")
def event_track_analysis(event_id: str, date: str) -> dict:
    ev = _event_or_404(event_id)
    ctx = track_lib.field_context(get_view(_event_date(ev, date)))
    return {**track_lib.analyze(ctx, _event_points(ev)), "event_id": event_id,
            "field_source": "historical replay_field",
            "labels": {"track": EVENT_TRACK_LABEL, "thermal_state": THERMAL_LABEL}}


@app.get("/api/events/{event_id}/section")
def event_section(event_id: str, date: str, mode: str = "temperature") -> dict:
    ev = _event_or_404(event_id)
    ctx = track_lib.field_context(get_view(_event_date(ev, date)))
    try:
        payload = track_lib.section(ctx, _event_points(ev), mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**payload, "event_id": event_id,
            "labels": {"track": EVENT_TRACK_LABEL, "thermal_state": THERMAL_LABEL}}


@app.get("/api/events/{event_id}/difference")
def event_difference(event_id: str, to_segment: str = "Wake",
                     from_segment: str = "Pre-event", depth: int = 100,
                     tchp_grid: bool = False) -> dict:
    ev = _event_or_404(event_id)
    a, b = _resolve_segment(ev, from_segment), _resolve_segment(ev, to_segment)
    bundle = _event_bundle(event_id)
    try:
        change = track_lib.difference(bundle["composites"][a], bundle["composites"][b],
                                      local_water_depth(strict=False), depth, tchp_grid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**change, "event_id": event_id, "from_segment": a, "to_segment": b,
            "label": "Change between frozen-segment composites of independent daily "
                     "reconstructions.",
            "caution": "A cooling pattern may be consistent with cyclone-associated "
                       "mixing; OceanEmbed does not establish its cause."}


@app.get("/api/events/{event_id}/brief")
def event_brief(event_id: str) -> dict:
    ev = _event_or_404(event_id)
    bundle = _event_bundle(event_id)
    metrics = event_series_lib.event_metrics(bundle["rows"], ev["segments"])
    water = local_water_depth(strict=False)
    pre = bundle["composites"][ev["segments"][0]["label"]]
    to_wake = track_lib.difference(pre, bundle["composites"][_resolve_segment(ev, "WAKE")], water)
    to_recovery = track_lib.difference(
        pre, bundle["composites"][_resolve_segment(ev, "RECOVERY")], water)
    region = to_wake["footprint"]["tchp"]["min"]
    sentences = []
    if metrics["pre_event_tchp"] is not None:
        sentences.append(f"Before the event, corridor TCHP averaged "
                         f"{metrics['pre_event_tchp']:.1f} kJ/cm2.")
    if metrics["tchp_change"] is not None and metrics["wake_min_tchp"]:
        verb = "fell" if metrics["tchp_change"] < 0 else "did not fall"
        sentences.append(
            f"In the wake segment corridor TCHP {verb} to a minimum of "
            f"{metrics['wake_min_tchp']['value']:.1f} kJ/cm2 on "
            f"{metrics['wake_min_tchp']['date']} ({metrics['tchp_change']:+.1f} kJ/cm2).")
    if metrics["final_vs_pre_tchp"] is not None and metrics["final"]:
        sentences.append(
            f"By {metrics['final']['date']} TCHP was {abs(metrics['final_vs_pre_tchp']):.1f} "
            f"kJ/cm2 {'below' if metrics['final_vs_pre_tchp'] < 0 else 'above'} the "
            f"pre-event mean.")
    return {
        "title": "CYCLONE OCEAN RESPONSE BRIEF", "event_id": event_id, "event": ev["name"],
        "basin": ev["basin"], "event_dates": [ev["window_start"], ev["window_end"]],
        "peak": ev["peak"], "landfall": ev["landfall"], "segments": ev["segments"],
        "track_source": EVENT_TRACK_LABEL, "external_metadata": ev["external_metadata"],
        "metrics": metrics,
        "strongest_subsurface_cooling_c": {
            "0": to_wake["footprint"]["temperature"]["0"]["min"],
            "100": to_wake["footprint"]["temperature"]["100"]["min"]},
        "strongest_affected_thermal_region": (
            {**region, "basin": _basin_name(region["lat"], region["lon"]),
             "quantity": "largest TCHP decrease, Pre-event to Wake composite"}
            if region else None),
        "pre_to_wake_footprint": to_wake["footprint"],
        "pre_to_recovery_footprint": to_recovery["footprint"],
        "interpretation": sentences,
        "limitations": EVENT_LIMITATIONS + [ev["split_note"]],
        "provenance": {
            "model": "L2 Spatial Satellite Embedding Engine (frozen)",
            "l2_state_dict_sha256": replay_api.engine().l2_state_dict_sha256,
            "l2_encoder_sha256": replay_api.engine().l2_encoder_sha256,
            "split": ev["split"], "in_sample": ev["in_sample"],
            "phase_rule": ev["selection"], "independence_note": ev["independence_note"],
            "track_citation": ev["track"]["citation"]},
        "non_prediction": NON_PREDICTION_STATEMENT,
    }


@app.get("/api/events/{event_id}/stress-test")
def event_stress_test(event_id: str, mode: str = "temperature") -> dict:
    """The event's OBSERVED geometry, unmoved, sampled on the historical and the
    latest qualified field. Replayed historical geometry, not a forecast."""
    from ..science import coastal, stress_test
    ev = _event_or_404(event_id)
    points = _event_points(ev)
    historical_ctx = track_lib.field_context(get_view(ev["peak"]))
    historical = track_lib.analyze(historical_ctx, points)
    result, summary = _qualified_latest_field(replay_api.engine())
    base = {"label": stress_test.LABEL, "note": stress_test.NOTE, "event_id": event_id,
            "event": ev["name"], "geometry": {"source": EVENT_TRACK_LABEL, "points": points,
                                              "translated": False, "retimed": False},
            "historical": {"date": ev["peak"], "analysis": historical,
                           "section": track_lib.section(historical_ctx, points, mode),
                           "field": "historical replay_field on the event peak date"}}
    try:
        base["coastal_approach"] = coastal.track_coastal_approach(historical["samples"])
    except coastal.CoastalContextUnavailable:
        base["coastal_approach"] = None
    if result is None:
        return {**base, "latest": None, "comparison": None, "latest_state": LATEST_UNAVAILABLE}
    latest_ctx = track_lib.field_context(result.view, _withheld(summary))
    latest = track_lib.analyze(latest_ctx, points)
    assert stress_test.same_geometry(historical["samples"], latest["samples"])
    return {**base,
            "latest": {"date": result.view.date, "analysis": latest,
                       "section": track_lib.section(latest_ctx, points, mode),
                       "withheld": list(latest_ctx.withheld),
                       "reconstruction_lag_hours": result.meta.get("reconstruction_lag_hours"),
                       "field": "latest qualified OceanEmbed field"},
            "comparison": stress_test.compare(historical, latest)}


def _advisory_points(adv: dict) -> list[dict]:
    return [{"lat": p["lat"], "lon": p["lon"], "valid_time": p["valid_time"],
             "point_type": p["point_type"]}
            for p in adv["observed_points"] + adv["forecast_points"]]


def _qualified_latest_field(engine):
    """The newest immutable qualified field on disk, or the last snapshot, or None."""
    from ..nrt import latest as LQ
    summary = LQ.qualification_summary()
    if not summary["qualified"]:
        return None, summary
    root = LQ.DAILY_CACHE_DIR
    days = sorted((d.name for d in root.iterdir() if d.is_dir()), reverse=True) \
        if root.is_dir() else []
    for day in days:
        result = LQ.load_daily(engine, day)
        if result is not None:
            return result, summary
    return LQ.load_snapshot(engine), summary


def _withheld(summary: dict) -> tuple:
    return tuple(k for k in ("d26", "tchp") if summary.get(f"{k}_category") != "QUALIFIED")


def _hours_between(advisory_iso: str, valid_date: str) -> float:
    advisory = pd.Timestamp(advisory_iso).tz_localize(None) \
        if pd.Timestamp(advisory_iso).tzinfo is None else \
        pd.Timestamp(advisory_iso).tz_convert(None)
    return round((advisory - pd.Timestamp(valid_date)).total_seconds() / 3600, 1)


LATEST_UNAVAILABLE = ("Latest OceanEmbed reconstruction unavailable. Historical Event "
                      "Intelligence remains available.")


@app.get("/api/cyclones/current")
async def cyclones_current():
    """Active North Indian Ocean cyclones according to GDACS (external context only)."""
    result = await run_in_threadpool(gdacs.current_cyclones, gdacs.fetch_json, gdacs.CACHE_FILE)
    return JSONResponse(result)


@app.get("/api/cyclones/current/thermal-analysis")
async def cyclones_current_thermal(index: int = 0, mode: str = "temperature"):
    current = await run_in_threadpool(gdacs.current_cyclones, gdacs.fetch_json, gdacs.CACHE_FILE)
    advisories = current.get("advisories") or []
    if not advisories:
        return JSONResponse({**current, "advisory": None, "analysis": None, "section": None})
    if not 0 <= index < len(advisories):
        raise HTTPException(422, "no advisory at that index")
    adv = advisories[index]
    engine = replay_api.engine()
    async with _engine_lock():
        result, summary = await run_in_threadpool(_qualified_latest_field, engine)
        if result is None:
            return JSONResponse({**current, "advisory": adv, "analysis": None,
                                 "section": None, "latest_state": LATEST_UNAVAILABLE})
        ctx = await run_in_threadpool(track_lib.field_context, result.view, _withheld(summary))
    points = _advisory_points(adv)
    try:
        section_payload = track_lib.section(ctx, points, mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse({
        **current, "advisory": adv,
        "analysis": track_lib.analyze(ctx, points), "section": section_payload,
        "thermal_field": {
            "source": "latest qualified OceanEmbed field", "valid_date": result.view.date,
            "served_from": result.view.provenance.get("inference_source"),
            "retrieval_time_utc": result.meta.get("retrieval_time_utc"),
            "reconstruction_lag_hours": result.meta.get("reconstruction_lag_hours"),
            "advisory_minus_valid_hours": _hours_between(adv["advisory_issued_at"],
                                                         result.view.date),
            "withheld": list(ctx.withheld)},
        "labels": {"track": adv["provenance_label"],
                   "thermal_state": "Thermal state: latest qualified OceanEmbed reconstruction"}})


@app.get("/api/cyclones/archived-test")
async def cyclones_archived_test(mode: str = "temperature"):
    """An archived GDACS advisory, labelled HISTORICAL / TEST EVENT, never live."""
    payload = gdacs.archived_test_advisory()
    adv = payload["advisories"][0]
    date = adv["advisory_issued_at"][:10]
    points = _advisory_points(adv)
    async with _engine_lock():
        view = await run_in_threadpool(get_view, date)
        ctx = await run_in_threadpool(track_lib.field_context, view)
    try:
        section_payload = track_lib.section(ctx, points, mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse({
        **payload, "advisory": adv,
        "analysis": track_lib.analyze(ctx, points), "section": section_payload,
        "thermal_field": {
            "source": "historical replay_field", "valid_date": date,
            "advisory_minus_valid_hours": _hours_between(adv["advisory_issued_at"], date),
            "withheld": []},
        "labels": {"track": f"HISTORICAL / TEST EVENT · {adv['provenance_label']}",
                   "thermal_state": f"Thermal state: OceanEmbed historical reconstruction "
                                    f"for {date}, the archived advisory date"}})


SCENARIO_BADGE = "USER-DRAWN SCENARIO - NOT AN OFFICIAL FORECAST"


@app.post("/api/scenario/analysis")
def scenario_analysis(body: dict) -> dict:
    """Thermal conditions along a user-drawn path. Not a forecast of anything."""
    source = body.get("field", "historical")
    mode = body.get("mode", "temperature")
    points = [{"lat": p.get("lat"), "lon": p.get("lon")} for p in (body.get("points") or [])
              if isinstance(p, dict)]
    if source == "historical":
        date = body.get("date")
        if not date:
            raise HTTPException(422, "a historical scenario needs a date")
        view, withheld = get_view(str(date)), ()
        field_meta = {"source": "historical replay_field", "valid_date": view.date}
    elif source == "latest":
        result, summary = _qualified_latest_field(replay_api.engine())
        if result is None:
            raise HTTPException(503, LATEST_UNAVAILABLE)
        view, withheld = result.view, _withheld(summary)
        field_meta = {"source": "latest qualified OceanEmbed field",
                      "valid_date": view.date,
                      "reconstruction_lag_hours": result.meta.get("reconstruction_lag_hours")}
    else:
        raise HTTPException(422, "field must be 'historical' or 'latest'")
    ctx = track_lib.field_context(view, withheld)
    try:
        analysis = track_lib.analyze(ctx, points)
        section_payload = track_lib.section(ctx, points, mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"badge": SCENARIO_BADGE, "analysis": analysis, "section": section_payload,
            "thermal_field": {**field_meta, "withheld": list(withheld)},
            "labels": {"path": "Path: user-drawn scenario - not an observed or forecast track",
                       "thermal_state": THERMAL_LABEL}}


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
        if refresh:
            # A user refresh must bypass the persisted fast path as well as
            # memory. Clearing memory alone reloaded the same disk discovery.
            dates, errors = await run_in_threadpool(LQ.channel_dates, allow_persisted=False)
            window = LQ.available_window(days, dates, errors)
        else:
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
        dates, errors = await run_in_threadpool(LQ.channel_dates, allow_persisted=not refresh)
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
# Model Science and disaster-context endpoints (science package); registered before
# the static mount so the SPA fallback can never shadow them.
from ..science.api import router as science_router  # noqa: E402
app.include_router(science_router)
DIST = REPO_ROOT / "web/dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if not (DIST / "index.html").is_file():
        raise HTTPException(503, "Frontend build unavailable. Run npm ci and npm run build in web/.")
    return FileResponse(DIST / "index.html")
