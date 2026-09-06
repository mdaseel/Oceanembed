"""Phase 6B-A guards: leakage, masking, shapes, determinism, metric correctness.

The dominant risk in a baseline like this is not a crash but a quietly
optimistic number - a statistic fitted on data it should not have seen, a
masked target silently treated as zero, or a "skill" score that is really a
bug. Each test targets one of those.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.ml import splits  # noqa: E402
from oceanembed.ml.climatology import HarmonicClimatology  # noqa: E402
from oceanembed.ml.dataset import PointwiseSampler  # noqa: E402
from oceanembed.ml.features import (FEATURE_NAMES, N_FEATURES, cyclic_doy,  # noqa: E402
                                    harmonic_design)
from oceanembed.ml.metrics import DepthAccumulator, basin_of, skill_table  # noqa: E402
from oceanembed.ml.model import PointwiseMLP, masked_mse, set_seed  # noqa: E402
from oceanembed.ml.scaler import RunningMoments, ZScoreScaler  # noqa: E402

BASE = ROOT / "outputs" / "baselines"
MODELS = ROOT / "outputs" / "models"
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]


# ------------------------------------------------------- split separation
def test_splits_do_not_overlap():
    splits.assert_no_overlap()


def test_train_strictly_precedes_validation_precedes_test():
    tr, va, te = (splits.split_dates(n) for n in ("train", "validation", "test"))
    assert tr.max() < va.min(), "train must end before validation begins"
    assert va.max() < te.min(), "validation must end before test begins"


def test_test_split_is_locked_against_accidental_opening():
    with pytest.raises(PermissionError):
        splits.open_split("test")


def test_contains_test_dates_detects_leakage():
    assert splits.contains_test_dates(pd.to_datetime(["2023-06-01"])) is True
    assert splits.contains_test_dates(pd.to_datetime(["2019-06-01"])) is False
    assert splits.contains_test_dates(pd.to_datetime(["2022-01-01"])) is True
    assert splits.contains_test_dates(pd.to_datetime(["2021-12-31"])) is False


# ----------------------------------------------- cyclic day-of-year encoding
def test_cyclic_doy_is_continuous_across_new_year():
    s, c = cyclic_doy(pd.to_datetime(["2019-12-31", "2020-01-01"]))
    gap = float(np.hypot(s[1] - s[0], c[1] - c[0]))
    assert gap < 0.05, f"Dec31->Jan1 discontinuity {gap}"


def test_cyclic_doy_lies_on_unit_circle():
    s, c = cyclic_doy(pd.date_range("2020-01-01", periods=366))
    assert np.allclose(s ** 2 + c ** 2, 1.0)


def test_cyclic_doy_is_roughly_periodic_year_to_year():
    a = cyclic_doy(pd.to_datetime(["2017-03-15"]))
    b = cyclic_doy(pd.to_datetime(["2018-03-15"]))
    assert abs(a[0][0] - b[0][0]) < 0.05 and abs(a[1][0] - b[1][0]) < 0.05


# ------------------------------------------------------------- climatology
def _toy_clim_ds():
    t = pd.date_range("2015-01-01", "2020-12-31", freq="D")
    doy = t.dayofyear.to_numpy()
    sig = 28 + 2 * np.cos(2 * np.pi * doy / 365.25) + 0.5 * np.sin(4 * np.pi * doy / 365.25)
    return xr.Dataset(
        {"temp_0m": (("time", "lat", "lon"), sig[:, None, None] * np.ones((1, 1))),
         "target_valid_0m": (("time", "lat", "lon"), np.ones((len(t), 1, 1), bool))},
        coords={"time": t, "lat": [10.0], "lon": [70.0]})


def test_climatology_recovers_a_known_harmonic_signal():
    ds = _toy_clim_ds()
    c = HarmonicClimatology.fit(ds, [0], n_harmonics=3, log=lambda *a: None)
    pred = c.predict(pd.DatetimeIndex(ds.time.values))[:, 0, 0, 0]
    assert np.max(np.abs(pred - ds["temp_0m"].values[:, 0, 0])) < 1e-6


def test_climatology_is_periodic_no_new_year_jump():
    c = HarmonicClimatology.fit(_toy_clim_ds(), [0], n_harmonics=3, log=lambda *a: None)
    p = c.predict(pd.to_datetime(["2021-12-31", "2022-01-01"]))[:, 0, 0, 0]
    assert abs(p[1] - p[0]) < 0.1, "climatology must not jump at the year boundary"


def test_climatology_predicts_unseen_dates():
    c = HarmonicClimatology.fit(_toy_clim_ds(), [0], n_harmonics=3, log=lambda *a: None)
    assert np.isfinite(c.predict(pd.to_datetime(["2023-07-15"]))).all()


def test_harmonic_design_has_expected_shape():
    A = harmonic_design(pd.date_range("2020-01-01", periods=10), n_harmonics=3)
    assert A.shape == (10, 7)
    assert np.allclose(A[:, 0], 1.0), "first column must be the intercept"


@pytest.mark.skipif(not (BASE / "phase6b_climatology.nc").exists(),
                    reason="fit_climatology.py not run")
def test_fitted_climatology_used_train_years_only():
    c = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert c.meta["fitted_on"] == "train"
    tr_s, tr_e = splits.split_bounds("train")
    assert c.meta["fit_start"] == tr_s and c.meta["fit_end"] == tr_e
    assert int(c.meta["n_fit_days"]) == len(splits.split_dates("train"))
    assert not splits.contains_test_dates(
        pd.to_datetime([c.meta["fit_start"], c.meta["fit_end"]]))


# ------------------------------------------------------------------ scaler
def test_running_moments_match_numpy():
    rng = np.random.default_rng(0)
    X = rng.normal(5, 3, size=(5000, 3))
    rm = RunningMoments(3)
    for i in range(0, 5000, 617):
        rm.update(X[i:i + 617])
    assert np.allclose(rm.mean, X.mean(axis=0))
    assert np.allclose(rm.std, X.std(axis=0, ddof=1))


def test_running_moments_respect_the_valid_mask():
    X = np.array([[1.0, 100.0], [2.0, 200.0], [3.0, 999.0]])
    v = np.array([[True, True], [True, True], [True, False]])
    rm = RunningMoments(2)
    rm.update(X, valid=v)
    assert np.isclose(rm.mean[1], 150.0), "masked value must not enter the mean"


def test_scaler_roundtrip_is_lossless(tmp_path):
    s = ZScoreScaler(np.array([1.0, 2.0]), np.array([3.0, 4.0]), ["a", "b"])
    p = tmp_path / "s.json"
    s.to_json(p)
    b = ZScoreScaler.from_json(p)
    x = np.random.default_rng(0).normal(size=(50, 2))
    assert np.allclose(s.transform(x), b.transform(x))
    assert np.allclose(s.inverse_transform(s.transform(x)), x)


def test_scaler_handles_zero_variance_channel():
    s = ZScoreScaler(np.array([5.0]), np.array([0.0]), ["const"])
    assert np.isfinite(s.transform(np.array([[5.0], [5.0]]))).all()


@pytest.mark.skipif(not (BASE / "phase6b_feature_scaler.json").exists(),
                    reason="fit_scaler.py not run")
def test_fitted_scalers_are_train_only():
    for f in ("phase6b_feature_scaler.json", "phase6b_target_scaler.json"):
        d = json.load(open(BASE / f, encoding="utf-8"))
        assert d["fitted_on"] == "train"
    d = json.load(open(BASE / "phase6b_feature_scaler.json", encoding="utf-8"))
    assert d["names"] == FEATURE_NAMES
    assert d["meta"]["start"] == splits.split_bounds("train")[0]
    assert d["meta"]["end"] == splits.split_bounds("train")[1]


# ------------------------------------------------------------------ model
def test_model_output_is_fifteen_depths():
    m = PointwiseMLP(N_FEATURES, (256, 256, 128), 15)
    assert m(torch.randn(7, N_FEATURES)).shape == (7, 15)


def test_model_input_width_matches_feature_list():
    assert N_FEATURES == len(FEATURE_NAMES) == 11


def test_model_is_pointwise_no_cross_sample_mixing():
    """A pointwise model must give the same answer for a row regardless of the
    other rows in the batch - i.e. no spatial or temporal context leaks in."""
    set_seed(0)
    m = PointwiseMLP().eval()
    x = torch.randn(16, N_FEATURES)
    with torch.no_grad():
        full = m(x)
        alone = m(x[3:4])
    assert torch.allclose(full[3], alone[0], atol=1e-6)


# ------------------------------------------------------------ masked loss
def test_masked_loss_matches_hand_computation():
    p = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    t = torch.zeros(2, 2)
    m = torch.tensor([[True, False], [True, True]])
    assert float(masked_mse(p, t, m)) == pytest.approx(10.5)


def test_masked_loss_ignores_a_fully_masked_depth():
    p = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    t = torch.zeros(2, 2)
    m = torch.tensor([[True, False], [True, False]])
    assert float(masked_mse(p, t, m)) == pytest.approx(5.0)


def test_masked_loss_is_nan_safe_for_missing_targets():
    """Missing targets must never be replaced by zero, and a NaN sitting under
    a False mask must not poison the depth it belongs to."""
    p = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    t = torch.tensor([[0.0, 0.0], [float("nan"), 0.0]])
    m = torch.tensor([[True, True], [False, True]])
    v = float(masked_mse(p, t, m))
    assert np.isfinite(v) and v == pytest.approx(5.5)


def test_masked_loss_gradient_is_zero_on_masked_entries():
    p = torch.tensor([[1.0, 2.0]], requires_grad=True)
    masked_mse(p, torch.zeros(1, 2), torch.tensor([[True, False]])).backward()
    assert float(p.grad[0, 1]) == 0.0
    assert float(p.grad[0, 0]) != 0.0


def test_masked_loss_does_not_favour_depths_with_more_samples():
    """Averaging per depth then across depths keeps a depth with few valid
    cells from being drowned out by shallow depths that have many."""
    p = torch.zeros(100, 2)
    t = torch.zeros(100, 2)
    p[:, 0] = 1.0
    p[0, 1] = 10.0
    m = torch.zeros(100, 2, dtype=torch.bool)
    m[:, 0] = True
    m[0, 1] = True
    assert float(masked_mse(p, t, m)) == pytest.approx(50.5)


# --------------------------------------------------------------- dataset
def _toy_store(n_days=4):
    t = pd.date_range("2015-01-01", periods=n_days, freq="D")
    lat = np.array([5.0, 5.25])
    lon = np.array([45.0, 45.25, 45.5])
    shp = (n_days, 2, 3)
    ds = xr.Dataset(coords={"time": t, "lat": lat, "lon": lon})
    rng = np.random.default_rng(0)
    for v in ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]:
        ds[v] = (("time", "lat", "lon"), rng.normal(size=shp))
    for d in DEPTHS:
        ds[f"temp_{d}m"] = (("time", "lat", "lon"), rng.normal(20, 2, size=shp))
        tv = np.ones(shp, bool)
        if d >= 500:
            tv[:, 0, 0] = False
            ds[f"temp_{d}m"].values[:, 0, 0] = np.nan
        ds[f"target_valid_{d}m"] = (("time", "lat", "lon"), tv)
    siv = np.ones(shp, bool)
    siv[:, 1, 2] = False
    ds["surface_input_valid"] = (("time", "lat", "lon"), siv)
    ds["ocean_mask"] = (("time", "lat", "lon"), np.ones(shp, bool))
    return ds


def test_dataset_feature_shape_is_eleven():
    smp = PointwiseSampler(_toy_store(), DEPTHS, chunk_days=2)
    X, Y, M, *_ = next(smp.blocks())
    assert X.shape[1] == N_FEATURES
    assert Y.shape[1] == len(DEPTHS) == 15
    assert M.shape == Y.shape


def test_dataset_excludes_cells_failing_surface_input_valid():
    smp = PointwiseSampler(_toy_store(), DEPTHS, chunk_days=4)
    assert smp.n_cells == 5, "the one surface-invalid cell must be dropped"
    X, *_ = next(smp.blocks())
    assert len(X) == 4 * 5


def test_dataset_keeps_shallow_cells_that_lack_deep_targets():
    """The regression this guards: dropping a sample because 1000 m is missing
    would delete the entire continental shelf from training."""
    smp = PointwiseSampler(_toy_store(), DEPTHS, chunk_days=4)
    _, _, M, *_ = next(smp.blocks())
    i500 = DEPTHS.index(500)
    assert (~M[:, i500]).any(), "expected some samples missing the 500 m target"
    assert M[:, 0].all(), "those same samples must still be valid at the surface"


def test_dataset_never_emits_nan_features_or_unmasked_nan_targets():
    smp = PointwiseSampler(_toy_store(), DEPTHS, chunk_days=4)
    X, Y, M, *_ = next(smp.blocks())
    assert np.isfinite(X).all()
    assert np.isfinite(Y[M]).all(), "every unmasked target must be finite"


def test_dataset_lat_lon_features_match_the_cell():
    smp = PointwiseSampler(_toy_store(), DEPTHS, chunk_days=1)
    X, *_ = next(smp.blocks())
    assert np.allclose(X[:, 7], smp.cell_lat)
    assert np.allclose(X[:, 8], smp.cell_lon)


def test_dataset_has_no_future_day_leakage():
    """Each emitted row must carry only its own day's surface values."""
    ds = _toy_store(n_days=3)
    smp = PointwiseSampler(ds, DEPTHS, chunk_days=3)
    X, *_ = next(smp.blocks())
    for k, v in enumerate(["sst", "sss", "sla", "current_u", "current_v",
                           "wind_u", "wind_v"]):
        expect = ds[v].values[:, smp.cell_idx[:, 0], smp.cell_idx[:, 1]].reshape(-1)
        assert np.allclose(X[:, k], expect, atol=1e-6), v


def test_dataset_target_is_not_among_the_features():
    """No temp_* value may appear in the input vector."""
    assert not any(n.startswith("temp_") for n in FEATURE_NAMES)


# --------------------------------------------------------------- metrics
def test_metric_accumulator_matches_direct_numpy():
    rng = np.random.default_rng(1)
    t = rng.normal(20, 3, size=(2000, 2))
    p = t + rng.normal(0.4, 1.0, size=(2000, 2))
    m = np.ones_like(t, bool)
    m[:50, 1] = False
    acc = DepthAccumulator([0, 100])
    for i in range(0, 2000, 137):
        acc.update(p[i:i + 137], t[i:i + 137], m[i:i + 137])
    f = acc.frame("x").set_index("depth_m")
    for j, d in enumerate([0, 100]):
        mm = m[:, j]
        dd = p[mm, j] - t[mm, j]
        assert f.loc[d, "rmse"] == pytest.approx(np.sqrt((dd ** 2).mean()))
        assert f.loc[d, "mae"] == pytest.approx(np.abs(dd).mean())
        assert f.loc[d, "bias"] == pytest.approx(dd.mean())
        assert f.loc[d, "correlation"] == pytest.approx(
            np.corrcoef(p[mm, j], t[mm, j])[0, 1], abs=1e-8)


def test_nrmse_normalises_by_truth_std():
    t = np.array([[10.0], [12.0], [14.0], [16.0]])
    p = t + 1.0
    acc = DepthAccumulator([0])
    acc.update(p, t, np.ones_like(t, bool))
    f = acc.frame("x").iloc[0]
    assert f["nrmse"] == pytest.approx(f["rmse"] / f["truth_std"])


def test_metric_accumulator_ignores_masked_entries():
    t = np.array([[1.0], [2.0], [1e6]])
    p = np.array([[1.0], [2.0], [0.0]])
    m = np.array([[True], [True], [False]])
    acc = DepthAccumulator([0])
    acc.update(p, t, m)
    assert acc.frame("x").iloc[0]["rmse"] == pytest.approx(0.0)
    assert int(acc.frame("x").iloc[0]["n"]) == 2


def test_skill_table_improvement_sign():
    l0 = pd.DataFrame({"depth_m": [0], "rmse": [2.0], "nrmse": [1.0], "correlation": [0.5]})
    l1 = pd.DataFrame({"depth_m": [0], "rmse": [1.0], "nrmse": [0.5], "correlation": [0.9]})
    s = skill_table(l0, l1)
    assert s.improvement_percent.iloc[0] == pytest.approx(50.0)
    assert bool(s.L1_beats_L0.iloc[0]) is True
    s2 = skill_table(l1, l0)
    assert s2.improvement_percent.iloc[0] == pytest.approx(-100.0)
    assert bool(s2.L1_beats_L0.iloc[0]) is False


def test_anomaly_is_difference_from_the_same_climatology():
    truth = np.array([[25.0], [26.0]])
    pred = np.array([[24.5], [26.5]])
    clim = np.array([[25.5], [25.5]])
    acc = DepthAccumulator([0])
    acc.update(pred - clim, truth - clim, np.ones_like(truth, bool))
    f = acc.frame("a").iloc[0]
    assert f["rmse"] == pytest.approx(np.sqrt(np.mean((pred - truth) ** 2)))


def test_basin_masks_are_disjoint_and_nonempty():
    lat = np.array([15.0, 15.0, 15.0])
    lon = np.array([65.0, 88.0, 78.5])
    a = basin_of(lat, lon, "arabian_sea")
    b = basin_of(lat, lon, "bay_of_bengal")
    assert a.tolist() == [True, False, False]
    assert b.tolist() == [False, True, False]
    assert not (a & b).any(), "basin boxes must not overlap"


# ------------------------------------------------- checkpoint / determinism
def test_checkpoint_roundtrip_is_exact(tmp_path):
    set_seed(3)
    m = PointwiseMLP()
    m.eval()
    x = torch.randn(32, N_FEATURES)
    with torch.no_grad():
        before = m(x)
    p = tmp_path / "ck.pt"
    torch.save({"state_dict": m.state_dict(), "n_features": N_FEATURES,
                "hidden": [256, 256, 128], "n_out": 15}, p)
    ck = torch.load(p, map_location="cpu", weights_only=False)
    m2 = PointwiseMLP(ck["n_features"], tuple(ck["hidden"]), ck["n_out"])
    m2.load_state_dict(ck["state_dict"])
    m2.eval()
    with torch.no_grad():
        after = m2(x)
    assert torch.equal(before, after), "reloaded model must be bit-identical"


def test_inference_is_deterministic():
    set_seed(11)
    m = PointwiseMLP().eval()
    x = torch.randn(64, N_FEATURES)
    with torch.no_grad():
        a, b = m(x), m(x)
    assert torch.equal(a, b)


def test_seeded_initialisation_is_reproducible():
    set_seed(7)
    a = PointwiseMLP().net[0].weight.detach().clone()
    set_seed(7)
    b = PointwiseMLP().net[0].weight.detach().clone()
    assert torch.equal(a, b)


@pytest.mark.skipif(not (MODELS / "phase6b_l1_mlp.pt").exists(),
                    reason="training not run")
def test_saved_checkpoint_has_expected_shape_and_metadata():
    ck = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    assert ck["n_out"] == 15
    assert ck["n_features"] == 11
    assert ck["depths"] == DEPTHS
    assert ck["feature_names"] == FEATURE_NAMES
    m = PointwiseMLP(ck["n_features"], tuple(ck["hidden"]), ck["n_out"])
    m.load_state_dict(ck["state_dict"])
    assert m(torch.zeros(2, 11)).shape == (2, 15)


def test_block_row_indices_align_after_dropping_bad_rows():
    """Regression guard.

    ``_read_block`` drops rows whose features are not all finite. Any auxiliary
    array built as (n_times x n_cells) - notably the L0 climatology - must be
    indexed by the returned row_time/row_cell, never by assuming nothing was
    dropped. That assumption held on the validation split and was silently
    false on the test split, which is exactly how an evaluation bug hides.
    """
    ds = _toy_store(n_days=3)
    ds["sst"].values[1, 0, 1] = np.nan          # kill one cell on one day
    smp = PointwiseSampler(ds, DEPTHS, chunk_days=3)
    X, Y, M, stamp, row_t, row_c = next(smp.blocks())

    nt = 3
    assert len(X) == nt * smp.n_cells - 1, "exactly one row should be dropped"
    assert len(row_t) == len(row_c) == len(stamp) == len(X)
    assert row_t.max() < nt and row_c.max() < smp.n_cells

    # An auxiliary (nt, n_cells) field indexed by row_t/row_c must reproduce
    # the same per-row values as the emitted features.
    aux = np.arange(nt * smp.n_cells).reshape(nt, smp.n_cells).astype("float64")
    picked = aux[row_t, row_c]
    expect = aux.reshape(-1)[np.isfinite(
        ds["sst"].values[:, smp.cell_idx[:, 0], smp.cell_idx[:, 1]]).reshape(-1)]
    assert np.array_equal(picked, expect)

    # lat/lon recovered via row_cell must match the emitted lat/lon features
    assert np.allclose(smp.cell_lat[row_c], X[:, 7])
    assert np.allclose(smp.cell_lon[row_c], X[:, 8])


def test_block_emits_no_rows_when_all_features_bad():
    ds = _toy_store(n_days=1)
    for v in ["sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"]:
        ds[v].values[:] = np.nan
    smp = PointwiseSampler(ds, DEPTHS, chunk_days=1)
    X, Y, M, stamp, row_t, row_c = next(smp.blocks())
    assert len(X) == 0 and len(row_t) == 0
