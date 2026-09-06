"""Evaluate L0 climatology and L1 MLP on one split, depth by depth.

Also computes anomaly skill against the TRAIN-ONLY climatology, which is the
test that separates "reproduces the seasonal cycle" from "predicts day-to-day
departures from it".

Usage:  python scripts/baselines/evaluate.py [--split validation|test]
The test split requires --allow-test and is intended to be run exactly once,
after everything is frozen.
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np, pandas as pd, torch, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.dataset import PointwiseSampler
from oceanembed.ml.features import FEATURE_NAMES
from oceanembed.ml.metrics import (BASINS, DepthAccumulator, basin_of,
                                   group_summary, skill_table)
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
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    if args.split == "test" and not args.allow_test:
        raise SystemExit("Refusing: the test split is LOCKED. Pass --allow-test "
                         "only for the single final frozen evaluation.")

    t0 = time.time()
    ds = splits.open_split(args.split, allow_test=args.allow_test)
    tt = pd.DatetimeIndex(ds.time.values)
    print(f"SPLIT {args.split}: {tt[0].date()} .. {tt[-1].date()} ({len(tt)} days)")

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta.get("fitted_on") == "train", "climatology not train-only"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"
    print(f"frozen artefacts: climatology(fit={clim.meta['fit_start']}..{clim.meta['fit_end']}), "
          f"scalers(fitted_on=train)")

    ck = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    model = PointwiseMLP(ck["n_features"], tuple(ck["hidden"]), ck["n_out"])
    model.load_state_dict(ck["state_dict"]); model.eval()
    print(f"L1 checkpoint: epoch {ck['epoch']}, val_loss {ck['val_loss']:.5f}")

    smp = PointwiseSampler(ds, DEPTHS, chunk_days=64)
    lat_i, lon_i = smp.cell_idx[:, 0], smp.cell_idx[:, 1]

    acc = {"L0_climatology": DepthAccumulator(DEPTHS), "L1_mlp": DepthAccumulator(DEPTHS)}
    anom = {"L1_mlp": DepthAccumulator(DEPTHS)}
    basin_acc = {b: {k: DepthAccumulator(DEPTHS) for k in acc} for b in BASINS}
    n_tot = 0

    n_dropped = 0
    for X, Y, M, times, row_t, row_c in smp.blocks():
        uniq = pd.DatetimeIndex(np.unique(times))
        n_dropped += len(uniq) * smp.n_cells - len(X)
        # L0: climatology for this block, then indexed by the SURVIVING rows
        c_full = clim.predict(uniq, lat_i, lon_i)          # (nt, n_cells, n_depths)
        c = c_full[row_t, row_c, :].astype("float64")
        with torch.no_grad():
            xb = torch.from_numpy(fs.transform(X).astype("float32"))
            p = ts.inverse_transform(model(xb).numpy().astype("float64"))

        acc["L0_climatology"].update(c, Y, M)
        acc["L1_mlp"].update(p, Y, M)
        # anomalies are defined against the SAME train-only climatology
        anom["L1_mlp"].update(p - c, Y - c, M)

        blat = smp.cell_lat[row_c]; blon = smp.cell_lon[row_c]
        for b in BASINS:
            sel = basin_of(blat, blon, b)
            if sel.any():
                basin_acc[b]["L0_climatology"].update(c[sel], Y[sel], M[sel])
                basin_acc[b]["L1_mlp"].update(p[sel], Y[sel], M[sel])
        n_tot += len(X)
        print(f"  {n_tot/1e6:5.2f} M samples", end="\r")

    print(f"\nevaluated {n_tot:,} samples in {time.time()-t0:.0f}s")
    sfx = args.suffix or ("_test" if args.split == "test" else "")

    by_depth = pd.concat([acc[k].frame(k) for k in acc], ignore_index=True)
    an = anom["L1_mlp"].frame("L1_mlp_anomaly")
    an = an.rename(columns={"rmse": "anomaly_rmse", "correlation": "anomaly_correlation"})
    by_depth = by_depth.merge(
        an[["depth_m", "anomaly_rmse", "anomaly_correlation"]], on="depth_m", how="left")
    by_depth.loc[by_depth["model"] != "L1_mlp", ["anomaly_rmse", "anomaly_correlation"]] = np.nan
    by_depth.to_csv(TAB / f"phase6b_metrics_by_depth{sfx}.csv", index=False)

    sk = skill_table(acc["L0_climatology"].frame("L0"), acc["L1_mlp"].frame("L1"))
    sk.to_csv(TAB / f"phase6b_skill_vs_climatology{sfx}.csv", index=False)
    group_summary(by_depth).to_csv(TAB / f"phase6b_depth_group_summary{sfx}.csv", index=False)

    brows = []
    for b in BASINS:
        for k in acc:
            f = basin_acc[b][k].frame(k); f.insert(0, "basin", b); brows.append(f)
    pd.concat(brows, ignore_index=True).to_csv(TAB / f"phase6b_basin_summary{sfx}.csv", index=False)

    pd.set_option("display.width", 200)
    print("\n=== DEPTH-WISE: L0 climatology vs L1 MLP ===")
    print(sk.round(4).to_string(index=False))
    print("\n=== ANOMALY SKILL (L1 vs train-only climatology) ===")
    print(an[["depth_m", "anomaly_rmse", "anomaly_correlation"]].round(4).to_string(index=False))
    print("\n=== DEPTH GROUPS ===")
    print(group_summary(by_depth).round(4).to_string(index=False))
    json.dump({"split": args.split, "n_samples": int(n_tot),
               "start": str(tt[0].date()), "end": str(tt[-1].date()),
               "checkpoint_epoch": int(ck["epoch"])},
              open(TAB / f"phase6b_eval_meta{sfx}.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
