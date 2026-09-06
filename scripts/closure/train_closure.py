"""Train one architecture-closure model (Experiment C or D).

The protocol is the one that produced the frozen L2 and is not re-tuned here:
patch 33, latent 32, Adam 1e-3, ReduceLROnPlateau(0.5, patience 2), max 15
epochs, early-stopping patience 4, train-day stride 1, gradients on TRAIN only,
checkpoint selection on VALIDATION only.

Two modes, selected by flag, never mixed:

  --residual         predict the departure from the frozen L0 climatology
  --ablate GROUP     zero one input group in standardised space (D)

Neither mode touches a frozen artefact. Checkpoints are written only under
outputs/models/architecture_closure/.
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

from oceanembed.closure.ablation import ABLATION_GROUPS, ablate_field
from oceanembed.closure.residual import ResidualTargets, residual_scaler_path
from oceanembed.closure.sampling import CachedDaySampler
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import masked_mse, set_seed
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
CACHE = REPO_ROOT / "outputs" / "targets_cache"
CLOSURE = REPO_ROOT / "outputs" / "architecture_closure"
CK_DIR = REPO_ROOT / "outputs" / "models" / "architecture_closure"

PATCH, LATENT = 33, 32
MAX_EPOCHS, PATIENCE, LR = 15, 4, 1e-3


def file_sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


FROZEN = {
    "l2_checkpoint_file": REPO_ROOT / "outputs" / "models" / "phase6b_l2_final.pt",
    "feature_scaler_file": BASE / "phase6b_feature_scaler.json",
    "target_scaler_file": BASE / "phase6b_target_scaler.json",
    "climatology_file": BASE / "phase6b_climatology.nc",
}
EXPECTED = {
    "l2_checkpoint_file": "81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35",
    "feature_scaler_file": "49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467",
    "target_scaler_file": "5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b",
    "climatology_file": "748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5",
}


def check_frozen(stage: str) -> dict:
    got = {k: file_sha(p) for k, p in FROZEN.items()}
    for k, want in EXPECTED.items():
        if got[k] != want:
            raise RuntimeError(f"{stage}: FROZEN ARTEFACT CHANGED - {k}")
    return got


def build_residual(smp_tr, clim, log=print) -> ZScoreScaler:
    """Fit (or reuse) the train-only residual scaler. Never refits L0."""
    p = residual_scaler_path()
    if p.exists():
        sc = ZScoreScaler.from_json(p)
        log(f"  residual scaler loaded from {p.name} (train-only)")
    else:
        log("  fitting train-only residual scaler")
        sc = ResidualTargets.fit_scaler(clim, smp_tr.r, smp_tr.c, DEPTHS,
                                        smp_tr.cache, smp_tr.times, log=log)
        p.parent.mkdir(parents=True, exist_ok=True)
        sc.to_json(p)
        log(f"  wrote {p}")
    assert sc.fitted_on == "train"
    return sc


def epoch_pass(model, smp, opt, group, seed=None, shuffle=False, stride=1):
    train = opt is not None
    model.train() if train else model.eval()
    run, n = 0.0, 0
    ctxman = torch.enable_grad() if train else torch.no_grad()
    with ctxman:
        for t, (field, ctx, Yz, M, _) in smp.days(shuffle=shuffle, seed=seed,
                                                  stride=stride):
            field = ablate_field(field, group)
            z = model.embed_field(torch.from_numpy(field)[None])[0]
            pred = model.forward_from_z(z[:, smp.r, smp.c].T, torch.from_numpy(ctx))
            loss = masked_mse(pred, torch.from_numpy(Yz), torch.from_numpy(M))
            if train:
                opt.zero_grad()
                loss.backward()
                opt.step()
            run += float(loss.detach()) * smp.n_cells
            n += smp.n_cells
    return run / max(n, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="checkpoint tag, e.g. L2_RESIDUAL_s20260905")
    ap.add_argument("--residual", action="store_true")
    ap.add_argument("--ablate", default=None, choices=sorted(ABLATION_GROUPS))
    ap.add_argument("--seed", type=int, default=20260905)
    args = ap.parse_args()

    if args.residual and args.ablate:
        raise SystemExit("residual and ablation modes are not combined in this study")

    CK_DIR.mkdir(parents=True, exist_ok=True)
    CLOSURE.mkdir(parents=True, exist_ok=True)
    sha_start = check_frozen("start")
    set_seed(args.seed)
    t_start = time.time()

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds_tr, ds_va = splits.open_split("train"), splits.open_split("validation")
    t_tr = pd.DatetimeIndex(ds_tr.time.values)
    t_va = pd.DatetimeIndex(ds_va.time.values)
    assert not splits.contains_test_dates(t_tr), "LEAK: test dates in train"
    assert not splits.contains_test_dates(t_va), "LEAK: test dates in validation"
    assert t_tr.max() < t_va.min()

    smp_tr = CachedDaySampler(ds_tr, DEPTHS, fs, ts, PATCH, CACHE, "train")
    smp_va = CachedDaySampler(ds_va, DEPTHS, fs, ts, PATCH, CACHE, "validation")

    mode = "residual" if args.residual else (f"ablate:{args.ablate}" if args.ablate
                                             else "control_full_inputs")
    print(f"[{args.name}] mode={mode} seed={args.seed}")
    print(f"  TRAIN {t_tr[0].date()}..{t_tr[-1].date()} ({smp_tr.n_days} d, "
          f"{smp_tr.n_cells} cells)")
    print(f"  VALIDATION {t_va[0].date()}..{t_va[-1].date()} ({smp_va.n_days} d, "
          f"{smp_va.n_cells} cells)")

    residual_meta = None
    if args.residual:
        clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
        assert clim.meta["fitted_on"] == "train"
        rsc = build_residual(smp_tr, clim)
        smp_tr.residual = ResidualTargets(clim, smp_tr.r, smp_tr.c, DEPTHS, rsc)
        smp_va.residual = ResidualTargets(clim, smp_va.r, smp_va.c, DEPTHS, rsc)
        residual_meta = {"scaler": str(residual_scaler_path()),
                         "scaler_sha256": file_sha(residual_scaler_path()),
                         "l0_file_sha256": sha_start["climatology_file"],
                         "mean": rsc.mean.tolist(), "std": rsc.std.tolist()}
        print(f"  residual std by depth: "
              f"{[round(float(x), 3) for x in rsc.std]}")

    model = L2EmbeddingModel(latent=LATENT, patch=PATCH)
    assert model.n_parameters == 136335, model.n_parameters
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=2)
    ck_path = CK_DIR / f"closure_{args.name}.pt"

    best, best_ep, bad, hist = float("inf"), -1, 0, []
    for ep in range(1, MAX_EPOCHS + 1):
        te = time.time()
        tr_l = epoch_pass(model, smp_tr, opt, args.ablate, seed=args.seed + ep,
                          shuffle=True)
        va_l = epoch_pass(model, smp_va, None, args.ablate)
        sched.step(va_l)
        lr = opt.param_groups[0]["lr"]
        hist.append({"epoch": ep, "train_loss": tr_l, "val_loss": va_l, "lr": lr,
                     "seconds": time.time() - te})
        flag = ""
        if va_l < best - 1e-6:
            best, best_ep, bad = va_l, ep, 0
            torch.save({"state_dict": model.state_dict(),
                        "encoder_state_dict": model.encoder.state_dict(),
                        "epoch": ep, "val_loss": va_l, "train_loss": tr_l,
                        "patch": PATCH, "latent": LATENT, "depths": DEPTHS,
                        "seed": args.seed, "mode": mode,
                        "ablated_group": args.ablate,
                        "residual": bool(args.residual),
                        "residual_meta": residual_meta,
                        "dilations": model.encoder.dilations,
                        "receptive_field": model.encoder.receptive_field,
                        "n_parameters": model.n_parameters,
                        "n_encoder_parameters": model.n_encoder_parameters},
                       ck_path)
            flag = "  <- best"
        else:
            bad += 1
        print(f"  epoch {ep:2d}  train {tr_l:.5f}  val {va_l:.5f}  lr {lr:.2e}  "
              f"{time.time()-te:5.0f}s{flag}", flush=True)
        if bad >= PATIENCE:
            print(f"  early stopping after {bad} epochs without improvement")
            break

    check_frozen("end")
    meta = {"name": args.name, "mode": mode, "seed": args.seed,
            "residual": bool(args.residual), "ablated_group": args.ablate,
            "patch": PATCH, "latent": LATENT,
            "max_epochs": MAX_EPOCHS, "patience": PATIENCE, "lr": LR,
            "epochs_run": len(hist), "best_epoch": best_ep, "best_val_loss": best,
            "runtime_seconds": time.time() - t_start,
            "n_parameters": model.n_parameters,
            "train_days": int(smp_tr.n_days), "val_days": int(smp_va.n_days),
            "n_cells_train": int(smp_tr.n_cells),
            "n_cells_validation": int(smp_va.n_cells),
            "loss": "per-depth masked MSE in standardised target space",
            "residual_meta": residual_meta,
            "frozen_sha256_start": sha_start,
            "frozen_sha256_end": check_frozen("end"),
            "history": hist}
    json.dump(meta, open(CK_DIR / f"closure_{args.name}_training.json", "w"), indent=2)
    print(f"[{args.name}] best epoch {best_ep} val {best:.5f} "
          f"({(time.time()-t_start)/60:.1f} min) -> {ck_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
