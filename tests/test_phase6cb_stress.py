"""Phase 6C-B guards for the input-availability stress baseline.

The ways this stress test could produce a wrong-but-flattering number: reading a
future day when simulating staleness, letting U and V drift to different ages,
scoring modes on different populations, mutating the source dataset while
degrading it, or quietly training something.
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
from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.ml.patches import N_CHANNELS, N_DATA_CHANNELS, day_field  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402
from oceanembed.ml.stress import (CH, MODES, MODES_BY_NAME, Mode,  # noqa: E402
                                  build_field, coherent_sss_gap_mask)

MODELS = ROOT / "outputs" / "models"
BASE = ROOT / "outputs" / "baselines"
TAB = ROOT / "outputs" / "tables"
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
PATCH = 33
L2_FULL_SHA = "b715bb2bff32d5e4a1e696b5350e29c3"
L2_ENC_SHA = "30cfd2db9e8b6b96473c1e205280c009"


def _sha(sd) -> str:
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


# ------------------------------------------------------------ frozen guards
def test_l2_checkpoint_unchanged():
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    assert _sha(ck["state_dict"])[:32] == L2_FULL_SHA
    assert _sha(ck["encoder_state_dict"])[:32] == L2_ENC_SHA


def test_stress_scripts_contain_no_training():
    for p in ("scripts/validate/input_stress.py", "src/oceanembed/ml/stress.py"):
        src = (ROOT / p).read_text(encoding="utf-8")
        for banned in ("torch.optim", ".backward()", "opt.step(", "requires_grad_(True)"):
            assert banned not in src, f"{p} contains {banned}"


def test_surface_climatology_is_train_only():
    from oceanembed.ml.surface_climatology import SurfaceClimatology
    c = SurfaceClimatology.load(BASE / "phase6cb_surface_climatology.nc")
    assert c.meta["fitted_on"] == "train"
    assert c.meta["fit_end"] == splits.split_bounds("train")[1]


def test_target_climatology_and_scalers_still_train_only():
    for f in ("phase6b_feature_scaler.json", "phase6b_target_scaler.json"):
        assert json.load(open(BASE / f, encoding="utf-8"))["fitted_on"] == "train"


def test_2024_argo_holdout_remains_inaccessible():
    matched = ROOT / "outputs" / "argo" / "matched_profiles.parquet"
    if matched.exists():
        df = pd.read_parquet(matched, columns=["date"])
        assert pd.to_datetime(df.date).max() < pd.Timestamp("2024-01-01")
    assert not (ROOT / "data" / "raw" / "argo_gdac" / "floats_2024").exists()


def test_split_lock_still_enforced():
    with pytest.raises(PermissionError):
        splits.open_split("test")


# -------------------------------------------------------- pre-registration
def test_modes_are_pre_registered_and_unique():
    names = [m.name for m in MODES]
    assert len(names) == len(set(names))
    for want in ("A_COMPLETE", "B_SSS_MISSING", "C_SSS_SPATIAL_GAPS",
                 "D_CURRENT_STALE_1D", "E_CURRENT_STALE_2D", "F_CURRENT_STALE_3D",
                 "G_WIND_STALE_1D", "H_SLA_STALE_1D",
                 "I_SSS_MISSING_CURRENT_STALE_2D"):
        assert want in MODES_BY_NAME


def test_current_and_wind_ages_are_paired():
    """U and V of the same vector must never be at different ages."""
    for m in MODES:
        cu, cv = m.age.get("current_u", 0), m.age.get("current_v", 0)
        wu, wv = m.age.get("wind_u", 0), m.age.get("wind_v", 0)
        assert cu == cv, f"{m.name}: current U/V ages differ"
        assert wu == wv, f"{m.name}: wind U/V ages differ"


def test_stale_modes_declare_the_expected_ages():
    assert MODES_BY_NAME["D_CURRENT_STALE_1D"].age["current_u"] == 1
    assert MODES_BY_NAME["E_CURRENT_STALE_2D"].age["current_v"] == 2
    assert MODES_BY_NAME["F_CURRENT_STALE_3D"].max_age == 3
    assert MODES_BY_NAME["G_WIND_STALE_1D"].age["wind_u"] == 1
    assert MODES_BY_NAME["H_SLA_STALE_1D"].age["sla"] == 1


# ------------------------------------------------------------- toy dataset
def _toy(n_days=8, nlat=40, nlon=45, seed=0):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2021-01-01", periods=n_days, freq="D")
    ds = xr.Dataset(coords={"time": t, "lat": 5.0 + 0.25 * np.arange(nlat),
                            "lon": 45.0 + 0.25 * np.arange(nlon)})
    for k, v in enumerate(SURFACE):
        # each channel gets a distinct per-day constant so provenance is traceable
        base = np.arange(n_days, dtype="float64")[:, None, None] * 100.0 + k
        ds[v] = (("time", "lat", "lon"), base + np.zeros((n_days, nlat, nlon)))
    land = np.zeros((n_days, nlat, nlon), bool)
    land[:, :3, :3] = True
    for v in SURFACE:
        vals = ds[v].values.copy()
        vals[land] = np.nan
        ds[v] = (("time", "lat", "lon"), vals)
    return ds


def _scaler():
    return ZScoreScaler(np.zeros(11), np.ones(11),
                        list(SURFACE) + ["lat", "lon", "doy_sin", "doy_cos"])


def _centre(field, ds, ch, patch=PATCH):
    """Value of channel ch at an interior domain cell, undoing the padding."""
    h = patch // 2
    return field[ch, h + 20, h + 20]


# ---------------------------------------------------------- time semantics
@pytest.mark.parametrize("age", [0, 1, 2, 3])
def test_stale_channel_reads_exactly_t_minus_age(age):
    ds, sc = _toy(), _scaler()
    m = Mode(f"age{age}", age={"current_u": age, "current_v": age})
    t = 5
    f = build_field(ds, t, sc, PATCH, m)
    assert _centre(f, ds, CH["current_u"]) == pytest.approx((t - age) * 100.0 + CH["current_u"])
    # an unaffected channel must still be same-day
    assert _centre(f, ds, CH["sst"]) == pytest.approx(t * 100.0 + CH["sst"])


def test_no_future_day_can_ever_be_read():
    """Every channel value must come from day <= t, never t+1."""
    ds, sc = _toy(), _scaler()
    t = 4
    for m in MODES:
        if m.max_age > t:
            continue
        f = build_field(ds, t, sc, PATCH, m,
                        sss_keep=coherent_sss_gap_mask(ds.sizes["lat"], ds.sizes["lon"], t)
                        if m.name == "C_SSS_SPATIAL_GAPS" else None)
        for k, v in enumerate(SURFACE):
            if v in m.missing or (m.name == "C_SSS_SPATIAL_GAPS" and v == "sss"):
                continue
            val = _centre(f, ds, k)
            day = round((val - k) / 100.0)
            assert day <= t, f"{m.name}/{v} read day {day} for target {t}"


def test_negative_index_is_refused():
    ds, sc = _toy(), _scaler()
    with pytest.raises(AssertionError):
        build_field(ds, 1, sc, PATCH, MODES_BY_NAME["F_CURRENT_STALE_3D"])


def test_persistence_carries_forward_and_never_looks_forward():
    """A declared outage filled by persistence must take the most recent PAST
    day, never a future one."""
    ds, sc = _toy(), _scaler()
    f = build_field(ds, 3, sc, PATCH, MODES_BY_NAME["B_SSS_MISSING"],
                    policy="persistence")
    got = _centre(f, ds, CH["sss"])
    day = round((got - CH["sss"]) / 100.0)
    assert day == 2, f"persistence used day {day}; must carry forward from day 2"
    assert day < 3, "persistence must never reach the target day or later"


def test_persistence_walks_further_back_when_recent_days_are_also_missing():
    ds, sc = _toy(), _scaler()
    vals = ds["sss"].values.copy()
    vals[2] = np.nan                      # day 2 also unavailable
    ds["sss"] = (("time", "lat", "lon"), vals)
    f = build_field(ds, 3, sc, PATCH, MODES_BY_NAME["B_SSS_MISSING"],
                    policy="persistence")
    day = round((_centre(f, ds, CH["sss"]) - CH["sss"]) / 100.0)
    assert day == 1, f"expected day 1 after skipping the missing day 2, got {day}"


def test_undeclared_nan_channel_still_triggers_the_joint_blanking():
    """Frozen behaviour, pinned: a channel that is NaN in the DATA but not
    declared as an outage still participates in the joint validity mask, so the
    cell is blanked. Only a declared outage is excluded from the mask."""
    ds, sc = _toy(), _scaler()
    vals = ds["sss"].values.copy()
    vals[3] = np.nan
    ds["sss"] = (("time", "lat", "lon"), vals)
    f = build_field(ds, 3, sc, PATCH, Mode("undeclared"), policy="persistence")
    assert f[N_DATA_CHANNELS].sum() == 0.0
    assert _centre(f, ds, CH["sst"]) == 0.0


# ------------------------------------------------------- masking semantics
def test_complete_mode_reproduces_the_frozen_day_field():
    """A_COMPLETE must be bit-identical to the existing production path."""
    ds, sc = _toy(), _scaler()
    a = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["A_COMPLETE"])
    b = day_field(ds, 4, sc, PATCH)
    assert np.array_equal(a, b)


def test_joint_mask_blanks_everything_on_a_whole_channel_outage():
    """The documented architectural limitation, pinned so it cannot regress
    silently: one missing channel zeroes all seven and the mask."""
    ds, sc = _toy(), _scaler()
    f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["J_SSS_MISSING_JOINT_MASK"])
    assert f[N_DATA_CHANNELS].sum() == 0.0
    assert np.all(f[:N_DATA_CHANNELS] == 0.0)


def test_available_mask_keeps_the_remaining_channels_alive():
    ds, sc = _toy(), _scaler()
    f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["B_SSS_MISSING"])
    assert f[N_DATA_CHANNELS].sum() > 0, "other channels must remain usable"
    assert _centre(f, ds, CH["sst"]) != 0.0


def test_zero_standardised_puts_the_missing_channel_at_the_train_mean():
    ds = _toy()
    sc = ZScoreScaler(np.array([0, 7.0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype="float64"),
                      np.ones(11), list(SURFACE) + ["lat", "lon", "doy_sin", "doy_cos"])
    f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["B_SSS_MISSING"],
                    policy="zero_standardised")
    assert _centre(f, ds, CH["sss"]) == pytest.approx(0.0, abs=1e-6), \
        "the train mean must map to exactly zero in standardised space"


def test_land_masking_is_unchanged_by_degradation():
    ds, sc = _toy(), _scaler()
    h = PATCH // 2
    for name in ("A_COMPLETE", "B_SSS_MISSING", "E_CURRENT_STALE_2D"):
        f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME[name])
        assert f[N_DATA_CHANNELS, h + 0, h + 0] == 0.0, f"{name}: land became valid"


def test_no_nan_reaches_the_cnn_in_any_mode():
    ds, sc = _toy(), _scaler()
    for m in MODES:
        if m.max_age > 4:
            continue
        keep = coherent_sss_gap_mask(ds.sizes["lat"], ds.sizes["lon"], 4) \
            if m.name == "C_SSS_SPATIAL_GAPS" else None
        f = build_field(ds, 4, sc, PATCH, m, sss_keep=keep)
        assert np.isfinite(f).all(), m.name


def test_field_shape_matches_the_frozen_contract():
    ds, sc = _toy(), _scaler()
    f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["A_COMPLETE"])
    h = PATCH // 2
    assert f.shape == (N_CHANNELS, ds.sizes["lat"] + 2 * h, ds.sizes["lon"] + 2 * h)


def test_degradation_does_not_mutate_the_source_dataset():
    ds, sc = _toy(), _scaler()
    before = {v: ds[v].values.copy() for v in SURFACE}
    for m in MODES:
        if m.max_age > 4:
            continue
        keep = coherent_sss_gap_mask(ds.sizes["lat"], ds.sizes["lon"], 4) \
            if m.name == "C_SSS_SPATIAL_GAPS" else None
        build_field(ds, 4, sc, PATCH, m, sss_keep=keep)
    for v in SURFACE:
        assert np.array_equal(before[v], ds[v].values, equal_nan=True), f"{v} mutated"


def test_degradation_is_deterministic():
    ds, sc = _toy(), _scaler()
    for m in (MODES_BY_NAME["B_SSS_MISSING"], MODES_BY_NAME["E_CURRENT_STALE_2D"]):
        assert np.array_equal(build_field(ds, 4, sc, PATCH, m),
                              build_field(ds, 4, sc, PATCH, m))


# --------------------------------------------------------- spatial gaps
def test_spatial_gap_mask_is_coherent_not_per_pixel():
    keep = coherent_sss_gap_mask(101, 241, 7)
    removed = ~keep
    assert 0.2 < removed.mean() < 0.6
    from scipy import ndimage
    _, n_blobs = ndimage.label(removed)
    assert n_blobs <= 12, "gaps must be coherent regions, not scattered pixels"


def test_spatial_gap_mask_is_reproducible_and_day_dependent():
    a = coherent_sss_gap_mask(101, 241, 3)
    assert np.array_equal(a, coherent_sss_gap_mask(101, 241, 3))
    assert not np.array_equal(a, coherent_sss_gap_mask(101, 241, 4))


def test_spatial_gaps_only_remove_sss():
    ds, sc = _toy(), _scaler()
    keep = coherent_sss_gap_mask(ds.sizes["lat"], ds.sizes["lon"], 4)
    f = build_field(ds, 4, sc, PATCH, MODES_BY_NAME["C_SSS_SPATIAL_GAPS"], sss_keep=keep)
    for k, v in enumerate(SURFACE):
        if v == "sss":
            continue
        assert _centre(f, ds, k) == pytest.approx(4 * 100.0 + k), f"{v} was altered"


# -------------------------------------------------------------- outputs
@pytest.mark.skipif(not (TAB / "phase6cb_skill_vs_climatology.csv").exists(),
                    reason="stress run not completed")
class TestStressOutputs:
    @pytest.fixture(scope="class")
    def sk(self):
        return pd.read_csv(TAB / "phase6cb_skill_vs_climatology.csv")

    def test_every_mode_scored_on_identical_populations(self, sk):
        for d, g in sk.groupby("depth_m"):
            assert g.n.nunique() == 1, f"depth {d}: modes have different sample counts"

    def test_complete_mode_has_zero_degradation_by_construction(self, sk):
        c = sk[sk["mode"] == "A_COMPLETE"]
        assert np.allclose(c.degradation_pct, 0.0, atol=1e-9)

    def test_all_fifteen_depths_present(self, sk):
        assert sorted(sk.depth_m.unique()) == DEPTHS

    def test_l2_weights_recorded_unchanged(self):
        m = json.load(open(TAB / "phase6cb_stress_meta.json", encoding="utf-8"))
        assert m["l2_sha256_before"] == m["l2_sha256_after"]
        assert m["heldout_2024_argo"] == "untouched"

    def test_cohort_is_development_data_only(self):
        m = json.load(open(TAB / "phase6cb_stress_meta.json", encoding="utf-8"))
        assert m["split"] == "validation"
        assert pd.Timestamp(m["last_target"]) < pd.Timestamp("2022-01-01")

    def test_current_age_sensitivity_covers_all_four_ages(self):
        a = pd.read_csv(TAB / "phase6cb_current_age_sensitivity.csv")
        assert sorted(a.current_age_days.unique()) == [0, 1, 2, 3]
        assert sorted(a.depth_m.unique()) == DEPTHS
