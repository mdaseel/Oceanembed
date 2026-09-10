"""Phase 8A — live input telemetry for SST and SLA. TELEMETRY ONLY.

This module retrieves and describes two *inputs*. It does not run the frozen
L2, does not produce a subsurface field, and does not touch the historical
replay path. Nothing here can produce a temperature reconstruction, by
construction: it imports no model and no replay code.

Why only SST and SLA: the controlled Phase 6B channel ablation (Experiment D)
found clear incremental predictive value from SST near the surface and SLA
through the thermocline, while SSS, currents and winds showed no detectable
incremental contribution above the measured run-to-run noise floor. That does
NOT mean those channels are physically unimportant, and it does NOT mean the
frozen L2 can accept arbitrary values in them. The full seven-channel
operational contract is a Phase 8B question and is not answered here.

Product definitions and the catalogue poll are reused from the Phase 6C-D
registry rather than redefined. Credentials are never read, written or logged
by this module; ``copernicusmarine`` resolves its own stored login, and a
missing or rejected login is reported as an ordinary source failure.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import EAST, NORTH, REPO_ROOT, SOUTH, WEST
from .discover import poll_product
from .registry import PRODUCTS

#: The two channels Phase 8A is scoped to. Not a claim that the others do not
#: matter - see the module docstring.
CHANNELS = ("sst_nrt", "sla_nrt")

SNAPSHOT_PATH = REPO_ROOT / "outputs" / "phase8a" / "last_successful_telemetry.json"

NOT_CERTIFIED = "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED"
TELEMETRY_AVAILABLE = "NRT INPUT TELEMETRY AVAILABLE"

WHY_THESE_INPUTS = (
    "Controlled L2 channel ablation found clear incremental predictive value "
    "from SST near the surface and SLA through the thermocline. SSS, currents "
    "and winds showed no detectable incremental contribution above the measured "
    "training-run noise floor in that experiment. This does NOT mean those "
    "variables are physically unimportant or that the frozen L2 can accept "
    "arbitrary values in those channels. Full operational input qualification "
    "remains future work."
)


class SourceState(str, Enum):
    """Per-source outcome. Never inferred from a network flag alone."""

    OK = "OK"
    #: The catalogue answered and the region was not asked for. This is a
    #: deliberate mode, NOT a failure, and must never be reported as offline:
    #: the provider responded and the valid time and age are real and current.
    CATALOGUE_ONLY = "CATALOGUE_ONLY"
    #: The catalogue answered but the region could not be retrieved.
    COVERAGE_UNAVAILABLE = "COVERAGE_UNAVAILABLE"
    #: Provider rejected the credentials, or none are configured.
    AUTH_FAILED = "AUTH_FAILED"
    #: No answer from the provider.
    UNREACHABLE = "UNREACHABLE"


class OverallState(str, Enum):
    """Whole-tab state, decided from the actual fetch results."""

    ONLINE_CURRENT = "ONLINE_CURRENT"
    ONLINE_PARTIAL = "ONLINE_PARTIAL"
    OFFLINE_OR_SOURCE_UNAVAILABLE = "OFFLINE_OR_SOURCE_UNAVAILABLE"
    CACHED_TELEMETRY_NOT_CURRENT = "CACHED_TELEMETRY_NOT_CURRENT"


@dataclass
class SourceTelemetry:
    """What is actually known about one input. Unknown stays null."""

    channel: str
    product_key: str
    product_id: str
    dataset_id: str
    doi: str | None
    provider: str
    source_tier: str = "NRT"
    state: str = SourceState.UNREACHABLE.value
    #: Newest valid time the provider advertises for this dataset.
    product_valid_time: str | None = None
    #: When THIS machine asked. Kept separate from the valid time, always.
    local_retrieval_time: str | None = None
    #: Provider-side generation time, only when the provider actually states it.
    product_generated_time: str | None = None
    data_age_hours: float | None = None
    #: Fraction of North Indian Ocean cells carrying a finite value, when the
    #: region was actually retrieved. Null when it was not - never guessed.
    nio_coverage_fraction: float | None = None
    nio_cells_valid: int | None = None
    nio_cells_total: int | None = None
    variables: list[str] = field(default_factory=list)
    error: str | None = None
    notes: str | None = None


def _now() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize(None)


def _iso(t) -> str | None:
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    ts = pd.Timestamp(t)
    return None if pd.isna(ts) else ts.isoformat(timespec="seconds")


def _classify_error(message: str) -> SourceState:
    """Auth problems must not be reported as 'the network is down'."""
    lowered = (message or "").lower()
    if any(w in lowered for w in ("credential", "login", "unauthor", "401",
                                  "403", "forbidden", "authentication")):
        return SourceState.AUTH_FAILED
    return SourceState.UNREACHABLE


def fetch_region(product_key: str, valid_time: pd.Timestamp,
                 workdir: Path) -> tuple[float | None, int | None, int | None, str | None]:
    """Subset the North Indian Ocean box for one day and measure coverage.

    Returns (coverage_fraction, valid_cells, total_cells, error). A failure here
    is not fatal: the catalogue answer is still useful telemetry, and coverage
    is reported as unknown rather than invented.
    """
    import copernicusmarine as cm
    import xarray as xr

    product = PRODUCTS[product_key]
    workdir.mkdir(parents=True, exist_ok=True)
    filename = f"{product_key}_{valid_time:%Y%m%d}.nc"
    out = workdir / filename
    try:
        if not out.exists():
            cm.subset(
                dataset_id=product["dataset_id"],
                variables=list(product["variables"]),
                minimum_longitude=WEST, maximum_longitude=EAST,
                minimum_latitude=SOUTH, maximum_latitude=NORTH,
                start_datetime=str(valid_time.normalize()),
                end_datetime=str(valid_time.normalize()),
                output_directory=str(workdir), output_filename=filename,
                file_format="netcdf", overwrite=True,
                disable_progress_bar=True,
            )
        with xr.open_dataset(out) as ds:
            name = product["variables"][0]
            values = np.asarray(ds[name].values, dtype="float64")
            total = int(values.size)
            valid = int(np.isfinite(values).sum())
        return (valid / total if total else None), valid, total, None
    except Exception as exc:  # noqa: BLE001 - a source failure is telemetry
        return None, None, None, f"{type(exc).__name__}: {exc}"


def collect(with_region: bool = True,
            workdir: Path | None = None) -> list[SourceTelemetry]:
    """Poll both NRT sources. Never raises; every failure becomes a state."""
    workdir = workdir or (REPO_ROOT / "outputs" / "phase8a" / "cache")
    out: list[SourceTelemetry] = []
    for key in CHANNELS:
        product = PRODUCTS[key]
        record = SourceTelemetry(
            channel=product["channel"], product_key=key,
            product_id=product["product_id"], dataset_id=product["dataset_id"],
            doi=product.get("doi"), provider=product["provider"],
            variables=list(product["variables"]),
        )
        asked = _now()
        record.local_retrieval_time = _iso(asked)
        poll = poll_product(key)
        newest = poll.get("newest_valid_time")

        if not poll.get("success") or newest is None:
            record.state = _classify_error(poll.get("error") or "").value
            record.error = poll.get("error") or "no newest valid time resolved"
            out.append(record)
            continue

        record.product_valid_time = _iso(newest)
        record.data_age_hours = round(
            (asked - pd.Timestamp(newest)).total_seconds() / 3600.0, 2)
        # The provider states a dataset revision label, not an acquisition
        # timestamp. Recording the label is honest; inventing a time is not.
        if poll.get("revision"):
            record.notes = f"catalogue revision label {poll['revision']}"

        if with_region:
            frac, valid, total, error = fetch_region(key, pd.Timestamp(newest),
                                                     workdir)
            if error is None:
                record.state = SourceState.OK.value
                record.nio_coverage_fraction = frac
                record.nio_cells_valid = valid
                record.nio_cells_total = total
            else:
                record.state = SourceState.COVERAGE_UNAVAILABLE.value
                record.error = error
        else:
            record.state = SourceState.CATALOGUE_ONLY.value
            record.notes = "catalogue poll only; region not requested"
        out.append(record)
    return out


#: Everything the provider actually answered. Distinguishing these from silence
#: is the whole point: an operator must be able to tell "the provider is down"
#: from "I did not ask for the region".
_ANSWERED = {SourceState.OK.value, SourceState.CATALOGUE_ONLY.value,
             SourceState.COVERAGE_UNAVAILABLE.value}


def overall_state(sources: list[SourceTelemetry]) -> OverallState:
    """Decided from actual fetch results, never from a network flag.

    A source counts as fully satisfied when everything that was requested of it
    succeeded — so a catalogue-only poll where the catalogue answered is
    CURRENT, not partial and certainly not offline.
    """
    if not sources:
        return OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE
    satisfied = sum(1 for s in sources
                    if s.state in (SourceState.OK.value,
                                   SourceState.CATALOGUE_ONLY.value))
    answered = sum(1 for s in sources if s.state in _ANSWERED)
    if satisfied == len(sources):
        return OverallState.ONLINE_CURRENT
    if answered:
        return OverallState.ONLINE_PARTIAL
    return OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE


def save_snapshot(payload: dict, path: Path | None = None) -> None:
    """Persist the last SUCCESSFUL telemetry, so a later failure can show it."""
    path = path or SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_snapshot(path: Path | None = None) -> dict | None:
    path = path or SNAPSHOT_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def telemetry_payload(with_region: bool = True,
                      workdir: Path | None = None,
                      snapshot_path: Path | None = None) -> dict:
    """The whole Latest Inputs response, including the failure paths.

    Cached telemetry is NEVER presented as fresh: it is returned under
    CACHED_TELEMETRY_NOT_CURRENT, keeps its original retrieval time, and carries
    the elapsed staleness measured now.
    """
    started = time.perf_counter()
    sources = collect(with_region=with_region, workdir=workdir)
    state = overall_state(sources)
    now = _now()

    payload = {
        "mode": "LATEST_INPUTS",
        "phase": "8A",
        "state": state.value,
        "generated_utc": _iso(now),
        "sources": [asdict(s) for s in sources],
        "subsurface_reconstruction": NOT_CERTIFIED,
        "telemetry_banner": TELEMETRY_AVAILABLE,
        "why_these_inputs": WHY_THESE_INPUTS,
        "scope_note": (
            "Phase 8A is input telemetry only. The frozen L2 is not run on "
            "these inputs, no latest subsurface field is produced, and no "
            "latest D26, TCHP or hazard indicator is derived from them."),
        "historical_note": (
            "Historical Replay and historical Ocean Hazard Indicators are local "
            "capabilities and remain fully available regardless of this state."),
        "is_cached": False,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }

    if state is OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE:
        cached = load_snapshot(snapshot_path)
        if cached:
            cached_at = cached.get("generated_utc")
            staleness = None
            if cached_at:
                staleness = round(
                    (now - pd.Timestamp(cached_at)).total_seconds() / 3600.0, 2)
            payload.update({
                "state": OverallState.CACHED_TELEMETRY_NOT_CURRENT.value,
                "is_cached": True,
                "cached_generated_utc": cached_at,
                "cached_staleness_hours": staleness,
                "cache_label": "LAST SUCCESSFUL TELEMETRY - NOT CURRENT",
                "live_attempt_sources": payload["sources"],
                "sources": cached.get("sources", []),
            })
        else:
            payload["unavailable_label"] = "DATA SOURCE CURRENTLY UNAVAILABLE"
    elif state in (OverallState.ONLINE_CURRENT, OverallState.ONLINE_PARTIAL):
        # Only a real, successful retrieval is ever written to the snapshot.
        save_snapshot({k: payload[k] for k in
                       ("mode", "phase", "state", "generated_utc", "sources")},
                      snapshot_path)
    return payload
