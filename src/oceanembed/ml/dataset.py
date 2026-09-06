"""Chunk-aware sample streaming from the model-ready Zarr stores.

The full record is 3,637 days x 24,341 cells; flattening it into one table
would be ~30 M rows and several GB. Instead this reads Zarr time-chunks and
emits arrays only for cells that pass ``surface_input_valid``.

Crucially, a sample is NEVER dropped because a deep target is missing. Each
sample carries a 15-element target mask, and the loss uses it per depth, so a
shelf cell valid to 50 m still trains those five depths.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from .features import FEATURE_NAMES, SURFACE, cyclic_doy


class PointwiseSampler:
    """Streams (X, Y, M) blocks. Validity masks are time-invariant (verified in
    the model-ready data), so the valid-cell index is computed once."""

    def __init__(self, ds: xr.Dataset, depths: list[int], chunk_days: int = 32):
        self.ds = ds
        self.depths = list(depths)
        self.chunk_days = int(chunk_days)
        self.times = pd.DatetimeIndex(ds.time.values)

        siv = ds["surface_input_valid"].isel(time=0).values.astype(bool)
        self.cell_idx = np.argwhere(siv)                      # (n_cells, 2)
        self.n_cells = len(self.cell_idx)
        lat = ds.lat.values[self.cell_idx[:, 0]]
        lon = ds.lon.values[self.cell_idx[:, 1]]
        self.cell_lat, self.cell_lon = lat, lon

        # per-depth target validity at those cells, also time-invariant
        self.target_mask = np.stack(
            [ds[f"target_valid_{d}m"].isel(time=0).values.astype(bool)[
                self.cell_idx[:, 0], self.cell_idx[:, 1]] for d in self.depths],
            axis=1)                                            # (n_cells, 15)

    @property
    def n_samples(self) -> int:
        return len(self.times) * self.n_cells

    def _read_block(self, t0: int, t1: int):
        sub = self.ds.isel(time=slice(t0, t1))
        r, c = self.cell_idx[:, 0], self.cell_idx[:, 1]
        nt = t1 - t0

        surf = np.empty((nt, self.n_cells, len(SURFACE)), dtype="float32")
        for k, v in enumerate(SURFACE):
            surf[:, :, k] = sub[v].values[:, r, c]

        y = np.empty((nt, self.n_cells, len(self.depths)), dtype="float32")
        for k, d in enumerate(self.depths):
            y[:, :, k] = sub[f"temp_{d}m"].values[:, r, c]

        times = pd.DatetimeIndex(sub.time.values)
        s, cdoy = cyclic_doy(times)

        X = np.empty((nt, self.n_cells, len(FEATURE_NAMES)), dtype="float32")
        X[:, :, :len(SURFACE)] = surf
        X[:, :, len(SURFACE) + 0] = self.cell_lat[None, :]
        X[:, :, len(SURFACE) + 1] = self.cell_lon[None, :]
        X[:, :, len(SURFACE) + 2] = s[:, None]
        X[:, :, len(SURFACE) + 3] = cdoy[:, None]

        M = np.broadcast_to(self.target_mask[None, :, :], y.shape).copy()
        # A target flagged valid must actually be finite; guard against any
        # mismatch rather than letting a NaN reach the loss.
        M &= np.isfinite(y)
        y = np.where(M, y, 0.0)      # value is irrelevant where masked out

        X = X.reshape(-1, X.shape[-1])
        y = y.reshape(-1, y.shape[-1])
        M = M.reshape(-1, M.shape[-1])
        keep = np.isfinite(X).all(axis=1)      # drop any residual bad feature row

        # Row-level bookkeeping so callers can align auxiliary arrays (e.g. a
        # climatology prediction) with EXACTLY the rows that survived `keep`.
        # Assuming nothing is dropped is a real bug: it is true on some splits
        # and silently false on others.
        row_time = np.repeat(np.arange(nt), self.n_cells)[keep]
        row_cell = np.tile(np.arange(self.n_cells), nt)[keep]
        row_stamp = np.repeat(times.values, self.n_cells)[keep]
        return X[keep], y[keep], M[keep], row_stamp, row_time, row_cell

    def blocks(self, shuffle: bool = False, seed: int | None = None):
        """Yield (X, Y, M, row_stamp, row_time, row_cell) per time-chunk."""
        starts = list(range(0, len(self.times), self.chunk_days))
        if shuffle:
            rng = np.random.default_rng(seed)
            rng.shuffle(starts)
        for t0 in starts:
            t1 = min(t0 + self.chunk_days, len(self.times))
            yield self._read_block(t0, t1)

    def minibatches(self, batch_size: int, shuffle: bool = True, seed: int = 0):
        """Yield shuffled minibatches, shuffling within each loaded chunk."""
        rng = np.random.default_rng(seed)
        for X, Y, M, *_ in self.blocks(shuffle=shuffle, seed=seed):
            order = rng.permutation(len(X)) if shuffle else np.arange(len(X))
            for i in range(0, len(order), batch_size):
                sel = order[i:i + batch_size]
                yield X[sel], Y[sel], M[sel]
