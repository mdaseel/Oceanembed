"""L2: the spatial Satellite Embedding Engine.

Encoder: a small CNN over a 17x17 x 8-channel surface patch producing an
explicit latent vector ``z`` (the satellite embedding). Every convolution is
'valid' (unpadded) with dilations chosen so the receptive field is exactly the
patch size and the spatial extent collapses to 1x1:

    17 -(3x3,d=1)-> 15 -(3x3,d=2)-> 11 -(3x3,d=4)-> 3 -(3x3,d=1)-> 1
    RF:        3            7             15            17

That property is what makes this experiment affordable. Because the network is
purely convolutional and unpadded, running it once over a whole padded
101x241 field yields the embedding for EVERY cell simultaneously, sharing the
computation between overlapping patches - identical results to extracting
24 M patches one at a time, roughly 289x less work. ``forward_field`` and
``forward_patch`` are asserted numerically equal in the tests.

Decoder: z concatenated with lat, lon, sin(doy), cos(doy) -> 15 depths.
The encoder never sees any temperature; targets enter only through the loss.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from .patches import N_CHANNELS

CONTEXT_DIM = 4          # lat, lon, doy_sin, doy_cos


def dilation_schedule(patch: int) -> list[int]:
    """3x3 dilations whose receptive field is exactly ``patch``.

    With 3x3 kernels, RF = 1 + 2*sum(dilations) and the unpadded spatial size
    shrinks by 2*sum(dilations) = patch-1, so the patch collapses to exactly
    1x1. Doubling dilations then a final d=1 keeps the layer count at
    O(log patch): 9 -> [1,2,1], 17 -> [1,2,4,1], 33 -> [1,2,4,8,1].
    """
    if patch < 3 or patch % 2 == 0:
        raise ValueError(f"patch must be odd and >= 3, got {patch}")
    need = (patch - 1) // 2
    dil, total = [], 0
    d = 1
    while total + d <= need:
        dil.append(d); total += d; d *= 2
    if total < need:
        dil.append(need - total)          # remainder as a final d=1-style step
    assert sum(dil) == need, (dil, need)
    return dil


class SpatialEncoder(nn.Module):
    """7 surface channels + validity mask -> satellite embedding z."""

    def __init__(self, in_ch: int = N_CHANNELS, widths=(32, 64, 64),
                 latent: int = 32, patch: int = 17):
        super().__init__()
        dil = dilation_schedule(patch)
        chans = [in_ch] + list(widths)[:max(len(dil) - 1, 0)]
        while len(chans) < len(dil):
            chans.append(widths[-1])
        layers = []
        for k, d in enumerate(dil):
            out_c = latent if k == len(dil) - 1 else chans[k + 1]
            layers += [nn.Conv2d(chans[k], out_c, 3, dilation=d), nn.ReLU()]
        self.conv = nn.Sequential(*layers)
        self.dilations = dil
        self.latent = latent
        self.patch = patch
        self.receptive_field = 1 + 2 * sum(dil)

    def forward_field(self, x: torch.Tensor) -> torch.Tensor:
        """(B, C, H, W) padded field -> (B, latent, H-16, W-16)."""
        return self.conv(x)

    def forward_patch(self, x: torch.Tensor) -> torch.Tensor:
        """(B, C, 17, 17) patches -> (B, latent)."""
        z = self.conv(x)
        assert z.shape[-1] == 1 and z.shape[-2] == 1, z.shape
        return z[:, :, 0, 0]

    forward = forward_patch


class Decoder(nn.Module):
    def __init__(self, latent: int = 32, context: int = CONTEXT_DIM,
                 hidden=(128, 128), n_out: int = 15):
        super().__init__()
        layers, d = [], latent + context
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU()]
            d = h
        layers += [nn.Linear(d, n_out)]
        self.net = nn.Sequential(*layers)

    def forward(self, z, ctx):
        return self.net(torch.cat([z, ctx], dim=1))


class L2EmbeddingModel(nn.Module):
    """Satellite Embedding Engine: patch -> z -> (+context) -> 15 depths."""

    def __init__(self, in_ch: int = N_CHANNELS, widths=(32, 64, 64),
                 latent: int = 32, decoder_hidden=(128, 128), n_out: int = 15,
                 patch: int = 17):
        super().__init__()
        self.encoder = SpatialEncoder(in_ch, widths, latent, patch)
        self.patch = patch
        self.decoder = Decoder(latent, CONTEXT_DIM, decoder_hidden, n_out)
        self.latent_dim = latent
        self.n_out = n_out

    def embed_patch(self, patches: torch.Tensor) -> torch.Tensor:
        """Named accessor for the satellite embedding z."""
        return self.encoder.forward_patch(patches)

    def embed_field(self, field: torch.Tensor) -> torch.Tensor:
        """z for every cell of a padded field, in one pass."""
        return self.encoder.forward_field(field)

    def forward(self, patches: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.embed_patch(patches), ctx)

    def forward_from_z(self, z: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        return self.decoder(z, ctx)

    @property
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())

    @property
    def n_encoder_parameters(self) -> int:
        return sum(p.numel() for p in self.encoder.parameters())
