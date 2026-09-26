"""Evaluate the SST-only baseline on 2021 validation (PREREGISTRATION §3).

Identical population and physical-°C metrics as Architecture Closure evaluation:
FROZEN_L2, the matched full-input control D_CONTROL_ALL, and SST_ONLY. The test
split is never opened and no Argo data is read.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "closure"))

import numpy as np
import pandas as pd
import torch

import evaluate_closure as EC
from oceanembed.closure.residual import ResidualTargets
from oceanembed.closure.sampling import CachedDaySampler
from oceanembed.ml import splits
from oceanembed.ml.metrics import BASINS, DepthAccumulator, basin_of
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.science.channels import keep_only

OUT_TAB = EC.REPO_ROOT / "outputs" / "tables" / "science"
OUT = EC.REPO_ROOT / "outputs" / "science"


def main() -> int:
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    fs = ZScoreScaler.from_json(EC.BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(EC.BASE / "phase6b_target_scaler.json")
    clim = EC.HarmonicClimatology.load(EC.BASE / "phase6b_climatology.nc")
    ds = splits.open_split("validation")
    times = pd.DatetimeIndex(ds.time.values)
    assert not splits.contains_test_dates(times)
    smp = CachedDaySampler(ds, EC.DEPTHS, fs, ts, 33, EC.CACHE, "validation")
    rt = ResidualTargets(clim, smp.r, smp.c, EC.DEPTHS)

    specs = []
    m, ck = EC.load_model(EC.MODELS / "phase6b_l2_final.pt")
    specs.append(("FROZEN_L2", m, None, EC.sd_sha(ck["state_dict"])))
    m, ck = EC.load_model(EC.CK_DIR / "closure_D_CONTROL_ALL.pt")
    specs.append(("D_CONTROL_ALL", m, None, EC.sd_sha(ck["state_dict"])))
    p = EC.REPO_ROOT / "outputs" / "models" / "science" / "SST_ONLY_s20260905.pt"
    m, ck = EC.load_model(p)
    specs.append(("SST_ONLY", m, ["sst"], EC.sd_sha(ck["state_dict"])))

    acc = {s[0]: DepthAccumulator(EC.DEPTHS) for s in specs}
    anom = {s[0]: DepthAccumulator(EC.DEPTHS) for s in specs}
    acc["L0_climatology"] = DepthAccumulator(EC.DEPTHS)
    sel = {b: basin_of(smp.cell_lat, smp.cell_lon, b) for b in BASINS}
    bacc = {b: {k: DepthAccumulator(EC.DEPTHS) for k in acc} for b in BASINS}
    for t in range(smp.n_days):
        field = smp.day(t)[0]
        ctx = torch.from_numpy(smp.context(t))
        Y = smp.targets(t)
        M = smp.target_mask & np.isfinite(Y)
        L0 = rt.climatology(times[t])
        acc["L0_climatology"].update(L0, Y, M)
        for b, s in sel.items():
            bacc[b]["L0_climatology"].update(L0[s], Y[s], M[s])
        for label, model, keep, _ in specs:
            f = keep_only(field, keep) if keep else field
            with torch.no_grad():
                z = model.embed_field(torch.from_numpy(f)[None])[0]
                raw = model.forward_from_z(z[:, smp.r, smp.c].T, ctx).numpy().astype("float64")
            pred = ts.inverse_transform(raw)
            acc[label].update(pred, Y, M)
            anom[label].update(pred - L0, Y - L0, M)
            for b, s in sel.items():
                bacc[b][label].update(pred[s], Y[s], M[s])
        if (t + 1) % 90 == 0:
            print(f"  {t + 1}/{smp.n_days} ({time.time() - t0:.0f}s)", flush=True)

    frames = []
    for label, a in acc.items():
        f = a.frame(label)
        if label in anom:
            an = anom[label].frame(label)[["depth_m", "rmse", "correlation"]].rename(
                columns={"rmse": "anomaly_rmse", "correlation": "anomaly_correlation"})
            f = f.merge(an, on="depth_m", how="left")
        frames.append(f)
    metrics = pd.concat(frames, ignore_index=True)
    l0 = metrics[metrics.model == "L0_climatology"].set_index("depth_m")["rmse"]
    metrics["skill_vs_L0_percent"] = [(l0[d] - r) / l0[d] * 100 for d, r in
                                     zip(metrics.depth_m, metrics.rmse)]
    metrics.to_csv(OUT_TAB / "sst_only_metrics_by_depth.csv", index=False)
    rows = []
    for b in BASINS:
        for label, a in bacc[b].items():
            f = a.frame(label)
            f.insert(0, "basin", b)
            rows.append(f)
    pd.concat(rows).to_csv(OUT_TAB / "sst_only_basin_metrics.csv", index=False)
    (OUT / "sst_only_eval_meta.json").write_text(json.dumps({
        "split": "validation", "dates": [str(times[0].date()), str(times[-1].date())],
        "n_days": int(smp.n_days), "n_cells": int(smp.n_cells),
        "models": [{"label": s[0], "kept_channels": s[2], "sha": s[3]} for s in specs],
        "runtime_seconds": time.time() - t0,
        "note": "physical temperature space; identical population; test split never "
                "opened; no Argo read"}, indent=2), encoding="utf-8")
    print(metrics.pivot(index="depth_m", columns="model", values="rmse").round(4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
