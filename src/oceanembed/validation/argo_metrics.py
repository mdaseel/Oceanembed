"""Metrics for the Argo observational audit, on an intersected sample population.

Two properties matter for this to be an honest comparison:

* IDENTICAL SAMPLES. At each depth the accepted set is the intersection of
  "Argo supported this depth" with "every one of L0, L1, L2 and GLORYS produced
  a finite value there". No system is scored on a more convenient subset.

* HONEST UNCERTAINTY. Observations from the same float on nearby cycles are
  strongly correlated, so resampling individual depth measurements would give
  spuriously tight intervals. The bootstrap resamples FLOATS (platform IDs),
  which is the natural independent unit here, and is paired so that the
  L2-minus-L0 and L2-minus-L1 differences are evaluated on identical resamples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = ["L0", "L1", "L2", "GLORYS"]

DEPTH_GROUPS = {
    "surface_mixed_layer": [0, 5, 10],
    "upper_thermocline": [20, 30, 50],
    "thermocline": [75, 100, 125],
    "intermediate": [150, 200, 300],
    "deep": [500, 700, 1000],
}
BASINS = {
    "arabian_sea": {"lat": (8.0, 25.0), "lon": (50.0, 77.0)},
    "bay_of_bengal": {"lat": (5.0, 22.0), "lon": (80.0, 100.0)},
}
MIN_SAMPLES = 30          # below this a subgroup metric is suppressed, not reported


def accepted_mask(df: pd.DataFrame, depth: int) -> np.ndarray:
    """Rows where Argo supports this depth AND all four systems are finite.

    The .copy() is load-bearing. For a bool column, ``to_numpy`` returns a VIEW
    into the DataFrame, so the in-place ``&=`` below would rewrite the stored
    ``argo_sup_<d>m`` column. That silently corrupted the basin summary: after
    the Arabian Sea pass the column meant "accepted AND Arabian Sea", and the
    Bay of Bengal pass then intersected two disjoint boxes to nothing.
    """
    m = df[f"argo_sup_{depth}m"].to_numpy(dtype=bool).copy()
    m &= np.isfinite(df[f"argo_pt_{depth}m"].to_numpy(dtype="float64"))
    for name in MODELS:
        m &= np.isfinite(df[f"{name}_{depth}m"].to_numpy(dtype="float64"))
    return m


def _stats(pred: np.ndarray, obs: np.ndarray, clim: np.ndarray | None) -> dict:
    d = pred - obs
    n = d.size
    out = {"n": int(n), "rmse": float(np.sqrt(np.mean(d ** 2))),
           "mae": float(np.mean(np.abs(d))), "bias": float(np.mean(d))}
    if n > 2 and np.std(pred) > 0 and np.std(obs) > 0:
        out["correlation"] = float(np.corrcoef(pred, obs)[0, 1])
    else:
        out["correlation"] = np.nan
    sd = float(np.std(obs))
    out["nrmse"] = out["rmse"] / sd if sd > 0 else np.nan
    out["obs_std"] = sd
    if clim is not None:
        pa, oa = pred - clim, obs - clim
        if n > 2 and np.std(pa) > 0 and np.std(oa) > 0:
            out["anomaly_correlation"] = float(np.corrcoef(pa, oa)[0, 1])
        else:
            out["anomaly_correlation"] = np.nan
        out["anomaly_rmse"] = float(np.sqrt(np.mean((pa - oa) ** 2)))
    return out


def metrics_by_depth(df: pd.DataFrame, depths: list[int],
                     subset: np.ndarray | None = None) -> pd.DataFrame:
    rows = []
    for d in depths:
        m = accepted_mask(df, d)
        if subset is not None:
            m = m & np.asarray(subset, dtype=bool)
        if m.sum() == 0:
            for name in MODELS:
                rows.append({"depth_m": d, "model": name, "n": 0})
            continue
        obs = df.loc[m, f"argo_pt_{d}m"].to_numpy(dtype="float64")
        clim = df.loc[m, f"L0_{d}m"].to_numpy(dtype="float64")
        for name in MODELS:
            pred = df.loc[m, f"{name}_{d}m"].to_numpy(dtype="float64")
            # L0 anomaly against itself is identically zero and meaningless
            rows.append({"depth_m": d, "model": name,
                         **_stats(pred, obs, None if name == "L0" else clim)})
    return pd.DataFrame(rows)


def pairwise(df: pd.DataFrame, depths: list[int], a: str, b: str) -> pd.DataFrame:
    """RMSE of `a` vs `b` on the identical accepted population."""
    rows = []
    for d in depths:
        m = accepted_mask(df, d)
        if m.sum() == 0:
            rows.append({"depth_m": d, "n": 0})
            continue
        obs = df.loc[m, f"argo_pt_{d}m"].to_numpy(dtype="float64")
        ra = float(np.sqrt(np.mean((df.loc[m, f"{a}_{d}m"].to_numpy("float64") - obs) ** 2)))
        rb = float(np.sqrt(np.mean((df.loc[m, f"{b}_{d}m"].to_numpy("float64") - obs) ** 2)))
        rows.append({"depth_m": d, "n": int(m.sum()),
                     f"rmse_{a}": ra, f"rmse_{b}": rb,
                     "rmse_difference": ra - rb,
                     "improvement_percent": (rb - ra) / rb * 100.0 if rb > 0 else np.nan,
                     f"{a}_better": ra < rb})
    return pd.DataFrame(rows)


def group_summary(by_depth: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g, deps in DEPTH_GROUPS.items():
        sub = by_depth[by_depth.depth_m.isin(deps) & (by_depth.n > 0)]
        for model, s in sub.groupby("model"):
            w = s["n"].to_numpy(dtype="float64")
            if w.sum() == 0:
                continue
            rows.append({"group": g, "depths_m": ",".join(map(str, deps)),
                         "model": model,
                         "rmse": float(np.sqrt(np.average(s["rmse"] ** 2, weights=w))),
                         "mae": float(np.average(s["mae"], weights=w)),
                         "bias": float(np.average(s["bias"], weights=w)),
                         "correlation": float(np.average(s["correlation"], weights=w)),
                         "n": int(w.sum())})
    return pd.DataFrame(rows)


def basin_mask(df: pd.DataFrame, name: str) -> np.ndarray:
    b = BASINS[name]
    lat = df["lat"].to_numpy(dtype="float64")
    lon = df["lon"].to_numpy(dtype="float64")
    return ((lat >= b["lat"][0]) & (lat <= b["lat"][1]) &
            (lon >= b["lon"][0]) & (lon <= b["lon"][1]))


def cluster_bootstrap_rmse_diff(df: pd.DataFrame, depth: int, a: str, b: str,
                                n_boot: int = 1000, seed: int = 20260905,
                                cluster: str = "wmo") -> dict:
    """Paired bootstrap of RMSE(a) - RMSE(b), resampling whole floats.

    Negative means `a` has the lower RMSE. The same resampled float set is used
    for both models on every replicate, so the difference is paired.
    """
    m = accepted_mask(df, depth)
    if m.sum() < MIN_SAMPLES:
        return {"depth_m": depth, "n": int(m.sum()), "insufficient": True}
    sub = df.loc[m]
    obs = sub[f"argo_pt_{depth}m"].to_numpy("float64")
    pa = sub[f"{a}_{depth}m"].to_numpy("float64")
    pb = sub[f"{b}_{depth}m"].to_numpy("float64")
    keys = sub[cluster].to_numpy()
    uniq = np.unique(keys)
    idx_by_key = {k: np.where(keys == k)[0] for k in uniq}

    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        sel = np.concatenate([idx_by_key[k] for k in pick])
        ra = np.sqrt(np.mean((pa[sel] - obs[sel]) ** 2))
        rb = np.sqrt(np.mean((pb[sel] - obs[sel]) ** 2))
        diffs[i] = ra - rb
    point = float(np.sqrt(np.mean((pa - obs) ** 2)) - np.sqrt(np.mean((pb - obs) ** 2)))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"depth_m": depth, "comparison": f"{a} minus {b}", "n": int(m.sum()),
            "n_clusters": int(uniq.size), "cluster_unit": cluster,
            "rmse_difference": point, "ci_lo": float(lo), "ci_hi": float(hi),
            "significant": bool(hi < 0 or lo > 0),
            "a_better": bool(point < 0), "n_boot": int(n_boot)}
