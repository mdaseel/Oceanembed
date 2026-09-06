"""Depth-wise metrics for L0/L1, computed by streaming accumulation.

Everything is accumulated from sums so that 4 M validation samples (or 12 M
test samples) never have to be held in memory at once. Metrics are computed
per depth first; aggregate-across-depth numbers are reported only as a
secondary summary because they hide the depth structure that actually matters.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEPTH_GROUPS = {
    "surface_mixed_layer": [0, 5, 10],
    "upper_thermocline":   [20, 30, 50],
    "thermocline":         [75, 100, 125],
    "intermediate":        [150, 200, 300],
    "deep":                [500, 700, 1000],
}
BASINS = {
    "arabian_sea":   {"lat": (8.0, 25.0), "lon": (50.0, 77.0)},
    "bay_of_bengal": {"lat": (5.0, 22.0), "lon": (80.0, 100.0)},
}


class DepthAccumulator:
    """Streaming sums for RMSE / MAE / bias / correlation / NRMSE per depth."""

    def __init__(self, depths: list[int]):
        self.depths = list(depths)
        k = len(depths)
        z = lambda: np.zeros(k, dtype="float64")  # noqa: E731
        self.n, self.se, self.ae, self.de = z(), z(), z(), z()
        self.sy, self.sp, self.syy, self.spp, self.syp = z(), z(), z(), z(), z()

    def update(self, pred: np.ndarray, truth: np.ndarray, mask: np.ndarray) -> None:
        for j in range(len(self.depths)):
            m = mask[:, j] & np.isfinite(pred[:, j]) & np.isfinite(truth[:, j])
            if not m.any():
                continue
            p, t = pred[m, j].astype("float64"), truth[m, j].astype("float64")
            d = p - t
            self.n[j] += p.size
            self.se[j] += (d ** 2).sum()
            self.ae[j] += np.abs(d).sum()
            self.de[j] += d.sum()
            self.sy[j] += t.sum(); self.sp[j] += p.sum()
            self.syy[j] += (t * t).sum(); self.spp[j] += (p * p).sum()
            self.syp[j] += (p * t).sum()

    def frame(self, label: str) -> pd.DataFrame:
        rows = []
        for j, d in enumerate(self.depths):
            n = self.n[j]
            if n < 2:
                rows.append({"depth_m": d, "model": label, "n": int(n)})
                continue
            rmse = np.sqrt(self.se[j] / n)
            mae = self.ae[j] / n
            bias = self.de[j] / n
            var_t = max(self.syy[j] / n - (self.sy[j] / n) ** 2, 0.0)
            var_p = max(self.spp[j] / n - (self.sp[j] / n) ** 2, 0.0)
            cov = self.syp[j] / n - (self.sy[j] / n) * (self.sp[j] / n)
            corr = cov / np.sqrt(var_t * var_p) if var_t > 0 and var_p > 0 else np.nan
            sd_t = np.sqrt(var_t)
            rows.append({"depth_m": d, "model": label, "n": int(n),
                         "rmse": rmse, "mae": mae, "bias": bias,
                         "correlation": corr,
                         # NRMSE normalised by the truth's own standard deviation:
                         # this is what stops low deep-ocean RMSE from being
                         # mistaken for skill when the deep variance is tiny.
                         "nrmse": rmse / sd_t if sd_t > 0 else np.nan,
                         "truth_std": sd_t})
        return pd.DataFrame(rows)


def skill_table(l0: pd.DataFrame, l1: pd.DataFrame) -> pd.DataFrame:
    a = l0.set_index("depth_m"); b = l1.set_index("depth_m")
    out = pd.DataFrame({
        "depth_m": a.index,
        "rmse_L0_climatology": a["rmse"].values,
        "rmse_L1_mlp": b["rmse"].values,
        "nrmse_L0": a["nrmse"].values,
        "nrmse_L1": b["nrmse"].values,
        "corr_L0": a["correlation"].values,
        "corr_L1": b["correlation"].values,
        "improvement_percent": (a["rmse"].values - b["rmse"].values) / a["rmse"].values * 100.0,
    })
    out["L1_beats_L0"] = out["improvement_percent"] > 0
    return out


def group_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g, deps in DEPTH_GROUPS.items():
        sub = df[df["depth_m"].isin(deps)]
        for model, s in sub.groupby("model"):
            w = s["n"].to_numpy(dtype="float64")
            rows.append({
                "group": g, "depths_m": ",".join(map(str, deps)), "model": model,
                # RMSE aggregates in quadrature, weighted by sample count.
                "rmse": float(np.sqrt(np.average(s["rmse"] ** 2, weights=w))),
                "mae": float(np.average(s["mae"], weights=w)),
                "bias": float(np.average(s["bias"], weights=w)),
                "correlation": float(np.average(s["correlation"], weights=w)),
                "nrmse": float(np.average(s["nrmse"], weights=w)),
                "n": int(w.sum()),
            })
    return pd.DataFrame(rows)


def basin_of(lat: np.ndarray, lon: np.ndarray, name: str) -> np.ndarray:
    b = BASINS[name]
    return ((lat >= b["lat"][0]) & (lat <= b["lat"][1]) &
            (lon >= b["lon"][0]) & (lon <= b["lon"][1]))
