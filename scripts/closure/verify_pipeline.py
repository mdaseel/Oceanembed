"""Equivalence and throughput check for the closure training pipeline.

Two things are established before any closure model is trained:

1. ``CachedDaySampler`` is behaviourally identical to the sampler that trained
   the frozen L2 - proved by reproducing the frozen L2's recorded best
   validation loss to floating tolerance, not by inspection;
2. how fast an epoch actually is on this machine, so the compute budget in the
   pre-registration is a measured decision rather than a guess.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import torch
import yaml

from oceanembed.closure.sampling import CachedDaySampler
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import masked_mse
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
CACHE = REPO_ROOT / "outputs" / "targets_cache"


def val_loss(model, smp, stride=1) -> float:
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for t, (field, ctx, Yz, M, _) in smp.days(stride=stride):
            z = model.embed_field(torch.from_numpy(field)[None])[0]
            pred = model.forward_from_z(z[:, smp.r, smp.c].T, torch.from_numpy(ctx))
            tot += float(masked_mse(pred, torch.from_numpy(Yz),
                                    torch.from_numpy(M))) * smp.n_cells
            n += smp.n_cells
    return tot / max(n, 1)


def main() -> int:
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu",
                    weights_only=False)
    l2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    l2.load_state_dict(ck["state_dict"])
    l2.eval()
    patch = int(ck["patch"])

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")

    ds_va = splits.open_split("validation")
    smp_cached = CachedDaySampler(ds_va, DEPTHS, fs, ts, patch, CACHE, "validation")
    smp_ref = DayFieldSampler(ds_va, DEPTHS, fs, ts, patch=patch)

    print(f"cells: cached={smp_cached.n_cells} reference={smp_ref.n_cells}")
    assert smp_cached.n_cells == smp_ref.n_cells
    assert np.array_equal(smp_cached.r, smp_ref.r)
    assert np.array_equal(smp_cached.target_mask, smp_ref.target_mask)

    # Day-level agreement. Inputs, context and the target mask must be BITWISE
    # identical - those are the things that decide what the model sees and which
    # samples exist. The targets themselves differ by the float32 storage of the
    # cache (the Zarr targets are float64): about 1e-6 degC, which is nine orders
    # of magnitude below the model's own error and is reported rather than
    # hidden.
    worst = 0.0
    for t in (0, 100, 364):
        a = smp_cached.day(t)
        b = smp_ref.day(t)
        for k, name in enumerate(("field", "ctx", "M")):
            assert np.array_equal(a[k if name != "M" else 3],
                                  b[k if name != "M" else 3]),                 f"day {t}: {name} differs"
        assert np.array_equal(np.isnan(a[4]), np.isnan(b[4])),             f"day {t}: target NaN pattern differs"
        worst = max(worst, float(np.nanmax(np.abs(a[4] - b[4]))))
        assert worst < 1e-4, f"day {t}: targets differ by {worst:.2e} degC"
    print("inputs, context and target mask are BITWISE identical on days 0/100/364")
    print(f"target values differ by at most {worst:.2e} degC "
          f"(float32 cache vs float64 Zarr)")

    t0 = time.time()
    vl = val_loss(l2, smp_cached)
    dt = time.time() - t0
    recorded = json.load(open(MODELS / "phase6b_l2_final_training.json"))["best_val_loss"]
    print(f"validation loss via cached sampler: {vl:.17f}")
    print(f"recorded frozen L2 best_val_loss  : {recorded:.17f}")
    print(f"absolute difference               : {abs(vl - recorded):.3e}")
    assert abs(vl - recorded) / recorded < 1e-6,         "the closure pipeline does NOT reproduce the frozen L2 validation loss"
    print(f"validation pass over {smp_cached.n_days} days took {dt:.0f}s "
          f"({dt / smp_cached.n_days * 1000:.0f} ms/day)")

    # measured training throughput on 30 train days (forward + backward)
    ds_tr = splits.open_split("train")
    smp_tr = CachedDaySampler(ds_tr, DEPTHS, fs, ts, patch, CACHE, "train")
    model = L2EmbeddingModel(latent=ck["latent"], patch=patch)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    n_probe = 30
    t0 = time.time()
    for t, (field, ctx, Yz, M, _) in smp_tr.days(stride=max(1, smp_tr.n_days // n_probe)):
        z = model.embed_field(torch.from_numpy(field)[None])[0]
        pred = model.forward_from_z(z[:, smp_tr.r, smp_tr.c].T, torch.from_numpy(ctx))
        loss = masked_mse(pred, torch.from_numpy(Yz), torch.from_numpy(M))
        opt.zero_grad(); loss.backward(); opt.step()
    dt = time.time() - t0
    per_day = dt / n_probe
    print(f"\ntrain step: {per_day * 1000:.0f} ms/day measured over {n_probe} days")
    print(f"projected full epoch (2192 train days + 365 val): "
          f"{(2192 * per_day + 365 * 0.06) / 60:.1f} min")
    json.dump({"validation_loss_cached": vl, "recorded_best_val_loss": recorded,
               "train_ms_per_day": per_day * 1000,
               "train_days": int(smp_tr.n_days),
               "val_days": int(smp_cached.n_days),
               "n_cells_train": int(smp_tr.n_cells),
               "n_cells_validation": int(smp_cached.n_cells)},
              open(REPO_ROOT / "outputs" / "architecture_closure"
                   / "pipeline_equivalence.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
