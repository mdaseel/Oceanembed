"""Product substitution into the FROZEN input contract.

One channel's product is swapped for its NRT counterpart while the other six
are held at their reference values, and the frozen L2 model is run on both.
The comparison is prediction-to-prediction: no target is read, so this measures
SENSITIVITY, not accuracy. See the Phase 6C-D pre-registration, section 0 and 1.

The substituted field is assembled first and then handed to the UNMODIFIED
``day_field``, exactly as the Phase 6C-C operational assembler does. The joint
validity mask, the internal zero-padding and the frozen scaler therefore behave
identically to production - a substituted product cannot quietly acquire
different mask semantics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..ml.features import SURFACE
from ..ml.patches import day_field

# Pre-registered single-channel runs (section 3.2). Each entry lists the
# channels replaced and the NRT source they are replaced from.
SUBSTITUTIONS = {
    "REFERENCE":          {"channels": (), "source": None},
    "NRT_SST_ONLY":       {"channels": ("sst",), "source": "sst_nrt"},
    "NRT_SSS_SMOS_ONLY":  {"channels": ("sss",), "source": "sss_nrt_smos"},
    "NRT_SSS_SMAP_ONLY":  {"channels": ("sss",), "source": "sss_nrt_smap"},
    "NRT_SLA_ONLY":       {"channels": ("sla",), "source": "sla_nrt"},
    "NRT_CURRENTS_ONLY":  {"channels": ("current_u", "current_v"),
                           "source": "currents_nrt"},
    "NRT_WIND_ONLY":      {"channels": ("wind_u", "wind_v"), "source": "wind_nrt"},
    "ALL_NRT_RAW":        {"channels": tuple(SURFACE), "source": "all"},
}

TARGET_PREFIXES = ("temp_", "target_valid_")


def assert_no_target_access(ds: xr.Dataset, requested: list[str]) -> None:
    """Hard guard for pre-registration constraint 1: no target is ever read.

    The overlap window lies inside the locked test split, so the only thing
    keeping the locked evaluation unspent is that this phase never opens a
    target. That is enforced here rather than merely intended.
    """
    bad = [v for v in requested if v.startswith(TARGET_PREFIXES)]
    if bad:
        raise PermissionError(
            f"Phase 6C-D must not read target variables; refused: {bad}")


def substituted_field(ds: xr.Dataset, t: int, scaler, patch: int,
                      replacements: dict[str, np.ndarray] | None = None):
    """Build a complete seven-channel field, then call the frozen day_field.

    ``replacements`` maps a channel name to a (nlat, nlon) array already
    harmonised onto the canonical grid and in the frozen contract's units.
    NaNs in a replacement are real missingness and are passed through untouched;
    the joint mask then does what it does in production.
    """
    replacements = replacements or {}
    assert_no_target_access(ds, list(replacements))
    unknown = set(replacements) - set(SURFACE)
    if unknown:
        raise ValueError(f"not input channels: {sorted(unknown)}")

    nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]
    arrays = {}
    for v in SURFACE:
        a = (np.asarray(replacements[v], dtype="float64") if v in replacements
             else np.asarray(ds[v].isel(time=t).values, dtype="float64"))
        if a.shape != (nlat, nlon):
            raise ValueError(f"{v}: got {a.shape}, expected {(nlat, nlon)}")
        arrays[v] = a

    shim = xr.Dataset(
        {v: (("time", "lat", "lon"), arrays[v][None, :, :]) for v in SURFACE},
        coords={"time": [ds.time.values[t]], "lat": ds.lat.values,
                "lon": ds.lon.values})
    return day_field(shim, 0, scaler, patch)


def joint_mask(arrays: dict[str, np.ndarray]) -> np.ndarray:
    """The frozen contract's single joint validity mask, recomputed openly."""
    stack = np.stack([np.asarray(arrays[v], dtype="float64") for v in SURFACE])
    return np.isfinite(stack).all(axis=0)


def prediction_shift(pred_ref: np.ndarray, pred_nrt: np.ndarray,
                     valid: np.ndarray | None = None) -> dict:
    """Per-depth shift between two frozen-model predictions.

    Both predictions are (n_cells, n_depths) in physical units. ``valid`` is an
    optional per-cell mask restricting the comparison to cells alive in BOTH
    runs, so a coverage change is never mistaken for a value change.
    """
    a = np.asarray(pred_ref, dtype="float64")
    b = np.asarray(pred_nrt, dtype="float64")
    ok = np.isfinite(a) & np.isfinite(b)
    if valid is not None:
        ok &= np.asarray(valid, dtype=bool)[:, None]
    n_depth = a.shape[1]
    rows = []
    for k in range(n_depth):
        m = ok[:, k]
        if m.sum() < 10:
            rows.append({"depth_index": k, "n": int(m.sum())})
            continue
        d = b[m, k] - a[m, k]
        rows.append({
            "depth_index": k, "n": int(m.sum()),
            "mean_shift": float(d.mean()),
            "rmsd": float(np.sqrt((d ** 2).mean())),
            "max_abs_shift": float(np.abs(d).max()),
            "p95_abs_shift": float(np.percentile(np.abs(d), 95)),
            "ref_mean": float(a[m, k].mean()), "nrt_mean": float(b[m, k].mean()),
        })
    return {"per_depth": rows}


class ShiftAccumulator:
    """Streaming accumulation of prediction shifts across days, per depth."""

    def __init__(self, depths):
        self.depths = list(depths)
        n = len(self.depths)
        self.n = np.zeros(n, dtype="int64")
        self.s = np.zeros(n, dtype="float64")     # sum of (nrt - ref)
        self.s2 = np.zeros(n, dtype="float64")    # sum of (nrt - ref)^2
        self.mx = np.zeros(n, dtype="float64")
        self.sa = np.zeros(n, dtype="float64")    # sum |nrt - ref|

    def update(self, pred_ref, pred_nrt, mask):
        a = np.asarray(pred_ref, dtype="float64")
        b = np.asarray(pred_nrt, dtype="float64")
        m = np.asarray(mask, dtype=bool)
        d = np.where(m, b - a, 0.0)
        self.n += m.sum(axis=0)
        self.s += d.sum(axis=0)
        self.s2 += (d ** 2).sum(axis=0)
        self.sa += np.abs(d).sum(axis=0)
        self.mx = np.maximum(self.mx, np.abs(d).max(axis=0))

    def frame(self, label: str) -> pd.DataFrame:
        n = np.maximum(self.n, 1)
        return pd.DataFrame({
            "run": label,
            "depth_m": self.depths,
            "n": self.n,
            "mean_shift": self.s / n,
            "mean_abs_shift": self.sa / n,
            "rmsd": np.sqrt(self.s2 / n),
            "max_abs_shift": self.mx,
        })
