"""Phase 6A.5 guards: splits, masks, all-15 depths, and the model-ready store.

As with the Phase 6A tests, the point is preventing silent scientific error at
scale - a leaked test date, a mask that quietly deletes the continental shelf,
a depth list that drifts from the problem statement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.config import FINAL_DEPTHS  # noqa: E402
from oceanembed.grid import canonical_lat, canonical_lon  # noqa: E402
from oceanembed.preprocessing.masks import (  # noqa: E402
    SURFACE_CHANNELS, ocean_mask, surface_input_valid, target_valid,
)

SPLITS_PATH = ROOT / "config" / "data_splits.yaml"
MODEL_READY = ROOT / "data" / "processed" / "model_ready"


# ------------------------------------------------------------------ splits
@pytest.fixture(scope="module")
def splits():
    return yaml.safe_load(open(SPLITS_PATH, encoding="utf-8"))


def test_splits_file_exists(splits):
    assert set(splits["splits"]) == {"train", "validation", "test"}


def test_splits_do_not_overlap(splits):
    s = splits["splits"]
    tr_end = pd.Timestamp(s["train"]["end"])
    va_start, va_end = pd.Timestamp(s["validation"]["start"]), pd.Timestamp(s["validation"]["end"])
    te_start = pd.Timestamp(s["test"]["start"])
    assert tr_end < va_start, "train overruns validation"
    assert va_end < te_start, "validation overruns test"


def test_splits_are_contiguous_and_cover_the_dataset(splits):
    s, d = splits["splits"], splits["dataset"]
    assert pd.Timestamp(s["train"]["start"]) == pd.Timestamp(d["start"])
    assert pd.Timestamp(s["test"]["end"]) == pd.Timestamp(d["end"])
    total = sum(len(pd.date_range(s[k]["start"], s[k]["end"], freq="D")) for k in s)
    assert total == splits["total_days"] == len(pd.date_range(d["start"], d["end"], freq="D"))


def test_declared_day_counts_are_correct(splits):
    for k, v in splits["splits"].items():
        assert len(pd.date_range(v["start"], v["end"], freq="D")) == v["n_days"], k


def test_test_split_is_marked_locked(splits):
    assert splits["splits"]["test"]["locked"] is True


def test_dataset_end_is_attributed_to_a_product(splits):
    """DATASET_END is a data limit, not a preference - it must say which
    product imposed it, so nobody later 'extends' it by guessing."""
    assert splits["dataset"]["end_determined_by"] == "cmems_obs-mob_glo_phy-sss_my_multi_P1D"


# ------------------------------------------------------------------- depths
def test_fifteen_depths_match_the_problem_statement():
    assert FINAL_DEPTHS == [0, 5, 10, 20, 30, 50, 75, 100, 125, 150,
                            200, 300, 500, 700, 1000]


# -------------------------------------------------------------------- masks
def _toy(with_hole: bool = True) -> xr.Dataset:
    """3 cells: [0] full-depth ocean, [1] shallow shelf, [2] land."""
    coords = {"time": [np.datetime64("2020-01-01")], "lat": [10.0], "lon": [70.0, 70.25, 70.5]}
    shape = (1, 1, 3)

    def arr(vals):
        return (("time", "lat", "lon"), np.array(vals, dtype="float64").reshape(shape))

    ds = xr.Dataset({v: arr([1.0, 1.0, np.nan]) for v in SURFACE_CHANNELS}, coords=coords)
    ds["temp_0m"] = arr([28.0, 28.0, np.nan])
    ds["temp_50m"] = arr([26.0, 25.0, np.nan])
    # cell 1 is a shelf: no 1000 m value
    ds["temp_1000m"] = arr([6.0, np.nan if with_hole else 6.0, np.nan])
    return ds


def test_ocean_mask_is_defined_by_surface_target_not_deep_water():
    ds = _toy()
    om = ocean_mask(ds["temp_0m"]).values.ravel()
    assert list(om) == [True, True, False]
    # the shelf cell has NO 1000 m target but MUST still count as ocean
    assert om[1], "shelf cell wrongly excluded from ocean"


def test_shallow_cell_is_retained_with_partial_depth_validity():
    """The regression this guards: using deep-water validity as the ocean
    definition would silently delete the continental shelf."""
    ds = _toy()
    tv = target_valid(ds, [0, 50, 1000])
    assert bool(tv["target_valid_0m"].values.ravel()[1]) is True
    assert bool(tv["target_valid_50m"].values.ravel()[1]) is True
    assert bool(tv["target_valid_1000m"].values.ravel()[1]) is False


def test_target_valid_is_false_over_land_at_every_depth():
    ds = _toy()
    tv = target_valid(ds, [0, 50, 1000])
    for k in tv:
        assert bool(tv[k].values.ravel()[2]) is False, k


def test_surface_input_valid_requires_all_seven_channels():
    ds = _toy()
    m = surface_input_valid(ds).values.ravel()
    assert list(m) == [True, True, False]
    ds2 = ds.copy()
    ds2["sla"] = (("time", "lat", "lon"),
                  np.array([1.0, np.nan, np.nan]).reshape(1, 1, 3))
    m2 = surface_input_valid(ds2).values.ravel()
    assert list(m2) == [True, False, False], "one missing channel must invalidate the cell"


# ------------------------------------------------------- model-ready store
_stores = sorted(MODEL_READY.glob("oceanembed_*.zarr")) if MODEL_READY.exists() else []


@pytest.mark.skipif(not _stores, reason="run scripts/preprocess/build_phase6a5.py first")
class TestModelReady:
    @pytest.fixture(scope="class")
    def ds(self):
        d = xr.open_zarr(_stores[0], consolidated=True)
        yield d
        d.close()

    def test_all_fifteen_targets_present(self, ds):
        for dep in FINAL_DEPTHS:
            assert f"temp_{int(dep)}m" in ds.data_vars, dep

    def test_all_seven_surface_channels_present(self, ds):
        for v in SURFACE_CHANNELS:
            assert v in ds.data_vars, v

    def test_all_masks_present(self, ds):
        assert "ocean_mask" in ds.data_vars
        assert "surface_input_valid" in ds.data_vars
        for dep in FINAL_DEPTHS:
            assert f"target_valid_{int(dep)}m" in ds.data_vars, dep

    def test_grid_still_canonical(self, ds):
        assert np.allclose(ds.lat.values, canonical_lat())
        assert np.allclose(ds.lon.values, canonical_lon())

    def test_dims_are_time_lat_lon(self, ds):
        for v in ds.data_vars:
            assert ds[v].dims == ("time", "lat", "lon"), v

    def test_time_is_daily_unique_and_ascending(self, ds):
        t = pd.DatetimeIndex(ds.time.values)
        assert (t == t.normalize()).all()
        assert t.is_unique and t.is_monotonic_increasing

    def test_chunking_is_as_documented(self, ds):
        ch = ds.chunks
        assert max(ch["lat"]) == 101 and max(ch["lon"]) == 241, "spatial field must be one chunk"
        assert max(ch["time"]) == 32

    def test_target_validity_never_increases_with_depth(self, ds):
        """Physically, a cell valid at depth d must be valid at every shallower
        depth. Rising validity would mean values invented below the seafloor."""
        prev = None
        for dep in FINAL_DEPTHS:
            frac = float(ds[f"target_valid_{int(dep)}m"].mean().compute())
            if prev is not None:
                assert frac <= prev + 1e-9, f"validity rose at {dep} m"
            prev = frac

    def test_zero_metre_clamp_is_recorded_in_metadata(self, ds):
        assert "CLAMPED" in ds.attrs["depth_0m_policy"]
        assert "0.494" in ds.attrs["depth_0m_policy"]

    def test_official_sss_product_is_the_one_recorded(self, ds):
        """The smoke-test SMAP 8-day product must not survive into model-ready data."""
        assert "cmems_obs-mob_glo_phy-sss_my_multi_P1D" in ds.attrs["source_sss"]
        assert "10.48670/moi-00051" in ds.attrs["source_sss"]
        assert "SMAP" not in ds.attrs["source_sss"]

    def test_no_variable_is_entirely_nan(self, ds):
        for v in ds.data_vars:
            if ds[v].dtype == bool:
                continue
            assert bool(np.isfinite(ds[v]).any().compute()), v

    def test_temperature_decreases_with_depth_in_domain_mean(self, ds):
        means = [float(ds[f"temp_{int(d)}m"].mean().compute()) for d in (100, 300, 500, 700, 1000)]
        assert means == sorted(means, reverse=True), means
