"""Locked train / validation / test split handling.

The test period is LOCKED. Every helper here refuses to hand back test dates
unless the caller passes ``allow_test=True``, which exists so that the single
final evaluation has to be deliberate and greppable rather than accidental.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from ..config import REPO_ROOT

SPLITS_PATH = REPO_ROOT / "config" / "data_splits.yaml"
MODEL_READY = REPO_ROOT / "data" / "processed" / "model_ready"


def load_splits(path: Path | str | None = None) -> dict:
    with open(Path(path) if path else SPLITS_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


SPLITS = load_splits()


def split_bounds(name: str) -> tuple[str, str]:
    s = SPLITS["splits"][name]
    return s["start"], s["end"]


def split_dates(name: str) -> pd.DatetimeIndex:
    start, end = split_bounds(name)
    return pd.date_range(start, end, freq="D")


def years_for(name: str) -> list[int]:
    start, end = split_bounds(name)
    return list(range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1))


def assert_no_overlap() -> None:
    tr, va, te = (set(split_dates(n)) for n in ("train", "validation", "test"))
    assert not (tr & va), "train/validation overlap"
    assert not (tr & te), "train/test overlap"
    assert not (va & te), "validation/test overlap"


def open_split(name: str, allow_test: bool = False) -> xr.Dataset:
    """Open the model-ready stores for one split, trimmed to its exact dates.

    Opening the LOCKED test split requires ``allow_test=True``. This is a
    deliberate speed bump: development code cannot touch test data by typo.
    """
    if name == "test" and not allow_test:
        raise PermissionError(
            "The test split is LOCKED. Pass allow_test=True only for the single "
            "final Phase 6B-A evaluation, after everything is frozen.")
    assert_no_overlap()
    start, end = split_bounds(name)
    stores = [MODEL_READY / f"oceanembed_{y}.zarr" for y in years_for(name)]
    missing = [p for p in stores if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing stores: {[p.name for p in missing]}")
    ds = xr.open_mfdataset([str(p) for p in stores], engine="zarr",
                           consolidated=True, combine="by_coords")
    ds = ds.sel(time=slice(start, end))
    n_expect = len(pd.date_range(start, end, freq="D"))
    assert ds.sizes["time"] == n_expect, \
        f"{name}: got {ds.sizes['time']} days, expected {n_expect}"
    return ds


def contains_test_dates(times) -> bool:
    """True if any timestamp falls inside the locked test window."""
    t0, t1 = (pd.Timestamp(x) for x in split_bounds("test"))
    t = pd.DatetimeIndex(np.atleast_1d(times))
    return bool(((t >= t0) & (t <= t1)).any())
