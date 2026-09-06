"""Train-only seasonal climatology of the SURFACE channels.

Used solely as a non-learned fallback for a missing input channel. It reuses
the same harmonic design as the Phase 6B-A target climatology (3 harmonics,
exactly periodic in day-of-year) and is fitted on the TRAIN split only, so no
evaluation data informs the fallback.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .features import SURFACE, harmonic_design, n_harmonic_terms


class SurfaceClimatology:
    def __init__(self, coef: xr.DataArray, n_harmonics: int, meta: dict):
        self.coef = coef              # (term, channel, lat, lon)
        self.n_harmonics = int(n_harmonics)
        self.meta = meta
        self._names = [str(c) for c in coef.channel.values]

    @classmethod
    def fit(cls, ds: xr.Dataset, n_harmonics: int = 3, chunk: int = 366,
            log=print) -> "SurfaceClimatology":
        times = ds.time.values
        A = harmonic_design(times, n_harmonics)
        n_terms = n_harmonic_terms(n_harmonics)
        AtA_inv = np.linalg.inv(A.T @ A)
        nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]
        coef = np.full((n_terms, len(SURFACE), nlat, nlon), np.nan)
        for k, v in enumerate(SURFACE):
            valid = np.isfinite(ds[v].isel(time=0).values)
            idx = np.argwhere(valid)
            if not len(idx):
                continue
            r, c = idx[:, 0], idx[:, 1]
            AtY = np.zeros((n_terms, len(idx)))
            for t0 in range(0, len(times), chunk):
                t1 = min(t0 + chunk, len(times))
                Y = ds[v].isel(time=slice(t0, t1)).values[:, r, c]
                AtY += A[t0:t1].T @ np.nan_to_num(Y, nan=0.0)
            coef[:, k, r, c] = AtA_inv @ AtY
            log(f"  {v:10s} fitted {len(idx):6d} cells")
        da = xr.DataArray(coef, dims=("term", "channel", "lat", "lon"),
                          coords={"term": np.arange(n_terms), "channel": list(SURFACE),
                                  "lat": ds.lat.values, "lon": ds.lon.values},
                          name="surface_harmonic_coef")
        meta = {"fitted_on": "train", "n_harmonics": n_harmonics,
                "fit_start": str(times[0])[:10], "fit_end": str(times[-1])[:10],
                "n_fit_days": int(len(times))}
        return cls(da, n_harmonics, meta)

    def predict_channel(self, name: str, when) -> np.ndarray:
        A = harmonic_design(pd.DatetimeIndex([pd.Timestamp(when)]), self.n_harmonics)[0]
        k = self._names.index(name)
        return np.einsum("k,kij->ij", A, self.coef.values[:, k])

    def save(self, path: Path | str) -> None:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        d = self.coef.to_dataset()
        d.attrs = {k: str(v) for k, v in self.meta.items()}
        d.to_netcdf(p)

    @classmethod
    def load(cls, path: Path | str) -> "SurfaceClimatology":
        d = xr.open_dataset(path)
        da = d["surface_harmonic_coef"].load()
        meta = dict(d.attrs); d.close()
        return cls(da, int(meta.get("n_harmonics", 3)), meta)
