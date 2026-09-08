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
        "provenance": view.provenance,
        "credits": CREDITS,
    }


@app.get("/api/replay/view")
def complete_field(date: str, force_recompute: bool = False):
    return JSONResponse(view_payload(get_view(date, force_recompute)))


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
    dims = ("lat", "lon", "depth")
    ds = xr.Dataset(
        {**{name: (dims, getattr(view, name), {"units": "degree_Celsius"})
            for name in ("temperature", "climatology", "anomaly")},
         "ocean_mask": (("lat", "lon"), view.ocean_mask.astype("int8")),
         "surface_input_valid": (("lat", "lon"), view.surface_input_valid.astype("int8")),
         "climatology_defined": (dims, view.climatology_defined.astype("int8"),
                                  {"description": "L0 coefficient availability; not bathymetry"})},
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
