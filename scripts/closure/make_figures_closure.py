"""Figures for the architecture-closure study.

Every panel is drawn from the CSV/JSON artefacts written by B, C and D, so a
figure can never disagree with the table it illustrates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from oceanembed.config import REPO_ROOT

TAB = REPO_ROOT / "outputs" / "tables" / "architecture_closure"
FIG = REPO_ROOT / "outputs" / "figures" / "architecture_closure"
CLOSURE = REPO_ROOT / "outputs" / "architecture_closure"

GROUP_COLOR = {"SST": "#b42318", "SSS": "#3b6fb6", "SLA": "#1a7f37",
               "CURRENTS": "#8a5cd0", "WINDS": "#d08a00"}


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=140)
    plt.close(fig)
    print("  ", name)


def depth_axis(ax):
    ax.invert_yaxis()
    ax.set_yscale("symlog", linthresh=50)
    ax.set_ylabel("depth (m)")
    ax.grid(alpha=0.3)


# ------------------------------------------------------------------ B
def fig_pca_cumulative():
    res = json.loads((CLOSURE / "pca_diagnostic.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, aname in zip(axes, ("B1_FULL15", "B2_UPPER300")):
        for rep, style in (("raw", "-o"), ("residual", "-s")):
            cum = np.array(res[aname][rep]["cumulative_explained_variance"])
            ax.plot(np.arange(1, len(cum) + 1), cum * 100, style, ms=4,
                    label=f"{rep} (k95={res[aname][rep]['k_for_95pct']})")
        for y in (90, 95, 99):
            ax.axhline(y, ls="--", c="k", lw=0.7)
            ax.text(len(cum) * 0.75, y + 0.3, f"{y}%", fontsize=7)
        ax.set_xlabel("number of components (k)")
        ax.set_ylabel("cumulative explained variance (%)")
        ax.set_title(f"{aname}  (n={res[aname]['sampling']['n_profiles']:,} profiles)",
                     fontsize=10)
        ax.set_ylim(40, 101)
        ax.legend(fontsize=8, loc="lower right")
        ax.grid(alpha=0.3)
    fig.suptitle("Experiment B — vertical low-rank structure, TRAIN-only basis",
                 fontsize=11)
    save(fig, "pca_cumulative_variance.png")


def fig_pca_eof_shapes():
    res = json.loads((CLOSURE / "pca_diagnostic.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 6), sharey=True)
    for ax, rep in zip(axes, ("raw", "residual")):
        a = res["B1_FULL15"][rep]
        depths = np.array(a["depths"], dtype="float64")
        V = np.array(a["eofs"])
        evr = np.array(a["explained_variance_ratio"])
        for k in range(5):
            v = V[:, k]
            # sign convention: make each mode's largest-magnitude entry positive
            # so the plotted shapes are comparable between panels
            if v[np.argmax(np.abs(v))] < 0:
                v = -v
            ax.plot(v, depths, "-o", ms=3,
                    label=f"EOF{k+1} ({evr[k]*100:.1f}%)")
        ax.axvline(0, c="k", lw=0.8)
        ax.set_xlabel("loading")
        ax.set_title(f"{rep} profiles", fontsize=10)
        depth_axis(ax)
        ax.legend(fontsize=8)
    fig.suptitle("Experiment B — leading vertical EOF shapes (B1_FULL15, train only)",
                 fontsize=11)
    save(fig, "pca_eof_shapes.png")


def fig_pca_reconstruction():
    rec = pd.read_csv(TAB / "pca_reconstruction_error.csv")
    l2 = pd.read_csv(REPO_ROOT / "outputs" / "tables"
                     / "phase6b_l2_metrics_by_depth.csv")
    l2 = l2[l2.model.str.contains("L2")].set_index("depth_m")["rmse"]
    r = rec[(rec.analysis == "B1_FULL15") & (rec.representation == "residual")]
    depths = [int(c.replace("rmse_", "").replace("m", ""))
              for c in r.columns if c.startswith("rmse_") and c != "rmse_overall"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for _, row in r.iterrows():
        vals = [row[f"rmse_{d}m"] for d in depths]
        axes[0].plot(vals, depths, "-o", ms=3, label=f"k={int(row['k'])}")
        axes[1].plot([v / l2[d] for v, d in zip(vals, depths)], depths, "-o", ms=3,
                     label=f"k={int(row['k'])}")
    axes[0].set_xlabel("residual reconstruction RMSE (degC)")
    axes[1].set_xlabel("reconstruction RMSE / frozen L2 validation RMSE")
    for x, lab in ((0.25, "pre-registered 25% tolerance"), (0.50, "WEAK trigger 50%")):
        axes[1].axvline(x, ls="--", c="k", lw=0.9)
        axes[1].text(x, 1.2, lab, rotation=90, fontsize=7, va="bottom")
    for ax in axes:
        depth_axis(ax)
    axes[0].legend(fontsize=8)
    fig.suptitle("Experiment B — what a truncated EOF basis would cost, by depth",
                 fontsize=11)
    save(fig, "pca_reconstruction_error.png")


# ------------------------------------------------------------------ C
def fig_residual_profile():
    p = TAB / "residual_metrics_validation_metrics_by_depth.csv"
    if not p.exists():
        print("   residual metrics missing, skipped")
        return
    d = pd.read_csv(p)
    piv = d.pivot(index="depth_m", columns="model", values="rmse").sort_index()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for m in piv.columns:
        axes[0].plot(piv[m], piv.index, "-o", ms=3, label=m)
    axes[0].set_xlabel("validation RMSE (degC)")
    axes[0].legend(fontsize=8)
    if "FROZEN_L2" in piv.columns:
        for m in piv.columns:
            if m in ("FROZEN_L2", "L0_climatology"):
                continue
            delta = (piv[m] - piv["FROZEN_L2"]) / piv["FROZEN_L2"] * 100
            axes[1].plot(delta, piv.index, "-o", ms=3, label=m)
        axes[1].axvline(0, c="k", lw=1)
        axes[1].axvline(-1.0, ls="--", c="#1a7f37", lw=0.8)
        axes[1].axvline(1.0, ls="--", c="#b42318", lw=0.8)
        axes[1].set_xlabel("RMSE change vs frozen L2 (%)   negative = better")
        axes[1].legend(fontsize=8)
    for ax in axes:
        depth_axis(ax)
    fig.suptitle("Experiment C — climatology-residual vs frozen L2, 2021 validation",
                 fontsize=11)
    save(fig, "residual_vs_l2_depth_profile.png")


def fig_residual_anomaly_corr():
    p = TAB / "residual_metrics_validation_metrics_by_depth.csv"
    if not p.exists():
        print("   residual metrics missing, skipped")
        return
    d = pd.read_csv(p)
    d = d[d.anomaly_correlation.notna()]
    piv = d.pivot(index="depth_m", columns="model",
                  values="anomaly_correlation").sort_index()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
    for m in piv.columns:
        axes[0].plot(piv[m], piv.index, "-o", ms=3, label=m)
    axes[0].set_xlabel("anomaly correlation vs L0")
    axes[0].legend(fontsize=8)
    if "FROZEN_L2" in piv.columns:
        for m in piv.columns:
            if m == "FROZEN_L2":
                continue
            axes[1].plot(piv[m] - piv["FROZEN_L2"], piv.index, "-o", ms=3, label=m)
        axes[1].axvline(0, c="k", lw=1)
        axes[1].set_xlabel("anomaly correlation minus frozen L2")
        axes[1].legend(fontsize=8)
    for ax in axes:
        depth_axis(ax)
    fig.suptitle("Experiment C — anomaly correlation (departures from L0)",
                 fontsize=11)
    save(fig, "residual_anomaly_corr.png")


# ------------------------------------------------------------------ D
def _ablation_table():
    p = TAB / "channel_ablation_metrics.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    d = d[d.model != "L0_climatology"]
    d["group"] = d["model"].str.replace("D_MINUS_", "", regex=False)
    return d


def fig_ablation_heatmap():
    d = _ablation_table()
    if d is None or "D_CONTROL_ALL" not in set(d.model):
        print("   ablation metrics missing, skipped")
        return
    ctrl = d[d.model == "D_CONTROL_ALL"].set_index("depth_m")["rmse"]
    groups = [g for g in ("SST", "SSS", "SLA", "CURRENTS", "WINDS")
              if f"D_MINUS_{g}" in set(d.model)]
    depths = sorted(ctrl.index)
    M = np.array([[(d[(d.model == f"D_MINUS_{g}") & (d.depth_m == dep)]["rmse"].iloc[0]
                    - ctrl[dep]) / ctrl[dep] * 100 for dep in depths]
                  for g in groups])
    fig, ax = plt.subplots(figsize=(12, 4.2))
    lim = float(np.nanmax(np.abs(M))) or 1.0
    im = ax.imshow(M, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(len(depths)))
    ax.set_xticklabels(depths, fontsize=8)
    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels(groups)
    ax.set_xlabel("depth (m)")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:+.1f}", ha="center", va="center", fontsize=6,
                    color="white" if abs(M[i, j]) > lim * 0.55 else "black")
    fig.colorbar(im, ax=ax, label="RMSE change vs full-input control (%)")
    ax.set_title("Experiment D — cost of removing one information group during "
                 "training\npositive = worse without that group "
                 "(controlled ablation, sample population fixed)", fontsize=10)
    save(fig, "channel_ablation_heatmap.png")


def fig_ablation_depth_groups():
    p = TAB / "channel_ablation_depth_groups.csv"
    if not p.exists():
        print("   ablation depth groups missing, skipped")
        return
    d = pd.read_csv(p)
    order = ["0-50 m", "75-150 m", "200-300 m", "500-1000 m"]
    groups = [g for g in ("SST", "SSS", "SLA", "CURRENTS", "WINDS")
              if g in set(d["group"])]
    fig, ax = plt.subplots(figsize=(10, 5))
    w = 0.8 / max(len(groups), 1)
    x = np.arange(len(order))
    for i, g in enumerate(groups):
        vals = [d[(d["group"] == g) & (d["band"] == b)]["rmse_change_percent"].iloc[0]
                if len(d[(d["group"] == g) & (d["band"] == b)]) else np.nan
                for b in order]
        ax.bar(x + i * w - 0.4 + w / 2, vals, w, label=g,
               color=GROUP_COLOR.get(g, "#888"))
    ax.axhline(0, c="k", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(order)
    ax.set_ylabel("RMSE change vs full-input control (%)")
    ax.set_title("Experiment D — information contribution by depth band\n"
                 "positive = the model is worse without that group")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    save(fig, "channel_ablation_depth_groups.png")


def main() -> int:
    print("figures ->", FIG)
    for fn in (fig_pca_cumulative, fig_pca_eof_shapes, fig_pca_reconstruction,
               fig_residual_profile, fig_residual_anomaly_corr,
               fig_ablation_heatmap, fig_ablation_depth_groups):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"   {fn.__name__} FAILED: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
