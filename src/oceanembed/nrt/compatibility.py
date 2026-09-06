"""Channel-level compatibility between a reference product and an NRT candidate.

Everything here is measurement only. Nothing is fitted, nothing is corrected,
and the frozen input contract is never bent to accommodate a product. The
frozen training-period standard deviation is used as the normalising scale
because that is the scale on which the model actually consumes each channel -
see the Phase 6C-D pre-registration, section 4.1.

The interpretation bands were frozen BEFORE any statistic in this module was
computed; they are transcribed here from the pre-registration and must not be
edited to suit a result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..ml.metrics import BASINS

# ---------------------------------------------------------------- pre-registered
COMPAT_BANDS = ["INTERCHANGEABLE", "USABLE_WITH_CAVEAT", "MARGINAL",
                "INCOMPATIBLE_RAW"]
SENS_BANDS = ["NEGLIGIBLE", "MINOR", "MATERIAL", "SEVERE"]

PREREGISTERED = {
    "source": "outputs/nrt/PREREGISTRATION_6CD.md section 4",
    "frozen_before_results": True,
    "compatibility": {
        "INTERCHANGEABLE": {"r_lt": 0.10, "b_lt": 0.05, "rho_ge": 0.98,
                            "q_in": [0.95, 1.05]},
        "USABLE_WITH_CAVEAT": {"r_lt": 0.25, "b_lt": 0.15, "rho_ge": 0.90,
                               "q_in": [0.85, 1.15]},
        "MARGINAL": {"r_lt": 0.50, "rho_ge": 0.75},
    },
    "sensitivity": {"NEGLIGIBLE": 0.10, "MINOR": 0.25, "MATERIAL": 0.50},
}


def compatibility_band(r: float, b: float, rho: float, q: float) -> str:
    """Assign the first pre-registered band whose conditions all hold."""
    vals = (r, b, rho, q)
    if not all(np.isfinite(v) for v in vals):
        return "INCOMPATIBLE_RAW"
    c = PREREGISTERED["compatibility"]
    for name in ("INTERCHANGEABLE", "USABLE_WITH_CAVEAT"):
        t = c[name]
        if (r < t["r_lt"] and b < t["b_lt"] and rho >= t["rho_ge"]
                and t["q_in"][0] <= q <= t["q_in"][1]):
            return name
    t = c["MARGINAL"]
    if r < t["r_lt"] and rho >= t["rho_ge"]:
        return "MARGINAL"
    return "INCOMPATIBLE_RAW"


def sensitivity_band(s: float) -> str:
    if not np.isfinite(s):
        return "SEVERE"
    t = PREREGISTERED["sensitivity"]
    if s < t["NEGLIGIBLE"]:
        return "NEGLIGIBLE"
    if s < t["MINOR"]:
        return "MINOR"
    if s < t["MATERIAL"]:
        return "MATERIAL"
    return "SEVERE"


def worst_band(bands, order) -> str:
    """The most severe band present, using the pre-registered ordering."""
    seen = [b for b in bands if b in order]
    return order[max(order.index(b) for b in seen)] if seen else order[-1]


# ------------------------------------------------------------------ statistics
def region_masks(lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]:
    """Full domain plus the two basin boxes already used in Phase 6B/6C."""
    LA, LO = np.meshgrid(lat, lon, indexing="ij")
    out = {"full_nio": np.ones(LA.shape, dtype=bool)}
    for name, b in BASINS.items():
        out[name] = ((LA >= b["lat"][0]) & (LA <= b["lat"][1])
                     & (LO >= b["lon"][0]) & (LO <= b["lon"][1]))
    return out


def _grad(f: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(np.where(np.isfinite(f), f, np.nan))
    return np.sqrt(gy ** 2 + gx ** 2)


def channel_stats(ref: np.ndarray, nrt: np.ndarray, region: np.ndarray,
                  ocean: np.ndarray | None = None) -> dict:
    """Distribution and discrepancy statistics on the COMMON valid support.

    Coverage numbers are computed over the ocean cells of the region, so that a
    gappy product's missingness is reported as missingness rather than being
    hidden by land.
    """
    dom = region if ocean is None else (region & ocean)
    n_dom = int(dom.sum())
    rf, nf = np.isfinite(ref) & dom, np.isfinite(nrt) & dom
    both = rf & nf
    out = {
        "n_domain_ocean": n_dom,
        "ref_coverage": float(rf.sum() / n_dom) if n_dom else np.nan,
        "nrt_coverage": float(nf.sum() / n_dom) if n_dom else np.nan,
        "common_coverage": float(both.sum() / n_dom) if n_dom else np.nan,
        "n_common": int(both.sum()),
    }
    if out["n_common"] < 10:
        return out
    a = ref[both].astype("float64")
    b = nrt[both].astype("float64")
    d = b - a
    out.update({
        "ref_mean": float(a.mean()), "nrt_mean": float(b.mean()),
        "ref_std": float(a.std()), "nrt_std": float(b.std()),
        "bias": float(d.mean()),
        "rmsd": float(np.sqrt((d ** 2).mean())),
        "mae": float(np.abs(d).mean()),
        "correlation": float(np.corrcoef(a, b)[0, 1])
        if a.std() > 1e-12 and b.std() > 1e-12 else np.nan,
        "std_ratio": float(b.std() / a.std()) if a.std() > 1e-12 else np.nan,
        "ref_p01": float(np.percentile(a, 1)), "nrt_p01": float(np.percentile(b, 1)),
        "ref_p50": float(np.percentile(a, 50)), "nrt_p50": float(np.percentile(b, 50)),
        "ref_p99": float(np.percentile(a, 99)), "nrt_p99": float(np.percentile(b, 99)),
    })
    gr, gn = _grad(np.where(dom, ref, np.nan)), _grad(np.where(dom, nrt, np.nan))
    if np.isfinite(gr).any() and np.isfinite(gn).any():
        out.update({
            "ref_grad_mean": float(np.nanmean(gr)),
            "nrt_grad_mean": float(np.nanmean(gn)),
            "ref_grad_p95": float(np.nanpercentile(gr[np.isfinite(gr)], 95)),
            "nrt_grad_p95": float(np.nanpercentile(gn[np.isfinite(gn)], 95)),
        })
        out["grad_ratio"] = (out["nrt_grad_mean"] / out["ref_grad_mean"]
                             if out["ref_grad_mean"] > 1e-12 else np.nan)
    return out


def pooled_from_daily(rows: pd.DataFrame) -> dict:
    """Pool per-day statistics into one record, weighting by common-support n.

    Pooling the daily numbers rather than concatenating every field keeps memory
    flat over a 168-day window. Second moments are pooled from the daily means
    and standard deviations, which is exact for the pooled variance.
    """
    r = rows[rows["n_common"] >= 10]
    if not len(r):
        # No day in the window had usable common support. Reported as zero
        # usable days, with the attempted count kept so the reader can see the
        # difference between "not tried" and "tried and found nothing".
        return {"n_days": 0, "n_days_attempted": int(len(rows)), "n_common": 0,
                "ref_coverage": float(rows["ref_coverage"].mean()),
                "nrt_coverage": float(rows["nrt_coverage"].mean()),
                "common_coverage": float(rows["common_coverage"].mean())}
    w = r["n_common"].to_numpy(dtype="float64")
    W = w.sum()

    def wm(c):
        return float(np.nansum(r[c].to_numpy("float64") * w) / W)

    def pooled_std(mean_col, std_col):
        m = r[mean_col].to_numpy("float64")
        s = r[std_col].to_numpy("float64")
        gm = float(np.nansum(m * w) / W)
        return float(np.sqrt(np.nansum(w * (s ** 2 + (m - gm) ** 2)) / W))

    out = {
        "n_days": int(len(r)),
        "n_days_attempted": int(len(rows)),
        "n_common": int(W),
        # Coverage is averaged over EVERY attempted day, not only the usable
        # ones. Averaging over usable days would flatter a gappy product by
        # discarding exactly the days on which it delivered nothing.
        "ref_coverage": float(rows["ref_coverage"].mean()),
        "nrt_coverage": float(rows["nrt_coverage"].mean()),
        "common_coverage": float(rows["common_coverage"].mean()),
        "bias": wm("bias"),
        "rmsd": float(np.sqrt(np.nansum(w * r["rmsd"].to_numpy("float64") ** 2) / W)),
        "mae": wm("mae"),
        "ref_mean": wm("ref_mean"), "nrt_mean": wm("nrt_mean"),
        "ref_std": pooled_std("ref_mean", "ref_std"),
        "nrt_std": pooled_std("nrt_mean", "nrt_std"),
        "correlation_daily_median": float(r["correlation"].median()),
        "correlation_daily_min": float(r["correlation"].min()),
        "std_ratio_daily_median": float(r["std_ratio"].median()),
    }
    out["std_ratio"] = (out["nrt_std"] / out["ref_std"]
                        if out["ref_std"] > 1e-12 else np.nan)
    for c in ("ref_grad_mean", "nrt_grad_mean", "ref_grad_p95", "nrt_grad_p95"):
        if c in r:
            out[c] = float(r[c].mean())
    if out.get("ref_grad_mean"):
        out["grad_ratio"] = out["nrt_grad_mean"] / out["ref_grad_mean"]
    return out


def classify(pooled: dict, sigma_train: float) -> dict:
    """Apply the pre-registered band to a pooled record."""
    if not pooled.get("n_common"):
        return {**pooled, "sigma_train": sigma_train,
                "compatibility_band": "INCOMPATIBLE_RAW",
                "band_reason": "no common valid support"}
    r = pooled["rmsd"] / sigma_train
    b = abs(pooled["bias"]) / sigma_train
    rho = pooled["correlation_daily_median"]
    q = pooled["std_ratio"]
    band = compatibility_band(r, b, rho, q)
    return {**pooled, "sigma_train": sigma_train,
            "rmsd_over_sigma": r, "abs_bias_over_sigma": b,
            "compatibility_band": band,
            "band_reason": f"r={r:.3f} b={b:.3f} rho={rho:.4f} q={q:.3f}"}
