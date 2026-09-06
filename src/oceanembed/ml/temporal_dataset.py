"""Causal sequence sampler over cached frozen-L2 embeddings.

Guarantees enforced here, each covered by a test:

* CAUSAL ONLY. The sequence for target date t is [t-T+1 ... t] inclusive, with
  the CURRENT day last. No t+1, no future surface field, no future target.
* COMMON TARGET DATES. Target indices start at ``max_history-1`` regardless of
  the window actually used, so the 1-day control, 3-day and 7-day models are
  scored on an identical sample population. Window length can therefore never
  confound the comparison through differing boundary dates.
* HISTORY NEVER CROSSES A SPLIT. Each cache holds exactly one split, so a
  validation target can only ever pull history from validation.
* NO TARGET LEAKAGE. The GRU sees only surface-derived z. Targets are read
  separately and used solely by the loss.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from .features import cyclic_doy
from .patches import N_DATA_CHANNELS


class TemporalSequenceSampler:
    def __init__(self, ds: xr.Dataset, cache, depths: list[int], feature_scaler,
                 target_scaler, window: int, max_history: int, target_cache=None):
        assert 1 <= window <= max_history, (window, max_history)
        self.ds = ds
        self.cache = cache
        self.depths = list(depths)
        self.fs = feature_scaler
        self.ts = target_scaler
        self.window = int(window)
        self.max_history = int(max_history)

        self.times = pd.DatetimeIndex(ds.time.values)
        assert len(self.times) == cache.meta["n_days"], "cache/split day mismatch"
        assert (self.times == cache.dates).all(), "cache dates do not match the split"

        self.r, self.c = cache.r, cache.c
        self.n_cells = len(self.r)
        self.cell_lat = ds.lat.values[self.r]
        self.cell_lon = ds.lon.values[self.c]

        # Identical for every window: the first max_history-1 days are dropped.
        self.target_idx = np.arange(self.max_history - 1, len(self.times))
        self.target_dates = self.times[self.target_idx]

        self.target_mask = np.stack(
            [ds[f"target_valid_{d}m"].isel(time=0).values.astype(bool)[self.r, self.c]
             for d in self.depths], axis=1)
        self.target_cache = target_cache
        if target_cache is not None:
            assert target_cache.meta["n_cells"] == self.n_cells
            assert target_cache.meta["depths"] == [int(d) for d in self.depths]
            assert (pd.DatetimeIndex(target_cache.meta["dates"]) == self.times).all()
        self._ctx_mean = feature_scaler.mean[N_DATA_CHANNELS:]
        self._ctx_std = feature_scaler.std[N_DATA_CHANNELS:]

    @property
    def n_targets(self) -> int:
        return len(self.target_idx)

    @property
    def n_samples(self) -> int:
        return self.n_targets * self.n_cells

    def context(self, t: int) -> np.ndarray:
        """Current-day lat/lon and cyclic day-of-year, standardised with the
        frozen train scaler (same entries L1 and L2 used)."""
        s, c = cyclic_doy(self.times[t:t + 1])
        raw = np.column_stack([self.cell_lat, self.cell_lon,
                               np.full(self.n_cells, s[0]),
                               np.full(self.n_cells, c[0])]).astype("float64")
        return ((raw - self._ctx_mean) / self._ctx_std).astype("float32")

    def sequence(self, t: int, order: str = "causal") -> np.ndarray:
        """(n_cells, window, latent); index -1 is the current day."""
        lo = t - self.window + 1
        assert lo >= 0, f"window {self.window} runs off the start at index {t}"
        seq = np.asarray(self.cache.z[lo:t + 1])          # (window, n_cells, latent)
        if order == "repeat_current":
            seq = np.repeat(seq[-1:], self.window, axis=0)
        elif order == "reversed":
            seq = seq[::-1]
        elif order != "causal":
            raise ValueError(order)
        return np.ascontiguousarray(seq.transpose(1, 0, 2))

    def targets(self, t: int):
        if self.target_cache is not None:
            Y = np.asarray(self.target_cache.y[t], dtype="float64")
        else:
            Y = np.empty((self.n_cells, len(self.depths)), dtype="float64")
            for k, d in enumerate(self.depths):
                Y[:, k] = self.ds[f"temp_{d}m"].isel(time=t).values[self.r, self.c]
        M = self.target_mask & np.isfinite(Y)
        Yz = np.where(M, (Y - self.ts.mean) / self.ts.std, 0.0).astype("float32")
        return Yz, M, Y

    def day(self, t: int, order: str = "causal"):
        Yz, M, Y = self.targets(t)
        return self.sequence(t, order), self.context(t), Yz, M, Y

    def batches(self, shuffle: bool = False, seed: int | None = None,
                order: str = "causal", block_days: int = 64):
        """Yield (t, (seq, ctx, Yz, M, Y)) for every common target date.

        Consecutive target dates share window-1 days of history, so reading one
        sequence at a time re-reads the memmap ~window times over. Instead a
        contiguous block of days is read once and every target inside it is
        served from RAM. Block order and within-block order are both shuffled,
        matching the chunked-shuffle pattern already used in Phase 6B-A. The
        sample population is unchanged - only the read pattern differs.
        """
        rng = np.random.default_rng(seed)
        starts = np.arange(0, self.n_targets, block_days)
        if shuffle:
            rng.shuffle(starts)
        for s in starts:
            e = min(int(s) + block_days, self.n_targets)
            t_first = int(self.target_idx[int(s)])
            t_last = int(self.target_idx[e - 1])
            lo = t_first - self.window + 1
            assert lo >= 0, f"window {self.window} runs off the start at {t_first}"
            block = np.asarray(self.cache.z[lo:t_last + 1])   # one contiguous read
            local = np.arange(int(s), e)
            if shuffle:
                rng.shuffle(local)
            for li in local:
                t = int(self.target_idx[int(li)])
                off = t - lo
                seq = block[off - self.window + 1:off + 1]
                if order == "repeat_current":
                    seq = np.repeat(seq[-1:], self.window, axis=0)
                elif order == "reversed":
                    seq = seq[::-1]
                elif order != "causal":
                    raise ValueError(order)
                Yz, M, Y = self.targets(t)
                yield t, (np.ascontiguousarray(seq.transpose(1, 0, 2)),
                          self.context(t), Yz, M, Y)
