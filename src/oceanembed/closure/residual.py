"""Climatology-residual target formulation (Experiment C).

The model predicts the departure from the frozen L0 harmonic climatology
instead of absolute temperature:

    delta_T(depth) = T_target(depth) - T_L0(date, cell, depth)
    T_pred         = T_L0 + delta_T_pred

L0 is loaded read-only and is NEVER refitted - it is a frozen Phase 6B-A
artefact and this experiment changes what the network is asked to predict, not
what the climatology is. The residual standardisation is a NEW scaler fitted on
TRAIN dates only and written to a new path; the frozen target scaler is not
touched and not reused, because residuals have a different spread from absolute
temperature and reusing the absolute scaler would silently reweight the
per-depth loss.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..config import REPO_ROOT
from ..ml.climatology import HarmonicClimatology
from ..ml.scaler import ZScoreScaler

CLOSURE_BASE = REPO_ROOT / "outputs" / "architecture_closure"


def residual_scaler_path() -> Path:
    return CLOSURE_BASE / "closure_residual_target_scaler.json"


class ResidualTargets:
    """Turns absolute GLORYS targets into standardised climatology residuals."""

    def __init__(self, clim: HarmonicClimatology, r: np.ndarray, c: np.ndarray,
                 depths: list[int], scaler: ZScoreScaler | None = None):
        if clim.meta.get("fitted_on") != "train":
            raise ValueError("L0 climatology is not the train-only artefact")
        self.clim = clim
        self.r, self.c = np.asarray(r), np.asarray(c)
        self.depths = list(depths)
        self.scaler = scaler
        self._cache: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------ L0
    def climatology(self, when) -> np.ndarray:
        """(n_cells, n_depths) L0 temperature for one date, memoised by date."""
        key = str(pd.Timestamp(when).date())
        if key not in self._cache:
            self._cache[key] = self.clim.predict(
                pd.DatetimeIndex([when]), self.r, self.c)[0].astype("float64")
        return self._cache[key]

    def residual(self, Y: np.ndarray, when) -> np.ndarray:
        return np.asarray(Y, dtype="float64") - self.climatology(when)

    def to_absolute(self, delta: np.ndarray, when) -> np.ndarray:
        """The only way a residual prediction becomes a temperature."""
        return np.asarray(delta, dtype="float64") + self.climatology(when)

    # -------------------------------------------------------------- scaling
    def standardise(self, delta: np.ndarray) -> np.ndarray:
        if self.scaler is None:
            raise RuntimeError("no residual scaler attached")
        return (np.asarray(delta, dtype="float64") - self.scaler.mean) / self.scaler.std

    def destandardise(self, z: np.ndarray) -> np.ndarray:
        if self.scaler is None:
            raise RuntimeError("no residual scaler attached")
        return np.asarray(z, dtype="float64") * self.scaler.std + self.scaler.mean

    # ------------------------------------------------------------------ fit
    @classmethod
    def fit_scaler(cls, clim, r, c, depths, target_cache, times,
                   log=print) -> ZScoreScaler:
        """Per-depth mean/std of the TRAIN residuals, streamed day by day.

        Only masked-in target values contribute, so a depth that does not exist
        over the shelf is not given an artificial mean of zero from land.
        """
        n = np.zeros(len(depths), dtype="float64")
        s = np.zeros(len(depths), dtype="float64")
        s2 = np.zeros(len(depths), dtype="float64")
        rt = cls(clim, r, c, depths)
        for t, when in enumerate(times):
            Y = np.asarray(target_cache.y[t], dtype="float64")
            d = Y - rt.climatology(when)
            ok = np.isfinite(d)
            n += ok.sum(axis=0)
            s += np.where(ok, d, 0.0).sum(axis=0)
            s2 += np.where(ok, d ** 2, 0.0).sum(axis=0)
            if (t + 1) % 500 == 0:
                log(f"    residual scaler: {t + 1}/{len(times)} days")
        mean = s / np.maximum(n, 1)
        var = np.maximum(s2 / np.maximum(n, 1) - mean ** 2, 0.0)
        return ZScoreScaler(mean, np.sqrt(var), [f"resid_{d}m" for d in depths],
                            fitted_on="train",
                            meta={"experiment": "architecture_closure_C",
                                  "definition": "GLORYS target minus frozen L0 "
                                                "harmonic climatology",
                                  "n_values_per_depth": n.tolist(),
                                  "fit_start": str(pd.Timestamp(times[0]).date()),
                                  "fit_end": str(pd.Timestamp(times[-1]).date())})
