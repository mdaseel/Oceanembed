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


@asynccontextmanager
async def lifespan(application):
    application.state.engine_lock = asyncio.Lock()
    yield


app = FastAPI(title="OceanEmbed Historical PoC", version="7B", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=3)


@app.middleware("http")
async def local_transport(request, call_next):
    # xarray/netCDF and the shared replay cache are serialized in one process.
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
    # Derived on the server from the SAME authoritative field the map and the
    # profile use, so a D26 shown on the map and a D26 shown for a clicked cell
    # cannot come from two different calculations.
    diag = field_diagnostics(view)
    # Physical water-column support: the SAME ETOPO artifact the 3D view reads.
    # It qualifies the presentation; it never edits a raw model value.
    water = local_water_depth(strict=False)
    d26_phys, tchp_phys = qualify(diag, water)
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
        "surface_inputs": {
            name: {"values": replay_api._nan_to_none(ds[name].isel(time=t).values),
                   "units": _UNITS[name], "product": _PRODUCTS[name]}
            for name in view.provenance["surface_inputs"]
        },
        "diagnostics": {
            "d26_m": replay_api._nan_to_none(diag.d26),
            "tchp_kj_cm2": replay_api._nan_to_none(diag.tchp),
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
                               view.ocean_mask & view.surface_input_valid),
        "provenance": view.provenance,
        "credits": CREDITS,
    }


def hazard_block(diag, d26_phys, tchp_phys, population) -> dict:
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
        "scope_note": (
            "Historical only. Not connected to live or near-real-time data. No "
            "numeric cyclone probability is produced."),
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
