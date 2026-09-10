"""Physical water-column support, from the SAME ETOPO artifact the 3D view uses.

There is exactly one authoritative physical-depth representation in this
project: ``web/public/assets/bathymetry/depth.bin``, produced by
``scripts/poc/build_bathymetry.py`` from the local ETOPO 2022 source and
regridded onto the canonical 101x241 grid with the frozen
``regrid_horizontal``. The 3D renderer and the profile panel already consume
that file through ``web/src/field/bathymetry.ts``; this module reads the very
same bytes so the backend cannot disagree with what the user sees.

This is NOT a second bathymetry implementation. It is a second *reader* of one
artifact, and its checksum is verified against the metadata the build script
wrote, so a drift fails closed instead of silently diverging.

Nothing here touches the frozen L2, its inference path, or any raw model value.
Physical support is an ADDITIONAL qualification carried alongside the raw
output, never a substitute for it:

    temperature_raw  +  depth_physically_valid  ->  qualified presentation

``climatology_defined`` is not bathymetry and is never used here.
"""
from __future__ import annotations

import hashlib
import json
from enum import IntEnum
from pathlib import Path

import numpy as np

from ..config import REPO_ROOT
from .thermal import D26Status, ThermalResult

BATHYMETRY_DIR = REPO_ROOT / "web" / "public" / "assets" / "bathymetry"
DEPTH_BIN = BATHYMETRY_DIR / "depth.bin"
METADATA = BATHYMETRY_DIR / "metadata.json"

GRID_SHAPE = (101, 241)

#: Bathymetric existence ONLY. Whether the seabed is deep enough here is a
#: property of the ocean, not of whether a satellite saw the surface that day.
PHYSICAL_SUPPORT_RULE = (
    "ocean cell AND local_water_depth_m >= requested_depth_m"
)

#: What the map actually draws. Composes the physical rule with input
#: availability, and mirrors ``displayDepthValid`` in
#: web/src/field/bathymetry.ts; a cross-language test pins that they agree.
#: Keeping the two apart is what lets a deep cell with a missing satellite pass
#: report MISSING INPUT rather than BELOW SEAFLOOR.
DISPLAY_VALID_RULE = "surface_input_valid AND (" + PHYSICAL_SUPPORT_RULE + ")"


class BathymetryUnavailable(RuntimeError):
    """The local bathymetry artifact is missing or does not match its checksum."""


class PhysicalSupport(IntEnum):
    """Whether a diagnostic has a real water column underneath it.

    Deliberately separate from :class:`D26Status`. The Phase 7C diagnostic
    statuses are frozen and unchanged; this is an additional axis, so a cell
    can carry both "the isotherm exists" and "but not in this much water".
    """

    #: The full required interval fits inside the local water column.
    SUPPORTED = 0
    #: The diagnostic resolved, but below the local seafloor.
    INSUFFICIENT_WATER_COLUMN_SUPPORT = 1
    #: The diagnostic does not exist for a non-bathymetric reason, so
    #: bathymetry has no verdict to give. Never conflated with a support
    #: failure - SURFACE_BELOW_26 in particular is a real result, not a gap.
    NOT_APPLICABLE = 2
    #: Bathymetry could not be read. Fails closed: never assume support.
    UNVERIFIED = 3


_CACHE: dict[str, np.ndarray] = {}


def local_water_depth(strict: bool = True) -> np.ndarray | None:
    """Metres of water at each canonical cell, NaN where the source had none.

    Returns ``None`` instead of raising when ``strict`` is False, so the
    application can degrade to UNVERIFIED rather than fail to start.
    """
    if "depth" in _CACHE:
        return _CACHE["depth"]
    try:
        meta = json.loads(METADATA.read_text(encoding="utf-8"))
        raw = DEPTH_BIN.read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta["depthSha256"]:
            raise BathymetryUnavailable("depth.bin does not match its recorded sha256")
        if len(raw) != GRID_SHAPE[0] * GRID_SHAPE[1] * 8:
            raise BathymetryUnavailable("depth.bin is not the canonical 101x241 grid")
        depth = np.frombuffer(raw, dtype="<f8").reshape(GRID_SHAPE).copy()
        if np.any(depth[np.isfinite(depth)] < 0):
            raise BathymetryUnavailable("negative water depth in bathymetry")
    except BathymetryUnavailable:
        if strict:
            raise
        return None
    except (OSError, KeyError, ValueError) as exc:
        if strict:
            raise BathymetryUnavailable(f"bathymetry unreadable: {exc}") from exc
        return None
    _CACHE["depth"] = depth
    return depth


def bathymetry_provenance() -> dict:
    """What the UI and the exports must be able to state about this mask."""
    try:
        meta = json.loads(METADATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False, "rule": PHYSICAL_SUPPORT_RULE,
                "note": "local bathymetry unavailable; physical support is UNVERIFIED"}
    return {
        "available": local_water_depth(strict=False) is not None,
        "dataset": meta.get("dataset"),
        "version": meta.get("version"),
        "source_sha256": meta.get("sourceSha256"),
        "depth_sha256": meta.get("depthSha256"),
        "sign_convention": meta.get("signConvention"),
        "regridding": meta.get("regridding"),
        "rule": PHYSICAL_SUPPORT_RULE,
        "display_rule": DISPLAY_VALID_RULE,
        "separation_note": "physical depth support is bathymetric existence "
                           "alone; a deep cell whose surface input is missing "
                           "is still deep water and is reported as MISSING "
                           "INPUT, never as BELOW SEAFLOOR",
        "shared_with": "the 3D depth view and the profile panel read this same "
                       "artifact through web/src/field/bathymetry.ts",
        "not_bathymetry_note": "climatology_defined is L0 coefficient "
                               "availability and is never used as seafloor depth",
        "sampling_caveat": "point samples at canonical cell centres, not cell "
                           "minima: a 0.25 degree cell spanning a shelf edge is "
                           "represented by its centre depth alone",
    }


def depth_physically_valid(depth_m: float, water_depth: np.ndarray | None,
                           ocean_mask: np.ndarray | None = None) -> np.ndarray:
    """Does a water column this deep EXIST at each cell?

    Bathymetry and land only. Surface input availability is deliberately not an
    argument: whether a satellite observed the surface on a given day cannot
    change where the seabed is, and conflating the two would make a deep cell
    with a missing input report "below seafloor", which is false.

    Fails closed when bathymetry is unverified - never assumes support.
    """
    if water_depth is None:
        shape = ocean_mask.shape if ocean_mask is not None else GRID_SHAPE
        return np.zeros(shape, dtype=bool)
    valid = np.isfinite(water_depth) & (water_depth >= float(depth_m))
    if ocean_mask is not None:
        valid &= ocean_mask.astype(bool)
    return valid


def display_valid(depth_m: float, water_depth: np.ndarray | None,
                  ocean_mask: np.ndarray | None = None,
                  surface_input_valid: np.ndarray | None = None) -> np.ndarray:
    """What the map may draw: a real value AND a real water column.

    The composition of the two orthogonal concepts, kept explicit so a caller
    can always ask which of them failed. Mirrors ``displayDepthValid`` in the
    frontend, which the 3D view, the profile and the 2D map all share.
    """
    valid = depth_physically_valid(depth_m, water_depth, ocean_mask)
    if surface_input_valid is not None:
        valid = valid & surface_input_valid.astype(bool)
    return valid


def qualify(thermal: ThermalResult,
            water_depth: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """Physical-support status for D26 and for TCHP.

    The Phase 7C diagnostic itself is untouched: ``thermal.d26`` and
    ``thermal.tchp`` keep the exact values the frozen algorithm produced. D26 is
    never clamped to the seabed, never zeroed and never given a fabricated
    crossing - it is only *labelled* as unusable where no water column supports
    it.

    TCHP integrates from the surface to D26, so its interval is contained in
    D26's. It therefore inherits D26's verdict rather than getting a second,
    independently tunable threshold. The one exception is SURFACE_BELOW_26,
    where TCHP is exactly 0 by definition of the diagnostic and is a real
    answer regardless of how deep the water is.
    """
    status = np.asarray(thermal.status)
    d26_phys = np.full(status.shape, PhysicalSupport.NOT_APPLICABLE, dtype="int8")
    tchp_phys = np.full(status.shape, PhysicalSupport.NOT_APPLICABLE, dtype="int8")

    ok = status == D26Status.OK
    below_26 = status == D26Status.SURFACE_BELOW_26

    if water_depth is None:
        d26_phys[ok] = PhysicalSupport.UNVERIFIED
        tchp_phys[ok | below_26] = PhysicalSupport.UNVERIFIED
        return d26_phys, tchp_phys

    fits = np.isfinite(water_depth) & (np.asarray(thermal.d26) <= water_depth)
    d26_phys[ok & fits] = PhysicalSupport.SUPPORTED
    d26_phys[ok & ~fits] = PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT
    tchp_phys[ok & fits] = PhysicalSupport.SUPPORTED
    tchp_phys[ok & ~fits] = PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT
    # A column that never reaches 26 degC has TCHP = 0 whatever the depth.
    tchp_phys[below_26] = PhysicalSupport.SUPPORTED
    return d26_phys, tchp_phys
