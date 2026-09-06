"""Train-only z-score normalisation, frozen to disk.

Fitting any statistic on validation or test data leaks information about them
into the model. These statistics are computed on the training split alone and
then reused verbatim; ``load`` is the only way evaluation code obtains them.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class ZScoreScaler:
    def __init__(self, mean: np.ndarray, std: np.ndarray, names: list[str],
                 fitted_on: str = "train", meta: dict | None = None):
        self.mean = np.asarray(mean, dtype="float64")
        self.std = np.asarray(std, dtype="float64")
        # A zero-variance channel would divide by zero; keep it at 1.0 so the
        # channel becomes a constant zero rather than NaN.
        self.std = np.where(self.std > 1e-12, self.std, 1.0)
        self.names = list(names)
        self.fitted_on = fitted_on
        self.meta = meta or {}

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse_transform(self, z: np.ndarray) -> np.ndarray:
        return z * self.std + self.mean

    def to_json(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"mean": self.mean.tolist(), "std": self.std.tolist(),
                       "names": self.names, "fitted_on": self.fitted_on,
                       "meta": self.meta}, fh, indent=2)

    @classmethod
    def from_json(cls, path: Path | str) -> "ZScoreScaler":
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return cls(np.array(d["mean"]), np.array(d["std"]), d["names"],
                   d.get("fitted_on", "train"), d.get("meta", {}))


class RunningMoments:
    """Streaming mean/std so a 24 M-sample split never has to sit in RAM."""

    def __init__(self, n: int):
        self.n = np.zeros(n, dtype="float64")
        self._mean = np.zeros(n, dtype="float64")
        self._m2 = np.zeros(n, dtype="float64")

    def update(self, x: np.ndarray, valid: np.ndarray | None = None) -> None:
        """Chunked Welford update; ``valid`` masks per-column missing values."""
        x = np.asarray(x, dtype="float64")
        if valid is None:
            valid = np.isfinite(x)
        for j in range(x.shape[1]):
            v = x[valid[:, j], j]
            if v.size == 0:
                continue
            n_a, mean_a, m2_a = self.n[j], self._mean[j], self._m2[j]
            n_b = float(v.size)
            mean_b = v.mean()
            m2_b = ((v - mean_b) ** 2).sum()
            delta = mean_b - mean_a
            n_t = n_a + n_b
            self._mean[j] = mean_a + delta * n_b / n_t
            self._m2[j] = m2_a + m2_b + delta ** 2 * n_a * n_b / n_t
            self.n[j] = n_t

    @property
    def mean(self) -> np.ndarray:
        return self._mean.copy()

    @property
    def std(self) -> np.ndarray:
        return np.sqrt(np.where(self.n > 1, self._m2 / np.maximum(self.n - 1, 1), 0.0))
