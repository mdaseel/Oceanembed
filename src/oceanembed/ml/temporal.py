"""L3 temporal fusion over frozen-L2 satellite embeddings.

A single small GRU consumes the sequence [z_(t-k+1), ..., z_t] and its final
hidden state is decoded, together with current-day context, to the 15-depth
profile at time t.

The GRU parameter count does not depend on sequence length, so the 1-day
control, the 3-day model and the 7-day model have IDENTICAL trainable
parameter counts and differ only in how much history they are shown. That is
what makes "does history help?" separable from "does extra capacity help?".
"""
from __future__ import annotations

import torch
import torch.nn as nn

from .l2_model import CONTEXT_DIM, Decoder


class TemporalHead(nn.Module):
    def __init__(self, latent: int = 32, hidden: int | None = None,
                 context: int = CONTEXT_DIM, decoder_hidden=(128, 128),
                 n_out: int = 15):
        super().__init__()
        hidden = latent if hidden is None else hidden
        self.gru = nn.GRU(input_size=latent, hidden_size=hidden,
                          num_layers=1, batch_first=True)
        self.decoder = Decoder(hidden, context, decoder_hidden, n_out)
        self.latent, self.hidden, self.n_out = latent, hidden, n_out

    def forward(self, z_seq: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        """z_seq (B, T, latent) with z_seq[:, -1] = the CURRENT day."""
        out, _ = self.gru(z_seq)
        return self.decoder(out[:, -1, :], ctx)

    def init_decoder_from(self, l2_decoder_state: dict) -> None:
        """Warm-start from the L2 decoder; structurally identical by design."""
        self.decoder.load_state_dict(l2_decoder_state)

    @property
    def n_trainable(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def freeze_encoder(encoder: nn.Module) -> nn.Module:
    for p in encoder.parameters():
        p.requires_grad_(False)
    encoder.eval()
    return encoder
