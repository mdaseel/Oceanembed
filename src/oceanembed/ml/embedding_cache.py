"""Cache of frozen-L2 satellite embeddings, one z vector per valid cell per day.

Why this exists: a naive temporal model would re-run the 33x33 CNN once per
timestep per sample, multiplying the already-expensive L2 spatial cost by the
window length. Because the encoder is FROZEN, every z is a fixed function of
that day's surface field, so each date can be encoded exactly once and reused
by every window length and every seed.

The cache holds only surface-derived embeddings. It contains no temperature,
no target, and no climatology - a property asserted in the tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

Z_FILE = "z.npy"
META_FILE = "meta.json"


def encoder_fingerprint(encoder_state: dict) -> str:
    """Stable hash of the frozen encoder weights, recorded as cache provenance."""
    h = hashlib.sha256()
    for k in sorted(encoder_state):
        t = encoder_state[k]
        h.update(k.encode("utf-8"))
        h.update(np.ascontiguousarray(t.detach().cpu().numpy()).tobytes())
    return h.hexdigest()


class EmbeddingCache:
    """Memory-mapped (n_days, n_cells, latent) float32 store for one split."""

    def __init__(self, root: Path | str, split: str):
        self.dir = Path(root) / split
        self.split = split

    # ------------------------------------------------------------- build
    def build(self, sampler, model, log=print) -> "EmbeddingCache":
        """Encode every day of ``sampler`` once with the frozen encoder."""
        self.dir.mkdir(parents=True, exist_ok=True)
        n_days, n_cells = sampler.n_days, sampler.n_cells
        latent = model.latent_dim
        z = np.lib.format.open_memmap(self.dir / Z_FILE, mode="w+", dtype="float32",
                                      shape=(n_days, n_cells, latent))
        model.eval()
        with torch.no_grad():
            for t in range(n_days):
                field, _, _, _, _ = sampler.day(t)
                zf = model.embed_field(torch.from_numpy(field)[None])[0]
                z[t] = zf[:, sampler.r, sampler.c].T.numpy().astype("float32")
                if (t + 1) % 200 == 0:
                    log(f"    cached {t+1}/{n_days} days")
        z.flush()
        meta = {
            "split": self.split,
            "n_days": int(n_days),
            "n_cells": int(n_cells),
            "latent": int(latent),
            "dates": [str(d)[:10] for d in sampler.times],
            "cell_row": sampler.r.astype(int).tolist(),
            "cell_col": sampler.c.astype(int).tolist(),
            "patch": int(model.patch),
            "encoder_sha256": encoder_fingerprint(model.encoder.state_dict()),
            "contains_targets": False,
            "contains_climatology": False,
            "source": "frozen L2 spatial encoder applied to surface fields only",
        }
        json.dump(meta, open(self.dir / META_FILE, "w"), indent=2)
        log(f"    wrote {self.dir / Z_FILE} shape=({n_days},{n_cells},{latent})")
        return self

    # -------------------------------------------------------------- load
    def load(self) -> "EmbeddingCache":
        self.meta = json.load(open(self.dir / META_FILE, encoding="utf-8"))
        self.z = np.load(self.dir / Z_FILE, mmap_mode="r")
        self.dates = pd.DatetimeIndex(self.meta["dates"])
        self.r = np.asarray(self.meta["cell_row"], dtype=int)
        self.c = np.asarray(self.meta["cell_col"], dtype=int)
        assert self.z.shape == (self.meta["n_days"], self.meta["n_cells"],
                                self.meta["latent"]), self.z.shape
        return self

    def verify_encoder(self, encoder_state: dict) -> None:
        """Refuse to use a cache built by a different encoder."""
        got = encoder_fingerprint(encoder_state)
        want = self.meta["encoder_sha256"]
        if got != want:
            raise RuntimeError(
                f"embedding cache was built with encoder {want[:16]} but the "
                f"loaded encoder is {got[:16]}; rebuild the cache")

    def exists(self) -> bool:
        return (self.dir / Z_FILE).exists() and (self.dir / META_FILE).exists()

    def index_of(self, date) -> int:
        hits = np.where(self.dates == pd.Timestamp(date))[0]
        if not len(hits):
            raise KeyError(f"{date} not in {self.split} cache")
        return int(hits[0])


Y_FILE = "y.npy"


class TargetCache:
    """Cached GLORYS targets, kept in a SEPARATE directory from the embeddings.

    Profiling showed that re-reading 15 depth variables from Zarr for every
    target date cost ~68% of L3 epoch time, because a one-day read decompresses
    a whole 32-day chunk fifteen times over. Targets are static, so they are
    materialised once.

    This deliberately does NOT live inside the embedding cache: the z store must
    remain provably free of any temperature information, since z is the model
    input. Targets are only ever consumed by the loss and the metrics.
    """

    def __init__(self, root: Path | str, split: str):
        self.dir = Path(root) / split
        self.split = split

    def build(self, ds, depths, r, c, dates, log=print) -> "TargetCache":
        self.dir.mkdir(parents=True, exist_ok=True)
        n_days, n_cells = len(dates), len(r)
        y = np.lib.format.open_memmap(self.dir / Y_FILE, mode="w+", dtype="float32",
                                      shape=(n_days, n_cells, len(depths)))
        for t in range(n_days):
            for k, d in enumerate(depths):
                y[t, :, k] = ds[f"temp_{d}m"].isel(time=t).values[r, c]
            if (t + 1) % 300 == 0:
                log(f"    targets {t+1}/{n_days}")
        y.flush()
        json.dump({"split": self.split, "n_days": int(n_days), "n_cells": int(n_cells),
                   "depths": [int(d) for d in depths],
                   "dates": [str(x)[:10] for x in dates],
                   "note": "GLORYS targets only; never used as model input"},
                  open(self.dir / META_FILE, "w"), indent=2)
        log(f"    wrote {self.dir / Y_FILE} shape=({n_days},{n_cells},{len(depths)})")
        return self

    def load(self) -> "TargetCache":
        self.meta = json.load(open(self.dir / META_FILE, encoding="utf-8"))
        self.y = np.load(self.dir / Y_FILE, mmap_mode="r")
        self.dates = pd.DatetimeIndex(self.meta["dates"])
        return self

    def exists(self) -> bool:
        return (self.dir / Y_FILE).exists() and (self.dir / META_FILE).exists()
