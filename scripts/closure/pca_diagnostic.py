"""Experiment B - train-only vertical PCA / EOF diagnostic.

A DIAGNOSTIC. No EOF decoder is trained here, whatever the outcome.

The basis is fitted on TRAIN dates only (2015-01-01..2020-12-31). No validation,
test or Argo value enters the covariance. Sampling was declared in the
pre-registration before this script was run: every 7th train day, 2,000 cells
per day drawn without replacement with rng seed 20260905 + day index.

Because target validity follows bathymetry, a complete-profile population is a
BIASED sample of the domain - deep water is over-represented. That bias is
measured and reported rather than assumed away.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import pandas as pd
import yaml

from oceanembed.closure.holdout import assert_no_2024_argo
from oceanembed.config import REPO_ROOT
from oceanembed.ml import splits
from oceanembed.ml.climatology import HarmonicClimatology
from oceanembed.ml.embedding_cache import TargetCache
from oceanembed.ml.metrics import BASINS

CFG = yaml.safe_load(open(REPO_ROOT / "config" / "phase6b.yaml", encoding="utf-8"))
DEPTHS = CFG["targets"]["depths_m"]
BASE = REPO_ROOT / CFG["paths"]["baselines"]
CACHE = REPO_ROOT / "outputs" / "targets_cache"
TAB = REPO_ROOT / "outputs" / "tables" / "architecture_closure"
OUT = REPO_ROOT / "outputs" / "architecture_closure"

DAY_STRIDE = 7          # pre-registered
CELLS_PER_DAY = 2000    # pre-registered
SEED = 20260905         # pre-registered
UPPER_MAX_DEPTH = 300


def sample(smp_dates, y, r, c, depth_idx, log=print):
    """Deterministic stratified draw of complete profiles over the depth subset."""
    rows, cell_ids, day_ids = [], [], []
    days = np.arange(0, len(smp_dates), DAY_STRIDE)
    for di, t in enumerate(days):
        block = np.asarray(y[t][:, depth_idx], dtype="float64")
        ok = np.isfinite(block).all(axis=1)
        idx = np.flatnonzero(ok)
        if len(idx) == 0:
            continue
        rng = np.random.default_rng(SEED + int(t))
        take = rng.choice(idx, size=min(CELLS_PER_DAY, len(idx)), replace=False)
        rows.append(block[take])
        cell_ids.append(take)
        day_ids.append(np.full(len(take), t))
        if (di + 1) % 50 == 0:
            log(f"    sampled {di + 1}/{len(days)} days")
    X = np.concatenate(rows, axis=0)
    cells = np.concatenate(cell_ids)
    return X, cells, np.concatenate(day_ids), len(days)


def eligibility(y, depth_idx):
    """Fraction of days on which each cell has a complete profile."""
    n_days = y.shape[0]
    hits = np.zeros(y.shape[1], dtype="int64")
    for t in range(0, n_days, DAY_STRIDE):
        hits += np.isfinite(np.asarray(y[t][:, depth_idx], dtype="float64")).all(axis=1)
    return hits / len(range(0, n_days, DAY_STRIDE))


def pca(X):
    """Covariance EOFs of the profile matrix (n_samples, n_depths)."""
    mean = X.mean(axis=0)
    A = X - mean
    cov = (A.T @ A) / (len(A) - 1)
    w, V = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1]
    return mean, w[order], V[:, order], cov


def reconstruct_errors(X, mean, V, ks, depths):
    """Per-k and per-depth reconstruction RMSE in physical units."""
    A = X - mean
    rows = []
    for k in ks:
        P = V[:, :k]
        R = A @ P @ P.T
        E = A - R
        rows.append({"k": int(k),
                     "rmse_overall": float(np.sqrt((E ** 2).mean())),
                     **{f"rmse_{d}m": float(np.sqrt((E[:, j] ** 2).mean()))
                        for j, d in enumerate(depths)}})
    return pd.DataFrame(rows)


def analyse(name, X, depths, log=print) -> dict:
    mean, evals, V, _ = pca(X)
    evr = evals / evals.sum()
    cum = np.cumsum(evr)
    ks = [k for k in (1, 2, 3, 5, 8, 10, 15) if k <= len(depths)]
    err = reconstruct_errors(X, mean, V, ks, depths)
    need = {f"k_for_{p}pct": int(np.searchsorted(cum, p / 100.0) + 1)
            for p in (90, 95, 99)}
    log(f"  {name}: n={len(X):,}  EVR1={evr[0]:.4f}  "
        f"k90={need['k_for_90pct']} k95={need['k_for_95pct']} k99={need['k_for_99pct']}")
    return {"name": name, "n_samples": int(len(X)), "depths": list(depths),
            "mean_profile": mean.tolist(), "eigenvalues": evals.tolist(),
            "explained_variance_ratio": evr.tolist(),
            "cumulative_explained_variance": cum.tolist(),
            "eofs": V.tolist(), **need,
            "reconstruction": err.to_dict(orient="records")}


def main() -> int:
    TAB.mkdir(parents=True, exist_ok=True)
    ds_tr = splits.open_split("train")
    times = pd.DatetimeIndex(ds_tr.time.values)
    assert not splits.contains_test_dates(times), "LEAK: test dates in the PCA basis"
    assert_no_2024_argo(times, what="PCA basis dates")
    assert times.min() == pd.Timestamp("2015-01-01") and times.max() == pd.Timestamp("2020-12-31")

    tc = TargetCache(CACHE, "train").load()
    assert list(tc.meta["depths"]) == DEPTHS
    assert tc.dates.equals(times.normalize()), "target cache dates != train dates"
    y = tc.y

    siv = ds_tr["surface_input_valid"].isel(time=0).values.astype(bool)
    idx = np.argwhere(siv)
    r, c = idx[:, 0], idx[:, 1]
    lat, lon = ds_tr.lat.values[r], ds_tr.lon.values[c]
    print(f"train {times[0].date()}..{times[-1].date()}  "
          f"{len(times)} days  {len(r)} cells")

    clim = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert clim.meta["fitted_on"] == "train"

    analyses = {"B1_FULL15": list(range(len(DEPTHS))),
                "B2_UPPER300": [i for i, d in enumerate(DEPTHS) if d <= UPPER_MAX_DEPTH]}

    results, pop_rows = {}, []
    for aname, didx in analyses.items():
        depths = [DEPTHS[i] for i in didx]
        print(f"\n[{aname}] {len(depths)} depths: {depths}")
        elig = eligibility(y, didx)
        always = elig >= 0.999
        print(f"  eligible cells (complete on >=99.9% of sampled days): "
              f"{int(always.sum())}/{len(r)} = {always.mean():.3f} of the "
              f"surface-valid domain")
        pop_rows.append({
            "analysis": aname, "n_depths": len(depths),
            "n_surface_valid_cells": int(len(r)),
            "n_eligible_cells": int(always.sum()),
            "eligible_fraction": float(always.mean()),
            "mean_lat_all": float(lat.mean()), "mean_lat_eligible": float(lat[always].mean()),
            "mean_lon_all": float(lon.mean()), "mean_lon_eligible": float(lon[always].mean()),
            **{f"frac_{b}_all": float((( lat >= v["lat"][0]) & (lat <= v["lat"][1])
                                       & (lon >= v["lon"][0]) & (lon <= v["lon"][1])).mean())
               for b, v in BASINS.items()},
            **{f"frac_{b}_eligible": float((((lat >= v["lat"][0]) & (lat <= v["lat"][1])
                                             & (lon >= v["lon"][0]) & (lon <= v["lon"][1]))[always]).mean())
               for b, v in BASINS.items()},
        })

        X, cells, days, n_days = sample(times, y, r, c, didx)
        print(f"  sampled {len(X):,} complete profiles from {n_days} days")

        # residual profiles use the SAME sampled (day, cell) pairs
        Xr = np.empty_like(X)
        for t in np.unique(days):
            m = days == t
            cl = clim.predict(pd.DatetimeIndex([times[t]]), r[cells[m]], c[cells[m]])[0]
            Xr[m] = X[m] - cl[:, didx]

        results[aname] = {
            "raw": analyse(f"{aname}_raw", X, depths),
            "residual": analyse(f"{aname}_residual", Xr, depths),
            "sampling": {"day_stride": DAY_STRIDE, "cells_per_day": CELLS_PER_DAY,
                         "seed": SEED, "n_days_sampled": int(n_days),
                         "n_profiles": int(len(X))},
        }

    pop = pd.DataFrame(pop_rows)
    pop.to_csv(TAB / "pca_sample_population.csv", index=False)

    for rep in ("raw", "residual"):
        rows = []
        for aname, res in results.items():
            a = res[rep]
            for i, (ev, evr, cum) in enumerate(zip(a["eigenvalues"],
                                                   a["explained_variance_ratio"],
                                                   a["cumulative_explained_variance"]), 1):
                rows.append({"analysis": aname, "representation": rep, "component": i,
                             "eigenvalue": ev, "explained_variance_ratio": evr,
                             "cumulative_explained_variance": cum})
        pd.DataFrame(rows).to_csv(TAB / f"pca_explained_variance_{rep}.csv", index=False)

    rec = []
    for aname, res in results.items():
        for rep in ("raw", "residual"):
            for row in res[rep]["reconstruction"]:
                rec.append({"analysis": aname, "representation": rep, **row})
    pd.DataFrame(rec).to_csv(TAB / "pca_reconstruction_error.csv", index=False)

    json.dump(results, open(OUT / "pca_diagnostic.json", "w"), indent=2)
    print(f"\n-> {TAB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
