"""Train an L3 temporal head on cached frozen-L2 embeddings.

The spatial encoder is NEVER updated: training consumes cached z vectors, so
encoder gradients are structurally impossible, and the encoder weights are
additionally asserted bit-identical before and after.
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
from oceanembed.ml.embedding_cache import (EmbeddingCache, TargetCache,
                                           encoder_fingerprint)
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import masked_mse, set_seed
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.ml.temporal import TemporalHead, freeze_encoder
from oceanembed.ml.temporal_dataset import TemporalSequenceSampler

L3 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6c_l3.yaml", encoding="utf-8"))
B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
MODELS = REPO_ROOT / B6["paths"]["models"]
CACHE_DIR = REPO_ROOT / L3["cache"]["dir"]
MAXH = int(L3["max_history_days"])
TR = L3["training"]


def val_loss(head, smp) -> float:
    head.eval()
    tot = 0.0
    n = 0.0
    with torch.no_grad():
        for t, (seq, ctx, Yz, M, _) in smp.batches():
            pred = head(torch.from_numpy(seq), torch.from_numpy(ctx))
            tot += float(masked_mse(pred, torch.from_numpy(Yz),
                                    torch.from_numpy(M))) * smp.n_cells
            n += smp.n_cells
    head.train()
    return tot / max(n, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, required=True)
    ap.add_argument("--seed", type=int, default=int(TR["seed"]))
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    set_seed(args.seed)

    ck = torch.load(REPO_ROOT / L3["frozen"]["l2_checkpoint"], map_location="cpu",
                    weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    freeze_encoder(l2.encoder)
    fp_before = encoder_fingerprint(l2.encoder.state_dict())
    n_frozen = sum(p.numel() for p in l2.encoder.parameters())
    assert all(not p.requires_grad for p in l2.encoder.parameters()), "encoder not frozen"

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    ds_tr = splits.open_split("train")
    ds_va = splits.open_split("validation")
    c_tr = EmbeddingCache(CACHE_DIR, "train").load()
    c_va = EmbeddingCache(CACHE_DIR, "validation").load()
    for c in (c_tr, c_va):
        c.verify_encoder(l2.encoder.state_dict())
    TGT = REPO_ROOT / "outputs" / "targets_cache"
    y_tr = TargetCache(TGT, "train").load() if TargetCache(TGT, "train").exists() else None
    y_va = TargetCache(TGT, "validation").load() if TargetCache(TGT, "validation").exists() else None

    smp_tr = TemporalSequenceSampler(ds_tr, c_tr, DEPTHS, fs, ts, args.window, MAXH,
                                     target_cache=y_tr)
    smp_va = TemporalSequenceSampler(ds_va, c_va, DEPTHS, fs, ts, args.window, MAXH,
                                     target_cache=y_va)
    assert not splits.contains_test_dates(smp_tr.target_dates)
    assert not splits.contains_test_dates(smp_va.target_dates)
    print(f"window={args.window}  seed={args.seed}")
    print(f"TRAIN targets {smp_tr.target_dates[0].date()}..{smp_tr.target_dates[-1].date()} "
          f"n={smp_tr.n_targets} days x {smp_tr.n_cells} cells = {smp_tr.n_samples:,}")
    print(f"VAL   targets {smp_va.target_dates[0].date()}..{smp_va.target_dates[-1].date()} "
          f"n={smp_va.n_targets} days x {smp_va.n_cells} cells = {smp_va.n_samples:,}")

    head = TemporalHead(latent=ck["latent"], hidden=ck["latent"])
    dec_state = {k.replace("decoder.", ""): v for k, v in ck["state_dict"].items()
                 if k.startswith("decoder.")}
    head.init_decoder_from(dec_state)
    n_gru = sum(p.numel() for p in head.gru.parameters())
    n_dec = sum(p.numel() for p in head.decoder.parameters())
    print(f"trainable={head.n_trainable:,} (gru {n_gru:,} + decoder {n_dec:,})  "
          f"frozen={n_frozen:,}")

    opt = torch.optim.Adam(head.parameters(), lr=float(TR["learning_rate"]))
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, factor=float(TR["lr_factor"]), patience=int(TR["lr_patience"]))

    ckpt = MODELS / f"phase6b_l3_{args.tag}.pt"
    best = float("inf")
    best_ep = -1
    bad = 0
    hist = []
    t0 = time.time()
    for ep in range(1, int(TR["max_epochs"]) + 1):
        te = time.time()
        run = 0.0
        n = 0.0
        for t, (seq, ctx, Yz, M, _) in smp_tr.batches(shuffle=True, seed=args.seed + ep):
            pred = head(torch.from_numpy(seq), torch.from_numpy(ctx))
            loss = masked_mse(pred, torch.from_numpy(Yz), torch.from_numpy(M))
            opt.zero_grad()
            loss.backward()
            opt.step()
            run += float(loss.detach()) * smp_tr.n_cells
            n += smp_tr.n_cells
        tr_l = run / n
        va_l = val_loss(head, smp_va)
        sched.step(va_l)
        lr_now = opt.param_groups[0]["lr"]
        hist.append({"epoch": ep, "train_loss": tr_l, "val_loss": va_l,
                     "lr": lr_now, "seconds": time.time() - te})
        flag = ""
        if va_l < best - 1e-6:
            best, best_ep, bad = va_l, ep, 0
            torch.save({"state_dict": head.state_dict(), "window": args.window,
                        "seed": args.seed, "epoch": ep, "val_loss": va_l,
                        "latent": ck["latent"], "depths": DEPTHS,
                        "l2_checkpoint": str(L3["frozen"]["l2_checkpoint"]),
                        "l2_encoder_sha256": fp_before,
                        "n_trainable": head.n_trainable, "n_frozen": n_frozen,
                        "selection": "validation only; test never inspected"}, ckpt)
            flag = "  <- best"
        else:
            bad += 1
        print(f"epoch {ep:3d}  train {tr_l:.5f}  val {va_l:.5f}  lr {lr_now:.2e}  "
              f"{time.time()-te:5.0f}s{flag}", flush=True)
        if bad >= int(TR["early_stopping_patience"]):
            print(f"early stopping after {bad} epochs without improvement")
            break

    fp_after = encoder_fingerprint(l2.encoder.state_dict())
    assert fp_after == fp_before, "FROZEN ENCODER CHANGED during L3 training"
    print(f"encoder unchanged: {fp_before[:16]} == {fp_after[:16]}  OK")

    json.dump({"tag": args.tag, "window": args.window, "seed": args.seed,
               "epochs_run": len(hist), "best_epoch": best_ep, "best_val_loss": best,
               "runtime_seconds": time.time() - t0, "n_trainable": head.n_trainable,
               "n_frozen": n_frozen,
               "train_targets": int(smp_tr.n_targets), "val_targets": int(smp_va.n_targets),
               "train_samples": int(smp_tr.n_samples), "val_samples": int(smp_va.n_samples),
               "encoder_sha256_before": fp_before, "encoder_sha256_after": fp_after,
               "history": hist},
              open(MODELS / f"phase6b_l3_{args.tag}_training.json", "w"), indent=2)
    print(f"best epoch {best_ep}  val {best:.5f}  runtime {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
