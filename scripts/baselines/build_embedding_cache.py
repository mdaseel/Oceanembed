"""Encode every day of a split ONCE with the frozen L2 encoder and cache z."""
from __future__ import annotations

import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import torch, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.embedding_cache import EmbeddingCache, encoder_fingerprint
from oceanembed.ml.l2_dataset import DayFieldSampler
from oceanembed.ml.l2_model import L2EmbeddingModel
from oceanembed.ml.scaler import ZScoreScaler
from oceanembed.ml.temporal import freeze_encoder

L3 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6c_l3.yaml", encoding="utf-8"))
B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
BASE = REPO_ROOT / B6["paths"]["baselines"]
CACHE_DIR = REPO_ROOT / L3["cache"]["dir"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", nargs="*", default=["train", "validation"],
                    choices=["train", "validation", "test"])
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if "test" in args.split and not args.allow_test:
        raise SystemExit("Test embeddings must not be precomputed before the L3 "
                         "architecture is frozen. Pass --allow-test only then.")

    ck = torch.load(REPO_ROOT / L3["frozen"]["l2_checkpoint"], map_location="cpu",
                    weights_only=False)
    model = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    model.load_state_dict(ck["state_dict"])
    freeze_encoder(model.encoder)
    fp = encoder_fingerprint(model.encoder.state_dict())
    print(f"frozen L2 encoder: patch={ck['patch']} latent={ck['latent']} "
          f"sha256={fp[:16]}  trainable_encoder_params="
          f"{sum(p.numel() for p in model.encoder.parameters() if p.requires_grad)}")

    fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
    ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert fs.fitted_on == "train" and ts.fitted_on == "train"

    for split in args.split:
        cache = EmbeddingCache(CACHE_DIR, split)
        if cache.exists() and not args.force:
            cache.load()
            try:
                cache.verify_encoder(model.encoder.state_dict())
                print(f"[{split}] cache present and matches encoder - skipping")
                continue
            except RuntimeError as e:
                print(f"[{split}] rebuilding: {e}")
        t0 = time.time()
        ds = splits.open_split(split, allow_test=args.allow_test)
        smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
        print(f"[{split}] {smp.n_days} days x {smp.n_cells} cells")
        cache.build(smp, model)
        print(f"[{split}] done in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
