"""SST-only experimental baseline (pre-registered, outputs/science/PREREGISTRATION.md §3).

Identical to Architecture Closure Experiment D in every respect except the input
information: the six non-SST data planes are set to the training mean for
training and validation. Architecture, width, parameter count, sampler, target
cache, seed and schedule are unchanged. Writes only under
outputs/models/science/. The production L2 is never loaded for writing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "closure"))

import pandas as pd
import torch

import train_closure as TC  # the frozen closure protocol, imported not copied
from oceanembed.closure.sampling import CachedDaySampler
from oceanembed.ml import splits
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import masked_mse, set_seed
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.science.channels import keep_only

NAME = "SST_ONLY_s20260905"
SEED = 20260905
CK_DIR = TC.REPO_ROOT / "outputs" / "models" / "science"


def epoch_pass(model, smp, opt, seed=None, shuffle=False):
    train = opt is not None
    model.train() if train else model.eval()
    run, n = 0.0, 0
    with (torch.enable_grad() if train else torch.no_grad()):
        for _, (field, ctx, Yz, M, _) in smp.days(shuffle=shuffle, seed=seed):
            field = keep_only(field, ["sst"])
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
    CK_DIR.mkdir(parents=True, exist_ok=True)
    sha_start = TC.check_frozen("start")
    set_seed(SEED)
    t0 = time.time()
    fs = ZScoreScaler.from_json(TC.BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(TC.BASE / "phase6b_target_scaler.json")
    ds_tr, ds_va = splits.open_split("train"), splits.open_split("validation")
    t_tr, t_va = pd.DatetimeIndex(ds_tr.time.values), pd.DatetimeIndex(ds_va.time.values)
    assert not splits.contains_test_dates(t_tr) and not splits.contains_test_dates(t_va)
    smp_tr = CachedDaySampler(ds_tr, TC.DEPTHS, fs, ts, TC.PATCH, TC.CACHE, "train")
    smp_va = CachedDaySampler(ds_va, TC.DEPTHS, fs, ts, TC.PATCH, TC.CACHE, "validation")
    print(f"[{NAME}] keep only SST  TRAIN {smp_tr.n_days} d  VALIDATION {smp_va.n_days} d",
          flush=True)

    model = L2EmbeddingModel(latent=TC.LATENT, patch=TC.PATCH)
    assert model.n_parameters == 136335
    opt = torch.optim.Adam(model.parameters(), lr=TC.LR)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=2)
    ck = CK_DIR / f"{NAME}.pt"
    best, best_ep, bad, hist = float("inf"), -1, 0, []
    for ep in range(1, TC.MAX_EPOCHS + 1):
        te = time.time()
        tr = epoch_pass(model, smp_tr, opt, seed=SEED + ep, shuffle=True)
        va = epoch_pass(model, smp_va, None)
        sched.step(va)
        hist.append({"epoch": ep, "train_loss": tr, "val_loss": va,
                     "lr": opt.param_groups[0]["lr"], "seconds": time.time() - te})
        flag = ""
        if va < best - 1e-6:
            best, best_ep, bad = va, ep, 0
            torch.save({"state_dict": model.state_dict(), "epoch": ep, "val_loss": va,
                        "patch": TC.PATCH, "latent": TC.LATENT, "depths": TC.DEPTHS,
                        "seed": SEED, "mode": "keep_only:sst", "kept_channels": ["sst"]}, ck)
            flag = "  <- best"
        else:
            bad += 1
        print(f"  epoch {ep:2d} train {tr:.5f} val {va:.5f} {time.time() - te:5.0f}s{flag}",
              flush=True)
        if bad >= TC.PATIENCE:
            print("  early stopping")
            break
    meta = {"name": NAME, "mode": "keep_only:sst", "seed": SEED, "patch": TC.PATCH,
            "latent": TC.LATENT, "epochs_run": len(hist), "best_epoch": best_ep,
            "best_val_loss": best, "runtime_seconds": time.time() - t0,
            "protocol": "outputs/science/PREREGISTRATION.md §3 (= Experiment D protocol)",
            "frozen_sha256_start": sha_start, "frozen_sha256_end": TC.check_frozen("end"),
            "history": hist}
    (CK_DIR / f"{NAME}_training.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[{NAME}] best epoch {best_ep} val {best:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
