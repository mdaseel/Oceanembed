"""Phase 6C-A guards for the Argo observational audit.

The ways this audit could produce a wrong-but-plausible number: comparing
in-situ against potential temperature, extrapolating a profile to a depth it
never sampled, interpolating a model field through land, scoring the four
systems on different samples, letting the 2024 holdout in, or mutating the
matched table while computing metrics.
"""
from __future__ import annotations

import hashlib
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
from oceanembed.validation import argo as A  # noqa: E402
from oceanembed.validation import argo_metrics as AM  # noqa: E402
from oceanembed.validation.collocate import (METHOD, bracket_indices,  # noqa: E402
                                             interp_point, nearest_grid_cell)

ARGO = ROOT / "outputs" / "argo"
MODELS = ROOT / "outputs" / "models"
BASE = ROOT / "outputs" / "baselines"
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
MATCHED = ARGO / "matched_profiles.parquet"
HELDOUT_START = pd.Timestamp("2024-01-01")

L2_ENCODER_SHA = "30cfd2db9e8b6b96473c1e205280c009"
L2_FULL_SHA = "b715bb2bff32d5e4a1e696b5350e29c3"
L1_SHA = "29419ad1dc2c4a1d6943e524e852c934"


def _sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


# ------------------------------------------------------- frozen model guards
def test_l2_checkpoint_is_unchanged():
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    assert _sha(ck["state_dict"])[:32] == L2_FULL_SHA
    assert _sha(ck["encoder_state_dict"])[:32] == L2_ENCODER_SHA


def test_l1_checkpoint_is_unchanged():
    ck = torch.load(MODELS / "phase6b_l1_mlp.pt", map_location="cpu", weights_only=False)
    assert _sha(ck["state_dict"])[:32] == L1_SHA


def test_frozen_climatology_and_scalers_are_train_only():
    from oceanembed.ml.climatology import HarmonicClimatology
    c = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert c.meta["fitted_on"] == "train"
    assert c.meta["fit_end"] == splits.split_bounds("train")[1]
    for f in ("phase6b_feature_scaler.json", "phase6b_target_scaler.json"):
        assert json.load(open(BASE / f, encoding="utf-8"))["fitted_on"] == "train"


def test_audit_scripts_create_no_optimiser():
    """This phase performs inference only - no training may be present."""
    for p in ("scripts/validate/argo_validate.py", "scripts/validate/argo_analyse.py"):
        src = (ROOT / p).read_text(encoding="utf-8")
        for banned in ("torch.optim", ".backward()", "optimizer", "opt.step("):
            assert banned not in src, f"{p} contains {banned}"


# ------------------------------------------------------------ QC / DATA_MODE
def test_qc_bytes_handles_every_encoding():
    assert list(A._qc_bytes(np.array([b"1", b"4", b" "], dtype=object))) == [b"1", b"4", b"9"]
    assert list(A._qc_bytes(np.array([b"114"], dtype=object))) == [b"1", b"1", b"4"]
    assert list(A._qc_bytes(np.array([1.0, 4.0, np.nan]))) == [b"1", b"4", b"9"]
    assert list(A._qc_bytes(np.array(["1", "2"]))) == [b"1", b"2"]


def test_only_qc_1_and_2_are_good():
    assert A.GOOD_QC == {b"1", b"2"}
    assert b"3" not in A.GOOD_QC and b"4" not in A.GOOD_QC


def test_interpolated_position_flag_8_is_rejected():
    """Flag 8 is an interpolated location, too coarse for 0.25 deg collocation."""
    assert b"8" not in A.GOOD_POSITION_QC


def _fake_ds(mode=b"D", n_levels=6, fill_adjusted=True):
    n = n_levels
    pres = np.linspace(5, 500, n)
    temp = np.linspace(28, 8, n)
    psal = np.full(n, 35.0)
    adj_t = temp + 0.5 if fill_adjusted else np.full(n, np.nan)
    ds = xr.Dataset({
        "DATA_MODE": ("N_PROF", np.array([mode], dtype=object)),
        "POSITION_QC": ("N_PROF", np.array([b"1"], dtype=object)),
        "JULD_QC": ("N_PROF", np.array([b"1"], dtype=object)),
        "LATITUDE": ("N_PROF", np.array([15.0])),
        "LONGITUDE": ("N_PROF", np.array([70.0])),
        "PRES": (("N_PROF", "N_LEVELS"), pres[None, :]),
        "TEMP": (("N_PROF", "N_LEVELS"), temp[None, :]),
        "PSAL": (("N_PROF", "N_LEVELS"), psal[None, :]),
        "PRES_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
        "TEMP_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
        "PSAL_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
        "PRES_ADJUSTED": (("N_PROF", "N_LEVELS"), pres[None, :]),
        "TEMP_ADJUSTED": (("N_PROF", "N_LEVELS"), adj_t[None, :]),
        "PSAL_ADJUSTED": (("N_PROF", "N_LEVELS"), psal[None, :]),
        "PRES_ADJUSTED_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
        "TEMP_ADJUSTED_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
        "PSAL_ADJUSTED_QC": (("N_PROF", "N_LEVELS"), np.array([[b"1"] * n], dtype=object)),
    })
    return ds


@pytest.mark.parametrize("mode,expect_adjusted", [(b"D", True), (b"A", True), (b"R", False)])
def test_data_mode_selects_adjusted_or_raw(mode, expect_adjusted):
    f = A.select_fields(_fake_ds(mode), 0)
    assert f["used_adjusted"] is expect_adjusted
    assert f["TEMP_source"] == ("TEMP_ADJUSTED" if expect_adjusted else "TEMP")


def test_delayed_mode_uses_adjusted_values_not_raw():
    f = A.select_fields(_fake_ds(b"D"), 0)
    raw = _fake_ds(b"D")["TEMP"].values[0]
    assert np.allclose(f["TEMP"], raw + 0.5), "delayed mode must use the calibrated values"


def test_adjusted_empty_profile_yields_no_levels_rather_than_falling_back():
    f = A.select_fields(_fake_ds(b"D", fill_adjusted=False), 0)
    assert A.accepted_levels(f).sum() == 0


def test_bad_qc_levels_are_dropped():
    ds = _fake_ds(b"R")
    q = ds["TEMP_QC"].values.copy()
    q[0][2] = b"4"
    ds["TEMP_QC"] = (("N_PROF", "N_LEVELS"), q)
    f = A.select_fields(ds, 0)
    acc = A.accepted_levels(f)
    assert acc.sum() == ds.sizes["N_LEVELS"] - 1 and not acc[2]


def test_implausible_values_are_dropped():
    ds = _fake_ds(b"R")
    t = ds["TEMP"].values.copy()
    t[0][1] = 99.0
    ds["TEMP"] = (("N_PROF", "N_LEVELS"), t)
    assert not A.accepted_levels(A.select_fields(ds, 0))[1]


def test_profile_gate_rejects_bad_position_and_time():
    ds = _fake_ds()
    ds["POSITION_QC"] = ("N_PROF", np.array([b"4"], dtype=object))
    ok, why = A.profile_is_acceptable(ds, 0)
    assert not ok and "position_qc" in why
    ds2 = _fake_ds()
    ds2["JULD_QC"] = ("N_PROF", np.array([b"3"], dtype=object))
    ok2, why2 = A.profile_is_acceptable(ds2, 0)
    assert not ok2 and "juld_qc" in why2


# ------------------------------------------------- potential temperature
def test_potential_temperature_differs_from_in_situ_at_depth():
    """The whole point of the conversion: at 1000 dbar the difference is
    ~0.08 degC, comparable to the model differences being measured."""
    pt, depth = A.to_potential_temperature(
        np.array([1000.0]), np.array([5.0]), np.array([35.0]), 70.0, 15.0)
    assert 0.05 < (5.0 - pt[0]) < 0.15
    assert 980 < depth[0] < 1010, "depth from pressure must be near 1000 m"


def test_potential_temperature_equals_in_situ_at_the_surface():
    pt, _ = A.to_potential_temperature(
        np.array([0.0]), np.array([28.0]), np.array([35.0]), 70.0, 15.0)
    assert abs(pt[0] - 28.0) < 1e-6


def test_depth_from_pressure_is_latitude_dependent():
    _, d_eq = A.to_potential_temperature(np.array([1000.0]), np.array([5.0]),
                                         np.array([35.0]), 70.0, 0.0)
    _, d_hi = A.to_potential_temperature(np.array([1000.0]), np.array([5.0]),
                                         np.array([35.0]), 70.0, 30.0)
    assert d_eq[0] != d_hi[0], "gsw.z_from_p must use latitude, not 1 dbar = 1 m"


# ------------------------------------------------- vertical interpolation
def test_no_extrapolation_above_or_below_the_profile():
    depth = np.array([20.0, 50.0, 100.0])
    val = np.array([28.0, 25.0, 20.0])
    out, sup, _ = A.interp_to_depths(depth, val, [0, 5, 10, 50, 200, 1000])
    assert not sup[0] and not sup[1] and not sup[2], "must not extrapolate shallower"
    assert not sup[4] and not sup[5], "must not extrapolate deeper"
    assert sup[3] and out[3] == pytest.approx(25.0)


def test_zero_metre_is_essentially_never_supported():
    depth = np.array([4.9, 20.0, 100.0])
    _, sup, _ = A.interp_to_depths(depth, np.array([28.0, 27.0, 20.0]), [0])
    assert not sup[0], "0 m must not be produced from a 4.9 m shallowest sample"


def test_exact_match_is_returned_unchanged():
    out, sup, gap = A.interp_to_depths(np.array([50.0, 100.0]), np.array([25.0, 20.0]), [50])
    assert sup[0] and out[0] == pytest.approx(25.0) and gap[0] == 0.0


def test_linear_interpolation_is_correct():
    out, sup, _ = A.interp_to_depths(np.array([50.0, 100.0]), np.array([20.0, 10.0]), [75])
    assert sup[0] and out[0] == pytest.approx(15.0)


def test_large_vertical_gap_is_not_bridged():
    out, sup, _ = A.interp_to_depths(np.array([100.0, 400.0]), np.array([20.0, 8.0]),
                                     [200], max_gap_m=100.0)
    assert not sup[0], "a 300 m gap must not be interpolated across"


def test_unsorted_and_duplicate_depths_are_handled():
    out, sup, _ = A.interp_to_depths(np.array([100.0, 50.0, 50.0]),
                                     np.array([20.0, 25.0, 25.0]), [75])
    assert sup[0] and out[0] == pytest.approx(22.5)


def test_too_few_levels_yields_nothing():
    _, sup, _ = A.interp_to_depths(np.array([50.0]), np.array([25.0]), [50])
    assert not sup.any()


# ------------------------------------------------------------ collocation
def _grid():
    return np.array([10.0, 10.25, 10.5]), np.array([70.0, 70.25, 70.5])


def test_bilinear_reproduces_a_uniform_field():
    lat, lon = _grid()
    f = np.full((3, 3), 25.0)
    v, how = interp_point(f, lat, lon, 10.1, 70.1)
    assert v == pytest.approx(25.0) and how == "bilinear_wet"


def test_bilinear_is_exact_at_a_grid_node():
    lat, lon = _grid()
    f = np.arange(9, dtype="float64").reshape(3, 3)
    v, _ = interp_point(f, lat, lon, 10.25, 70.25)
    assert v == pytest.approx(f[1, 1])


def test_interpolation_never_mixes_land_into_the_value():
    """A NaN (land) corner must not drag the interpolated value toward zero."""
    lat, lon = _grid()
    f = np.full((3, 3), 20.0)
    f[0, 0] = np.nan
    v, how = interp_point(f, lat, lon, 10.1, 70.1)
    assert v == pytest.approx(20.0), "wet-only weights must renormalise"
    assert how == "bilinear_wet"
    assert np.isfinite(v)


def test_single_wet_neighbour_falls_back_to_nearest_wet():
    lat, lon = _grid()
    f = np.full((3, 3), np.nan)
    f[1, 1] = 22.0
    v, how = interp_point(f, lat, lon, 10.24, 70.24)
    assert v == pytest.approx(22.0) and how == "nearest_wet"


def test_all_land_returns_nan_not_a_fabricated_value():
    lat, lon = _grid()
    v, how = interp_point(np.full((3, 3), np.nan), lat, lon, 10.1, 70.1)
    assert np.isnan(v) and how == "no_wet_neighbour"


def test_outside_domain_returns_nan():
    lat, lon = _grid()
    v, how = interp_point(np.full((3, 3), 20.0), lat, lon, 40.0, 70.1)
    assert np.isnan(v) and how == "outside_domain"


def test_collocation_is_deterministic():
    lat, lon = _grid()
    f = np.arange(9, dtype="float64").reshape(3, 3)
    assert interp_point(f, lat, lon, 10.12, 70.19) == interp_point(f, lat, lon, 10.12, 70.19)


def test_bracket_indices_are_ordered():
    ax = np.array([0.0, 1.0, 2.0, 3.0])
    i0, i1, w = bracket_indices(ax, 1.5)
    assert i0 == 1 and i1 == 2 and w == pytest.approx(0.5)


def test_nearest_grid_cell_reports_offset():
    lat, lon = _grid()
    i, j, off = nearest_grid_cell(lat, lon, 10.26, 70.24)
    assert (i, j) == (1, 1) and off < 0.05


def test_collocation_method_is_fixed_and_recorded():
    assert METHOD == "ocean_aware_bilinear_then_nearest_wet_within_1_cell"


# ------------------------------------------------------------------ metrics
def _toy_matched(n=200, seed=0):
    rng = np.random.default_rng(seed)
    d = {"wmo": [f"F{i % 10}" for i in range(n)],
         "lat": rng.uniform(6, 24, n), "lon": rng.uniform(52, 98, n),
         "date": pd.to_datetime(["2022-06-01"] * n)}
    for dep in DEPTHS:
        obs = rng.normal(20, 3, n)
        d[f"argo_pt_{dep}m"] = obs
        d[f"argo_sup_{dep}m"] = np.ones(n, dtype=bool)
        d["L0_" + f"{dep}m"] = obs + rng.normal(0, 1.5, n)
        d["L1_" + f"{dep}m"] = obs + rng.normal(0, 1.0, n)
        d["L2_" + f"{dep}m"] = obs + rng.normal(0, 0.7, n)
        d["GLORYS_" + f"{dep}m"] = obs + rng.normal(0, 0.4, n)
    return pd.DataFrame(d)


def test_accepted_mask_does_not_mutate_the_dataframe():
    """Regression: to_numpy on a bool column returns a VIEW, so an in-place &=
    rewrote argo_sup_<d>m and silently emptied the second basin subgroup."""
    df = _toy_matched()
    before = {d: int(df[f"argo_sup_{d}m"].sum()) for d in DEPTHS}
    for d in DEPTHS:
        AM.accepted_mask(df, d)
    assert {d: int(df[f"argo_sup_{d}m"].sum()) for d in DEPTHS} == before


def test_subset_evaluation_does_not_mutate_the_dataframe():
    df = _toy_matched()
    before = {d: int(df[f"argo_sup_{d}m"].sum()) for d in DEPTHS}
    for name in AM.BASINS:
        AM.metrics_by_depth(df, DEPTHS, subset=AM.basin_mask(df, name))
    assert {d: int(df[f"argo_sup_{d}m"].sum()) for d in DEPTHS} == before


def test_disjoint_basins_both_retain_samples():
    df = _toy_matched()
    a = AM.metrics_by_depth(df, DEPTHS, subset=AM.basin_mask(df, "arabian_sea"))
    b = AM.metrics_by_depth(df, DEPTHS, subset=AM.basin_mask(df, "bay_of_bengal"))
    assert a.n.sum() > 0 and b.n.sum() > 0
    assert not (AM.basin_mask(df, "arabian_sea") & AM.basin_mask(df, "bay_of_bengal")).any()


def test_all_four_systems_score_on_identical_samples():
    df = _toy_matched()
    df.loc[:20, "L1_100m"] = np.nan          # make one model missing somewhere
    bd = AM.metrics_by_depth(df, DEPTHS)
    at100 = bd[bd.depth_m == 100]
    assert at100.n.nunique() == 1, "every model must use the same sample count"


def test_missing_argo_support_excludes_the_depth():
    df = _toy_matched()
    df["argo_sup_100m"] = False
    assert AM.accepted_mask(df, 100).sum() == 0


def test_rmse_and_bias_match_direct_numpy():
    df = _toy_matched()
    bd = AM.metrics_by_depth(df, [100])
    m = AM.accepted_mask(df, 100)
    obs = df.loc[m, "argo_pt_100m"].to_numpy()
    for name in AM.MODELS:
        pred = df.loc[m, f"{name}_100m"].to_numpy()
        row = bd[(bd.depth_m == 100) & (bd.model == name)].iloc[0]
        assert row["rmse"] == pytest.approx(np.sqrt(np.mean((pred - obs) ** 2)))
        assert row["bias"] == pytest.approx(np.mean(pred - obs))


def test_improvement_sign_is_reported_both_ways():
    df = _toy_matched()
    good = AM.pairwise(df, [100], "L2", "L0").iloc[0]
    bad = AM.pairwise(df, [100], "L0", "L2").iloc[0]
    assert good["improvement_percent"] > 0 and bool(good["L2_better"])
    assert bad["improvement_percent"] < 0 and not bool(bad["L0_better"])


def test_bootstrap_resamples_floats_not_observations():
    df = _toy_matched()
    r = AM.cluster_bootstrap_rmse_diff(df, 100, "L2", "L0", n_boot=100)
    assert r["cluster_unit"] == "wmo"
    assert r["n_clusters"] == df.wmo.nunique()
    assert r["ci_lo"] < r["rmse_difference"] < r["ci_hi"]


def test_bootstrap_is_reproducible():
    df = _toy_matched()
    a = AM.cluster_bootstrap_rmse_diff(df, 100, "L2", "L0", n_boot=50, seed=1)
    b = AM.cluster_bootstrap_rmse_diff(df, 100, "L2", "L0", n_boot=50, seed=1)
    assert a == b


def test_small_subgroups_are_suppressed_not_reported():
    df = _toy_matched(n=10)
    r = AM.cluster_bootstrap_rmse_diff(df, 100, "L2", "L0", n_boot=10)
    assert r.get("insufficient") is True


def test_depth_groups_cover_all_fifteen_depths():
    flat = [d for v in AM.DEPTH_GROUPS.values() for d in v]
    assert sorted(flat) == sorted(DEPTHS)


# ------------------------------------------------------ real outputs / leakage
@pytest.mark.skipif(not MATCHED.exists(), reason="matched profiles not built")
class TestRealOutputs:
    @pytest.fixture(scope="class")
    def df(self):
        return pd.read_parquet(MATCHED)

    def test_holdout_2024_never_appears(self, df):
        assert df.date.max() < HELDOUT_START, "2024 is a declared observational holdout"

    def test_audit_window_is_as_declared(self, df):
        assert df.date.min() >= pd.Timestamp("2022-01-01")
        assert df.date.max() <= pd.Timestamp("2023-12-31")

    def test_no_test_embeddings_of_heldout_dates_used(self, df):
        assert not (pd.DatetimeIndex(df.date) >= HELDOUT_START).any()

    def test_every_matched_profile_is_inside_the_domain(self, df):
        assert df.lat.between(5.0, 30.0).all()
        assert df.lon.between(45.0, 105.0).all()

    def test_collocation_offsets_are_within_one_grid_cell(self, df):
        assert (df.grid_offset_deg <= 0.25 * np.sqrt(2) / 2 + 1e-9).all()

    def test_temporal_offset_is_zero(self, df):
        assert (df.temporal_offset_days == 0).all()

    def test_no_argo_temperature_leaks_into_a_model_column(self, df):
        """Model predictions must never simply echo the observation."""
        for d in (50, 100, 200):
            m = AM.accepted_mask(df, d)
            for name in AM.MODELS:
                same = np.isclose(df.loc[m, f"{name}_{d}m"].to_numpy(),
                                  df.loc[m, f"argo_pt_{d}m"].to_numpy(), atol=1e-9)
                assert same.mean() < 0.01, f"{name} at {d} m mirrors Argo"

    def test_zero_metre_support_is_rare_as_expected(self, df):
        n0 = int(AM.accepted_mask(df, 0).sum())
        n100 = int(AM.accepted_mask(df, 100).sum())
        assert n0 < 0.1 * n100, "Argo essentially never samples the nominal 0 m level"

    def test_qc_summary_records_data_mode_distribution(self):
        q = json.load(open(ARGO / "qc_summary.json", encoding="utf-8"))
        assert set(q["data_mode"]) <= {"D", "A", "R"}
        assert q["accepted"] > 0 and q["collocated"] == q["accepted"]

    def test_collocation_manifest_records_the_method(self):
        m = json.load(open(ARGO / "collocation_manifest.json", encoding="utf-8"))
        assert m["method"] == METHOD
        assert m["heldout_untouched"][0] == "2024-01-01"
        assert m["depths_m"] == DEPTHS
