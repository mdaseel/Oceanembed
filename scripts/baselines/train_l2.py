"""Train L2, the spatial Satellite Embedding Engine.

Gradients on TRAIN only; model selection on VALIDATION only. The locked test
split is never opened here.
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np, pandas as pd, torch, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.model import masked_mse, set_seed
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
MODELS.mkdir(parents=True, exist_ok=True)


def val_loss(model, smp) -> float:
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for t, (field, ctx, Yz, M, _) in smp.days():
            z = model.embed_field(torch.from_numpy(field)[None])[0]
            pred = model.forward_from_z(z[:, smp.r, smp.c].T, torch.from_numpy(ctx))
            tot += float(masked_mse(pred, torch.from_numpy(Yz),
                                    torch.from_numpy(M))) * smp.n_cells
            n += smp.n_cells
    model.train()
    return tot / max(n, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", type=int, default=17)
    ap.add_argument("--latent", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--stride", type=int, default=1, help="train-day stride (compute budget)")
    ap.add_argument("--val-stride", type=int, default=1)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    seed = int(CFG["training"]["seed"]); set_seed(seed)
    tag = args.tag or f"p{args.patch}"
    ck_path = MODELS / f"phase6b_l2_{tag}.pt"

    ds_tr = splits.open_split("train")
    ds_va = splits.open_split("validation")
    t_tr = pd.DatetimeIndex(ds_tr.time.values); t_va = pd.DatetimeIndex(ds_va.time.values)
    assert not splits.contains_test_dates(t_tr), "LEAK: test dates in train"
    assert not splits.contains_test_dates(t_va), "LEAK: test dates in validation"
    assert t_tr.max() < t_va.min()
    print(f"TRAIN {t_tr[0].date()}..{t_tr[-1].date()}  VALIDATION {t_va[0].date()}..{t_va[-1].date()}")

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    smp_tr = DayFieldSampler(ds_tr, DEPTHS, fs, ts, patch=args.patch)
    smp_va = DayFieldSampler(ds_va, DEPTHS, fs, ts, patch=args.patch)

    model = L2EmbeddingModel(latent=args.latent, patch=args.patch)
    print(f"L2 patch={args.patch} dilations={model.encoder.dilations} "
          f"RF={model.encoder.receptive_field} latent={args.latent}")
    print(f"params total={model.n_parameters:,} encoder={model.n_encoder_parameters:,}")
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=2)

    n_train_days = len(range(0, smp_tr.n_days, args.stride))
    print(f"train days/epoch={n_train_days} (stride {args.stride}), "
          f"samples/epoch={n_train_days*smp_tr.n_cells:,}")

    best, best_ep, bad, hist = float("inf"), -1, 0, []
    t_start = time.time()
    for ep in range(1, args.epochs + 1):
        te = time.time(); run, n = 0.0, 0
        for t, (field, ctx, Yz, M, _) in smp_tr.days(shuffle=True, seed=seed + ep,
                                                     stride=args.stride):
            z = model.embed_field(torch.from_numpy(field)[None])[0]
            pred = model.forward_from_z(z[:, smp_tr.r, smp_tr.c].T, torch.from_numpy(ctx))
            loss = masked_mse(pred, torch.from_numpy(Yz), torch.from_numpy(M))
            opt.zero_grad(); loss.backward(); opt.step()
            run += float(loss.detach()) * smp_tr.n_cells; n += smp_tr.n_cells
        tr_l = run / n
        va_l = val_loss(model, smp_va)
        sched.step(va_l)
        lr = opt.param_groups[0]["lr"]
        hist.append({"epoch": ep, "train_loss": tr_l, "val_loss": va_l,
                     "lr": lr, "seconds": time.time() - te})
        flag = ""
        if va_l < best - 1e-6:
            best, best_ep, bad = va_l, ep, 0
            torch.save({"state_dict": model.state_dict(),
                        "encoder_state_dict": model.encoder.state_dict(),
                        "epoch": ep, "val_loss": va_l, "train_loss": tr_l,
                        "patch": args.patch, "latent": args.latent,
                        "depths": DEPTHS, "seed": seed,
                        "dilations": model.encoder.dilations,
                        "receptive_field": model.encoder.receptive_field,
                        "n_parameters": model.n_parameters,
                        "n_encoder_parameters": model.n_encoder_parameters},
                       ck_path)
            flag = "  <- best"
        else:
            bad += 1
        print(f"epoch {ep:3d}  train {tr_l:.5f}  val {va_l:.5f}  lr {lr:.2e}  "
              f"{time.time()-te:5.0f}s{flag}", flush=True)
        if bad >= args.patience:
            print(f"early stopping after {bad} epochs without improvement")
            break

    meta = {"tag": tag, "patch": args.patch, "latent": args.latent, "seed": seed,
            "stride": args.stride, "epochs_run": len(hist), "best_epoch": best_ep,
            "best_val_loss": best, "runtime_seconds": time.time() - t_start,
            "n_parameters": model.n_parameters,
            "n_encoder_parameters": model.n_encoder_parameters,
            "dilations": model.encoder.dilations,
            "receptive_field": model.encoder.receptive_field,
            "train_days_per_epoch": n_train_days,
            "samples_per_epoch": n_train_days * smp_tr.n_cells,
            "loss": "per-depth masked MSE in per-depth standardised target space",
            "history": hist}
    json.dump(meta, open(MODELS / f"phase6b_l2_{tag}_training.json", "w"), indent=2)
    print(f"\nbest epoch {best_ep}  val {best:.5f}  runtime {(time.time()-t_start)/60:.1f} min")
    print(f"checkpoint {ck_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
