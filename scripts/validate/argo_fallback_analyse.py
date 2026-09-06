"""Phase 6C-C analysis: fallback metrics, bootstrap and figures against Argo."""
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

MODES = ["COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
         "CURRENT_STALE_1D", "CURRENT_STALE_2D", "CURRENT_STALE_3D",
         "WIND_STALE_1D", "SLA_STALE_1D", "SSS_ABSENT_PERSIST_CURRENT_STALE_2D"]
ALL = MODES + ["L0"]
KEY = [50, 75, 100, 125, 150, 200]
COL = {"COMPLETE": "#128A6B", "SSS_ABSENT_PERSIST": "#1F6FB0",
       "SSS_ABSENT_CLIM": "#7BAF3A", "CURRENT_STALE_2D": "#E08A1E",
       "CURRENT_STALE_3D": "#C0392B", "WIND_STALE_1D": "#8B3A9E",
       "SLA_STALE_1D": "#5D6D7E", "CURRENT_STALE_1D": "#48C9B0",
       "SSS_ABSENT_PERSIST_CURRENT_STALE_2D": "#884EA0", "L0": "#B0651A"}


def mask_all(df, depth):
    """Argo supports this depth AND every mode produced a finite value."""
    m = df[f"argo_sup_{depth}m"].to_numpy(dtype=bool).copy()
    m &= np.isfinite(df[f"argo_pt_{depth}m"].to_numpy("float64"))
    for lab in ALL:
        m &= np.isfinite(df[f"{lab}_{depth}m"].to_numpy("float64"))
    return m


def stats(pred, obs, clim):
    d = pred - obs
    out = {"n": int(d.size), "rmse": float(np.sqrt(np.mean(d ** 2))),
           "mae": float(np.mean(np.abs(d))), "bias": float(np.mean(d))}
    pa, oa = pred - clim, obs - clim
    out["anomaly_correlation"] = (float(np.corrcoef(pa, oa)[0, 1])
                                  if d.size > 2 and np.std(pa) > 0 and np.std(oa) > 0
                                  else np.nan)
    return out


def boot(df, depth, a, b, n_boot=1000, seed=20260905):
    m = mask_all(df, depth)
    if m.sum() < 30:
        return None
    s = df.loc[m]
    obs = s[f"argo_pt_{depth}m"].to_numpy("float64")
    pa = s[f"{a}_{depth}m"].to_numpy("float64")
    pb = s[f"{b}_{depth}m"].to_numpy("float64")
    keys = s["wmo"].to_numpy()
    uniq = np.unique(keys)
    idx = {k: np.where(keys == k)[0] for k in uniq}
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        sel = np.concatenate([idx[k] for k in pick])
        diffs[i] = (np.sqrt(np.mean((pa[sel] - obs[sel]) ** 2))
                    - np.sqrt(np.mean((pb[sel] - obs[sel]) ** 2)))
    point = float(np.sqrt(np.mean((pa - obs) ** 2)) - np.sqrt(np.mean((pb - obs) ** 2)))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"depth_m": depth, "comparison": f"{a} minus {b}", "n": int(m.sum()),
            "n_floats": int(uniq.size), "rmse_difference": point,
            "ci_lo": float(lo), "ci_hi": float(hi),
            "significant": bool(hi < 0 or lo > 0),
            "within_noise": bool(lo <= 0 <= hi)}


def main() -> int:
    df = pd.read_parquet(ARGO / "fallback_replay.parquet")
    df["date"] = pd.to_datetime(df["date"])
    assert df.date.max() < pd.Timestamp("2024-01-01"), "HOLDOUT LEAK"
    print(f"replay matches: {len(df):,}  floats: {df.wmo.nunique()}  "
          f"dates {df.date.min().date()}..{df.date.max().date()}")

    rows = []
    for d in DEPTHS:
        m = mask_all(df, d)
        if m.sum() == 0:
            continue
        obs = df.loc[m, f"argo_pt_{d}m"].to_numpy("float64")
        clim = df.loc[m, f"L0_{d}m"].to_numpy("float64")
        for lab in ALL:
            pred = df.loc[m, f"{lab}_{d}m"].to_numpy("float64")
            rows.append({"mode": lab, "depth_m": d,
                         **stats(pred, obs, clim if lab != "L0" else clim)})
    bd = pd.DataFrame(rows)
    bd.to_csv(TAB / "phase6cc_argo_fallback_metrics_by_depth.csv", index=False)

    piv = bd.pivot_table(index="depth_m", columns="mode", values="rmse")
    comp, l0 = piv["COMPLETE"], piv["L0"]
    cmpr = []
    for lab in MODES:
        for d in DEPTHS:
            if d not in piv.index:
                continue
            cmpr.append({"mode": lab, "depth_m": d, "rmse": float(piv.loc[d, lab]),
                         "rmse_complete": float(comp.loc[d]), "rmse_L0": float(l0.loc[d]),
                         "degradation_vs_complete_pct":
                             (piv.loc[d, lab] - comp.loc[d]) / comp.loc[d] * 100,
                         "skill_over_L0_pct": (l0.loc[d] - piv.loc[d, lab]) / l0.loc[d] * 100,
                         "beats_L0": bool(piv.loc[d, lab] < l0.loc[d]),
                         "n": int(bd[(bd["mode"] == lab) & (bd.depth_m == d)].n.iloc[0])})
    cm = pd.DataFrame(cmpr)
    cm.to_csv(TAB / "phase6cc_fallback_vs_complete.csv", index=False)
    cm.to_csv(TAB / "phase6cc_fallback_vs_climatology.csv", index=False)

    grows = []
    for g, deps in AM.DEPTH_GROUPS.items():
        sub = bd[bd.depth_m.isin(deps) & (bd.n > 0)]
        for lab, s in sub.groupby("mode"):
            w = s["n"].to_numpy("float64")
            grows.append({"group": g, "mode": lab, "n": int(w.sum()),
                          "rmse": float(np.sqrt(np.average(s["rmse"] ** 2, weights=w))),
                          "bias": float(np.average(s["bias"], weights=w))})
    pd.DataFrame(grows).to_csv(TAB / "phase6cc_argo_fallback_depth_groups.csv", index=False)

    brows = [b for d in KEY for lab in MODES if lab != "COMPLETE"
             for b in [boot(df, d, lab, "COMPLETE")] if b]
    bdf = pd.DataFrame(brows)
    bdf.to_csv(TAB / "phase6cc_fallback_bootstrap.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print("\n=== RMSE vs Argo (degC) ===")
    print(piv[ALL].round(4).to_string())
    print("\n=== degradation vs COMPLETE (%) ===")
    dg = cm.pivot_table(index="depth_m", columns="mode", values="degradation_vs_complete_pct")
    print(dg[[m for m in MODES if m != "COMPLETE"]].round(3).to_string())
    print("\n=== bootstrap vs COMPLETE at key depths (negative = fallback better) ===")
    print(bdf.round(4).to_string(index=False))

    # ------------------------------------------------------------- figures
    d_ax = np.array(sorted(piv.index))
    fig, ax = plt.subplots(figsize=(6.2, 5.8))
    for lab in ["L0", "COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
                "CURRENT_STALE_3D", "SSS_ABSENT_PERSIST_CURRENT_STALE_2D"]:
        ax.plot(piv.loc[d_ax, lab], d_ax, "o-", color=COL[lab], label=lab, lw=1.8, ms=4)
    ax.invert_yaxis(); ax.set_xlabel("RMSE vs Argo (degC)"); ax.set_ylabel("depth (m)")
    ax.set_title("Fallback policies against Argo, 2022-2023\nidentical matched samples",
                 fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "phase6cc_argo_fallback_rmse.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.2, 5.8))
    for lab in [m for m in MODES if m != "COMPLETE"]:
        ax.plot(dg.loc[d_ax, lab], d_ax, "o-", color=COL[lab], label=lab, lw=1.6, ms=3.5)
    ax.axvline(0, color="k", lw=1.2)
    ax.invert_yaxis(); ax.set_xlabel("degradation vs COMPLETE (%)")
    ax.set_ylabel("depth (m)")
    ax.set_title("Observational cost of each fallback\n(right of the line = worse)",
                 fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "phase6cc_argo_fallback_degradation.png", dpi=140)
    plt.close(fig)

    s100 = cm[cm.depth_m == 100].sort_values("degradation_vs_complete_pct")
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    cols = ["#128A6B" if b else "#C0392B" for b in s100.beats_L0]
    ax.barh(range(len(s100)), s100.degradation_vs_complete_pct, color=cols)
    ax.set_yticks(range(len(s100)))
    ax.set_yticklabels([m.replace("_", " ") for m in s100["mode"]], fontsize=8)
    ax.axvline(0, color="k", lw=1.0)
    ax.set_xlabel("degradation at 100 m vs COMPLETE (%)")
    ax.set_title("100 m fallback summary against Argo\ngreen = still beats climatology",
                 fontsize=10)
    ax.grid(alpha=0.3, axis="x")
    for i, v in enumerate(s100.degradation_vs_complete_pct):
        ax.text(v, i, f" {v:+.2f}%", va="center", fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "phase6cc_100m_fallback_summary.png", dpi=140)
    plt.close(fig)

    sk = cm.pivot_table(index="depth_m", columns="mode", values="skill_over_L0_pct")
    fig, ax = plt.subplots(figsize=(6.2, 5.8))
    for lab in MODES:
        ax.plot(sk.loc[d_ax, lab], d_ax, "o-", color=COL[lab], label=lab, lw=1.6, ms=3.5)
    ax.axvline(0, color="k", lw=1.2)
    ax.invert_yaxis(); ax.set_xlabel("skill over L0 climatology (%)")
    ax.set_ylabel("depth (m)")
    ax.set_title("Retained observational skill over climatology", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "phase6cc_fallback_skill_vs_depth.png", dpi=140)
    plt.close(fig)

    json.dump({"n_matches": int(len(df)), "n_floats": int(df.wmo.nunique()),
               "modes": ALL, "key_depths": KEY},
              open(ARGO / "fallback_analysis_meta.json", "w"), indent=2)
    print("\nwrote tables and 4 figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
