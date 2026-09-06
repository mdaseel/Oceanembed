"""L0 baseline: train-only, cell- and depth-specific day-of-year climatology.

Method: truncated Fourier (harmonic) regression in day-of-year, fit
independently for every (lat, lon, depth) on the TRAINING years only.

Why harmonics rather than a raw day-of-year mean: six training years give ~6
samples per calendar day, so a raw per-day mean is noisy and has an artificial
31-Dec -> 1-Jan discontinuity. A truncated Fourier series is smooth and exactly
periodic by construction, is defined for any day-of-year including 29 Feb and
day 366, and with 3 harmonics resolves the annual cycle plus the semiannual
monsoon signal that dominates the North Indian Ocean.

Fitting uses ~2,192 training days against 7 coefficients per series, so the
system is strongly over-determined.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from .features import harmonic_design, n_harmonic_terms


class HarmonicClimatology:
    def __init__(self, coef: xr.DataArray, depths: list[int], n_harmonics: int,
                 meta: dict | None = None):
        self.coef = coef                 # (term, depth, lat, lon)
        self.depths = list(depths)
        self.n_harmonics = int(n_harmonics)
        self.meta = meta or {}

    # ------------------------------------------------------------------ fit
    @classmethod
    def fit(cls, ds: xr.Dataset, depths: list[int], n_harmonics: int = 3,
            fitted_on: str = "train", chunk_days: int = 366,
            log=print) -> "HarmonicClimatology":
        times = ds.time.values
        A = harmonic_design(times, n_harmonics)               # (n_days, n_terms)
        n_terms = n_harmonic_terms(n_harmonics)
        nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]

        # Normal equations once - the design matrix is shared by every series.
        AtA = A.T @ A
        AtA_inv = np.linalg.inv(AtA)
        cond = float(np.linalg.cond(AtA))
        log(f"  design {A.shape}, {n_terms} terms, cond(A'A)={cond:.1f}")

        coef = np.full((n_terms, len(depths), nlat, nlon), np.nan, dtype="float64")
        for k, d in enumerate(depths):
            valid = ds[f"target_valid_{d}m"].isel(time=0).values.astype(bool)
            idx = np.argwhere(valid)
            if len(idx) == 0:
                log(f"  depth {d:5d} m: no valid cells")
                continue
            r, c = idx[:, 0], idx[:, 1]
            # Read in time-chunks so a full (n_days x n_cells) float64 block is
            # never materialised for the whole record at once.
            AtY = np.zeros((n_terms, len(idx)), dtype="float64")
            for t0 in range(0, len(times), chunk_days):
                t1 = min(t0 + chunk_days, len(times))
                Y = ds[f"temp_{d}m"].isel(time=slice(t0, t1)).values[:, r, c]
                AtY += A[t0:t1].T @ np.nan_to_num(Y, nan=0.0)
            beta = AtA_inv @ AtY                              # (n_terms, n_cells)
            coef[:, k, r, c] = beta
            log(f"  depth {d:5d} m: fitted {len(idx):6d} cells")

        da = xr.DataArray(
            coef, dims=("term", "depth", "lat", "lon"),
            coords={"term": np.arange(n_terms), "depth": depths,
                    "lat": ds.lat.values, "lon": ds.lon.values},
            name="harmonic_coef")
        meta = {"method": "harmonic_regression", "n_harmonics": n_harmonics,
                "n_terms": n_terms, "fitted_on": fitted_on,
                "n_fit_days": int(len(times)),
                "fit_start": str(times[0])[:10], "fit_end": str(times[-1])[:10],
                "cond_AtA": cond}
        return cls(da, depths, n_harmonics, meta)

    # -------------------------------------------------------------- predict
    def predict(self, times, lat_idx=None, lon_idx=None) -> np.ndarray:
        """Climatological temperature. Returns (n_times, n_depths, nlat, nlon)
        or, when cell indices are given, (n_times, n_cells, n_depths)."""
        A = harmonic_design(times, self.n_harmonics)          # (nt, n_terms)
        C = self.coef.values                                  # (term, depth, lat, lon)
        if lat_idx is None:
            return np.einsum("kt,kdij->tdij", A.T, C)
        c = C[:, :, lat_idx, lon_idx]                         # (term, depth, n_cells)
        return np.einsum("tk,kdc->tcd", A, c)

    # ------------------------------------------------------------------- io
    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        ds = self.coef.to_dataset()
        ds.attrs = {k: (v if isinstance(v, (str, int, float)) else str(v))
                    for k, v in self.meta.items()}
        ds.to_netcdf(p)

    @classmethod
    def load(cls, path: Path | str) -> "HarmonicClimatology":
        ds = xr.open_dataset(path)
        da = ds["harmonic_coef"].load()
        meta = dict(ds.attrs)
        ds.close()
        return cls(da, [int(d) for d in da.depth.values],
                   int(meta.get("n_harmonics", 3)), meta)
