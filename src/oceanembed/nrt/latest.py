"""Phase 8B — the authoritative latest qualified field path.

    latest_qualified_field()
      -> resolve the common valid date D over the five qualified products
      -> retrieve all seven channels for D from exactly the qualified datasets
      -> harmonise with the SAME functions the hindcast used
      -> evaluate the pre-registered request-time conditions L1-L5
      -> REFUSE, with reasons, if any condition fails (no partial stack, no fallback)
      -> the engine's own frozen whole-field inference (ReplayEngine._infer)
      -> 101x241x15 FieldView + L0 + anomaly, with complete per-source provenance

Everything here is fixed by ``outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md``
(commit 5b69dda) and gated on ``outputs/phase8b/qualification_decision.json``:
without a qualified decision on disk, no latest inference runs at all.

There is no second network implementation. The inference call is the same
``_infer`` Historical Replay uses, handed an assembled seven-channel field exactly
as the hindcast did, so a latest field and a hindcast field differ only in their
inputs. Authentication is delegated to the configured Copernicus Marine and
NASA Earthdata clients; this module never reads, prints or stores a credential.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import xarray as xr

from ..config import EAST, NORTH, REPO_ROOT, SOUTH, WEST
from ..ml.features import SURFACE
from ..replay.contract import DEPTHS, FieldView
from . import harmonize as H
from . import qualification as Q
from .discover import poll_product
from .registry import PRODUCTS
from .substitution import joint_mask

DECISION_PATH = REPO_ROOT / "outputs" / "phase8b" / "qualification_decision.json"
PROTOCOL_PATH = "outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md"
PROTOCOL_COMMIT = "5b69dda"
SNAPSHOT_DIR = REPO_ROOT / "outputs" / "phase8b" / "latest_snapshot"
WORK_DIR = REPO_ROOT / "outputs" / "phase8b" / "cache"

PAD = 1.0                          # identical to training and the hindcast
BOX = dict(minimum_longitude=WEST - PAD, maximum_longitude=EAST + PAD,
           minimum_latitude=SOUTH - PAD, maximum_latitude=NORTH + PAD)

POLICY = {
    "name": "NRT_STACK_V1 / COMMON_VALID_DATE / SSS_MULTIOBS_NRT_SAME_DATE",
    "stack": "NRT_STACK_V1",
    "alignment": "COMMON_VALID_DATE",
    "sss_policy": "SSS_MULTIOBS_NRT_SAME_DATE",
    "persistence_envelope_days": 0,
    "policy_version": "8B.1",
}
#: product -> the channels it supplies. Every channel comes from exactly one.
PRODUCT_CHANNELS = {
    "sst_nrt": ("sst",),
    "sss_nrt_multiobs": ("sss",),
    "sla_nrt": ("sla",),
    "currents_nrt": ("current_u", "current_v"),
    "wind_nrt": ("wind_u", "wind_v"),
}
#: Protocol L4: the 6C-D < 5 % joint-mask coverage-loss condition.
COVERAGE_TOLERANCE = 0.05

OPERATING_MODE = "LATEST_QUALIFIED_NRT_STACK_V1"
LIVE_STATE = "LATEST_QUALIFIED"
SNAPSHOT_STATE = "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT_NOT_CURRENT"
UNAVAILABLE_STATE = "LATEST_QUALIFIED_OCEAN_STATE_CURRENTLY_UNAVAILABLE"
NOT_QUALIFIED_STATE = "NOT_QUALIFIED"
SNAPSHOT_LABEL = "LAST SUCCESSFUL QUALIFIED SNAPSHOT — NOT CURRENT"
UNAVAILABLE_LABEL = "LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE"
NOT_QUALIFIED_LABEL = "LATEST SUBSURFACE RECONSTRUCTION NOT QUALIFIED"
QUALIFIED_TAB = "Latest Qualified Ocean State"
UNQUALIFIED_TAB = "Latest Inputs"

#: Human-facing statements added in the Phase 8B hardening pass. They explain
#: the frozen results; they change no category, gate or threshold.
TIMELINESS_NOTE = (
    "Scientific input-stack qualification and operational timeliness are separate. "
    "The reconstruction is valid for the common valid date of all seven inputs, "
    "which trails the retrieval time by the reconstruction lag shown with it. "
    "Operational timeliness has not been separately certified; the field is never "
    "'the ocean now'.")
D26_TCHP_EXPLANATION = (
    "D26 is withheld as a standalone operational diagnostic because its depth error "
    "degraded significantly. TCHP was independently evaluated end-to-end and passed "
    "its frozen non-inferiority criterion. The internal 26°C crossing required for "
    "TCHP calculation is not exposed as a qualified D26 product.")
HAZARD_TRANSFER_NOTE = (
    "Latest Ocean Hazard Indicators are qualified by transfer from the frozen TCHP "
    "rule; not observationally validated as a cyclone forecast.")

CLIMATOLOGY_NOTE = (
    "isfinite(climatology) records CLIMATOLOGY DEPTH-SUPPORT availability - where "
    "the frozen L0 has coefficients. It is NOT a bathymetry product and NOT an "
    "authoritative seafloor mask. Anomaly is NaN where it is False because there "
    "is no baseline to subtract. The raw frozen-L2 temperature is preserved at all "
    "15 mandated depths regardless.")


class LatestRefused(RuntimeError):
    """The complete qualified stack is not available; no inference was run."""

    def __init__(self, reasons: list[str], sources: list[dict] | None = None,
                 effective_date: str | None = None):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)
        self.sources = sources or []
        self.effective_date = effective_date


# ------------------------------------------------------------------ decision
def load_decision(path: Path | None = None) -> dict | None:
    p = Path(path) if path else DECISION_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _decision_sha(path: Path | None = None) -> str | None:
    p = Path(path) if path else DECISION_PATH
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def qualification_summary(path: Path | None = None) -> dict:
    """What the UI may claim, read from the frozen decision artifact only.

    The tab name, the banner and every "qualified" statement in the frontend
    derive from this. A missing or unqualified artifact can never produce a
    qualified claim.
    """
    d = load_decision(path)
    if d is None:
        return {"qualified": False, "temperature_category": Q.NOT_QUALIFIED,
                "tab_name": UNQUALIFIED_TAB, "banner": NOT_QUALIFIED_LABEL,
                "reason": "qualification artifact missing or unreadable",
                "d26_category": Q.NOT_QUALIFIED, "tchp_category": Q.NOT_QUALIFIED,
                "latest_hazard_indicators": "HISTORICAL ONLY"}
    cat = d["temperature_category"]
    ok = Q.is_qualified(cat)
    limitations = [
        "No observational (in-situ) validation of the operational stack exists: the "
        "NRT products begin in 2024, 2022-2023 Argo predates them and 2024 Argo is "
        "protected. The hindcast reference is the GLORYS12V1 reanalysis, which "
        "assimilates observations and is not independent truth.",
        f"Operational inputs move the reconstruction materially: at 100 m the stack "
        f"shift is s = {d['stack_sensitivity']['s_ratio_100m']:.2f} of the frozen "
        f"model's own error (band {d['stack_sensitivity']['band_100m']}; verdict "
        f"{d['stack_verdict']}).",
        "SLA (all-satellite DUACS NRT) and currents (OSCAR NRT) were decided "
        "SUBSTITUTE_WITH_MONITORING in Phase 6C-D.",
        D26_TCHP_EXPLANATION,
        HAZARD_TRANSFER_NOTE,
        TIMELINESS_NOTE,
        "Deep-ocean daily anomaly skill is weaker and more climatology-dominant at "
        "500-1000 m; a low deep RMSE is not strong deep anomaly skill.",
        "The reconstruction is valid for the common valid date of all seven inputs, "
        "which trails the retrieval time; it is not the ocean 'now'.",
    ]
    for region, depths in d.get("depths_where_N_does_not_beat_L0", {}).items():
        if depths:
            limitations.append(
                f"{region.replace('_', ' ').title()}: the operational mode did not "
                f"beat climatology at {', '.join(str(x) for x in depths)} m in the "
                f"hindcast.")
    return {
        "qualified": ok,
        "temperature_category": cat,
        "tab_name": QUALIFIED_TAB if ok else UNQUALIFIED_TAB,
        "banner": cat if ok else NOT_QUALIFIED_LABEL,
        "d26_category": d.get("d26_category", Q.NOT_QUALIFIED),
        "tchp_category": d.get("tchp_category", Q.NOT_QUALIFIED),
        "latest_hazard_indicators": d.get("latest_hazard_indicators", "HISTORICAL ONLY"),
        "qualified_reachable_in_8b": d.get("qualified_reachable_in_8b", False),
        "qualified_unreachable_reason": d.get("qualified_unreachable_reason"),
        "limitations": limitations if ok else [],
        "timeliness_note": TIMELINESS_NOTE,
        "d26_tchp_explanation": D26_TCHP_EXPLANATION,
        "hazard_transfer_note": HAZARD_TRANSFER_NOTE,
        "policy": POLICY,
        "products": {k: PRODUCTS[k]["dataset_id"] for k in PRODUCT_CHANNELS},
        "stack_verdict": d.get("stack_verdict"),
        "gates": d.get("gates"),
        "hindcast": {"n_dates": d.get("n_dates_used"),
                     "window": [d["dates_used"][0], d["dates_used"][-1]]
                     if d.get("dates_used") else None,
                     "replay_mode": d.get("replay_mode")},
        "protocol": PROTOCOL_PATH, "protocol_commit": d.get("protocol_commit"),
        "decision_sha256": _decision_sha(path),
    }


# ------------------------------------------------------------------ sources
@dataclass
class SourceRecord:
    product_key: str
    channels: list[str]
    product_id: str
    dataset_id: str
    doi: str | None
    provider: str
    source_tier: str = "NRT"
    state: str = "PENDING"
    newest_valid_time: str | None = None
    product_valid_time: str | None = None
    local_retrieval_time: str | None = None
    age_hours: float | None = None
    harmonisation: str | None = None
    error: str | None = None


def _now() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize(None).floor("s")


def _iso(t) -> str | None:
    return None if t is None or pd.isna(t) else pd.Timestamp(t).isoformat()


def _state_from_error(message: str) -> str:
    low = message.lower()
    if any(w in low for w in ("credential", "login", "unauthor", "401", "403",
                              "netrc", "authentic")):
        return "AUTH_FAILED"
    return "UNREACHABLE"


def _record(key: str) -> SourceRecord:
    p = PRODUCTS[key]
    return SourceRecord(product_key=key, channels=list(PRODUCT_CHANNELS[key]),
                        product_id=p["product_id"], dataset_id=p["dataset_id"],
                        doi=p.get("doi"), provider=p["provider"])


def _complete_day(key: str, newest: pd.Timestamp) -> pd.Timestamp:
    """Newest calendar day the product fully covers.

    Wind is hourly and is aggregated to a daily U/V mean, so a day counts only
    once its 23:00 field exists; the daily products are stamped once per day.
    """
    newest = pd.Timestamp(newest)
    if key == "wind_nrt" and newest.hour < 23:
        return (newest - pd.Timedelta(days=1)).normalize()
    return newest.normalize()


def resolve_common_date(poll: Callable = poll_product
                        ) -> tuple[pd.Timestamp | None, dict[str, SourceRecord]]:
    """COMMON_VALID_DATE: D = min over products of the newest complete day."""
    records, days = {}, {}
    for key in PRODUCT_CHANNELS:
        rec = _record(key)
        res = poll(key)
        newest = res.get("newest_valid_time")
        if res.get("success") and newest is not None:
            rec.newest_valid_time = _iso(newest)
            days[key] = _complete_day(key, newest)
        else:
            err = res.get("error") or "no newest valid time resolved"
            rec.state, rec.error = _state_from_error(err), err
        records[key] = rec
    if len(days) != len(PRODUCT_CHANNELS):
        return None, records
    return min(days.values()), records


# ------------------------------------------------------------------ fetchers
_CM_VARIABLES = {"sst_nrt": ["analysed_sst"], "sla_nrt": ["sla"],
                 "sss_nrt_multiobs": ["sos"],
                 "wind_nrt": ["eastward_wind", "northward_wind"]}
_HARMONISE = {"sst_nrt": H.harmonise_sst, "sla_nrt": H.harmonise_sla,
              "sss_nrt_multiobs": H.harmonise_multiobs_sss,
              "wind_nrt": H.harmonise_wind_hourly, "currents_nrt": H.harmonise_oscar}


def copernicus_day(key: str, day: pd.Timestamp, workdir: Path) -> xr.Dataset:
    """One day of one Copernicus product, harmonised onto the canonical grid."""
    import copernicusmarine as cm
    workdir.mkdir(parents=True, exist_ok=True)
    name = f"{key}_{day.date()}.nc"
    cm.subset(dataset_id=PRODUCTS[key]["dataset_id"], variables=_CM_VARIABLES[key],
              output_directory=str(workdir), output_filename=name,
              file_format="netcdf", overwrite=True, disable_progress_bar=True,
              start_datetime=f"{day.date()}T00:00:00",
              end_datetime=f"{day.date()}T23:59:59", **BOX)
    with xr.open_dataset(workdir / name) as ds:
        return _HARMONISE[key](ds.load())


def oscar_day(day: pd.Timestamp, workdir: Path) -> xr.Dataset:
    """One OSCAR NRT day via the same OPeNDAP server-side subset as 6C-D."""
    import earthaccess
    import requests  # noqa: F401  (earthaccess session dependency)

    earthaccess.login(strategy="netrc")
    ymd = str(day.date()).replace("-", "")
    grans = earthaccess.search_data(short_name=PRODUCTS["currents_nrt"]["dataset_id"],
                                    temporal=(str(day.date()), str(day.date())),
                                    count=20)
    urls = sorted({u["URL"] for g in grans for u in g["umm"].get("RelatedUrls", [])
                   if u.get("Type") == "USE SERVICE API" and "opendap" in u.get("URL", "")
                   and ymd in u["URL"]})
    if not urls:
        raise FileNotFoundError(f"no OSCAR NRT granule for {day.date()}")
    sess = earthaccess.get_requests_https_session()

    def read(content):
        with xr.open_dataset(io.BytesIO(content), engine="h5netcdf") as d:
            return d.load().copy(deep=True)

    r = sess.get(urls[0] + ".dap.nc4", params={"dap4.ce": "/lat;/lon"}, timeout=180)
    r.raise_for_status()
    d0 = read(r.content)
    lat = np.ravel(d0["lat"].values)
    lon = ((np.ravel(d0["lon"].values) + 180) % 360) - 180
    la = np.where((lat >= BOX["minimum_latitude"]) & (lat <= BOX["maximum_latitude"]))[0]
    lo = np.where((lon >= BOX["minimum_longitude"]) & (lon <= BOX["maximum_longitude"]))[0]
    ce = (f"/u[0:1:0][{lo.min()}:1:{lo.max()}][{la.min()}:1:{la.max()}];"
          f"/v[0:1:0][{lo.min()}:1:{lo.max()}][{la.min()}:1:{la.max()}];"
          f"/lat[{la.min()}:1:{la.max()}];/lon[{lo.min()}:1:{lo.max()}];/time[0:1:0]")
    rr = sess.get(urls[0] + ".dap.nc4", params={"dap4.ce": ce}, timeout=300)
    rr.raise_for_status()
    return H.harmonise_oscar(read(rr.content))


def default_fetchers() -> dict[str, Callable]:
    return {"sst_nrt": lambda d, w: copernicus_day("sst_nrt", d, w),
            "sla_nrt": lambda d, w: copernicus_day("sla_nrt", d, w),
            "sss_nrt_multiobs": lambda d, w: copernicus_day("sss_nrt_multiobs", d, w),
            "wind_nrt": lambda d, w: copernicus_day("wind_nrt", d, w),
            "currents_nrt": oscar_day}


def assemble(day: pd.Timestamp, records: dict[str, SourceRecord],
             fetchers: dict[str, Callable], workdir: Path
             ) -> dict[str, np.ndarray]:
    """Retrieve every product for D. A failure is recorded, never papered over."""
    arrays: dict[str, np.ndarray] = {}
    for key, rec in records.items():
        try:
            ds = fetchers[key](day, workdir)
            rec.local_retrieval_time = _iso(_now())
            times = pd.DatetimeIndex(ds.time.values).normalize()
            if list(times) != [day]:
                rec.state = "NOT_ON_COMMON_DATE"
                rec.error = (f"retrieved valid dates {[str(t.date()) for t in times]} "
                             f"!= common date {day.date()}")
                continue
            for ch in rec.channels:
                a = np.asarray(ds[ch].sel(time=day).values, dtype="float64")
                if a.shape != (101, 241) or not np.isfinite(a).any():
                    raise ValueError(f"{ch}: unusable field shape {a.shape}")
                arrays[ch] = a
            rec.product_valid_time = _iso(day)
            rec.age_hours = round(
                (pd.Timestamp(rec.local_retrieval_time) - day).total_seconds() / 3600, 2)
            rec.harmonisation = f"nrt.harmonize.{_HARMONISE[key].__name__}"
            rec.state = "OK"
        except Exception as exc:  # noqa: BLE001 - reported per source, not raised
            rec.local_retrieval_time = rec.local_retrieval_time or _iso(_now())
            msg = f"{type(exc).__name__}: {exc}"
            rec.state, rec.error = _state_from_error(msg), msg
    return arrays


# ------------------------------------------------------------------ conditions
_CELLS: dict[str, tuple] = {}


def reference_cells(engine) -> tuple[np.ndarray, np.ndarray]:
    """The 6C-D / hindcast cell list: 2024 store surface support on day 0."""
    if "rc" not in _CELLS:
        siv = np.asarray(engine._store(2024)["surface_input_valid"].isel(time=0).values,
                         dtype=bool)
        _CELLS["rc"] = np.nonzero(siv)
    return _CELLS["rc"]


def check_conditions(engine, arrays: dict, records: dict[str, SourceRecord],
                     day: pd.Timestamp, decision: dict) -> tuple[list[str], float | None]:
    """Protocol section 10, L1-L5. Returns (reasons to refuse, coverage)."""
    from ..replay.engine import (EXPECTED_L2_ENCODER, EXPECTED_L2_STATE_DICT,
                                 EXPECTED_SHA256, state_dict_sha256)
    reasons: list[str] = []
    for ch in SURFACE:                                              # L1
        key = decision["products"].get(ch)
        rec = records.get(key) if key else None
        if rec is None or rec.dataset_id != PRODUCTS[key]["dataset_id"]:
            reasons.append(f"L1: {ch} is not from its qualified dataset")
        elif ch not in arrays:
            reasons.append(f"L1: {ch} not retrieved ({rec.state}"
                           + (f": {rec.error}" if rec.error else "") + ")")
    for rec in records.values():                                    # L2
        if rec.state == "OK" and rec.product_valid_time != _iso(day):
            reasons.append(f"L2: {rec.product_key} valid {rec.product_valid_time} "
                           f"!= common date {day.date()}")
    coverage = None
    if not reasons:                                                 # L4
        rr, cc = reference_cells(engine)
        coverage = float(joint_mask(arrays)[rr, cc].mean())
        floor = float(decision["reference_coverage_mean"]) - COVERAGE_TOLERANCE
        if coverage < floor:
            reasons.append(f"L4: joint-mask coverage {coverage:.4f} below {floor:.4f}")
    sd = engine.model.state_dict()                                  # L5
    enc = {k[len("encoder."):]: v for k, v in sd.items() if k.startswith("encoder.")}
    if (state_dict_sha256(sd) != EXPECTED_L2_STATE_DICT
            or state_dict_sha256(enc) != EXPECTED_L2_ENCODER
            or any(engine.file_hashes[k] != v for k, v in EXPECTED_SHA256.items())):
        reasons.append("L5: a frozen artifact hash does not match")
    return reasons, coverage


# ------------------------------------------------------------------ inference
@dataclass
class LatestResult:
    view: FieldView
    surface: dict[str, np.ndarray]
    sources: list[dict]
    meta: dict = field(default_factory=dict)


def infer(engine, arrays: dict[str, np.ndarray], day: pd.Timestamp,
          sources: list[dict], meta: dict) -> FieldView:
    """The engine's own inference on the assembled field - identical to the
    hindcast's call, so latest and hindcast differ only in their inputs."""
    ref = engine._store(2024)
    jm = joint_mask(arrays)
    shim = xr.Dataset(
        {**{v: (("time", "lat", "lon"), arrays[v][None]) for v in SURFACE},
         "surface_input_valid": (("time", "lat", "lon"), jm[None])},
        coords={"time": [np.datetime64(day)], "lat": ref.lat.values,
                "lon": ref.lon.values})
    t0 = time.perf_counter()
    temperature, siv = engine._infer(shim, 0, day)
    clim = np.moveaxis(engine.climatology.predict(pd.DatetimeIndex([day]))[0], 0, -1)
    seconds = time.perf_counter() - t0
    ocean = np.asarray(ref["ocean_mask"].isel(time=0).values, dtype=bool)
    prov = {**engine.provenance,
            "inference_source": "LIVE_MODEL_RUN",
            "compute_seconds": seconds,
            "operating_mode": OPERATING_MODE,
            "n_supported_cells": int(siv.sum()),
            "n_ocean_cells": int(ocean.sum()),
            "climatology_defined_note": CLIMATOLOGY_NOTE,
            "effective_date": str(day.date()),
            "sources": sources,
            **meta}
    return FieldView(date=str(day.date()), temperature=temperature,
                     climatology=clim.astype("float64"),
                     anomaly=temperature - clim, lat=engine.lat.copy(),
                     lon=engine.lon.copy(), depths=list(DEPTHS), ocean_mask=ocean,
                     surface_input_valid=siv, provenance=prov).validate()


@dataclass
class PreparedStack:
    """A complete stack that has passed L1-L5. Nothing has been inferred yet."""
    day: pd.Timestamp
    arrays: dict[str, np.ndarray]
    records: dict[str, SourceRecord]
    decision: dict
    coverage: float | None
    started: pd.Timestamp
    decision_path: Path | None = None


def prepare_stack(engine, fetchers: dict[str, Callable] | None = None,
                  poll: Callable | None = None, decision_path: Path | None = None,
                  workdir: Path | None = None) -> PreparedStack:
    """Resolve, retrieve and check the complete stack. Refuses, never guesses.

    Network-bound and model-free, so the caller can run it without holding the
    engine lock: a slow provider must never block Historical Replay.
    """
    decision = load_decision(decision_path)
    if decision is None or not Q.is_qualified(decision.get("temperature_category", "")):
        raise LatestRefused([
            "operational mode is not qualified: "
            + (decision or {}).get("temperature_category", "no qualification artifact")])
    started = _now()
    day, records = resolve_common_date(poll or poll_product)
    if day is None:
        raise LatestRefused(["no common valid date: "
                             + ", ".join(f"{r.product_key} {r.state}"
                                         for r in records.values() if r.error)],
                            [asdict(r) for r in records.values()])
    arrays = assemble(day, records, fetchers or default_fetchers(),
                      Path(workdir) if workdir else WORK_DIR / str(day.date()))
    reasons, coverage = check_conditions(engine, arrays, records, day, decision)
    if reasons:
        raise LatestRefused(reasons, [asdict(r) for r in records.values()],
                            str(day.date()))
    return PreparedStack(day, arrays, records, decision, coverage, started,
                         decision_path)


def latest_qualified_field(engine, fetchers: dict[str, Callable] | None = None,
                           poll: Callable | None = None,
                           decision_path: Path | None = None,
                           workdir: Path | None = None) -> LatestResult:
    """The ONLY way a latest subsurface field is produced. Refuses, never guesses."""
    return run_prepared(engine, prepare_stack(engine, fetchers, poll,
                                              decision_path, workdir))


def run_prepared(engine, prepared: PreparedStack) -> LatestResult:
    """Frozen inference on a stack that already passed every condition."""
    day, records, decision = prepared.day, prepared.records, prepared.decision
    coverage, started, decision_path = (prepared.coverage, prepared.started,
                                        prepared.decision_path)
    arrays = prepared.arrays
    sources = [asdict(r) for r in records.values()]
    ages = [r.age_hours for r in records.values() if r.age_hours is not None]
    retrieved = max(pd.Timestamp(r.local_retrieval_time) for r in records.values())
    meta = {
        "qualification": decision["temperature_category"],
        "qualification_protocol": PROTOCOL_PATH,
        "qualification_protocol_commit": decision.get("protocol_commit"),
        "decision_sha256": _decision_sha(decision_path),
        "policy": POLICY,
        "requested_utc": _iso(started),
        "retrieval_time_utc": _iso(retrieved),
        "oldest_input_age_hours": max(ages),
        "newest_input_age_hours": min(ages),
        "reconstruction_lag_hours": round((retrieved - day).total_seconds() / 3600, 2),
        "persisted_inputs": "none - every channel is valid on the effective date",
        "joint_mask_coverage": coverage,
        "reference_coverage_mean": decision["reference_coverage_mean"],
        "d26_category": decision["d26_category"],
        "tchp_category": decision["tchp_category"],
        "latest_hazard_indicators": decision["latest_hazard_indicators"],
        "replay_mode": "OPERATIONAL_LATEST",
    }
    view = infer(engine, arrays, day, sources, meta)
    return LatestResult(view=view, surface=arrays, sources=sources, meta=meta)


# ------------------------------------------------------------------ snapshot
def snapshot_identity(result: LatestResult) -> dict:
    """Cache identity (protocol 8B.12): everything that makes the output what it is."""
    p = result.view.provenance
    return {
        "l2_state_dict_sha256": p["l2_state_dict_sha256"],
        "l2_encoder_sha256": p["l2_encoder_sha256"],
        "feature_scaler_sha256": p["feature_scaler_sha256"],
        "target_scaler_sha256": p["target_scaler_sha256"],
        "climatology_sha256": p["climatology_sha256"],
        "processing_version": p["processing_version"],
        "grid_version": p["grid_version"],
        "policy_version": POLICY["policy_version"],
        "policy": POLICY["name"],
        "source_products": {s["product_key"]: s["dataset_id"] for s in result.sources},
        "source_valid_times": {s["product_key"]: s["product_valid_time"]
                               for s in result.sources},
        "source_ages_hours": {s["product_key"]: s["age_hours"] for s in result.sources},
        "persisted_inputs": "none",
        "effective_date": result.view.date,
        "qualification_protocol_commit": p.get("qualification_protocol_commit"),
        "decision_sha256": p.get("decision_sha256"),
    }


def save_snapshot(result: LatestResult, directory: Path | None = None) -> Path:
    """Persist the EXACT output of a successful qualified run. Nothing else."""
    if result.view.provenance.get("operating_mode") != OPERATING_MODE or \
            result.view.provenance.get("inference_source") != "LIVE_MODEL_RUN":
        raise ValueError("only a live qualified inference may become a snapshot")
    d = Path(directory) if directory else SNAPSHOT_DIR
    d.mkdir(parents=True, exist_ok=True)
    v = result.view
    tmp = d / "field.tmp.npz"
    np.savez_compressed(tmp, temperature=v.temperature, climatology=v.climatology,
                        surface_input_valid=v.surface_input_valid,
                        ocean_mask=v.ocean_mask,
                        **{f"surface_{k}": a for k, a in result.surface.items()})
    tmp.replace(d / "field.npz")
    meta = {"generated_utc": _iso(_now()), "identity": snapshot_identity(result),
            "provenance": v.provenance, "sources": result.sources, "meta": result.meta}
    (d / "meta.tmp.json").write_text(json.dumps(meta, indent=2, default=str),
                                     encoding="utf-8")
    (d / "meta.tmp.json").replace(d / "meta.json")
    return d


def load_snapshot(engine, directory: Path | None = None,
                  decision_path: Path | None = None) -> LatestResult | None:
    """The last qualified output, or None. Invalid if the model or decision changed."""
    d = Path(directory) if directory else SNAPSHOT_DIR
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        z = np.load(d / "field.npz")
    except (OSError, ValueError):
        return None
    ident = meta["identity"]
    prov_now = engine.provenance
    if (ident["l2_state_dict_sha256"] != prov_now["l2_state_dict_sha256"]
            or ident["climatology_sha256"] != prov_now["climatology_sha256"]
            or ident["decision_sha256"] != _decision_sha(decision_path)):
        return None
    generated = pd.Timestamp(meta["generated_utc"])
    prov = {**meta["provenance"],
            "inference_source": "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT",
            "snapshot_generated_utc": meta["generated_utc"],
            "snapshot_staleness_hours": round(
                (_now() - generated).total_seconds() / 3600, 2)}
    t, c = z["temperature"], z["climatology"]
    view = FieldView(date=ident["effective_date"], temperature=t, climatology=c,
                     anomaly=t - c, lat=engine.lat.copy(), lon=engine.lon.copy(),
                     depths=list(DEPTHS), ocean_mask=z["ocean_mask"].astype(bool),
                     surface_input_valid=z["surface_input_valid"].astype(bool),
                     provenance=prov).validate()
    surface = {k[len("surface_"):]: z[k] for k in z.files if k.startswith("surface_")
               and k != "surface_input_valid"}
    return LatestResult(view=view, surface=surface, sources=meta["sources"],
                        meta={**meta["meta"], "identity": ident,
                              "snapshot_generated_utc": meta["generated_utc"],
                              "snapshot_staleness_hours": prov["snapshot_staleness_hours"]})
