"""The canonical field-view contract and location semantics for replay.

The ``FieldView`` shape is fixed by the master prompt (§7.0): the temperature,
anomaly and climatology fields are (nlat, nlon, n_depths) = (101, 241, 15), and
the depth axis is the exact mandated ordering. A 3D renderer, a map layer and a
point profile are all views of this one object, so they can never disagree.

Location resolution is deliberately explicit. A requested coordinate is resolved
to the nearest canonical cell and BOTH are returned; a land or input-invalid
cell is reported as such and is never silently swapped for a different ocean
cell. A nearest usable cell may be offered as a separate suggestion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..ml.features import SURFACE

#: Exact mandated output depths, in order. Never reorder, never subset.
DEPTHS: list[int] = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500,
                     700, 1000]

#: The ONLY variables replay may read from a model-ready store. Targets
#: (``temp_*``) and target masks (``target_valid_*``) are absent by
#: construction, so a target cannot leak into inference by accident.
ALLOWED_STORE_VARS: frozenset[str] = frozenset(
    set(SURFACE) | {"ocean_mask", "surface_input_valid"})

NOMINAL_ZERO_M_NOTE = (
    "Nominal 0 m is the shallowest GLORYS target level (approximately 0.494 m), "
    "not the OSTIA sea-surface-temperature input. The two are physically "
    "related but are not the same quantity and are not fully independent."
)

DEEP_SKILL_NOTE = (
    "Deep-ocean daily anomaly skill is weaker and more climatology-dominant at "
    "500-1000 m. Interpret L2 departures from climatology cautiously at those "
    "depths."
)


class LocationStatus(str, Enum):
    """Structured outcome of resolving a requested coordinate."""

    OK = "OK"
    OUTSIDE_DOMAIN = "OUTSIDE_DOMAIN"
    INVALID_OCEAN_CELL = "INVALID_OCEAN_CELL"
    INPUT_NOT_VALID = "INPUT_NOT_VALID"


class InferenceSource(str, Enum):
    LIVE_MODEL_RUN = "LIVE_MODEL_RUN"
    VALIDATED_CACHE = "VALIDATED_CACHE"


class OutsideDomain(ValueError):
    """Raised when a requested coordinate or date is outside the domain."""


@dataclass(frozen=True)
class ResolvedLocation:
    requested_lat: float
    requested_lon: float
    status: LocationStatus
    grid_row: int | None = None
    grid_col: int | None = None
    grid_lat: float | None = None
    grid_lon: float | None = None
    #: Offered only as a suggestion. It never replaces the requested cell.
    nearest_usable_lat: float | None = None
    nearest_usable_lon: float | None = None
    nearest_usable_distance_deg: float | None = None

    def as_dict(self) -> dict:
        return {
            "requested_lat": self.requested_lat,
            "requested_lon": self.requested_lon,
            "grid_lat": self.grid_lat,
            "grid_lon": self.grid_lon,
            "grid_row": self.grid_row,
            "grid_col": self.grid_col,
            "status": self.status.value,
            "nearest_usable_lat": self.nearest_usable_lat,
            "nearest_usable_lon": self.nearest_usable_lon,
            "nearest_usable_distance_deg": self.nearest_usable_distance_deg,
            "note": ("the requested cell is returned as resolved; any nearest "
                     "usable cell is a suggestion only and was not substituted"),
        }


@dataclass
class FieldView:
    """The canonical field-view object (master prompt §7.0).

    One authoritative result per date. The map, the 3D renderer and every point
    profile are derived from this and from nothing else.
    """

    date: str
    temperature: np.ndarray          # (nlat, nlon, n_depths) degC, NaN off-support
    climatology: np.ndarray          # (nlat, nlon, n_depths) degC, NaN where L0 undefined
    anomaly: np.ndarray              # temperature - climatology
    lat: np.ndarray                  # (nlat,)
    lon: np.ndarray                  # (nlon,)
    depths: list[int]                # the 15 mandated depths, in order
    ocean_mask: np.ndarray           # (nlat, nlon) bool
    surface_input_valid: np.ndarray  # (nlat, nlon) bool - this date's joint mask
    provenance: dict = field(default_factory=dict)

    @property
    def climatology_defined(self) -> np.ndarray:
        """(nlat, nlon, n_depths) bool — CLIMATOLOGY DEPTH-SUPPORT availability.

        True where the frozen L0 harmonic climatology has coefficients at this
        cell and depth. L0 was fitted only where a GLORYS target existed on the
        training reference day, so this records **where a comparison baseline
        exists**, and nothing more.

        This is NOT a bathymetry product and NOT an authoritative seafloor mask.
        It is one reanalysis's target availability at 1/12 deg regridded to
        0.25 deg, sampled on a single day. It correlates with water depth, but
        an absent value here can equally mean the target was missing for a
        processing reason. Do not label it "seafloor", "water depth" or
        "bathymetry" in the UI or in any report; if a real depth mask is ever
        needed, bring in an actual static bathymetry source (e.g. GEBCO) and say
        which one.

        What it is for: ``anomaly`` is NaN wherever this is False, because there
        is no climatology to subtract. A consumer needs to know the difference
        between "no anomaly available" and "zero anomaly".

        The raw frozen-L2 ``temperature`` is preserved at ALL 15 mandated depths
        regardless of this mask. Suppressing or overwriting deep L2 output is
        forbidden, and nothing here does it.
        """
        return np.isfinite(self.climatology)

    # -------------------------------------------------------------- validation
    def validate(self) -> "FieldView":
        nlat, nlon, nd = self.temperature.shape
        if list(self.depths) != DEPTHS:
            raise ValueError(f"depth axis is not the mandated ordering: {self.depths}")
        if nd != len(DEPTHS):
            raise ValueError(f"expected {len(DEPTHS)} depths, got {nd}")
        for name in ("climatology", "anomaly"):
            if getattr(self, name).shape != self.temperature.shape:
                raise ValueError(f"{name} shape {getattr(self, name).shape} "
                                 f"!= temperature {self.temperature.shape}")
        if self.lat.shape != (nlat,) or self.lon.shape != (nlon,):
            raise ValueError("lat/lon lengths do not match the field")
        if self.ocean_mask.shape != (nlat, nlon):
            raise ValueError("ocean_mask shape mismatch")
        if self.surface_input_valid.shape != (nlat, nlon):
            raise ValueError("surface_input_valid shape mismatch")
        return self

    # ------------------------------------------------------------------ access
    def depth_index(self, depth_m: int) -> int:
        if int(depth_m) not in self.depths:
            raise ValueError(f"{depth_m} m is not one of the mandated depths "
                             f"{self.depths}")
        return self.depths.index(int(depth_m))

    def layer(self, depth_m: int, which: str = "temperature") -> np.ndarray:
        """One (nlat, nlon) horizontal slice - the map / 3D depth-scrub view."""
        if which not in ("temperature", "climatology", "anomaly"):
            raise ValueError(f"unknown layer {which!r}")
        return getattr(self, which)[:, :, self.depth_index(depth_m)]

    def profile_at(self, row: int, col: int) -> dict[str, np.ndarray]:
        """The 15-depth profile at one grid cell - what replay_point samples."""
        return {
            "prediction_c": self.temperature[row, col, :],
            "climatology_c": self.climatology[row, col, :],
            "anomaly_c": self.anomaly[row, col, :],
        }


@dataclass
class PointResult:
    date: str
    location: ResolvedLocation
    model: dict
    surface_inputs: dict
    profile: list[dict]
    provenance: dict
    status: dict

    def as_dict(self) -> dict:
        return {
            "mode": "HISTORICAL_REPLAY",
            "date": self.date,
            "location": self.location.as_dict(),
            "model": self.model,
            "surface_inputs": self.surface_inputs,
            "profile": self.profile,
            "nominal_zero_m_note": NOMINAL_ZERO_M_NOTE,
            "deep_skill_note": DEEP_SKILL_NOTE,
            "provenance": self.provenance,
            "status": self.status,
        }
