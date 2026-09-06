"""Train L1, the pointwise MLP. Gradients from TRAIN only; selection on VALIDATION."""
from __future__ import annotations

import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np, pandas as pd, torch, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.dataset import PointwiseSampler
from oceanembed.ml.features import FEATURE_NAMES
from oceanembed.ml.model import PointwiseMLP, masked_mse, set_seed
from oceanembed.ml.scaler import ZScoreScaler

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
TR = CFG["training"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
MODELS = REPO_ROOT / CFG["paths"]["models"]
MODELS.mkdir(parents=True, exist_ok=True)
CKPT = MODELS / "phase6b_l1_mlp.pt"


def evaluate_loss(model, sampler, fs, ts, device) -> float:
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for X, Y, M, *_ in sampler.blocks():
            xb = torch.from_numpy(fs.transform(X).astype("float32")).to(device)
            yb = torch.from_numpy(ts.transform(Y).astype("float32")).to(device)
            mb = torch.from_numpy(M).to(device)
            tot += float(masked_mse(model(xb), yb, mb)) * len(X)
            n += len(X)
    model.train()
    return tot / max(n, 1)


def main() -> int:
    seed = int(TR["seed"]); set_seed(seed)
    device = torch.device("cpu")

    ds_tr = splits.open_split("train")
    ds_va = splits.open_split("validation")
    t_tr = pd.DatetimeIndex(ds_tr.time.values); t_va = pd.DatetimeIndex(ds_va.time.values)
    assert not splits.contains_test_dates(t_tr), "LEAK: test dates in train"
    assert not splits.contains_test_dates(t_va), "LEAK: test dates in validation"
    assert t_tr.max() < t_va.min(), "train must precede validation"
    print(f"TRAIN      {t_tr[0].date()} .. {t_tr[-1].date()} ({len(t_tr)} d)")
    print(f"VALIDATION {t_va[0].date()} .. {t_va[-1].date()} ({len(t_va)} d)")

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"
    print(f"scalers: frozen, fitted_on={fs.fitted_on}")

    smp_tr = PointwiseSampler(ds_tr, DEPTHS, chunk_days=64)
    smp_va = PointwiseSampler(ds_va, DEPTHS, chunk_days=64)

    model = PointwiseMLP(len(FEATURE_NAMES), tuple(CFG["model"]["hidden"]), len(DEPTHS)).to(device)
    print(f"model: {FEATURE_NAMES.__len__()} -> {CFG['model']['hidden']} -> {len(DEPTHS)}"
          f"  ({model.n_parameters:,} params)")
    opt = torch.optim.Adam(model.parameters(), lr=float(TR["learning_rate"]))
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, factor=float(TR["lr_factor"]), patience=int(TR["lr_patience"]))

    best, best_epoch, bad, hist = float("inf"), -1, 0, []
    t_start = time.time()
    for epoch in range(1, int(TR["max_epochs"]) + 1):
        te = time.time(); run, n = 0.0, 0
        for X, Y, M in smp_tr.minibatches(int(TR["batch_size"]), shuffle=True, seed=seed + epoch):
            xb = torch.from_numpy(fs.transform(X).astype("float32")).to(device)
            yb = torch.from_numpy(ts.transform(Y).astype("float32")).to(device)
            mb = torch.from_numpy(M).to(device)
            opt.zero_grad()
            loss = masked_mse(model(xb), yb, mb)
            loss.backward(); opt.step()
            run += float(loss) * len(X); n += len(X)
        tr_loss = run / n
        va_loss = evaluate_loss(model, smp_va, fs, ts, device)
        sched.step(va_loss)
        lr = opt.param_groups[0]["lr"]
        hist.append({"epoch": epoch, "train_loss": tr_loss, "val_loss": va_loss,
                     "lr": lr, "seconds": time.time() - te})
        flag = ""
        if va_loss < best - 1e-6:
            best, best_epoch, bad = va_loss, epoch, 0
            torch.save({"state_dict": model.state_dict(), "epoch": epoch,
                        "val_loss": va_loss, "train_loss": tr_loss, "seed": seed,
                        "n_features": len(FEATURE_NAMES), "hidden": list(CFG["model"]["hidden"]),
                        "n_out": len(DEPTHS), "depths": DEPTHS,
                        "feature_names": FEATURE_NAMES}, CKPT)
            flag = "  <- best (saved)"
        else:
            bad += 1
        print(f"epoch {epoch:3d}  train {tr_loss:.5f}  val {va_loss:.5f}  "
              f"lr {lr:.2e}  {time.time()-te:5.0f}s{flag}")
        if bad >= int(TR["early_stopping_patience"]):
            print(f"early stopping: no improvement for {bad} epochs")
            break

    runtime = time.time() - t_start
    meta = {"seed": seed, "architecture": f"{len(FEATURE_NAMES)}->"
            f"{'->'.join(map(str, CFG['model']['hidden']))}->{len(DEPTHS)}",
            "parameter_count": model.n_parameters, "optimizer": "adam",
            "learning_rate": float(TR["learning_rate"]), "batch_size": int(TR["batch_size"]),
            "max_epochs": int(TR["max_epochs"]), "epochs_run": len(hist),
            "early_stopping_epoch": best_epoch, "best_val_loss": best,
            "final_train_loss": hist[-1]["train_loss"], "runtime_seconds": runtime,
            "train_samples": int(smp_tr.n_samples), "val_samples": int(smp_va.n_samples),
            "loss": "per-depth masked MSE in per-depth standardised target space",
            "device": "cpu", "torch": torch.__version__, "history": hist}
    json.dump(meta, open(MODELS / "phase6b_l1_training.json", "w"), indent=2)
    print(f"\nbest epoch {best_epoch}  val {best:.5f}  runtime {runtime/60:.1f} min")
    print(f"checkpoint: {CKPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
