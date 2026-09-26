"""Validation context from the existing Phase 6C Argo 2022-2023 evaluation.

Display only. Nothing is recomputed and no Argo file is opened: the numbers are
read from the published tables. A regional RMSE is expected historical
validation error, never a calibrated uncertainty interval.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from ..ml.metrics import BASINS

TABLES = REPO_ROOT / "outputs" / "tables"
WORDING = ("Expected historical validation error / validation context: the error "
           "OceanEmbed showed against independent 2022-2023 Argo profiles at this depth. "
           "It is not a calibrated uncertainty interval for this location or date.")
SOURCE = "outputs/tables/phase6c_argo_*.csv (PHASE6C_ARGO_VALIDATION_REPORT.md)"
BASIN_NAMES = {"arabian_sea": "Arabian Sea", "bay_of_bengal": "Bay of Bengal"}


@lru_cache(maxsize=1)
def _tables():
    return {"nio": pd.read_csv(TABLES / "phase6c_argo_metrics_by_depth.csv"),
            "basin": pd.read_csv(TABLES / "phase6c_argo_basin_summary.csv"),
            "ci": pd.read_csv(TABLES / "phase6c_argo_bootstrap_ci.csv")}


def basin_for(lat: float, lon: float) -> str | None:
    for name, box in BASINS.items():
        if box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]:
            return name
    return None


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if not np.isfinite(f) else round(f, 4)


def _rows(df: pd.DataFrame, depth: int) -> dict:
    out = {}
    for _, r in df[df.depth_m == depth].iterrows():
        out[r.model] = {"n": int(r.n), "rmse_c": _clean(r.rmse), "bias_c": _clean(r.bias),
                        "correlation": _clean(r.correlation),
                        "anomaly_correlation": _clean(r.get("anomaly_correlation"))}
    return out


def context(depth_m: int, lat: float | None = None, lon: float | None = None) -> dict:
    t = _tables()
    depths = sorted(t["nio"].depth_m.unique())
    depth = int(min(depths, key=lambda d: abs(d - depth_m)))
    basin = basin_for(lat, lon) if lat is not None and lon is not None else None
    nio = _rows(t["nio"], depth)
    regional = _rows(t["basin"][t["basin"].basin == basin], depth) if basin else {}
    use = regional if regional.get("L2") and regional["L2"]["n"] >= 30 else nio
    scope = BASIN_NAMES[basin] if use is regional and basin else "North Indian Ocean domain"
    l2, l0 = use.get("L2"), use.get("L0")
    improvement = (None if not (l2 and l0 and l0["rmse_c"]) else
                   round((l0["rmse_c"] - l2["rmse_c"]) / l0["rmse_c"] * 100, 1))
    ci_rows = t["ci"][(t["ci"].depth_m == depth) & (t["ci"].comparison == "L2 minus L0")]
    ci = None
    if len(ci_rows):
        r = ci_rows.iloc[0]
        ci = {"rmse_difference_c": _clean(r.rmse_difference), "ci_lo": _clean(r.ci_lo),
              "ci_hi": _clean(r.ci_hi), "significant": bool(r.significant),
              "clusters": int(r.n_clusters), "cluster_unit": "Argo float (WMO)"}
    return {"depth_m": depth, "requested_depth_m": depth_m, "scope": scope,
            "basin": basin, "models": use, "nio_models": nio,
            "l2_improvement_vs_l0_percent": improvement, "bootstrap_l2_minus_l0": ci,
            "regional_sample_note": None if use is regional else
            ("regional Argo sample too small at this depth (n < 30); the domain-wide "
             "result is shown" if basin else "outside the named basins; domain-wide result"),
            "period": "2022-01-01..2023-12-31 Argo profiles (2024 protected, not used)",
            "wording": WORDING, "source": SOURCE}
