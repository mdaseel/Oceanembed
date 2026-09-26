"""Channel attribution over the frozen L2 (PREREGISTRATION §1).

Integrated Gradients, implemented directly. The attribution is computed on the
receptive-field patch centred on the requested cell: because the encoder is
unpadded with a receptive field exactly the patch size, no input outside that
patch can influence the cell's output, so nothing is truncated.

Wording is "model sensitivity / attribution". An attribution says how the frozen
network's output responds along a straight path from a neutral input to the
actual input; it is not a statement that a surface variable causes subsurface
temperature.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from ..config import REPO_ROOT
from ..ml.patches import N_DATA_CHANNELS
from . import frozen
from .channels import CHANNELS, LABELS, SHORT

METHOD = "integrated_gradients"
STEPS = 64
BASELINE = "seven data planes = 0 in standardised space (training mean); mask and context actual"
VERSION = "science-attribution-1"
WORDING = ("Model sensitivity / attribution of the frozen L2 output to each surface "
           "channel. Not causal: it does not say a surface variable causes subsurface "
           "temperature.")
CACHE_DIR = REPO_ROOT / "outputs" / "science" / "cache" / "attribution"


def patch_at(field: np.ndarray, row: int, col: int, patch: int) -> np.ndarray:
    """Receptive-field patch whose centre is domain cell (row, col)."""
    return field[:, row:row + patch, col:col + patch]


def integrated_gradients(model, patch: np.ndarray, ctx: np.ndarray, steps: int = STEPS):
    """IG of all 15 standardised outputs w.r.t. the seven data planes of one patch.

    Returns (attr (15, 7, P, P), f_x (15,), f_baseline (15,)) in standardised
    target units.
    """
    x = torch.from_numpy(np.ascontiguousarray(patch, dtype="float32"))[None]
    base = x.clone()
    base[:, :N_DATA_CHANNELS] = 0.0
    c = torch.from_numpy(np.ascontiguousarray(ctx, dtype="float32")).reshape(1, -1)
    alphas = (torch.arange(steps, dtype=torch.float32) + 0.5) / steps
    path = base + alphas[:, None, None, None] * (x - base)
    path.requires_grad_(True)
    out = model.decoder(model.encoder.forward_patch(path), c.expand(steps, -1))
    n_out = out.shape[1]
    delta = (x - base)[0, :N_DATA_CHANNELS]
    attr = np.empty((n_out, N_DATA_CHANNELS) + tuple(patch.shape[1:]), dtype="float64")
    for d in range(n_out):
        grad = torch.autograd.grad(out[:, d].sum(), path, retain_graph=d < n_out - 1)[0]
        attr[d] = (delta * grad[:, :N_DATA_CHANNELS].mean(0)).detach().numpy()
    with torch.no_grad():
        f_x = model.decoder(model.encoder.forward_patch(x), c)[0].numpy().astype("float64")
        f_b = model.decoder(model.encoder.forward_patch(base), c)[0].numpy().astype("float64")
    return attr, f_x, f_b


def cache_key(model_sha: str, date: str, row: int, col: int, steps: int = STEPS,
              source: str = "historical") -> dict:
    return {"model_sha256": model_sha, "date": date, "row": int(row), "col": int(col),
            "method": METHOD, "steps": int(steps), "baseline": BASELINE,
            "version": VERSION, "source": source}


def _cache_path(key: dict) -> Path:
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def attribute_cell(engine, field: np.ndarray, siv: np.ndarray, when, row: int, col: int,
                   steps: int = STEPS, source: str = "historical", use_cache: bool = True,
                   cache_dir: Path | None = None) -> dict:
    """Depth x channel attribution for one supported cell, in degC."""
    if not bool(siv[row, col]):
        raise ValueError("the selected cell has no valid surface input on this date")
    date = str(np.datetime_as_string(np.datetime64(when, "D")))
    key = cache_key(engine.l2_state_dict_sha256, date, row, col, steps, source)
    path = (Path(cache_dir) if cache_dir else CACHE_DIR) / _cache_path(key).name
    if use_cache and path.exists():
        hit = json.loads(path.read_text(encoding="utf-8"))
        if hit.get("key") == key:
            return {**hit, "cached": True}

    ctx = frozen.context(engine, np.array([row]), np.array([col]), when)[0]
    patch = patch_at(field, row, col, engine.patch)
    attr, f_x, f_b = integrated_gradients(engine.model, patch, ctx, steps)
    sigma = np.asarray(engine.target_scaler.std, dtype="float64")
    mu = np.asarray(engine.target_scaler.mean, dtype="float64")
    attr_c = attr * sigma[:, None, None, None]
    net = attr_c.sum(axis=(2, 3))                        # (15, 7) signed, degC
    gross = np.abs(attr_c).sum(axis=(2, 3))              # (15, 7) magnitude, degC
    share = gross / np.where(gross.sum(1, keepdims=True) > 0, gross.sum(1, keepdims=True), 1)
    completeness = np.abs(net.sum(1) - (f_x - f_b) * sigma)
    result = {
        "key": key,
        "date": date, "row": int(row), "col": int(col),
        "lat": float(engine.lat[row]), "lon": float(engine.lon[col]),
        "depths_m": [int(d) for d in engine_depths(engine)],
        "channels": list(CHANNELS),
        "channel_labels": [LABELS[c] for c in CHANNELS],
        "channel_short": [SHORT[c] for c in CHANNELS],
        "net_c": np.round(net, 6).tolist(),
        "gross_c": np.round(gross, 6).tolist(),
        "gross_share": np.round(share, 6).tolist(),
        "prediction_c": np.round(f_x * sigma + mu, 4).tolist(),
        "baseline_prediction_c": np.round(f_b * sigma + mu, 4).tolist(),
        "completeness_residual_c": np.round(completeness, 6).tolist(),
        "method": {"name": METHOD, "steps": steps, "baseline": BASELINE,
                   "integration": "midpoint Riemann sum along the straight path",
                   "patch": engine.patch, "units": "degC per output depth",
                   "net": "sum of signed attributions over the receptive-field patch",
                   "gross": "sum of absolute attributions over the patch",
                   "share": "gross magnitude divided by the seven-channel total at that depth"},
        "wording": WORDING,
        "model_sha256": engine.l2_state_dict_sha256,
        "version": VERSION,
        "cached": False,
    }
    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result), encoding="utf-8")
    return result


def engine_depths(engine) -> list[int]:
    from ..replay.engine import DEPTHS
    return list(DEPTHS)
