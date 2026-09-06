"""Phase 6B-A figures: depth-wise skill curves and representative profiles."""
from __future__ import annotations

import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd, torch, yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.dataset import PointwiseSampler
from oceanembed.ml.model import PointwiseMLP
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
TAB = REPO_ROOT / CFG["paths"]["tables"]
FIG = REPO_ROOT / CFG["paths"]["figures"]
FIG.mkdir(parents=True, exist_ok=True)

C0, C1 = "#B0651A", "#1F6FB0"   # L0 climatology, L1 MLP


def _curve(ax, d, y0, y1, ylab, title):
    if y0 is not None:
        ax.plot(y0, d, "o-", color=C0, label="L0 climatology", lw=1.8, ms=4)
    if y1 is not None:
        ax.plot(y1, d, "s-", color=C1, label="L1 pointwise MLP", lw=1.8, ms=4)
    ax.invert_yaxis()
    ax.set_ylabel("depth (m)"); ax.set_xlabel(ylab)
    ax.set_title(title, fontsize=10); ax.grid(alpha=0.3); ax.legend(fontsize=8)


def skill_figures(sfx: str = "") -> None:
    m = pd.read_csv(TAB / f"phase6b_metrics_by_depth{sfx}.csv")
    s = pd.read_csv(TAB / f"phase6b_skill_vs_climatology{sfx}.csv")
    l0 = m[m.model == "L0_climatology"].sort_values("depth_m")
    l1 = m[m.model == "L1_mlp"].sort_values("depth_m")
    d = l0.depth_m.values

    for fname, y0, y1, lab, title in [
        ("rmse_vs_depth", l0.rmse.values, l1.rmse.values, "RMSE (degC)", "RMSE vs depth"),
        ("nrmse_vs_depth", l0.nrmse.values, l1.nrmse.values, "NRMSE (RMSE / truth std)",
         "NRMSE vs depth  (guards against low deep RMSE looking like skill)"),
        ("correlation_vs_depth", l0.correlation.values, l1.correlation.values,
         "correlation", "Correlation vs depth"),
    ]:
        fig, ax = plt.subplots(figsize=(5.6, 5.6))
        _curve(ax, d, y0, y1, lab, title)
        fig.tight_layout(); fig.savefig(FIG / f"{fname}{sfx}.png", dpi=140); plt.close(fig)
        print(f"  wrote {fname}{sfx}.png")

    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    _curve(ax, d, None, l1.anomaly_correlation.values, "anomaly correlation",
           "Anomaly correlation vs depth\n(day-to-day departure from seasonal cycle)")
    ax.axvline(0, color="k", lw=0.8, ls=":")
    fig.tight_layout(); fig.savefig(FIG / f"anomaly_correlation_vs_depth{sfx}.png", dpi=140)
    plt.close(fig); print(f"  wrote anomaly_correlation_vs_depth{sfx}.png")

    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    imp = s.sort_values("depth_m")
    ax.plot(imp.improvement_percent.values, imp.depth_m.values, "s-", color=C1, lw=1.8, ms=4)
    ax.axvline(0, color="k", lw=1.0)
    ax.invert_yaxis(); ax.set_ylabel("depth (m)")
    ax.set_xlabel("RMSE improvement over climatology (%)")
    ax.set_title("L1 skill over L0\n(negative = climatology wins)", fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG / f"skill_over_climatology_vs_depth{sfx}.png", dpi=140)
    plt.close(fig); print(f"  wrote skill_over_climatology_vs_depth{sfx}.png")


def profile_figures(split: str, allow_test: bool, sfx: str = "", n: int = 4) -> None:
    ds = splits.open_split(split, allow_test=allow_test)
    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    ck = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    model = PointwiseMLP(ck["n_features"], tuple(ck["hidden"]), ck["n_out"])
    model.load_state_dict(ck["state_dict"]); model.eval()

    smp = PointwiseSampler(ds, DEPTHS, chunk_days=8)
    X, Y, M, times, row_t, row_c = next(smp.blocks())
    c_full = clim.predict(pd.DatetimeIndex(np.unique(times)),
                          smp.cell_idx[:, 0], smp.cell_idx[:, 1])
    c = c_full[row_t, row_c, :]
    with torch.no_grad():
        p = ts.inverse_transform(model(torch.from_numpy(fs.transform(X).astype("float32"))).numpy())

    blat, blon = smp.cell_lat[row_c], smp.cell_lon[row_c]
    # pick deep open-ocean cells with a complete 15-depth profile
    full = M.all(axis=1)
    picks = [("Arabian Sea", 15.0, 65.0), ("Bay of Bengal", 15.0, 88.0),
             ("Equatorial IO", 6.0, 75.0), ("N. Arabian Sea", 20.0, 65.0)][:n]
    fig, axes = plt.subplots(1, len(picks), figsize=(4.0 * len(picks), 5.2), sharey=True)
    for ax, (name, la, lo) in zip(np.atleast_1d(axes), picks):
        dist = np.hypot(blat - la, blon - lo) + np.where(full, 0.0, 1e6)
        i = int(np.argmin(dist))
        ax.plot(Y[i], DEPTHS, "k-o", lw=2, ms=4, label="GLORYS truth")
        ax.plot(c[i], DEPTHS, "--", color=C0, lw=1.8, label="L0 climatology")
        ax.plot(p[i], DEPTHS, "-", color=C1, lw=1.8, label="L1 MLP")
        ax.set_title(f"{name}\n{blat[i]:.2f}N {blon[i]:.2f}E  {str(times[i])[:10]}", fontsize=9)
        ax.set_xlabel("temperature (degC)"); ax.grid(alpha=0.3)
        ax.tick_params(labelsize=8)
    np.atleast_1d(axes)[0].set_ylabel("depth (m)")
    np.atleast_1d(axes)[0].invert_yaxis()
    np.atleast_1d(axes)[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / f"profiles_truth_clim_mlp{sfx}.png", dpi=140)
    plt.close(fig); print(f"  wrote profiles_truth_clim_mlp{sfx}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--allow-test", action="store_true")
    a = ap.parse_args()
    sfx = "_test" if a.split == "test" else ""
    skill_figures(sfx)
    profile_figures(a.split, a.allow_test, sfx)
