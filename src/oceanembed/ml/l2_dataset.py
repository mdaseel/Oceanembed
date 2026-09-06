"""Day-batched sampler for L2.

One day = one batch. The encoder runs once over the whole padded field for
that day and produces the embedding for every cell at once; the decoder then
consumes only the cells that pass ``surface_input_valid``. Targets and masks
are exactly those used by L1, so L0/L1/L2 are compared on identical samples.

Uses the FROZEN Phase 6B-A scalers - nothing is refitted here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from .features import SURFACE, cyclic_doy
from .patches import N_DATA_CHANNELS, day_field


class DayFieldSampler:
    def __init__(self, ds: xr.Dataset, depths: list[int], feature_scaler,
                 target_scaler, patch: int = 17):
        self.ds = ds
        self.depths = list(depths)
        self.fs = feature_scaler
        self.ts = target_scaler
        self.patch = int(patch)
        self.half = self.patch // 2
        self.times = pd.DatetimeIndex(ds.time.values)

        siv = ds["surface_input_valid"].isel(time=0).values.astype(bool)
        self.cell_idx = np.argwhere(siv)
        self.n_cells = len(self.cell_idx)
        self.r = self.cell_idx[:, 0]
        self.c = self.cell_idx[:, 1]
        self.cell_lat = ds.lat.values[self.r]
        self.cell_lon = ds.lon.values[self.c]

        self.target_mask = np.stack(
            [ds[f"target_valid_{d}m"].isel(time=0).values.astype(bool)[self.r, self.c]
             for d in self.depths], axis=1)

        # context uses the same frozen statistics as L1 (entries 7..10:
        # lat, lon, doy_sin, doy_cos) so the two models see identical context
        self._ctx_mean = feature_scaler.mean[N_DATA_CHANNELS:]
        self._ctx_std = feature_scaler.std[N_DATA_CHANNELS:]

    @property
    def n_days(self) -> int:
        return len(self.times)

    @property
    def n_samples(self) -> int:
        return self.n_days * self.n_cells

    def context(self, t: int) -> np.ndarray:
        s, c = cyclic_doy(self.times[t:t + 1])
        raw = np.column_stack([self.cell_lat, self.cell_lon,
                               np.full(self.n_cells, s[0]),
                               np.full(self.n_cells, c[0])]).astype("float64")
        return ((raw - self._ctx_mean) / self._ctx_std).astype("float32")

    def day(self, t: int):
        """Return (field, ctx, Y_std, mask) for day index t."""
        field = day_field(self.ds, t, self.fs, self.patch)
        ctx = self.context(t)
        Y = np.empty((self.n_cells, len(self.depths)), dtype="float64")
        for k, d in enumerate(self.depths):
            Y[:, k] = self.ds[f"temp_{d}m"].isel(time=t).values[self.r, self.c]
        M = self.target_mask & np.isfinite(Y)
        Yz = (Y - self.ts.mean) / self.ts.std
        Yz = np.where(M, Yz, 0.0).astype("float32")
        return field, ctx, Yz, M, Y

    def days(self, shuffle: bool = False, seed: int | None = None,
             stride: int = 1):
        order = np.arange(0, self.n_days, stride)
        if shuffle:
            np.random.default_rng(seed).shuffle(order)
        for t in order:
            yield int(t), self.day(int(t))
