"""Provenance-keyed replay cache — a PERFORMANCE optimization and nothing else.

Master prompt §7A.2A: a cache entry may contain ONLY an output previously
produced by the actual frozen-L2 replay pipeline. Fabricated, hand-authored or
placeholder values must never enter it, and a cache hit must be provably the
output of the exact frozen pipeline that would run today.

That is enforced by the key, not by trust: the identity includes the date, the
frozen L2 checkpoint hash, the scaler and climatology hashes, the processing
version and the canonical grid version. If any of those change, every previous
entry becomes unreachable rather than silently reused.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

CACHE_FORMAT_VERSION = 1


def cache_identity(date: str, provenance: dict) -> dict:
    """The full identity a cached field is keyed on."""
    return {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "date": str(date),
        "l2_state_dict_sha256": provenance["l2_state_dict_sha256"],
        "l2_encoder_sha256": provenance["l2_encoder_sha256"],
        "feature_scaler_sha256": provenance["feature_scaler_sha256"],
        "target_scaler_sha256": provenance["target_scaler_sha256"],
        "climatology_sha256": provenance["climatology_sha256"],
        "processing_version": provenance["processing_version"],
        "grid_version": provenance["grid_version"],
        "patch": provenance["patch"],
        "depths": provenance["depths_m"],
    }


def identity_key(identity: dict) -> str:
    blob = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ReplayCache:
    """Memory-mapped .npz store of previously computed authoritative fields."""

    def __init__(self, root: Path | str, enabled: bool = True):
        self.root = Path(root)
        self.enabled = bool(enabled)

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.root / f"{key}.npz", self.root / f"{key}.json"

    def get(self, date: str, provenance: dict):
        """Return (arrays, identity) on a valid hit, else None."""
        if not self.enabled:
            return None
        identity = cache_identity(date, provenance)
        key = identity_key(identity)
        npz, meta = self._paths(key)
        if not (npz.exists() and meta.exists()):
            return None
        try:
            stored = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt sidecar is a miss, not a crash
            return None
        # The key already encodes the identity, but re-checking makes a hash
        # collision or a hand-edited sidecar fail closed rather than silently
        # serve the wrong provenance.
        if stored.get("identity") != identity:
            return None
        with np.load(npz) as z:
            arrays = {k: z[k] for k in z.files}
        return arrays, identity

    def put(self, date: str, provenance: dict, arrays: dict) -> str:
        if not self.enabled:
            return ""
        identity = cache_identity(date, provenance)
        key = identity_key(identity)
        npz, meta = self._paths(key)
        self.root.mkdir(parents=True, exist_ok=True)
        # np.savez_compressed APPENDS ".npz" to any path that does not already
        # end in it, so a "*.npz.part" temp name would silently become
        # "*.npz.part.npz". Writing through an open handle avoids that rename.
        tmp = self.root / f"{key}.part"
        with open(tmp, "wb") as fh:
            np.savez_compressed(fh, **arrays)
        tmp.replace(npz)
        meta.write_text(json.dumps(
            {"identity": identity,
             "written_by": "oceanembed.replay.engine.replay_field",
             "content": "authoritative frozen-L2 replay output only; never "
                        "fabricated, hand-authored or placeholder values"},
            indent=2), encoding="utf-8")
        return key

    def clear(self) -> int:
        """Remove every entry. Returns how many files were deleted."""
        if not self.root.exists():
            return 0
        n = 0
        for p in list(self.root.glob("*.npz")) + list(self.root.glob("*.json")):
            p.unlink()
            n += 1
        return n
