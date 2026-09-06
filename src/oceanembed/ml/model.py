"""L1: a deliberately small pointwise MLP, plus the per-depth masked loss.

The model sees ONE grid cell on ONE day. It has no access to neighbouring
cells, spatial patches, previous or future days, convolutional features,
attention, recurrent state, or latent embeddings. That blindness is the point:
whatever skill it shows is attributable to the surface->subsurface mapping
itself and not to spatial or temporal context, which makes it the honest
baseline that the Satellite Embedding Engine must later beat.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class PointwiseMLP(nn.Module):
    def __init__(self, n_features: int = 11, hidden=(256, 256, 128), n_out: int = 15):
        super().__init__()
        layers, d = [], n_features
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU()]
            d = h
        layers += [nn.Linear(d, n_out)]
        self.net = nn.Sequential(*layers)
        self.n_features, self.hidden, self.n_out = n_features, tuple(hidden), n_out

    def forward(self, x):
        return self.net(x)

    @property
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())


def masked_mse(pred: torch.Tensor, target: torch.Tensor,
               mask: torch.Tensor) -> torch.Tensor:
    """Mean squared error over valid targets only.

    Depths where ``mask`` is False contribute nothing - no gradient, no
    denominator. Missing targets are never replaced by zero, and no
    sub-seafloor temperature is invented.

    Averaging over valid entries (rather than per-depth then averaging) would
    let shallow depths dominate simply because more cells have shallow data, so
    the mean is taken per depth first and then across depths that had any valid
    entry. Combined with per-depth target standardisation upstream, every depth
    contributes on an equal footing.
    """
    # Build the residual inside the mask: 0 * NaN is NaN in torch, so a NaN
    # sitting in a masked-out target would otherwise poison the whole depth.
    diff = torch.where(mask, pred - target, torch.zeros_like(pred))
    m = mask.float()
    se = diff ** 2
    per_depth_n = m.sum(dim=0)                       # (n_depths,)
    has = per_depth_n > 0
    if not bool(has.any()):
        return pred.sum() * 0.0
    per_depth_mse = se.sum(dim=0)[has] / per_depth_n[has]
    return per_depth_mse.mean()


def set_seed(seed: int) -> None:
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
