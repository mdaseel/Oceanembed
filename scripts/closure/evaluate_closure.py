"""Evaluate closure models on 2021 validation, in PHYSICAL TEMPERATURE SPACE.

Every model - frozen L2, the residual candidate, the ablation control and the
five ablations - is scored on an IDENTICAL population: the same days, the same
cells, the same target mask. A model can therefore never look better by being
scored on an easier subset.

A residual model's prediction is converted to temperature by adding the frozen
L0 climatology before any metric is computed; a model can only be compared to
another in degrees Celsius.

The locked test split is never opened. No Argo data is read here.
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

from oceanembed.closure.ablation import ablate_field
from oceanembed.closure.residual import ResidualTargets
from oceanembed.closure.sampling import CachedDaySampler
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.metrics import (BASINS, DepthAccumulator, basin_of,
                                   group_summary)
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
CK_DIR = MODELS / "architecture_closure"
CACHE = REPO_ROOT / "outputs" / "targets_cache"
TAB = REPO_ROOT / "outputs" / "tables" / "architecture_closure"
OUT = REPO_ROOT / "outputs" / "architecture_closure"


def sd_sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def load_model(path: Path):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    m.eval()
    for p in m.parameters():
        p.requires_grad_(False)
    return m, ck


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True,
                    help="closure checkpoint tags, or FROZEN_L2")
    ap.add_argument("--tag", required=True, help="output table prefix")
    args = ap.parse_args()

    TAB.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"
    assert clim.meta["fitted_on"] == "train"

    ds = splits.open_split("validation")
    times = pd.DatetimeIndex(ds.time.values)
    assert not splits.contains_test_dates(times), "LEAK: test dates in evaluation"
    smp = CachedDaySampler(ds, DEPTHS, fs, ts, 33, CACHE, "validation")
    r, c = smp.r, smp.c
    rt = ResidualTargets(clim, r, c, DEPTHS)      # for L0 and for anomalies
    print(f"validation {times[0].date()}..{times[-1].date()}  "
          f"{smp.n_days} days x {smp.n_cells} cells")

    specs = []
    for name in args.models:
        if name == "FROZEN_L2":
            m, ck = load_model(MODELS / "phase6b_l2_final.pt")
            specs.append({"label": "FROZEN_L2", "model": m, "residual": False,
                          "ablate": None, "sha": sd_sha(ck["state_dict"])})
        else:
            p = CK_DIR / f"closure_{name}.pt"
            if not p.exists():
                print(f"  {name}: checkpoint missing, skipped")
                continue
            m, ck = load_model(p)
            rsc = None
            if ck.get("residual"):
                rsc = ZScoreScaler.from_json(ck["residual_meta"]["scaler"])
                assert rsc.fitted_on == "train"
            specs.append({"label": name, "model": m,
                          "residual": bool(ck.get("residual")),
                          "rscaler": rsc, "ablate": ck.get("ablated_group"),
                          "sha": sd_sha(ck["state_dict"]),
                          "best_epoch": ck.get("epoch"),
                          "val_loss": ck.get("val_loss")})
    print("evaluating:", [s["label"] for s in specs])

    acc = {s["label"]: DepthAccumulator(DEPTHS) for s in specs}
    anom = {s["label"]: DepthAccumulator(DEPTHS) for s in specs}
    acc["L0_climatology"] = DepthAccumulator(DEPTHS)
    basin_acc = {b: {k: DepthAccumulator(DEPTHS) for k in acc} for b in BASINS}
    basin_sel = {b: basin_of(smp.cell_lat, smp.cell_lon, b) for b in BASINS}

    sha_before = {s["label"]: s["sha"] for s in specs}

    for t in range(smp.n_days):
        field = smp.day(t)[0]
        ctx = torch.from_numpy(smp.context(t))
        Y = smp.targets(t)
        M = smp.target_mask & np.isfinite(Y)
        L0 = rt.climatology(times[t])

        acc["L0_climatology"].update(L0, Y, M)
        for b, sel in basin_sel.items():
            basin_acc[b]["L0_climatology"].update(L0[sel], Y[sel], M[sel])

        for s in specs:
            f = ablate_field(field, s["ablate"])
            with torch.no_grad():
                z = s["model"].embed_field(torch.from_numpy(f)[None])[0]
                raw = s["model"].forward_from_z(z[:, r, c].T, ctx).numpy().astype("float64")
            if s["residual"]:
                delta = raw * s["rscaler"].std + s["rscaler"].mean
                pred = L0 + delta
            else:
                pred = ts.inverse_transform(raw)
            acc[s["label"]].update(pred, Y, M)
            anom[s["label"]].update(pred - L0, Y - L0, M)
            for b, sel in basin_sel.items():
                basin_acc[b][s["label"]].update(pred[sel], Y[sel], M[sel])
        if (t + 1) % 90 == 0:
            print(f"  {t + 1}/{smp.n_days} days ({time.time() - t0:.0f}s)", flush=True)

    for s in specs:
        assert sd_sha(s["model"].state_dict()) == sha_before[s["label"]], \
            f"{s['label']} CHANGED during evaluation"
    print("all model weights unchanged during evaluation")

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
    metrics["skill_vs_L0_percent"] = metrics.apply(
        lambda row: (l0[row["depth_m"]] - row["rmse"]) / l0[row["depth_m"]] * 100.0,
        axis=1)
    metrics.to_csv(TAB / f"{args.tag}_metrics_by_depth.csv", index=False)
    group_summary(metrics).to_csv(TAB / f"{args.tag}_depth_groups.csv", index=False)

    brows = []
    for b in BASINS:
        for label, a in basin_acc[b].items():
            f = a.frame(label)
            f.insert(0, "basin", b)
            brows.append(f)
    pd.concat(brows, ignore_index=True).to_csv(
        TAB / f"{args.tag}_basin_metrics.csv", index=False)

    json.dump({"tag": args.tag, "split": "validation",
               "dates": [str(times[0].date()), str(times[-1].date())],
               "n_days": int(smp.n_days), "n_cells": int(smp.n_cells),
               "models": [{k: v for k, v in s.items() if k != "model"
                           and k != "rscaler"} for s in specs],
               "runtime_seconds": time.time() - t0,
               "note": "physical temperature space; identical population for "
                       "every model; test split never opened; no Argo read"},
              open(OUT / f"{args.tag}_eval_meta.json", "w"), indent=2)

    piv = metrics.pivot(index="depth_m", columns="model", values="rmse")
    print("\nvalidation RMSE (degC) by depth:")
    print(piv.round(4).to_string())
    print(f"\n-> {TAB / (args.tag + '_metrics_by_depth.csv')}  "
          f"({(time.time() - t0) / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
