"""Phase 6C-B figures: input availability and latency stress."""
from __future__ import annotations

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
DEPTHS = B6["targets"]["depths_m"]
TAB = REPO_ROOT / B6["paths"]["tables"]
FIG = REPO_ROOT / B6["paths"]["figures"]
FIG.mkdir(parents=True, exist_ok=True)

MAIN = ["A_COMPLETE", "B_SSS_MISSING", "C_SSS_SPATIAL_GAPS", "E_CURRENT_STALE_2D",
        "I_SSS_MISSING_CURRENT_STALE_2D", "J_SSS_MISSING_JOINT_MASK"]
COL = {"A_COMPLETE": "#128A6B", "B_SSS_MISSING": "#C0392B",
       "C_SSS_SPATIAL_GAPS": "#E08A1E", "E_CURRENT_STALE_2D": "#1F6FB0",
       "I_SSS_MISSING_CURRENT_STALE_2D": "#8B3A9E",
       "J_SSS_MISSING_JOINT_MASK": "#444444", "L0_climatology": "#B0651A"}
LBL = {"A_COMPLETE": "complete inputs", "B_SSS_MISSING": "SSS missing (zero-fill)",
       "C_SSS_SPATIAL_GAPS": "SSS coherent gaps", "E_CURRENT_STALE_2D": "currents t-2",
       "I_SSS_MISSING_CURRENT_STALE_2D": "SSS missing + currents t-2",
       "J_SSS_MISSING_JOINT_MASK": "SSS missing, joint-mask path",
       "L0_climatology": "L0 climatology"}


def main() -> int:
    sk = pd.read_csv(TAB / "phase6cb_skill_vs_climatology.csv")
    d = np.array(DEPTHS)

    # 1 RMSE vs depth
    fig, ax = plt.subplots(figsize=(6.0, 5.8))
    for m in MAIN + ["L0_climatology"]:
        s = sk[sk["mode"] == m].set_index("depth_m").loc[DEPTHS]
        ax.plot(s.rmse, d, "o-", color=COL[m], label=LBL[m], lw=1.8, ms=4)
    ax.invert_yaxis(); ax.set_xlabel("RMSE vs GLORYS (degC)"); ax.set_ylabel("depth (m)")
    ax.set_title("Input stress: RMSE vs depth\n2021 validation, identical population",
                 fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "input_stress_rmse_vs_depth.png", dpi=140)
    plt.close(fig)

    # 2 skill over climatology
    fig, ax = plt.subplots(figsize=(6.0, 5.8))
    for m in MAIN:
        s = sk[sk["mode"] == m].set_index("depth_m").loc[DEPTHS]
        ax.plot(s.skill_over_L0_pct, d, "o-", color=COL[m], label=LBL[m], lw=1.8, ms=4)
    ax.axvline(0, color="k", lw=1.2)
    ax.invert_yaxis(); ax.set_xlabel("skill over climatology (%)"); ax.set_ylabel("depth (m)")
    ax.set_title("Where climatology becomes safer\n(left of the line = use L0)", fontsize=10)
    ax.set_xlim(-60, 45)
    ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "input_stress_skill_vs_depth.png", dpi=140)
    plt.close(fig)

    # 3 degradation heatmap
    modes = [m for m in sk["mode"].unique() if m not in ("L0_climatology",)
             and "::" not in m]
    piv = sk[sk["mode"].isin(modes)].pivot_table(index="mode", columns="depth_m",
                                                 values="degradation_pct").loc[modes, DEPTHS]
    fig, ax = plt.subplots(figsize=(10.5, 4.4))
    vmax = float(np.nanpercentile(np.abs(piv.values), 92))
    im = ax.imshow(piv.values, aspect="auto", cmap="RdYlGn_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(DEPTHS))); ax.set_xticklabels(DEPTHS, fontsize=8)
    ax.set_yticks(range(len(modes)))
    ax.set_yticklabels([m.replace("_", " ") for m in modes], fontsize=8)
    ax.set_xlabel("depth (m)")
    ax.set_title("RMSE degradation vs complete inputs (%)\n"
                 "colour saturates at the 92nd percentile so the joint-mask row "
                 "does not swamp the rest", fontsize=10)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6.5,
                    color="white" if abs(v) > vmax * 0.6 else "black")
    plt.colorbar(im, ax=ax, fraction=0.02, label="% RMSE increase")
    fig.tight_layout(); fig.savefig(FIG / "input_stress_heatmap.png", dpi=140)
    plt.close(fig)

    # 4 current age sensitivity
    ages = pd.read_csv(TAB / "phase6cb_current_age_sensitivity.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.4))
    focus = [50, 75, 100, 125, 150, 200]
    for dep in focus:
        s = ages[ages.depth_m == dep].sort_values("current_age_days")
        axes[0].plot(s.current_age_days, s.degradation_pct, "o-", label=f"{dep} m", lw=1.8)
        axes[1].plot(s.current_age_days, s.skill_over_L0_pct, "o-", label=f"{dep} m", lw=1.8)
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].set_xlabel("age of surface currents (days)")
    axes[0].set_ylabel("RMSE degradation (%)")
    axes[0].set_title("Current staleness: cost", fontsize=10)
    axes[1].set_xlabel("age of surface currents (days)")
    axes[1].set_ylabel("skill over climatology (%)")
    axes[1].set_title("Current staleness: retained skill", fontsize=10)
    for a in axes:
        a.set_xticks([0, 1, 2, 3]); a.grid(alpha=0.3); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "current_age_sensitivity.png", dpi=140)
    plt.close(fig)

    # 5 100 m operational summary
    s100 = sk[(sk.depth_m == 100) & (~sk["mode"].isin(["L0_climatology"]))]
    s100 = s100.sort_values("degradation_pct")
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    cols = ["#C0392B" if not b else "#128A6B" for b in s100.beats_L0]
    ax.barh(range(len(s100)), s100.degradation_pct, color=cols)
    ax.set_yticks(range(len(s100)))
    ax.set_yticklabels([m.replace("_", " ") for m in s100["mode"]], fontsize=8)
    ax.axvline(0, color="k", lw=1.0)
    ax.set_xlabel("RMSE degradation at 100 m vs complete inputs (%)")
    ax.set_title("100 m operational sensitivity\ngreen = still beats climatology, "
                 "red = climatology is safer", fontsize=10)
    ax.grid(alpha=0.3, axis="x")
    for i, (v, b) in enumerate(zip(s100.degradation_pct, s100.beats_L0)):
        ax.text(v, i, f" {v:+.1f}%", va="center", fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "input_stress_100m_summary.png", dpi=140)
    plt.close(fig)

    # 6 fallbacks
    fb = pd.read_csv(TAB / "phase6cb_simple_fallbacks.csv")
    fig, ax = plt.subplots(figsize=(6.0, 5.8))
    comp = sk[sk["mode"] == "A_COMPLETE"].set_index("depth_m").loc[DEPTHS]
    ax.plot(comp.rmse, d, "k-", lw=2.4, label="complete inputs (reference)")
    styles = {"persistence": ("#1F6FB0", "-"), "channel_climatology": ("#128A6B", "-"),
              "zero_standardised": ("#C0392B", "--"), "L0_climatology": ("#B0651A", ":")}
    for pol, (c, ls) in styles.items():
        s = fb[fb.policy == pol].set_index("depth_m").loc[DEPTHS]
        ax.plot(s.rmse, d, ls, color=c, lw=1.8, label=pol)
    ax.invert_yaxis(); ax.set_xlabel("RMSE vs GLORYS (degC)"); ax.set_ylabel("depth (m)")
    ax.set_title("Simple fallbacks under a total SSS outage\n"
                 "all use train-only information", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "input_stress_fallbacks.png", dpi=140)
    plt.close(fig)

    # 7 basin comparison
    bs = pd.read_csv(TAB / "phase6cb_basin_sensitivity.csv")
    rows = []
    for b in ("arabian_sea", "bay_of_bengal"):
        base = bs[(bs.basin == b) & (bs["mode"] == "A_COMPLETE")].set_index("depth_m")
        for m in ("B_SSS_MISSING", "C_SSS_SPATIAL_GAPS", "E_CURRENT_STALE_2D"):
            s = bs[(bs.basin == b) & (bs["mode"] == m)].set_index("depth_m")
            for dep in DEPTHS:
                if dep in s.index and dep in base.index and base.loc[dep, "n"] > 0:
                    rows.append({"basin": b, "mode": m, "depth_m": dep,
                                 "degradation_pct": (s.loc[dep, "rmse"] - base.loc[dep, "rmse"])
                                 / base.loc[dep, "rmse"] * 100,
                                 "n": int(base.loc[dep, "n"])})
    bd = pd.DataFrame(rows)
    bd.to_csv(TAB / "phase6cb_basin_degradation.csv", index=False)
    fig, ax = plt.subplots(figsize=(6.0, 5.8))
    for b, ls in (("arabian_sea", "-"), ("bay_of_bengal", "--")):
        s = bd[(bd.basin == b) & (bd["mode"] == "B_SSS_MISSING")].sort_values("depth_m")
        ax.plot(s.degradation_pct, s.depth_m, ls, marker="o", lw=1.8, ms=4,
                label=f"{b.replace('_',' ')} - SSS missing")
    ax.invert_yaxis(); ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("RMSE degradation (%)"); ax.set_ylabel("depth (m)")
    ax.set_title("Basin sensitivity to a total SSS outage", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "input_stress_basin.png", dpi=140)
    plt.close(fig)

    print("wrote 7 figures + phase6cb_basin_degradation.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
