"""Evaluate L0 / L1 / L2 / L3-control / L3-selected on the SAME common dates.

Every model is scored on the identical target-date range and identical cells,
so no comparison can be confounded by sample population. L2 is re-evaluated
here rather than reusing its Phase 6B-B numbers, because those were computed on
the full split rather than the common (first-6-days-dropped) range.

All predictions come from the cached frozen-L2 embeddings, so no CNN runs.
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
from oceanembed.ml.embedding_cache import EmbeddingCache, TargetCache
from oceanembed.ml.features import SURFACE, cyclic_doy
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.metrics import BASINS, DepthAccumulator, basin_of, group_summary
from oceanembed.ml.model import PointwiseMLP
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.ml.temporal import TemporalHead
from oceanembed.ml.temporal_dataset import TemporalSequenceSampler

L3 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6c_l3.yaml", encoding="utf-8"))
B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
TAB = REPO_ROOT / B6["paths"]["tables"]
EMB = REPO_ROOT / L3["cache"]["dir"]
TGT = REPO_ROOT / "outputs" / "targets_cache"
MAXH = int(L3["max_history_days"])


def load_head(tag: str):
    ck = torch.load(MODELS / f"phase6b_l3_{tag}.pt", map_location="cpu",
                    weights_only=False)
    h = TemporalHead(latent=ck["latent"], hidden=ck["latent"])
    h.load_state_dict(ck["state_dict"])
    h.eval()
    return h, ck


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation", choices=["validation", "test"])
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--control-tag", default="w1_s20260905")
    ap.add_argument("--selected-tag", required=True)
    ap.add_argument("--with-l1", action="store_true")
    ap.add_argument("--diagnostics", action="store_true",
                    help="also score repeated-current and reversed history")
    ap.add_argument("--suffix", default=None)
    args = ap.parse_args()
    if args.split == "test" and not args.allow_test:
        raise SystemExit("Test split is LOCKED. Use --allow-test only for the "
                         "single frozen benchmark after the L3 design is frozen.")
    sfx = args.suffix if args.suffix is not None else ("_test" if args.split == "test" else "")

    t0 = time.time()
    ds = splits.open_split(args.split, allow_test=args.allow_test)
    cache = EmbeddingCache(EMB, args.split).load()
    tgt = TargetCache(TGT, args.split).load()

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta["fitted_on"] == "train"
    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ck2 = torch.load(REPO_ROOT / L3["frozen"]["l2_checkpoint"], map_location="cpu",
                     weights_only=False)
    l2 = L2EmbeddingModel(latent=ck2["latent"], patch=ck2["patch"])
    l2.load_state_dict(ck2["state_dict"])
    l2.eval()
    cache.verify_encoder(l2.encoder.state_dict())

    ctrl, ck_c = load_head(args.control_tag)
    sel, ck_s = load_head(args.selected_tag)
    win_sel = int(ck_s["window"])
    print(f"SPLIT {args.split} | L3-control window={ck_c['window']} "
          f"| L3-selected window={win_sel} seed={ck_s['seed']}")

    smp_sel = TemporalSequenceSampler(ds, cache, DEPTHS, fs, ts, win_sel, MAXH,
                                      target_cache=tgt)
    smp_ctl = TemporalSequenceSampler(ds, cache, DEPTHS, fs, ts,
                                      int(ck_c["window"]), MAXH, target_cache=tgt)
    assert list(smp_sel.target_dates) == list(smp_ctl.target_dates)
    print(f"common targets {smp_sel.target_dates[0].date()}.."
          f"{smp_sel.target_dates[-1].date()}  n={smp_sel.n_targets} days "
          f"x {smp_sel.n_cells} cells = {smp_sel.n_samples:,}")

    names = ["L0_climatology", "L2_spatial", "L3_control_1d", "L3_selected"]
    if args.with_l1:
        names.insert(1, "L1_pointwise")
    if args.diagnostics:
        names += ["L3_repeated_current", "L3_reversed_history"]
    acc = {k: DepthAccumulator(DEPTHS) for k in names}
    anom = {k: DepthAccumulator(DEPTHS) for k in names if k != "L0_climatology"}
    basin_acc = {b: {k: DepthAccumulator(DEPTHS) for k in names} for b in BASINS}

    l1 = None
    if args.with_l1:
        ck1 = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu",
                         weights_only=False)
        l1 = PointwiseMLP(ck1["n_features"], tuple(ck1["hidden"]), ck1["n_out"])
        l1.load_state_dict(ck1["state_dict"])
        l1.eval()

    r, c = smp_sel.r, smp_sel.c
    n_tot = 0
    for t in smp_sel.target_idx:
        t = int(t)
        ctx = smp_sel.context(t)
        Yz, M, Y = smp_sel.targets(t)
        ctx_t = torch.from_numpy(ctx)
        preds = {}
        preds["L0_climatology"] = clim.predict(smp_sel.times[t:t + 1], r, c)[0].astype("float64")

        z_now = torch.from_numpy(np.asarray(cache.z[t]))
        with torch.no_grad():
            preds["L2_spatial"] = ts.inverse_transform(
                l2.forward_from_z(z_now, ctx_t).numpy().astype("float64"))
            preds["L3_control_1d"] = ts.inverse_transform(
                ctrl(torch.from_numpy(smp_ctl.sequence(t)), ctx_t).numpy().astype("float64"))
            preds["L3_selected"] = ts.inverse_transform(
                sel(torch.from_numpy(smp_sel.sequence(t)), ctx_t).numpy().astype("float64"))
            if args.diagnostics:
                for key, order in [("L3_repeated_current", "repeat_current"),
                                   ("L3_reversed_history", "reversed")]:
                    preds[key] = ts.inverse_transform(
                        sel(torch.from_numpy(smp_sel.sequence(t, order=order)),
                            ctx_t).numpy().astype("float64"))
            if l1 is not None:
                surf = np.column_stack([ds[v].isel(time=t).values[r, c] for v in SURFACE])
                s_, c_ = cyclic_doy(smp_sel.times[t:t + 1])
                X1 = np.column_stack([surf, smp_sel.cell_lat, smp_sel.cell_lon,
                                      np.full(smp_sel.n_cells, s_[0]),
                                      np.full(smp_sel.n_cells, c_[0])])
                ok = np.isfinite(X1).all(axis=1)
                p1 = np.full((smp_sel.n_cells, len(DEPTHS)), np.nan)
                if ok.any():
                    p1[ok] = ts.inverse_transform(
                        l1(torch.from_numpy(fs.transform(X1[ok]).astype("float32"))).numpy())
                preds["L1_pointwise"] = p1

        for k in names:
            acc[k].update(preds[k], Y, M)
            if k in anom:
                anom[k].update(preds[k] - preds["L0_climatology"],
                               Y - preds["L0_climatology"], M)
        for b in BASINS:
            selb = basin_of(smp_sel.cell_lat, smp_sel.cell_lon, b)
            if selb.any():
                for k in names:
                    basin_acc[b][k].update(preds[k][selb], Y[selb], M[selb])
        n_tot += smp_sel.n_cells
        if (t + 1) % 200 == 0:
            print(f"  day {t+1}  {n_tot/1e6:.2f} M", end="\r")

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
    by_depth.to_csv(TAB / f"phase6b_l3_metrics_by_depth{sfx}.csv", index=False)

    fr = {k: acc[k].frame(k).set_index("depth_m") for k in names}
    an = {k: anom[k].frame(k).set_index("depth_m") for k in anom}
    r0 = fr["L0_climatology"]["rmse"].values
    out = pd.DataFrame({"depth_m": fr["L0_climatology"].index, "rmse_L0": r0})
    for k in names:
        if k == "L0_climatology":
            continue
        out[f"rmse_{k}"] = fr[k]["rmse"].values
        out[f"anomcorr_{k}"] = an[k]["correlation"].values
        out[f"skill_{k}_over_L0_pct"] = (r0 - fr[k]["rmse"].values) / r0 * 100
    out["delta_selected_vs_L2_pct"] = (
        (fr["L2_spatial"]["rmse"].values - fr["L3_selected"]["rmse"].values)
        / fr["L2_spatial"]["rmse"].values * 100)
    out["delta_selected_vs_control_pct"] = (
        (fr["L3_control_1d"]["rmse"].values - fr["L3_selected"]["rmse"].values)
        / fr["L3_control_1d"]["rmse"].values * 100)
    out["selected_beats_control"] = out["delta_selected_vs_control_pct"] > 0
    out["selected_beats_L2"] = out["delta_selected_vs_L2_pct"] > 0
    out.to_csv(TAB / f"phase6b_l3_vs_control{sfx}.csv", index=False)
    out.to_csv(TAB / f"phase6b_l3_vs_l2{sfx}.csv", index=False)
    group_summary(by_depth).to_csv(
        TAB / f"phase6b_l3_depth_group_summary{sfx}.csv", index=False)

    brows = []
    for b in BASINS:
        for k in names:
            f = basin_acc[b][k].frame(k)
            f.insert(0, "basin", b)
            brows.append(f)
    pd.concat(brows, ignore_index=True).to_csv(
        TAB / f"phase6b_l3_basin_summary{sfx}.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    show = ["depth_m", "rmse_L0", "rmse_L2_spatial", "rmse_L3_control_1d",
            "rmse_L3_selected", "delta_selected_vs_control_pct",
            "delta_selected_vs_L2_pct", "anomcorr_L2_spatial",
            "anomcorr_L3_selected"]
    print("\n=== L0 / L2 / L3-control / L3-selected ===")
    print(out[show].round(4).to_string(index=False))
    if args.diagnostics:
        d = out[["depth_m", "rmse_L3_selected", "rmse_L3_repeated_current",
                 "rmse_L3_reversed_history"]]
        print("\n=== ORDERING DIAGNOSTICS (frozen model, no retraining) ===")
        print(d.round(4).to_string(index=False))

    json.dump({"split": args.split, "n_samples": int(n_tot),
               "selected_tag": args.selected_tag, "selected_window": win_sel,
               "control_tag": args.control_tag,
               "common_start": str(smp_sel.target_dates[0].date()),
               "common_end": str(smp_sel.target_dates[-1].date()),
               "n_targets": int(smp_sel.n_targets)},
              open(TAB / f"phase6b_l3_eval_meta{sfx}.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
