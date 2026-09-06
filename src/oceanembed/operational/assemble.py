"""Assemble a complete seven-channel field, then hand it to the FROZEN path.

Two entry points, deliberately separate:

``reference_complete_field``
    Calls the unmodified legacy ``day_field`` on the original store. Byte for
    byte the existing production path. Ordinary per-cell NaNs keep their
    existing handling - they are NOT filled just because this wrapper exists.

``assemble_field``
    Only for a DECLARED outage or staleness that appears in the tested
    allow-list. It builds a complete seven-channel field, substituting only the
    declared channels, and then calls the SAME unmodified ``day_field``. Because
    the assembled field has no whole-channel gap, the legacy joint validity mask
    behaves exactly as it does in normal operation: per-cell NaNs still blank
    those cells, land is still land.

The legacy mask semantics are therefore never changed. What changes is that a
whole-channel outage can no longer reach ``day_field`` at all: it is either
repaired by a registered policy or refused outright.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..ml.features import SURFACE
from ..ml.patches import day_field
from .availability import InputDeclaration
from .policy import (FILL_PERSIST, FILL_TRAIN_CLIM, NoUsableInput, Policy,
                     PolicyState, UnsupportedInputMode, lookup_policy)
from .provenance import ChannelProvenance, ReconstructionManifest


def reference_complete_field(ds: xr.Dataset, t: int, scaler, patch: int):
    """The unmodified legacy path. Returns (field, manifest)."""
    field = day_field(ds, t, scaler, patch)
    when = pd.Timestamp(ds.time.values[t])
    man = ReconstructionManifest(
        reconstruction_issue_time=str(when),
        requested_valid_time=str(when),
        replay_mode="RETROSPECTIVE",
        policy_name="REFERENCE_COMPLETE",
        policy_state=PolicyState.REFERENCE_COMPLETE.value,
        policy_evidence="original inputs through the unmodified legacy path",
        channels=[ChannelProvenance.observed(v, when) for v in SURFACE],
        note="ordinary per-cell NaNs retain their original legacy handling")
    return field, man


def _source_index(ds: xr.Dataset, t: int, age: int) -> int:
    src = t - int(age)
    if src < 0:
        raise NoUsableInput(f"age {age} runs off the start of the record at index {t}")
    if src > t:
        raise UnsupportedInputMode("a source index after the target would be a future read")
    return src


def assemble_field(ds: xr.Dataset, t: int, scaler, patch: int,
                   declaration: InputDeclaration,
                   surface_clim=None, store=None,
                   prefer_fill: str | None = None):
    """Assemble a complete field under a registered fallback policy.

    Raises UnsupportedInputMode for anything outside the allow-list, and
    NoUsableInput when a supported policy cannot actually be satisfied.
    """
    declaration.validate()
    policy: Policy = lookup_policy(declaration.absent, declaration.stale,
                                   prefer_fill=prefer_fill)

    when = pd.Timestamp(ds.time.values[t])
    if str(pd.Timestamp(declaration.requested_valid_time)) != str(when):
        raise UnsupportedInputMode(
            f"declaration is for {declaration.requested_valid_time} but index {t} "
            f"is {when}")

    nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]
    arrays: dict[str, np.ndarray] = {}
    prov: list[ChannelProvenance] = []

    for v in SURFACE:
        avail = declaration.channels.get(v)
        absent = bool(avail.absent) if avail else False
        age = int(avail.age_days) if avail else 0
        product = avail.source_product if avail else None
        avail_time = avail.source_available_time if avail else None
        revision = avail.source_revision if avail else None

        if not absent and age == 0:
            arrays[v] = np.asarray(ds[v].isel(time=t).values, dtype="float64")
            prov.append(ChannelProvenance.observed(v, when, product, avail_time, revision))
            continue

        if not absent and age > 0:
            src = _source_index(ds, t, age)
            arrays[v] = np.asarray(ds[v].isel(time=src).values, dtype="float64")
            src_time = pd.Timestamp(ds.time.values[src])
            prov.append(ChannelProvenance.persisted(
                v, when, src_time, src_time, policy.name, product, avail_time, revision))
            continue

        # ---- wholly absent: only a registered fill may repair it
        if policy.fill == FILL_TRAIN_CLIM:
            if surface_clim is None:
                raise NoUsableInput(f"{v}: channel climatology requested but none supplied")
            arrays[v] = np.asarray(surface_clim.predict_channel(v, when), dtype="float64")
            tp = f"{surface_clim.meta.get('fit_start')}/{surface_clim.meta.get('fit_end')}"
            prov.append(ChannelProvenance.climatology(v, when, FILL_TRAIN_CLIM, tp))
            continue

        if policy.fill == FILL_PERSIST:
            got = store.get(v, when) if store is not None else None
            if got is None:
                raise NoUsableInput(
                    f"{v}: no usable prior field within {getattr(store, 'max_age_days', 0)} "
                    f"days of {when}")
            arrays[v] = np.asarray(got["array"], dtype="float64")
            prov.append(ChannelProvenance.persisted(
                v, when, got["source_valid_time"], got["original_observation_time"],
                FILL_PERSIST, got.get("source_product") or product,
                avail_time, got.get("source_revision") or revision))
            continue

        raise UnsupportedInputMode(
            f"{v} is absent and policy {policy.name} declares no repair for it")

    for v, a in arrays.items():
        if a.shape != (nlat, nlon):
            raise UnsupportedInputMode(
                f"{v}: assembled field has shape {a.shape}, expected {(nlat, nlon)}")
        if not np.isfinite(a).any():
            raise NoUsableInput(f"{v}: assembled field is entirely non-finite")

    # A single-timestep view so the UNMODIFIED legacy day_field does the rest.
    shim = xr.Dataset(
        {v: (("time", "lat", "lon"), arrays[v][None, :, :]) for v in SURFACE},
        coords={"time": [ds.time.values[t]], "lat": ds.lat.values, "lon": ds.lon.values})
    field = day_field(shim, 0, scaler, patch)

    man = ReconstructionManifest(
        reconstruction_issue_time=str(pd.Timestamp(
            declaration.reconstruction_issue_time or when)),
        requested_valid_time=str(when),
        replay_mode=declaration.replay_mode,
        policy_name=policy.name,
        policy_state=policy.state.value,
        policy_evidence=policy.evidence,
        channels=prov,
        note="complete assembled field passed to the unmodified legacy day_field")
    return field, man
