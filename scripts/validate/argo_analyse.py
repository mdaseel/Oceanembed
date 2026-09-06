"""Phase 6C-A analysis: tables, bootstrap CIs and figures from matched profiles."""
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
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.validation import argo_metrics as AM

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
ARGO = REPO_ROOT / "outputs" / "argo"
TAB = REPO_ROOT / B6["paths"]["tables"]
FIG = REPO_ROOT / B6["paths"]["figures"]
FIG.mkdir(parents=True, exist_ok=True)

COL = {"L0": "#B0651A", "L1": "#1F6FB0", "L2": "#128A6B", "GLORYS": "#8B3A9E"}
LBL = {"L0": "L0 climatology", "L1": "L1 pointwise", "L2": "L2 spatial embedding",
       "GLORYS": "GLORYS (training target)"}
CI_DEPTHS = [50, 75, 100, 125, 150, 200]


def main() -> int:
    df = pd.read_parquet(ARGO / "matched_profiles.parquet")
    print(f"matched profiles: {len(df):,}  floats: {df.wmo.nunique()}  "
          f"dates {df.date.min().date()}..{df.date.max().date()}")
    assert df.date.max() < pd.Timestamp("2024-01-01"), "HOLDOUT LEAK"

    # ---------------------------------------------------------- by depth
    bd = AM.metrics_by_depth(df, DEPTHS)
    bd.to_csv(TAB / "phase6c_argo_metrics_by_depth.csv", index=False)
    AM.group_summary(bd).to_csv(TAB / "phase6c_argo_depth_groups.csv", index=False)

    l2_l0 = AM.pairwise(df, DEPTHS, "L2", "L0")
    l2_l1 = AM.pairwise(df, DEPTHS, "L2", "L1")
    l1_l0 = AM.pairwise(df, DEPTHS, "L1", "L0")
    l2_gl = AM.pairwise(df, DEPTHS, "L2", "GLORYS")
    l2_l0.to_csv(TAB / "phase6c_argo_l2_vs_l0.csv", index=False)
    l2_l1.to_csv(TAB / "phase6c_argo_l2_vs_l1.csv", index=False)
    l2_gl.to_csv(TAB / "phase6c_argo_glorys_context.csv", index=False)

    pd.set_option("display.width", 220)
    piv = bd.pivot_table(index="depth_m", columns="model",
                         values=["rmse", "bias", "anomaly_correlation", "n"])
    print("\n=== RMSE vs Argo (degC) ===")
    show = pd.DataFrame({"depth_m": sorted(bd.depth_m.unique())}).set_index("depth_m")
    for m in AM.MODELS:
        s = bd[bd.model == m].set_index("depth_m")
        show[f"rmse_{m}"] = s["rmse"]
    show["n"] = bd[bd.model == "L2"].set_index("depth_m")["n"]
    show["L2_vs_L0_%"] = l2_l0.set_index("depth_m")["improvement_percent"]
    show["L2_vs_L1_%"] = l2_l1.set_index("depth_m")["improvement_percent"]
    print(show.round(4).to_string())

    print("\n=== bias (model minus Argo, degC) and anomaly correlation ===")
    b2 = pd.DataFrame({"depth_m": sorted(bd.depth_m.unique())}).set_index("depth_m")
    for m in AM.MODELS:
        s = bd[bd.model == m].set_index("depth_m")
        b2[f"bias_{m}"] = s["bias"]
    for m in ("L1", "L2", "GLORYS"):
        s = bd[bd.model == m].set_index("depth_m")
        b2[f"anomcorr_{m}"] = s["anomaly_correlation"]
    print(b2.round(4).to_string())

    # ------------------------------------------------------- bootstrap CI
    boot = []
    for d in CI_DEPTHS:
        for a, b in (("L2", "L0"), ("L2", "L1")):
            boot.append(AM.cluster_bootstrap_rmse_diff(df, d, a, b))
    bdf = pd.DataFrame(boot)
    bdf.to_csv(TAB / "phase6c_argo_bootstrap_ci.csv", index=False)
    print("\n=== paired float-cluster bootstrap, RMSE difference (negative = first is better) ===")
    print(bdf.round(4).to_string(index=False))

    # ------------------------------------------------------------ basins
    brows = []
    for name in AM.BASINS:
        msk = AM.basin_mask(df, name)
        if msk.sum() < AM.MIN_SAMPLES:
            print(f"  basin {name}: only {msk.sum()} profiles - suppressed")
            continue
        g = AM.metrics_by_depth(df, DEPTHS, subset=msk)
        g.insert(0, "basin", name)
        brows.append(g)
    if brows:
        pd.concat(brows, ignore_index=True).to_csv(
            TAB / "phase6c_argo_basin_summary.csv", index=False)

    # ----------------------------------------------------------- figures
    d_ax = show.index.values

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    for m in AM.MODELS:
        ax.plot(show[f"rmse_{m}"], d_ax, "o-", color=COL[m], label=LBL[m], lw=1.8, ms=4)
    ax.invert_yaxis(); ax.set_xlabel("RMSE vs Argo (degC)"); ax.set_ylabel("depth (m)")
    ax.set_title("Argo observational RMSE vs depth\n2022-2023, identical matched samples",
                 fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "argo_rmse_vs_depth.png", dpi=140); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    for m in AM.MODELS:
        ax.plot(b2[f"bias_{m}"], d_ax, "o-", color=COL[m], label=LBL[m], lw=1.8, ms=4)
    ax.axvline(0, color="k", lw=1.0)
    ax.invert_yaxis(); ax.set_xlabel("bias: model minus Argo (degC)"); ax.set_ylabel("depth (m)")
    ax.set_title("Argo observational bias vs depth", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "argo_bias_vs_depth.png", dpi=140); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    for m in ("L1", "L2", "GLORYS"):
        ax.plot(b2[f"anomcorr_{m}"], d_ax, "o-", color=COL[m], label=LBL[m], lw=1.8, ms=4)
    ax.axvline(0, color="k", lw=0.8, ls=":")
    ax.invert_yaxis(); ax.set_xlabel("anomaly correlation vs Argo")
    ax.set_ylabel("depth (m)")
    ax.set_title("Anomaly correlation vs depth\n(anomalies about the train-only L0 climatology)",
                 fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "argo_anomaly_corr_vs_depth.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.plot(show["L2_vs_L0_%"], d_ax, "s-", color=COL["L0"], label="L2 vs L0", lw=1.8, ms=4)
    ax.plot(show["L2_vs_L1_%"], d_ax, "d-", color=COL["L1"], label="L2 vs L1", lw=1.8, ms=4)
    ax.axvline(0, color="k", lw=1.0)
    ax.invert_yaxis(); ax.set_xlabel("RMSE improvement (%)"); ax.set_ylabel("depth (m)")
    ax.set_title("L2 improvement against Argo\n(negative = the other model wins)", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "argo_l2_improvement_vs_depth.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    ax.barh(d_ax, show["n"].values, height=18, color="#555555")
    ax.invert_yaxis(); ax.set_xlabel("matched observations"); ax.set_ylabel("depth (m)")
    ax.set_title("Matched Argo sample count vs depth\n(intersection of all four systems)",
                 fontsize=10)
    ax.grid(alpha=0.3, axis="x")
    for y, v in zip(d_ax, show["n"].values):
        ax.text(v, y, f" {int(v)}", va="center", fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "argo_sample_count_vs_depth.png", dpi=140)
    plt.close(fig)

    # example profiles: fixed seeded random draw among fully-supported profiles
    core = [d for d in DEPTHS if d not in (0,)]
    full = np.ones(len(df), dtype=bool)
    for d in core:
        full &= AM.accepted_mask(df, d)
    idx = np.where(full)[0]
    print(f"\nprofiles with every depth 5-1000 m matched: {idx.size}")
    if idx.size:
        pick = np.random.default_rng(20260905).choice(idx, size=min(4, idx.size),
                                                      replace=False)
        fig, axes = plt.subplots(1, len(pick), figsize=(4.0 * len(pick), 5.2), sharey=True)
        axes = np.atleast_1d(axes)
        for ax, i in zip(axes, pick):
            row = df.iloc[i]
            dd = [d for d in core]
            ax.plot([row[f"argo_pt_{d}m"] for d in dd], dd, "k-o", lw=2, ms=4, label="Argo")
            for m in AM.MODELS:
                ax.plot([row[f"{m}_{d}m"] for d in dd], dd, "-", color=COL[m],
                        lw=1.6, label=LBL[m])
            ax.set_title(f"{row['wmo']} c{int(row['cycle'])}\n"
                         f"{row['lat']:.2f}N {row['lon']:.2f}E  {row['date'].date()}",
                         fontsize=8)
            ax.set_xlabel("potential temperature (degC)")
            ax.grid(alpha=0.3); ax.tick_params(labelsize=8)
        axes[0].set_ylabel("depth (m)"); axes[0].invert_yaxis(); axes[0].legend(fontsize=7)
        fig.tight_layout(); fig.savefig(FIG / "argo_example_profiles.png", dpi=140)
        plt.close(fig)

    json.dump({"n_matched": int(len(df)), "n_floats": int(df.wmo.nunique()),
               "date_min": str(df.date.min().date()), "date_max": str(df.date.max().date()),
               "example_profile_rule": "seeded RNG 20260905, uniform among profiles "
                                       "matched at every depth 5-1000 m"},
              open(ARGO / "analysis_meta.json", "w"), indent=2)
    print("\nwrote tables and figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
