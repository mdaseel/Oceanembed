"""Day sampler for the closure experiments.

Identical to ``DayFieldSampler`` in every respect that touches the model - same
cells, same frozen scaler, same ``day_field``, same context, same masked target
population - except that the fifteen GLORYS target variables are read from the
pre-built target cache instead of from Zarr on every epoch. Re-reading Zarr
costs about a third of an L2 epoch, because a one-day read decompresses a
32-day chunk fifteen times over.

Equivalence is not asserted by argument: ``verify_against_reference`` re-runs a
frozen model through this sampler and checks the validation loss reproduces the
value recorded in the frozen L2 training log.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..ml.embedding_cache import TargetCache
from ..ml.features import cyclic_doy
from ..ml.patches import N_DATA_CHANNELS, day_field


class CachedDaySampler:
    """One day = one batch, with targets served from a memory-mapped cache."""

    def __init__(self, ds: xr.Dataset, depths: list[int], feature_scaler,
                 target_scaler, patch: int, cache_root, split: str,
                 residual=None):
        self.ds = ds
        self.depths = list(depths)
        self.fs = feature_scaler
        self.ts = target_scaler
        self.patch = int(patch)
        self.times = pd.DatetimeIndex(ds.time.values)
        self.residual = residual          # ResidualTargets or None

        siv = ds["surface_input_valid"].isel(time=0).values.astype(bool)
        idx = np.argwhere(siv)
        self.r, self.c = idx[:, 0], idx[:, 1]
        self.n_cells = len(idx)
        self.cell_lat = ds.lat.values[self.r]
        self.cell_lon = ds.lon.values[self.c]

        self.target_mask = np.stack(
            [ds[f"target_valid_{d}m"].isel(time=0).values.astype(bool)[self.r, self.c]
             for d in self.depths], axis=1)

        self.cache = TargetCache(cache_root, split).load()
        if self.cache.meta["n_cells"] != self.n_cells:
            raise ValueError(
                f"target cache for {split} holds {self.cache.meta['n_cells']} cells "
                f"but this split has {self.n_cells}; the cache is not the one this "
                f"sampler needs")
        if list(self.cache.meta["depths"]) != self.depths:
            raise ValueError("target cache depth list does not match")
        if not self.cache.dates.equals(self.times.normalize()):
            raise ValueError("target cache dates do not match the split dates")

        self._ctx_mean = feature_scaler.mean[N_DATA_CHANNELS:]
        self._ctx_std = feature_scaler.std[N_DATA_CHANNELS:]

    @property
    def n_days(self) -> int:
        return len(self.times)

    def context(self, t: int) -> np.ndarray:
        s, c = cyclic_doy(self.times[t:t + 1])
        raw = np.column_stack([self.cell_lat, self.cell_lon,
                               np.full(self.n_cells, s[0]),
                               np.full(self.n_cells, c[0])]).astype("float64")
        return ((raw - self._ctx_mean) / self._ctx_std).astype("float32")

    def targets(self, t: int) -> np.ndarray:
        """Absolute GLORYS temperature at every cell, (n_cells, n_depths)."""
        return np.asarray(self.cache.y[t], dtype="float64")

    def day(self, t: int):
        """(field, ctx, Yz, M, Y_absolute) for day index t.

        ``Yz`` is what the loss sees. In residual mode it is the standardised
        departure from the frozen L0 climatology; in absolute mode it is the
        standardised temperature, exactly as in L2 training.
        """
        field = day_field(self.ds, t, self.fs, self.patch)
        ctx = self.context(t)
        Y = self.targets(t)
        M = self.target_mask & np.isfinite(Y)
        if self.residual is None:
            Yz = (Y - self.ts.mean) / self.ts.std
        else:
            Yz = self.residual.standardise(self.residual.residual(Y, self.times[t]))
        Yz = np.where(M, Yz, 0.0).astype("float32")
        return field, ctx, Yz, M, Y

    def days(self, shuffle: bool = False, seed: int | None = None, stride: int = 1):
        order = np.arange(0, self.n_days, stride)
        if shuffle:
            np.random.default_rng(seed).shuffle(order)
        for t in order:
            yield t, self.day(t)
