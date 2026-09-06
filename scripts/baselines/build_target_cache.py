"""Materialise GLORYS targets once per split (separate store from embeddings)."""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import pandas as pd, yaml
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.embedding_cache import EmbeddingCache, TargetCache

B6 = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = B6["targets"]["depths_m"]
EMB = REPO_ROOT / "outputs" / "embeddings"
TGT = REPO_ROOT / "outputs" / "targets_cache"

ap = argparse.ArgumentParser()
ap.add_argument("--split", nargs="*", default=["train", "validation"])
ap.add_argument("--allow-test", action="store_true")
a = ap.parse_args()
if "test" in a.split and not a.allow_test:
    raise SystemExit("test target cache requires --allow-test (post-freeze only)")
for sp in a.split:
    tc = TargetCache(TGT, sp)
    if tc.exists():
        print(f"[{sp}] target cache present - skipping"); continue
    t0 = time.time()
    ds = splits.open_split(sp, allow_test=a.allow_test)
    ec = EmbeddingCache(EMB, sp).load()
    print(f"[{sp}] building targets for {len(ec.dates)} days x {len(ec.r)} cells")
    tc.build(ds, DEPTHS, ec.r, ec.c, ec.dates)
    print(f"[{sp}] done in {time.time()-t0:.0f}s")
