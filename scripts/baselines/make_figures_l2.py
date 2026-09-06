"""Phase 6B-B figures: L0 vs L1 vs L2 depth curves and profiles."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.features import SURFACE, cyclic_doy
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import PointwiseMLP
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
TAB = REPO_ROOT / CFG["paths"]["tables"]
FIG = REPO_ROOT / CFG["paths"]["figures"]
FIG.mkdir(parents=True, exist_ok=True)

C0, C1, C2 = "#B0651A", "#1F6FB0", "#128A6B"      # L0, L1, L2


def curves(sfx: str) -> None:
    c = pd.read_csv(TAB / f"phase6b_l2_vs_l1{sfx}.csv").sort_values("depth_m")
    d = c.depth_m.values

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.rmse_L0, d, "o-", color=C0, label="L0 climatology", lw=1.8, ms=4)
    ax.plot(c.rmse_L1, d, "s-", color=C1, label="L1 pointwise MLP", lw=1.8, ms=4)
    ax.plot(c.rmse_L2, d, "^-", color=C2, label="L2 spatial embedding", lw=2.0, ms=5)
    ax.invert_yaxis()
    ax.set_xlabel("RMSE (degC)")
    ax.set_ylabel("depth (m)")
    ax.set_title("RMSE vs depth", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l0_l1_l2_rmse_vs_depth{sfx}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.anomcorr_L1, d, "s-", color=C1, label="L1", lw=1.8, ms=4)
    ax.plot(c.anomcorr_L2, d, "^-", color=C2, label="L2", lw=2.0, ms=5)
    ax.axvline(0, color="k", lw=0.8, ls=":")
    ax.invert_yaxis()
    ax.set_xlabel("anomaly correlation")
    ax.set_ylabel("depth (m)")
    ax.set_title("Anomaly correlation vs depth\n(day-to-day departure from the seasonal cycle)",
                 fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l1_vs_l2_anomaly_corr{sfx}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.delta_L2_vs_L1_pct, d, "^-", color=C2, lw=2.0, ms=5)
    ax.axvline(0, color="k", lw=1.0)
    ax.invert_yaxis()
    ax.set_xlabel("RMSE reduction of L2 relative to L1 (%)")
    ax.set_ylabel("depth (m)")
    ax.set_title("Spatial context gain\n(negative = L1 pointwise wins)", fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / f"l1_vs_l2_skill_delta{sfx}.png", dpi=140)
    plt.close(fig)
    for n in ("l0_l1_l2_rmse_vs_depth", "l1_vs_l2_anomaly_corr", "l1_vs_l2_skill_delta"):
        print(f"  wrote {n}{sfx}.png")


def profiles(split: str, allow_test: bool, tag: str, sfx: str) -> None:
    ds = splits.open_split(split, allow_test=allow_test)
    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    ck1 = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    l1 = PointwiseMLP(ck1["n_features"], tuple(ck1["hidden"]), ck1["n_out"])
    l1.load_state_dict(ck1["state_dict"])
    l1.eval()
    ck2 = torch.load(MODELS / f"phase6b_l2_{tag}.pt", map_location="cpu", weights_only=False)
    l2 = L2EmbeddingModel(latent=ck2["latent"], patch=ck2["patch"])
    l2.load_state_dict(ck2["state_dict"])
    l2.eval()

    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck2["patch"])
    t = 0
    field, ctx, _, M, Y = smp.day(t)
    r, c = smp.r, smp.c
    cp = clim.predict(smp.times[t:t + 1], r, c)[0]
    surf = np.column_stack([ds[v].isel(time=t).values[r, c] for v in SURFACE])
    s, cc = cyclic_doy(smp.times[t:t + 1])
    X1 = np.column_stack([surf, smp.cell_lat, smp.cell_lon,
                          np.full(smp.n_cells, s[0]), np.full(smp.n_cells, cc[0])])
    with torch.no_grad():
        p1 = ts.inverse_transform(
            l1(torch.from_numpy(fs.transform(X1).astype("float32"))).numpy())
        z = l2.embed_field(torch.from_numpy(field)[None])[0]
        p2 = ts.inverse_transform(
            l2.forward_from_z(z[:, r, c].T, torch.from_numpy(ctx)).numpy().astype("float64"))

    full = M.all(axis=1)
    picks = [("Arabian Sea", 15.0, 65.0), ("Bay of Bengal", 15.0, 88.0),
             ("Equatorial IO", 6.0, 75.0), ("N. Arabian Sea", 20.0, 65.0)]
    fig, axes = plt.subplots(1, len(picks), figsize=(4.0 * len(picks), 5.2), sharey=True)
    for ax, (name, la, lo) in zip(axes, picks):
        dist = np.hypot(smp.cell_lat - la, smp.cell_lon - lo) + np.where(full, 0.0, 1e6)
        i = int(np.argmin(dist))
        ax.plot(Y[i], DEPTHS, "k-o", lw=2, ms=4, label="GLORYS truth")
        ax.plot(cp[i], DEPTHS, "--", color=C0, lw=1.6, label="L0 climatology")
        ax.plot(p1[i], DEPTHS, "-", color=C1, lw=1.6, label="L1 MLP")
        ax.plot(p2[i], DEPTHS, "-", color=C2, lw=2.0, label="L2 embedding")
        ax.set_title(f"{name}\n{smp.cell_lat[i]:.2f}N {smp.cell_lon[i]:.2f}E  "
                     f"{str(smp.times[t])[:10]}", fontsize=9)
        ax.set_xlabel("temperature (degC)")
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("depth (m)")
    axes[0].invert_yaxis()
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l2_profiles{sfx}.png", dpi=140)
    plt.close(fig)
    print(f"  wrote l2_profiles{sfx}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--tag", default="final")
    a = ap.parse_args()
    sfx = "_test" if a.split == "test" else ""
    curves(sfx)
    profiles(a.split, a.allow_test, a.tag, sfx)
