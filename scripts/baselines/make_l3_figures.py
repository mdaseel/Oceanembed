"""Phase 6B-C figures: window selection, depth curves, seed stability, diagnostics."""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from oceanembed.config import REPO_ROOT

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
TAB = REPO_ROOT / B6["paths"]["tables"]
FIG = REPO_ROOT / B6["paths"]["figures"]
MODELS = REPO_ROOT / B6["paths"]["models"]
FIG.mkdir(parents=True, exist_ok=True)

C0, C1, C2, C3, CC = "#B0651A", "#1F6FB0", "#128A6B", "#8B3A9E", "#777777"


def window_selection() -> None:
    p = TAB / "phase6b_l3_window_selection.csv"
    if not p.exists():
        return
    d = pd.read_csv(p).sort_values("window")
    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    ax.plot(d.window, d.best_val, "o-", color=C3, lw=2, ms=7)
    for _, r in d.iterrows():
        ax.annotate(f"{r.best_val:.5f}", (r.window, r.best_val),
                    textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8)
    ax.set_xticks(d.window.tolist())
    ax.set_xlabel("temporal window (days of causal history)")
    ax.set_ylabel("validation masked standardised MSE")
    ax.set_title("L3 window selection (validation only)\n"
                 "identical trainable parameters at every window", fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "l3_validation_vs_window.png", dpi=140)
    plt.close(fig)
    print("  wrote l3_validation_vs_window.png")


def depth_curves(sfx: str) -> None:
    p = TAB / f"phase6b_l3_vs_control{sfx}.csv"
    if not p.exists():
        return
    c = pd.read_csv(p).sort_values("depth_m")
    d = c.depth_m.values

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.rmse_L0, d, "o-", color=C0, label="L0 climatology", lw=1.6, ms=4)
    if "rmse_L1_pointwise" in c:
        ax.plot(c.rmse_L1_pointwise, d, "s-", color=C1, label="L1 pointwise", lw=1.6, ms=4)
    ax.plot(c.rmse_L2_spatial, d, "^-", color=C2, label="L2 spatial", lw=1.8, ms=5)
    ax.plot(c.rmse_L3_control_1d, d, "--", color=CC, label="L3 control (1 day)", lw=1.6)
    ax.plot(c.rmse_L3_selected, d, "d-", color=C3, label="L3 selected", lw=2.0, ms=5)
    ax.invert_yaxis()
    ax.set_xlabel("RMSE (degC)")
    ax.set_ylabel("depth (m)")
    ax.set_title("RMSE vs depth (common target dates)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l0_l1_l2_l3_rmse_vs_depth{sfx}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.anomcorr_L2_spatial, d, "^-", color=C2, label="L2 spatial", lw=1.8, ms=5)
    ax.plot(c.anomcorr_L3_control_1d, d, "--", color=CC, label="L3 control (1 day)", lw=1.6)
    ax.plot(c.anomcorr_L3_selected, d, "d-", color=C3, label="L3 selected", lw=2.0, ms=5)
    ax.axvline(0, color="k", lw=0.8, ls=":")
    ax.invert_yaxis()
    ax.set_xlabel("anomaly correlation")
    ax.set_ylabel("depth (m)")
    ax.set_title("Anomaly correlation vs depth", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l2_vs_l3_anomaly_corr{sfx}.png", dpi=140)
    plt.close(fig)

    for col, fname, title in [
        ("delta_selected_vs_L2_pct", f"l3_delta_vs_l2{sfx}",
         "L3 selected vs L2\n(negative = L2 wins)"),
        ("delta_selected_vs_control_pct", f"l3_delta_vs_control{sfx}",
         "L3 selected vs 1-day temporal control\n"
         "THE causal test: negative = history does not help"),
    ]:
        fig, ax = plt.subplots(figsize=(5.8, 5.8))
        ax.plot(c[col], d, "d-", color=C3, lw=2.0, ms=5)
        ax.axvline(0, color="k", lw=1.0)
        ax.invert_yaxis()
        ax.set_xlabel("RMSE reduction (%)")
        ax.set_ylabel("depth (m)")
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / f"{fname}.png", dpi=140)
        plt.close(fig)
    print(f"  wrote depth curves{sfx}")


def depth_groups(sfx: str) -> None:
    p = TAB / f"phase6b_l3_depth_group_summary{sfx}.csv"
    if not p.exists():
        return
    g = pd.read_csv(p)
    order = ["surface_mixed_layer", "upper_thermocline", "thermocline",
             "intermediate", "deep"]
    models = ["L0_climatology", "L2_spatial", "L3_control_1d", "L3_selected"]
    cols = {"L0_climatology": C0, "L2_spatial": C2, "L3_control_1d": CC,
            "L3_selected": C3}
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    w = 0.2
    x = np.arange(len(order))
    for i, m in enumerate(models):
        vals = [float(g[(g.group == grp) & (g.model == m)].rmse.iloc[0])
                if len(g[(g.group == grp) & (g.model == m)]) else np.nan for grp in order]
        ax.bar(x + (i - 1.5) * w, vals, w, label=m, color=cols[m])
    ax.set_xticks(x)
    ax.set_xticklabels([o.replace("_", "\n") for o in order], fontsize=8)
    ax.set_ylabel("RMSE (degC)")
    ax.set_title("Depth-group RMSE", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(FIG / f"l3_depth_groups{sfx}.png", dpi=140)
    plt.close(fig)
    print(f"  wrote l3_depth_groups{sfx}.png")


def seed_stability() -> None:
    p = TAB / "phase6b_l3_seed_stability.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    for tagname, col in [("control_1d", CC), ("selected", C3)]:
        sub = d[d.model == tagname].sort_values("seed")
        ax.plot(range(len(sub)), sub.best_val, "o-", color=col, label=tagname, lw=1.8, ms=6)
    ax.set_xticks(range(d.seed.nunique()))
    ax.set_xticklabels([str(s) for s in sorted(d.seed.unique())], fontsize=8)
    ax.set_xlabel("seed")
    ax.set_ylabel("validation masked standardised MSE")
    ax.set_title("Seed stability: selected window vs 1-day control", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "l3_seed_stability.png", dpi=140)
    plt.close(fig)
    print("  wrote l3_seed_stability.png")


def ordering_diagnostic(sfx: str) -> None:
    p = TAB / f"phase6b_l3_vs_control{sfx}.csv"
    if not p.exists():
        return
    c = pd.read_csv(p).sort_values("depth_m")
    if "rmse_L3_repeated_current" not in c:
        return
    d = c.depth_m.values
    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(c.rmse_L3_selected, d, "d-", color=C3, label="correct causal order", lw=2.0, ms=5)
    ax.plot(c.rmse_L3_repeated_current, d, "-", color="#C0392B",
            label="repeated current day", lw=1.6)
    ax.plot(c.rmse_L3_reversed_history, d, "-", color="#2E86C1",
            label="reversed history", lw=1.6)
    ax.invert_yaxis()
    ax.set_xlabel("RMSE (degC)")
    ax.set_ylabel("depth (m)")
    ax.set_title("Does temporal ordering matter?\n(frozen model, no retraining)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"l3_ordering_diagnostic{sfx}.png", dpi=140)
    plt.close(fig)
    print(f"  wrote l3_ordering_diagnostic{sfx}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    a = ap.parse_args()
    sfx = "_test" if a.split == "test" else ""
    window_selection()
    depth_curves(sfx)
    depth_groups(sfx)
    seed_stability()
    ordering_diagnostic(sfx)
