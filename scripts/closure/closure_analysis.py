"""Apply the pre-registered gates and build the closure summary tables.

Nothing here chooses a threshold: every number compared against comes from
`outputs/architecture_closure/PREREGISTRATION.md`, which was written before any
closure model was trained. The gate result is recorded whichever way it falls.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd

from oceanembed.config import REPO_ROOT

TAB = REPO_ROOT / "outputs" / "tables" / "architecture_closure"
OUT = REPO_ROOT / "outputs" / "architecture_closure"

UPPER_300 = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300]
THERMOCLINE_KEY = [75, 100, 125, 150, 200]
DEEP = [500, 700, 1000]
BANDS = {"0-50 m": [0, 5, 10, 20, 30, 50],
         "75-150 m": [75, 100, 125, 150],
         "200-300 m": [200, 300],
         "500-1000 m": [500, 700, 1000]}

# pre-registered, section 5.3
GATE = {"upper300_rmse_improve_pct": 1.0,
        "anomaly_corr_min_improved_depths": 8,
        "anomaly_corr_max_degradation": 0.01,
        "thermocline_max_degradation_pct": 1.0,
        "deep_max_degradation_pct": 1.0,
        "max_new_abs_bias_degC": 0.10}


def rmse_of(d: pd.DataFrame, model: str) -> pd.Series:
    return d[d.model == model].set_index("depth_m")["rmse"]


def col_of(d: pd.DataFrame, model: str, col: str) -> pd.Series:
    return d[d.model == model].set_index("depth_m")[col]


def weighted_rmse(d: pd.DataFrame, model: str, depths) -> float:
    s = d[(d.model == model) & (d.depth_m.isin(depths))]
    w = s["n"].to_numpy(dtype="float64")
    return float(np.sqrt(np.average(s["rmse"] ** 2, weights=w)))


# --------------------------------------------------------------------- C
def residual_gate(tag: str, candidate: str) -> dict:
    d = pd.read_csv(TAB / f"{tag}_metrics_by_depth.csv")
    models = set(d.model)
    if candidate not in models or "FROZEN_L2" not in models:
        raise SystemExit(f"need both {candidate} and FROZEN_L2 in {tag}")

    l2_r, ca_r = rmse_of(d, "FROZEN_L2"), rmse_of(d, candidate)
    l2_a = col_of(d, "FROZEN_L2", "anomaly_correlation")
    ca_a = col_of(d, candidate, "anomaly_correlation")
    l2_b, ca_b = col_of(d, "FROZEN_L2", "bias"), col_of(d, candidate, "bias")

    up_l2 = weighted_rmse(d, "FROZEN_L2", UPPER_300)
    up_ca = weighted_rmse(d, candidate, UPPER_300)
    up_gain = (up_l2 - up_ca) / up_l2 * 100.0

    improved = [int(k) for k in UPPER_300 if ca_a[k] > l2_a[k]]
    degraded_amt = {int(k): float(l2_a[k] - ca_a[k]) for k in UPPER_300}
    worst_anom_loss = max(degraded_amt.values())
    c1 = (up_gain >= GATE["upper300_rmse_improve_pct"]) or (
        len(improved) >= GATE["anomaly_corr_min_improved_depths"]
        and worst_anom_loss <= GATE["anomaly_corr_max_degradation"])

    therm = {int(k): float((ca_r[k] - l2_r[k]) / l2_r[k] * 100.0)
             for k in THERMOCLINE_KEY}
    c2 = all(v <= GATE["thermocline_max_degradation_pct"] for v in therm.values())

    deep_l2 = weighted_rmse(d, "FROZEN_L2", DEEP)
    deep_ca = weighted_rmse(d, candidate, DEEP)
    deep_change = (deep_ca - deep_l2) / deep_l2 * 100.0
    c3 = deep_change <= GATE["deep_max_degradation_pct"]

    bias_growth = {int(k): float(abs(ca_b[k]) - abs(l2_b[k])) for k in ca_b.index}
    c4 = max(bias_growth.values()) <= GATE["max_new_abs_bias_degC"]

    res = {
        "candidate": candidate, "split": "validation_2021",
        "preregistered_gate": GATE,
        "criterion_1_upper300_or_anomaly": {
            "upper300_rmse_frozen_l2": up_l2, "upper300_rmse_candidate": up_ca,
            "upper300_improvement_percent": up_gain,
            "anomaly_corr_improved_depths": improved,
            "n_improved_of_11": len(improved),
            "worst_anomaly_corr_loss": worst_anom_loss,
            "passed": bool(c1)},
        "criterion_2_thermocline": {"rmse_change_percent": therm, "passed": bool(c2)},
        "criterion_3_deep": {"rmse_frozen_l2": deep_l2, "rmse_candidate": deep_ca,
                             "change_percent": deep_change, "passed": bool(c3)},
        "criterion_4_no_new_bias": {
            "max_abs_bias_growth_degC": max(bias_growth.values()),
            "worst_depth_m": int(max(bias_growth, key=bias_growth.get)),
            "per_depth": bias_growth, "passed": bool(c4)},
        "all_passed": bool(c1 and c2 and c3 and c4),
    }
    res["decision"] = ("ADVANCE_TO_ARGO_CONFIRMATION" if res["all_passed"]
                       else "REJECTED_AT_VALIDATION_GATE")
    json.dump(res, open(OUT / "residual_gate.json", "w"), indent=2)

    cmp = pd.DataFrame({
        "depth_m": l2_r.index,
        "rmse_L0": rmse_of(d, "L0_climatology").reindex(l2_r.index).values,
        "rmse_FROZEN_L2": l2_r.values, f"rmse_{candidate}": ca_r.values,
        "rmse_change_percent": ((ca_r - l2_r) / l2_r * 100.0).values,
        "anomaly_corr_FROZEN_L2": l2_a.reindex(l2_r.index).values,
        f"anomaly_corr_{candidate}": ca_a.reindex(l2_r.index).values,
        "anomaly_corr_change": (ca_a - l2_a).reindex(l2_r.index).values,
        "bias_FROZEN_L2": l2_b.reindex(l2_r.index).values,
        f"bias_{candidate}": ca_b.reindex(l2_r.index).values,
    })
    cmp.to_csv(TAB / "residual_metrics_validation.csv", index=False)

    print(f"\n=== Experiment C gate: {candidate} ===")
    print(cmp.round(4).to_string(index=False))
    for k in ("criterion_1_upper300_or_anomaly", "criterion_2_thermocline",
              "criterion_3_deep", "criterion_4_no_new_bias"):
        print(f"  {k}: {'PASS' if res[k]['passed'] else 'FAIL'}")
    print(f"  DECISION: {res['decision']}")
    return res


# --------------------------------------------------------------------- D
def ablation_summary(tag: str) -> pd.DataFrame:
    d = pd.read_csv(TAB / f"{tag}_metrics_by_depth.csv")
    d.to_csv(TAB / "channel_ablation_metrics.csv", index=False)
    ctrl = rmse_of(d, "D_CONTROL_ALL")
    ctrl_a = col_of(d, "D_CONTROL_ALL", "anomaly_correlation")
    groups = sorted(m.replace("D_MINUS_", "") for m in set(d.model)
                    if m.startswith("D_MINUS_"))

    rows = []
    for g in groups:
        m = f"D_MINUS_{g}"
        r, a = rmse_of(d, m), col_of(d, m, "anomaly_correlation")
        for dep in ctrl.index:
            rows.append({"group": g, "depth_m": int(dep),
                         "rmse_control": float(ctrl[dep]), "rmse_ablated": float(r[dep]),
                         "rmse_change_degC": float(r[dep] - ctrl[dep]),
                         "rmse_change_percent": float((r[dep] - ctrl[dep]) / ctrl[dep] * 100),
                         "anomaly_corr_control": float(ctrl_a[dep]),
                         "anomaly_corr_ablated": float(a[dep]),
                         "anomaly_corr_change": float(a[dep] - ctrl_a[dep]),
                         "bias_ablated": float(col_of(d, m, "bias")[dep]),
                         "bias_control": float(col_of(d, "D_CONTROL_ALL", "bias")[dep])})
    per_depth = pd.DataFrame(rows)
    per_depth.to_csv(TAB / "channel_ablation_by_depth.csv", index=False)

    brows = []
    for g in groups:
        m = f"D_MINUS_{g}"
        for band, deps in BANDS.items():
            cr = weighted_rmse(d, "D_CONTROL_ALL", deps)
            ar = weighted_rmse(d, m, deps)
            sub = per_depth[(per_depth.group == g) & (per_depth.depth_m.isin(deps))]
            brows.append({"group": g, "band": band,
                          "depths_m": ",".join(map(str, deps)),
                          "rmse_control": cr, "rmse_ablated": ar,
                          "rmse_change_degC": ar - cr,
                          "rmse_change_percent": (ar - cr) / cr * 100.0,
                          "mean_anomaly_corr_change": float(
                              sub["anomaly_corr_change"].mean())})
    bands = pd.DataFrame(brows)
    bands.to_csv(TAB / "channel_ablation_depth_groups.csv", index=False)

    print(f"\n=== Experiment D: impact by depth band (% RMSE vs control) ===")
    print(bands.pivot(index="group", columns="band",
                      values="rmse_change_percent").round(3).to_string())
    return bands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--residual-tag", default=None)
    ap.add_argument("--candidate", default="L2_RESIDUAL_s20260905")
    ap.add_argument("--ablation-tag", default=None)
    args = ap.parse_args()
    if args.residual_tag:
        residual_gate(args.residual_tag, args.candidate)
    if args.ablation_tag:
        ablation_summary(args.ablation_tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
