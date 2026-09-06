"""Phase 6C-B: input-availability and latency stress baseline for frozen L2.

No model is trained. The frozen L0/L1/L2 artefacts are loaded, hashed, used for
inference, and hashed again.

Development data only: the 2021 VALIDATION year. The 2024 Argo holdout is never
touched, and the frozen 2022-2024 benchmark is not used to choose anything.

Every operating mode is scored on an IDENTICAL population - the same days, the
same cells, the same targets - so a mode can never look better by predicting on
an easier subset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import torch
import yaml

from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.metrics import BASINS, DepthAccumulator, basin_of, group_summary
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.ml.stress import MODES, MODES_BY_NAME, coherent_sss_gap_mask, build_field
from oceanembed.ml.surface_climatology import SurfaceClimatology

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
TAB = REPO_ROOT / B6["paths"]["tables"]

MAX_AGE = 3          # so every mode shares the same first usable target day
SPLIT = "validation"

FALLBACK_MODE = "B_SSS_MISSING"
FALLBACK_POLICIES = ("zero_standardised", "persistence", "channel_climatology")


def sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    args = ap.parse_args()
    t_start = time.time()

    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    l2.eval()
    for p in l2.parameters():
        p.requires_grad_(False)
    sha_before = sha(ck["state_dict"])
    print(f"frozen L2: patch={ck['patch']} latent={ck['latent']} sha={sha_before[:16]}")

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta["fitted_on"] == "train"
    surf_clim = SurfaceClimatology.load(BASE / "phase6cb_surface_climatology.nc")
    assert surf_clim.meta["fitted_on"] == "train"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds = splits.open_split(SPLIT)
    tt = pd.DatetimeIndex(ds.time.values)
    assert not splits.contains_test_dates(tt), "LEAK: test dates in the stress cohort"
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
    r, c = smp.r, smp.c
    days = list(range(MAX_AGE, smp.n_days, args.stride))
    print(f"{SPLIT} cohort: targets {tt[days[0]].date()}..{tt[days[-1]].date()} "
          f"({len(days)} days) x {smp.n_cells} cells = {len(days)*smp.n_cells:,} samples")
    print("identical population for every operating mode\n")

    # runs: (label, mode, policy)
    runs = [(m.name, m, m.policy) for m in MODES]
    runs += [(f"{FALLBACK_MODE}::{p}", MODES_BY_NAME[FALLBACK_MODE], p)
             for p in FALLBACK_POLICIES if p != MODES_BY_NAME[FALLBACK_MODE].policy]

    acc = {lab: DepthAccumulator(DEPTHS) for lab, _, _ in runs}
    anom = {lab: DepthAccumulator(DEPTHS) for lab, _, _ in runs}
    acc["L0_climatology"] = DepthAccumulator(DEPTHS)
    basin_acc = {b: {lab: DepthAccumulator(DEPTHS) for lab, _, _ in runs} for b in BASINS}
    for b in BASINS:
        basin_acc[b]["L0_climatology"] = DepthAccumulator(DEPTHS)

    n_tot = 0
    for n, t in enumerate(days, 1):
        ctx = torch.from_numpy(smp.context(t))
        Y = np.empty((smp.n_cells, len(DEPTHS)), dtype="float64")
        for k, d in enumerate(DEPTHS):
            Y[:, k] = ds[f"temp_{d}m"].isel(time=t).values[r, c]
        M = smp.target_mask & np.isfinite(Y)
        cpred = clim.predict(tt[t:t + 1], r, c)[0].astype("float64")
        acc["L0_climatology"].update(cpred, Y, M)

        keep = coherent_sss_gap_mask(ds.sizes["lat"], ds.sizes["lon"], t)
        for lab, mode, policy in runs:
            sss_keep = keep if mode.name == "C_SSS_SPATIAL_GAPS" else None
            field = build_field(ds, t, fs, ck["patch"], mode, policy=policy,
                                surface_clim=surf_clim, sss_keep=sss_keep)
            with torch.no_grad():
                z = l2.embed_field(torch.from_numpy(field)[None])[0]
                p = ts.inverse_transform(
                    l2.forward_from_z(z[:, r, c].T, ctx).numpy().astype("float64"))
            acc[lab].update(p, Y, M)
            anom[lab].update(p - cpred, Y - cpred, M)
            for bname in BASINS:
                sel = basin_of(smp.cell_lat, smp.cell_lon, bname)
                if sel.any():
                    basin_acc[bname][lab].update(p[sel], Y[sel], M[sel])
        for bname in BASINS:
            sel = basin_of(smp.cell_lat, smp.cell_lon, bname)
            if sel.any():
                basin_acc[bname]["L0_climatology"].update(cpred[sel], Y[sel], M[sel])
        n_tot += smp.n_cells
        if n % 30 == 0:
            print(f"  day {n}/{len(days)}  ({time.time()-t_start:.0f}s)", flush=True)

    sha_after = sha(l2.state_dict())
    assert sha_after == sha_before, "FROZEN L2 CHANGED during the stress run"
    print(f"\nL2 unchanged: {sha_before[:16]} == {sha_after[:16]}")
    print(f"evaluated {n_tot:,} samples per mode in {(time.time()-t_start)/60:.1f} min")

    # ------------------------------------------------------------- tables
    parts = []
    for lab in list(acc):
        f = acc[lab].frame(lab)
        if lab in anom:
            a = anom[lab].frame(lab)[["depth_m", "rmse", "correlation"]].rename(
                columns={"rmse": "anomaly_rmse", "correlation": "anomaly_correlation"})
            f = f.merge(a, on="depth_m", how="left")
        else:
            f["anomaly_rmse"] = np.nan
            f["anomaly_correlation"] = np.nan
        parts.append(f)
    by_depth = pd.concat(parts, ignore_index=True).rename(columns={"model": "mode"})
    by_depth.to_csv(TAB / "phase6cb_input_stress_by_depth.csv", index=False)
    group_summary(by_depth.rename(columns={"mode": "model"})).to_csv(
        TAB / "phase6cb_input_stress_depth_groups.csv", index=False)

    base = acc["A_COMPLETE"].frame("A").set_index("depth_m")["rmse"]
    l0 = acc["L0_climatology"].frame("L0").set_index("depth_m")["rmse"]
    rows = []
    for lab in list(acc):
        s = acc[lab].frame(lab).set_index("depth_m")
        for d in DEPTHS:
            rows.append({
                "mode": lab, "depth_m": d, "rmse": float(s.loc[d, "rmse"]),
                "rmse_complete": float(base.loc[d]), "rmse_L0": float(l0.loc[d]),
                "degradation_pct": (s.loc[d, "rmse"] - base.loc[d]) / base.loc[d] * 100,
                "skill_over_L0_pct": (l0.loc[d] - s.loc[d, "rmse"]) / l0.loc[d] * 100,
                "beats_L0": bool(s.loc[d, "rmse"] < l0.loc[d]),
                "n": int(s.loc[d, "n"]),
            })
    skill = pd.DataFrame(rows)
    skill.to_csv(TAB / "phase6cb_skill_vs_climatology.csv", index=False)

    age_rows = []
    for lab, age in (("A_COMPLETE", 0), ("D_CURRENT_STALE_1D", 1),
                     ("E_CURRENT_STALE_2D", 2), ("F_CURRENT_STALE_3D", 3)):
        s = acc[lab].frame(lab).set_index("depth_m")
        an = anom[lab].frame(lab).set_index("depth_m")
        for d in DEPTHS:
            age_rows.append({"current_age_days": age, "depth_m": d,
                             "rmse": float(s.loc[d, "rmse"]),
                             "degradation_pct": (s.loc[d, "rmse"] - base.loc[d]) / base.loc[d] * 100,
                             "skill_over_L0_pct": (l0.loc[d] - s.loc[d, "rmse"]) / l0.loc[d] * 100,
                             "anomaly_correlation": float(an.loc[d, "correlation"])})
    pd.DataFrame(age_rows).to_csv(TAB / "phase6cb_current_age_sensitivity.csv", index=False)

    fb = []
    for lab in [f"{FALLBACK_MODE}", *[f"{FALLBACK_MODE}::{p}" for p in FALLBACK_POLICIES
                                      if p != MODES_BY_NAME[FALLBACK_MODE].policy]]:
        s = acc[lab].frame(lab).set_index("depth_m")
        pol = lab.split("::")[1] if "::" in lab else MODES_BY_NAME[FALLBACK_MODE].policy
        for d in DEPTHS:
            fb.append({"policy": pol, "depth_m": d, "rmse": float(s.loc[d, "rmse"]),
                       "rmse_L0": float(l0.loc[d]), "rmse_complete": float(base.loc[d]),
                       "beats_L0": bool(s.loc[d, "rmse"] < l0.loc[d])})
    for d in DEPTHS:
        fb.append({"policy": "L0_climatology", "depth_m": d, "rmse": float(l0.loc[d]),
                   "rmse_L0": float(l0.loc[d]), "rmse_complete": float(base.loc[d]),
                   "beats_L0": False})
    pd.DataFrame(fb).to_csv(TAB / "phase6cb_simple_fallbacks.csv", index=False)

    brows = []
    for bname in BASINS:
        for lab in list(basin_acc[bname]):
            f = basin_acc[bname][lab].frame(lab).rename(columns={"model": "mode"})
            f.insert(0, "basin", bname)
            brows.append(f)
    pd.concat(brows, ignore_index=True).to_csv(
        TAB / "phase6cb_basin_sensitivity.csv", index=False)

    pd.set_option("display.width", 240)
    piv = skill.pivot_table(index="depth_m", columns="mode", values="degradation_pct")
    order = [m.name for m in MODES]
    print("\n=== DEGRADATION vs COMPLETE (% RMSE increase) ===")
    print(piv[order].round(2).to_string())
    print("\n=== 100 m summary ===")
    s100 = skill[skill.depth_m == 100].set_index("mode")
    print(s100[["rmse", "degradation_pct", "skill_over_L0_pct", "beats_L0"]].round(3).to_string())

    json.dump({"split": SPLIT, "n_days": len(days), "n_cells": int(smp.n_cells),
               "samples_per_mode": int(n_tot), "max_age_days": MAX_AGE,
               "l2_sha256_before": sha_before, "l2_sha256_after": sha_after,
               "first_target": str(tt[days[0]].date()), "last_target": str(tt[days[-1]].date()),
               "modes": [m.name for m in MODES],
               "fallback_policies": list(FALLBACK_POLICIES),
               "heldout_2024_argo": "untouched"},
              open(TAB / "phase6cb_stress_meta.json", "w"), indent=2)
    print(f"\ntotal runtime {(time.time()-t_start)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
