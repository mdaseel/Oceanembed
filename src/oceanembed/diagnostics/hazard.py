"""Ocean Thermal Support for Cyclone Intensification.

Exactly the rule frozen in ``outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md``,
written before any threshold number existed:

    category = f(TCHP)   against percentiles of OceanEmbed's OWN TCHP over the
                         TRAIN split only, so no test-period information and no
                         model-vs-reference bias enters the label

D26 and the 100 m anomaly are displayed for explanation but do not categorise.
There is no numeric cyclone probability here, in any form, and this module makes
no statement about cyclone genesis, track, landfall or intensity.

A category is produced ONLY where TCHP is defined and physically supported. An
invalid or below-seafloor diagnostic yields NOT_CATEGORIZED with its reason left
readable from the existing Phase 7C status arrays - never a forced label.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import numpy as np

from ..config import REPO_ROOT
from .bathymetry import PhysicalSupport
from .thermal import D26Status

THRESHOLDS_PATH = REPO_ROOT / "outputs" / "phase7" / "HAZARD_THRESHOLDS.json"
PROTOCOL_PATH = "outputs/phase7/HAZARD_INDICATOR_PROTOCOL.md"

INDICATOR_NAME = "Ocean Thermal Support for Cyclone Intensification"

#: Shown verbatim wherever the indicator appears. Not paraphrased.
NON_PREDICTION_STATEMENT = (
    "This indicator describes the oceanic thermal environment relevant to "
    "cyclone intensification. It does not predict cyclone genesis, track, "
    "landfall, category, or exact future intensity."
)

#: Phase 7C measured error for TCHP on the locked test split, whole NIO,
#: B vs C. Travels with every label: a category narrower than this is not
#: distinguishable from its neighbour at a single cell.
TCHP_ERROR_KJ_CM2 = {"mae": 11.47, "rmse": 15.83, "bias": 5.80,
                     "source": "Phase 7C, whole NIO, B vs C"}


class ThermalSupport(IntEnum):
    LOW = 0
    MODERATE = 1
    ELEVATED = 2
    HIGH = 3
    #: No defensible category exists here. The reason stays readable from the
    #: Phase 7C D26Status and PhysicalSupport arrays rather than being merged in.
    NOT_CATEGORIZED = 4


class ThresholdsUnavailable(RuntimeError):
    """The frozen hazard thresholds are missing or malformed."""


@dataclass(frozen=True)
class HazardThresholds:
    """The frozen boundaries, and the provenance that makes them auditable."""

    p50: float
    p75: float
    p90: float
    reference_period: str
    n_dates: int
    n_samples: int
    quantity: str = "tchp_kj_cm2"

    def as_dict(self) -> dict:
        return {"p50": self.p50, "p75": self.p75, "p90": self.p90,
                "reference_period": self.reference_period,
                "n_dates": self.n_dates, "n_samples": self.n_samples,
                "quantity": self.quantity}

    def label_for(self, value: float) -> ThermalSupport:
        if not np.isfinite(value):
            return ThermalSupport.NOT_CATEGORIZED
        if value >= self.p90:
            return ThermalSupport.HIGH
        if value >= self.p75:
            return ThermalSupport.ELEVATED
        if value >= self.p50:
            return ThermalSupport.MODERATE
        return ThermalSupport.LOW


_CACHE: dict[str, HazardThresholds] = {}


def load_thresholds(strict: bool = True) -> HazardThresholds | None:
    """Read the frozen thresholds. Returns None (not a crash) when lenient."""
    if "t" in _CACHE:
        return _CACHE["t"]
    try:
        raw = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
        t = HazardThresholds(
            p50=float(raw["boundaries"]["p50"]),
            p75=float(raw["boundaries"]["p75"]),
            p90=float(raw["boundaries"]["p90"]),
            reference_period=str(raw["reference_period"]),
            n_dates=int(raw["n_dates"]),
            n_samples=int(raw["n_samples"]))
        if not (t.p50 < t.p75 < t.p90):
            raise ThresholdsUnavailable("hazard boundaries are not increasing")
    except ThresholdsUnavailable:
        if strict:
            raise
        return None
    except (OSError, KeyError, ValueError, TypeError) as exc:
        if strict:
            raise ThresholdsUnavailable(f"hazard thresholds unreadable: {exc}") from exc
        return None
    _CACHE["t"] = t
    return t


def categorize(tchp: np.ndarray, d26_status: np.ndarray,
               tchp_physical: np.ndarray,
               thresholds: HazardThresholds | None) -> np.ndarray:
    """Category per cell. NOT_CATEGORIZED wherever no defensible label exists.

    ``SURFACE_BELOW_26`` is categorised normally: TCHP is exactly 0 there, which
    is a real measurement of the heat above 26 degC, and zero heat is genuinely
    the least support there can be. It is never confused with a missing value.
    """
    tchp = np.asarray(tchp, dtype="float64")
    out = np.full(tchp.shape, ThermalSupport.NOT_CATEGORIZED, dtype="int8")
    if thresholds is None:
        return out

    status = np.asarray(d26_status)
    physical = np.asarray(tchp_physical)
    # A label needs a real number AND a real water column under it.
    usable = (np.isfinite(tchp)
              & (physical == PhysicalSupport.SUPPORTED)
              & ((status == D26Status.OK) | (status == D26Status.SURFACE_BELOW_26)))

    out[usable & (tchp < thresholds.p50)] = ThermalSupport.LOW
    out[usable & (tchp >= thresholds.p50)] = ThermalSupport.MODERATE
    out[usable & (tchp >= thresholds.p75)] = ThermalSupport.ELEVATED
    out[usable & (tchp >= thresholds.p90)] = ThermalSupport.HIGH
    return out


def not_categorized_reason(d26_status: int, tchp_physical: int,
                           thresholds_available: bool = True) -> str:
    """Why a cell carries no category. Reasons are never merged together."""
    if not thresholds_available:
        return "NOT CATEGORIZED - hazard thresholds unavailable"
    if tchp_physical == PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT:
        return "NOT CATEGORIZED - no water column"
    if tchp_physical == PhysicalSupport.UNVERIFIED:
        return "NOT CATEGORIZED - physical support unverified"
    if d26_status in (D26Status.NO_CROSSING_IN_SUPPORT,
                      D26Status.INSUFFICIENT_SUPPORT,
                      D26Status.NO_VALID_LEVELS):
        return "NOT CATEGORIZED - diagnostic unavailable"
    return "NOT CATEGORIZED"


def explain(value: float, thresholds: HazardThresholds | None) -> str:
    """The 'Why this level?' sentence, quoting the actual boundary crossed."""
    if thresholds is None or not np.isfinite(value):
        return "No category: the supporting diagnostic is unavailable here."
    label = thresholds.label_for(value)
    if label is ThermalSupport.HIGH:
        return (f"{value:.1f} kJ/cm2 is at or above the HIGH boundary of "
                f"{thresholds.p90:.1f}.")
    if label is ThermalSupport.ELEVATED:
        return (f"{value:.1f} kJ/cm2 is at or above the ELEVATED boundary of "
                f"{thresholds.p75:.1f}, below HIGH at {thresholds.p90:.1f}.")
    if label is ThermalSupport.MODERATE:
        return (f"{value:.1f} kJ/cm2 is at or above the MODERATE boundary of "
                f"{thresholds.p50:.1f}, below ELEVATED at {thresholds.p75:.1f}.")
    return (f"{value:.1f} kJ/cm2 is below the MODERATE boundary of "
            f"{thresholds.p50:.1f}.")
