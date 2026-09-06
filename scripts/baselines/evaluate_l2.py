"""Evaluate L0, L1 and L2 on one split, on IDENTICAL samples.

All three predictions are produced inside the same per-day loop from the same
valid cells, so any L2-vs-L1 difference is the model and not a sampling
difference.
"""
from __future__ import annotations

import argparse
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
from oceanembed.ml.features import SURFACE, cyclic_doy
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.metrics import BASINS, DepthAccumulator, basin_of, group_summary
from oceanembed.ml.model import PointwiseMLP
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
TAB = REPO_ROOT / CFG["paths"]["tables"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--l2-tag", default="final")
    ap.add_argument("--suffix", default=None)
    args = ap.parse_args()
    if args.split == "test" and not args.allow_test:
        raise SystemExit("Refusing: test split is LOCKED. Use --allow-test only "
                         "for the single frozen evaluation.")
    sfx = args.suffix if args.suffix is not None else ("_test" if args.split == "test" else "")

    t0 = time.time()
    ds = splits.open_split(args.split, allow_test=args.allow_test)
    tt = pd.DatetimeIndex(ds.time.values)
    print(f"SPLIT {args.split}: {tt[0].date()} .. {tt[-1].date()} ({len(tt)} days)")

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta.get("fitted_on") == "train"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ck1 = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    l1 = PointwiseMLP(ck1["n_features"], tuple(ck1["hidden"]), ck1["n_out"])
    l1.load_state_dict(ck1["state_dict"])
    l1.eval()

    ck2 = torch.load(MODELS / f"phase6b_l2_{args.l2_tag}.pt", map_location="cpu",
                     weights_only=False)
    l2 = L2EmbeddingModel(latent=ck2["latent"], patch=ck2["patch"])
    l2.load_state_dict(ck2["state_dict"])
    l2.eval()
    print(f"L1 epoch {ck1['epoch']} | L2 tag={args.l2_tag} patch={ck2['patch']} "
          f"latent={ck2['latent']} epoch {ck2['epoch']}")

    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck2["patch"])
    r, c = smp.r, smp.c
    names = ("L0_climatology", "L1_mlp", "L2_embedding")
    acc = {k: DepthAccumulator(DEPTHS) for k in names}
    anom = {k: DepthAccumulator(DEPTHS) for k in ("L1_mlp", "L2_embedding")}
    basin_acc = {b: {k: DepthAccumulator(DEPTHS) for k in names} for b in BASINS}
    n_tot = 0

    for t, (field, ctx, Yz, M, Y) in smp.days():
        cpred = clim.predict(smp.times[t:t + 1], r, c)[0].astype("float64")

        surf = np.column_stack([ds[v].isel(time=t).values[r, c] for v in SURFACE])
        s, cc = cyclic_doy(smp.times[t:t + 1])
        X1 = np.column_stack([surf, smp.cell_lat, smp.cell_lon,
                              np.full(smp.n_cells, s[0]), np.full(smp.n_cells, cc[0])])
        ok = np.isfinite(X1).all(axis=1)
        with torch.no_grad():
            p1 = np.full((smp.n_cells, len(DEPTHS)), np.nan)
            if ok.any():
                p1[ok] = ts.inverse_transform(
                    l1(torch.from_numpy(fs.transform(X1[ok]).astype("float32"))).numpy())
            z = l2.embed_field(torch.from_numpy(field)[None])[0]
            p2 = ts.inverse_transform(
                l2.forward_from_z(z[:, r, c].T,
                                  torch.from_numpy(ctx)).numpy().astype("float64"))

        acc["L0_climatology"].update(cpred, Y, M)
        acc["L1_mlp"].update(p1, Y, M)
        acc["L2_embedding"].update(p2, Y, M)
        anom["L1_mlp"].update(p1 - cpred, Y - cpred, M)
        anom["L2_embedding"].update(p2 - cpred, Y - cpred, M)
        for b in BASINS:
            sel = basin_of(smp.cell_lat, smp.cell_lon, b)
            if sel.any():
                basin_acc[b]["L0_climatology"].update(cpred[sel], Y[sel], M[sel])
                basin_acc[b]["L1_mlp"].update(p1[sel], Y[sel], M[sel])
                basin_acc[b]["L2_embedding"].update(p2[sel], Y[sel], M[sel])
        n_tot += smp.n_cells
        if (t + 1) % 90 == 0:
            print(f"  day {t+1}/{smp.n_days}  {n_tot/1e6:.2f} M", end="\r")

    print(f"\nevaluated {n_tot:,} samples in {time.time()-t0:.0f}s")

    parts = []
    for k in names:
        f = acc[k].frame(k)
        if k in anom:
            a = anom[k].frame(k)[["depth_m", "rmse", "correlation"]].rename(
                columns={"rmse": "anomaly_rmse", "correlation": "anomaly_correlation"})
            f = f.merge(a, on="depth_m", how="left")
        else:
            f["anomaly_rmse"] = np.nan
            f["anomaly_correlation"] = np.nan
        parts.append(f)
    by_depth = pd.concat(parts, ignore_index=True)
    by_depth.to_csv(TAB / f"phase6b_l2_metrics_by_depth{sfx}.csv", index=False)

    a0 = acc["L0_climatology"].frame("L0").set_index("depth_m")
    a1 = acc["L1_mlp"].frame("L1").set_index("depth_m")
    a2 = acc["L2_embedding"].frame("L2").set_index("depth_m")
    an1 = anom["L1_mlp"].frame("L1").set_index("depth_m")
    an2 = anom["L2_embedding"].frame("L2").set_index("depth_m")
    cmp = pd.DataFrame({
        "depth_m": a0.index,
        "rmse_L0": a0["rmse"].values,
        "rmse_L1": a1["rmse"].values,
        "rmse_L2": a2["rmse"].values,
        "mae_L2": a2["mae"].values,
        "bias_L2": a2["bias"].values,
        "nrmse_L1": a1["nrmse"].values,
        "nrmse_L2": a2["nrmse"].values,
        "corr_L1": a1["correlation"].values,
        "corr_L2": a2["correlation"].values,
        "anomcorr_L1": an1["correlation"].values,
        "anomcorr_L2": an2["correlation"].values,
        "skill_L1_over_L0_pct": (a0["rmse"].values - a1["rmse"].values) / a0["rmse"].values * 100,
        "skill_L2_over_L0_pct": (a0["rmse"].values - a2["rmse"].values) / a0["rmse"].values * 100,
        "delta_L2_vs_L1_pct": (a1["rmse"].values - a2["rmse"].values) / a1["rmse"].values * 100,
    })
    cmp["L2_beats_L1"] = cmp["delta_L2_vs_L1_pct"] > 0
    cmp.to_csv(TAB / f"phase6b_l2_vs_l1{sfx}.csv", index=False)
    group_summary(by_depth).to_csv(TAB / f"phase6b_l2_depth_group_summary{sfx}.csv", index=False)

    brows = []
    for b in BASINS:
        for k in names:
            f = basin_acc[b][k].frame(k)
            f.insert(0, "basin", b)
            brows.append(f)
    pd.concat(brows, ignore_index=True).to_csv(
        TAB / f"phase6b_l2_basin_summary{sfx}.csv", index=False)

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 30)
    show = ["depth_m", "rmse_L0", "rmse_L1", "rmse_L2", "skill_L1_over_L0_pct",
            "skill_L2_over_L0_pct", "delta_L2_vs_L1_pct", "anomcorr_L1",
            "anomcorr_L2", "L2_beats_L1"]
    print("\n=== L0 vs L1 vs L2 ===")
    print(cmp[show].round(4).to_string(index=False))
    json.dump({"split": args.split, "n_samples": int(n_tot), "l2_tag": args.l2_tag,
               "patch": int(ck2["patch"]), "latent": int(ck2["latent"])},
              open(TAB / f"phase6b_l2_eval_meta{sfx}.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
