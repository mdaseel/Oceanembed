"""Phase 7A — authoritative historical replay of the frozen L2 core.

Everything in this package is ADDITIVE and read-only with respect to the frozen
scientific artifacts. Nothing here trains, fine-tunes, refits or rewrites a
checkpoint, a scaler or the L0 climatology; all five are opened read-only and
hash-verified at load time.

The one scientific primitive is ``replay_field(date)``. It runs the EXISTING
frozen whole-field L2 path over the canonical 101x241 grid. ``replay_point``
does not perform inference of its own - it samples the authoritative field
result, which is the property the mandatory Phase 7A equivalence test pins.

Normal replay reads SURFACE INPUTS ONLY. The GLORYS ``temp_*`` targets, the
``target_valid_*`` masks, ``outputs/targets_cache`` and Argo are never opened;
this is enforced structurally by ``ALLOWED_STORE_VARS`` rather than left to
convention.
"""
from .contract import (ALLOWED_STORE_VARS, DEPTHS, FieldView, LocationStatus,
                       PointResult, ResolvedLocation)
from .engine import ReplayEngine, replay_field, replay_point, replay_range

__all__ = [
    "ALLOWED_STORE_VARS", "DEPTHS", "FieldView", "LocationStatus",
    "PointResult", "ResolvedLocation",
    "ReplayEngine", "replay_field", "replay_point", "replay_range",
]
