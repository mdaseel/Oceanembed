"""Architecture-closure study guards (Experiments B, C and D).

The risks these target: a frozen artefact being silently modified, the 2024 Argo
holdout being opened, the PCA basis absorbing non-train data, the residual
formulation drifting from `target - frozen L0`, and an ablation changing the
sample population or the architecture instead of only the information content.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.closure import ablation, holdout  # noqa: E402
from oceanembed.closure.residual import ResidualTargets  # noqa: E402
from oceanembed.config import REPO_ROOT  # noqa: E402
from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.ml.l2_model import L2EmbeddingModel  # noqa: E402
from oceanembed.ml.patches import N_DATA_CHANNELS, day_field  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402

CLOSURE = REPO_ROOT / "outputs" / "architecture_closure"
TAB = REPO_ROOT / "outputs" / "tables" / "architecture_closure"
BASE = REPO_ROOT / "outputs" / "baselines"
MODELS = REPO_ROOT / "outputs" / "models"


def file_sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ============================================================ SAFETY
FROZEN_EXPECTED = {
    MODELS / "phase6b_l1_mlp.pt":
        "fefebd216536b9a1b8383ae41b5d35057b8b46ed1b4b77a9642a514bc9c92b5b",
    MODELS / "phase6b_l2_final.pt":
        "81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35",
    BASE / "phase6b_feature_scaler.json":
        "49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467",
    BASE / "phase6b_target_scaler.json":
        "5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b",
    BASE / "phase6b_climatology.nc":
        "748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5",
    BASE / "phase6cb_surface_climatology.nc":
        "58f0c5812ebcb6d4394a4f18e5b133d0a69657960e0e4c98d74184e91f6e8932",
}


@pytest.mark.parametrize("path,expected", list(FROZEN_EXPECTED.items()),
                         ids=[p.name for p in FROZEN_EXPECTED])
def test_frozen_artefact_is_byte_identical(path, expected):
    assert path.exists(), f"{path.name} is missing"
    assert file_sha(path) == expected, f"{path.name} CHANGED"


def test_frozen_l2_state_dict_and_encoder_hashes_unchanged():
    import torch
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu",
                    weights_only=False)

    def h(sd):
        d = hashlib.sha256()
        for k in sorted(sd):
            d.update(k.encode())
            d.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
        return d.hexdigest()

    assert h(ck["state_dict"]) == \
        "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
    enc = {k[len("encoder."):]: v for k, v in ck["state_dict"].items()
           if k.startswith("encoder.")}
    assert h(enc) == \
        "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"


def test_closure_artefacts_never_land_in_a_frozen_directory():
    stray = [p.name for p in (MODELS.glob("closure_*"))]
    stray += [p.name for p in BASE.glob("closure_*")]
    assert stray == [], f"closure artefacts written into a frozen directory: {stray}"


# ============================================================ 2024 HOLDOUT
def test_2024_argo_is_refused():
    with pytest.raises(holdout.HoldoutViolation):
        holdout.assert_no_2024_argo(pd.DatetimeIndex(["2024-03-01"]))
    with pytest.raises(holdout.HoldoutViolation):
        holdout.assert_no_2024_argo(pd.DatetimeIndex(["2023-12-31", "2024-01-01"]))
    holdout.assert_no_2024_argo(pd.DatetimeIndex(["2022-06-01", "2023-12-31"]))
    holdout.assert_no_2024_argo(pd.DatetimeIndex([]))


def test_argo_confirmation_window_is_exactly_the_inspected_years():
    ok = pd.DataFrame({"date": pd.to_datetime(["2022-01-01", "2023-12-31"])})
    holdout.assert_argo_is_development_window(ok)
    bad = pd.DataFrame({"date": pd.to_datetime(["2022-01-01", "2024-02-01"])})
    with pytest.raises(holdout.HoldoutViolation):
        holdout.assert_argo_is_development_window(bad)


def test_existing_argo_collocation_still_excludes_2024():
    p = REPO_ROOT / "outputs" / "argo" / "matched_profiles.parquet"
    if not p.exists():
        pytest.skip("argo collocation not present")
    d = pd.read_parquet(p, columns=["date"])
    holdout.assert_argo_is_development_window(d)


def test_download_manifest_still_records_2024_as_not_fetched():
    p = REPO_ROOT / "outputs" / "argo" / "download_manifest.json"
    if not p.exists():
        pytest.skip("argo manifest not present")
    m = json.loads(p.read_text())
    assert m["heldout_period_not_fetched"] == ["2024-01-01", "2024-12-15"]


# ============================================================ B — PCA / EOF
@pytest.mark.skipif(not (CLOSURE / "pca_diagnostic.json").exists(),
                    reason="PCA diagnostic not run")
class TestPCA:
    @pytest.fixture(scope="class")
    def res(self):
        return json.loads((CLOSURE / "pca_diagnostic.json").read_text())

    def test_basis_is_train_only(self):
        from oceanembed.ml import splits
        ds = splits.open_split("train")
        t = pd.DatetimeIndex(ds.time.values)
        assert not splits.contains_test_dates(t)
        holdout.assert_no_2024_argo(t)
        assert t.min() == pd.Timestamp("2015-01-01")
        assert t.max() == pd.Timestamp("2020-12-31")

    def test_sampling_is_deterministic(self):
        a = np.random.default_rng(20260905 + 7).choice(1000, 50, replace=False)
        b = np.random.default_rng(20260905 + 7).choice(1000, 50, replace=False)
        assert np.array_equal(a, b)

    def test_dimensions_are_right(self, res):
        for name, r in res.items():
            n = len(r["raw"]["depths"])
            for rep in ("raw", "residual"):
                assert len(r[rep]["eigenvalues"]) == n, name
                assert np.array(r[rep]["eofs"]).shape == (n, n), name
                assert len(r[rep]["mean_profile"]) == n, name

    def test_cumulative_variance_is_monotonic_and_reaches_one(self, res):
        for name, r in res.items():
            for rep in ("raw", "residual"):
                cum = np.array(r[rep]["cumulative_explained_variance"])
                assert np.all(np.diff(cum) >= -1e-12), f"{name}/{rep} not monotonic"
                assert abs(cum[-1] - 1.0) < 1e-9, f"{name}/{rep} does not reach 1"
                assert (np.array(r[rep]["explained_variance_ratio"]) >= -1e-12).all()

    def test_full_rank_reconstruction_is_numerically_exact(self, res):
        for name, r in res.items():
            n = len(r["raw"]["depths"])
            for rep in ("raw", "residual"):
                full = [x for x in r[rep]["reconstruction"] if x["k"] == n]
                if not full:
                    continue
                assert full[0]["rmse_overall"] < 1e-6, f"{name}/{rep} k={n} not exact"

    def test_reconstruction_error_decreases_with_k(self, res):
        for name, r in res.items():
            for rep in ("raw", "residual"):
                e = [x["rmse_overall"] for x in
                     sorted(r[rep]["reconstruction"], key=lambda z: z["k"])]
                assert all(b <= a + 1e-12 for a, b in zip(e, e[1:])), f"{name}/{rep}"

    def test_population_bias_is_reported_not_assumed_away(self):
        p = TAB / "pca_sample_population.csv"
        assert p.exists()
        d = pd.read_csv(p)
        assert {"eligible_fraction", "mean_lat_all", "mean_lat_eligible"} <= set(d.columns)
        assert (d["eligible_fraction"] < 1.0).all(), \
            "complete-case eligibility should be strictly below the full domain"


# ============================================================ C — residual
def _toy(nlat=8, nlon=9, n_depths=3):
    rng = np.random.default_rng(0)
    r = np.repeat(np.arange(nlat), nlon)
    c = np.tile(np.arange(nlon), nlat)
    return r, c, rng


class _FakeClim:
    """Minimal stand-in with the real climatology's contract."""

    def __init__(self, values):
        self.values = values
        self.meta = {"fitted_on": "train"}

    def predict(self, times, r, c):
        return np.repeat(self.values[None, :, :], len(times), axis=0)


def test_residual_target_is_exactly_target_minus_frozen_l0():
    r, c, rng = _toy()
    L0 = rng.normal(size=(len(r), 3))
    rt = ResidualTargets(_FakeClim(L0), r, c, [0, 5, 10])
    Y = rng.normal(size=(len(r), 3)) + 20.0
    d = rt.residual(Y, pd.Timestamp("2019-05-05"))
    assert np.allclose(d, Y - L0)


def test_physical_output_is_l0_plus_predicted_residual():
    r, c, rng = _toy()
    L0 = rng.normal(size=(len(r), 3))
    rt = ResidualTargets(_FakeClim(L0), r, c, [0, 5, 10])
    delta = rng.normal(size=(len(r), 3))
    back = rt.to_absolute(delta, pd.Timestamp("2019-05-05"))
    assert np.allclose(back, L0 + delta)
    assert np.allclose(rt.residual(back, pd.Timestamp("2019-05-05")), delta)


def test_residual_refuses_a_climatology_not_fitted_on_train():
    r, c, _ = _toy()
    bad = _FakeClim(np.zeros((len(r), 3)))
    bad.meta = {"fitted_on": "validation"}
    with pytest.raises(ValueError):
        ResidualTargets(bad, r, c, [0, 5, 10])


def test_residual_scaler_is_train_only_and_separate_from_the_frozen_one():
    p = CLOSURE / "closure_residual_target_scaler.json"
    if not p.exists():
        pytest.skip("residual scaler not built")
    sc = ZScoreScaler.from_json(p)
    assert sc.fitted_on == "train"
    assert sc.meta["fit_start"] == "2015-01-01"
    assert sc.meta["fit_end"] == "2020-12-31"
    frozen = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
    assert not np.allclose(sc.std, frozen.std), \
        "the residual scaler is identical to the absolute-target scaler"
    assert file_sha(BASE / "phase6b_target_scaler.json") == \
        FROZEN_EXPECTED[BASE / "phase6b_target_scaler.json"]


def test_l0_climatology_file_untouched_by_the_residual_experiment():
    assert file_sha(BASE / "phase6b_climatology.nc") == \
        FROZEN_EXPECTED[BASE / "phase6b_climatology.nc"]


@pytest.mark.skipif(not (MODELS / "architecture_closure"
                         / "closure_L2_RESIDUAL_s20260905.pt").exists(),
                    reason="residual candidate not trained")
def test_residual_candidate_matches_the_frozen_input_contract():
    import torch
    ck = torch.load(MODELS / "architecture_closure"
                    / "closure_L2_RESIDUAL_s20260905.pt",
                    map_location="cpu", weights_only=False)
    frozen = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu",
                        weights_only=False)
    assert ck["patch"] == frozen["patch"] == 33
    assert ck["latent"] == frozen["latent"] == 32
    assert ck["depths"] == frozen["depths"]
    assert ck["n_parameters"] == frozen["n_parameters"] == 136335
    assert ck["receptive_field"] == frozen["receptive_field"] == 33
    assert ck["residual"] is True
    assert ck["ablated_group"] is None


def test_residual_candidate_is_stored_separately_from_l2():
    d = MODELS / "architecture_closure"
    if not d.exists():
        pytest.skip("no closure models yet")
    for p in d.glob("*.pt"):
        assert p.name.startswith("closure_"), p.name
        assert not (MODELS / p.name).exists(), "closure name collides with a phase artefact"


# ============================================================ D — ablation
def _scaler11():
    return ZScoreScaler(np.zeros(11), np.ones(11),
                        list(SURFACE) + ["lat", "lon", "doy_sin", "doy_cos"])


def _toy_ds(nlat=10, nlon=11):
    rng = np.random.default_rng(3)
    data = {v: (("time", "lat", "lon"),
                rng.normal(size=(1, nlat, nlon)) + 10.0) for v in SURFACE}
    ds = xr.Dataset(data, coords={"time": [np.datetime64("2019-05-05")],
                                  "lat": np.arange(nlat) * 0.25 + 5.0,
                                  "lon": np.arange(nlon) * 0.25 + 45.0})
    return ds


def test_ablated_group_is_exactly_zero_and_others_are_untouched():
    ds = _toy_ds()
    f = day_field(ds, 0, _scaler11(), patch=5)
    for group, names in ablation.ABLATION_GROUPS.items():
        g = ablation.ablate_field(f, group)
        idx = ablation.group_channel_indices(group)
        assert len(idx) == len(names)
        for k in idx:
            assert np.all(g[k] == 0.0), f"{group}: channel {k} not zeroed"
        for k in range(N_DATA_CHANNELS):
            if k not in idx:
                assert np.array_equal(g[k], f[k]), f"{group}: channel {k} changed"


def test_ablation_leaves_the_validity_mask_channel_alone():
    ds = _toy_ds()
    f = day_field(ds, 0, _scaler11(), patch=5)
    for group in ablation.ABLATION_GROUPS:
        g = ablation.ablate_field(f, group)
        assert np.array_equal(g[N_DATA_CHANNELS], f[N_DATA_CHANNELS]), group


def test_ablation_does_not_change_the_valid_population():
    """The joint mask still comes from the ORIGINAL seven-channel field."""
    ds = _toy_ds()
    ds["sss"][0, 2, 3] = np.nan               # a genuine per-cell gap
    f = day_field(ds, 0, _scaler11(), patch=5)
    before = f[N_DATA_CHANNELS].sum()
    for group in ablation.ABLATION_GROUPS:
        g = ablation.ablate_field(f, group)
        assert g[N_DATA_CHANNELS].sum() == before, group


def test_ablation_preserves_shape_and_channel_count():
    ds = _toy_ds()
    f = day_field(ds, 0, _scaler11(), patch=5)
    for group in ablation.ABLATION_GROUPS:
        assert ablation.ablate_field(f, group).shape == f.shape


def test_none_group_is_the_untouched_control():
    ds = _toy_ds()
    f = day_field(ds, 0, _scaler11(), patch=5)
    assert ablation.ablate_field(f, None) is f


def test_ablation_does_not_mutate_its_input():
    ds = _toy_ds()
    f = day_field(ds, 0, _scaler11(), patch=5)
    keep = f.copy()
    ablation.ablate_field(f, "SST")
    assert np.array_equal(f, keep), "ablate_field mutated the caller's field"


def test_unknown_group_is_refused():
    with pytest.raises(KeyError):
        ablation.group_channel_indices("CHLOROPHYLL")


def test_the_five_groups_partition_the_seven_channels():
    seen = [v for names in ablation.ABLATION_GROUPS.values() for v in names]
    assert sorted(seen) == sorted(SURFACE)
    assert len(seen) == len(set(seen)), "a channel appears in two groups"


def test_parameter_count_is_identical_for_every_ablation_variant():
    m = L2EmbeddingModel(latent=32, patch=33)
    assert m.n_parameters == 136335
    assert m.encoder.receptive_field == 33


@pytest.mark.skipif(not (MODELS / "architecture_closure"
                         / "closure_D_CONTROL_ALL_training.json").exists(),
                    reason="ablation control not trained")
def test_all_ablation_runs_share_protocol_seed_and_population():
    d = MODELS / "architecture_closure"
    metas = [json.loads(p.read_text()) for p in
             sorted(d.glob("closure_D_*_training.json"))]
    assert len(metas) >= 1
    ref = metas[0]
    for m in metas:
        for k in ("seed", "patch", "latent", "max_epochs", "patience", "lr",
                  "train_days", "val_days", "n_cells_train", "n_cells_validation",
                  "n_parameters"):
            assert m[k] == ref[k], f"{m['name']} differs in {k}"
        assert m["residual"] is False, f"{m['name']} is not an absolute-target run"
        assert m["frozen_sha256_start"] == m["frozen_sha256_end"], \
            f"{m['name']} changed a frozen artefact while training"


# ============================================================ result tables
@pytest.mark.skipif(not (TAB / "channel_ablation_metrics.csv").exists(),
                    reason="ablation metrics not built")
def test_ablation_metrics_cover_every_group_at_every_depth():
    d = pd.read_csv(TAB / "channel_ablation_metrics.csv")
    for model, g in d[d.model != "L0_climatology"].groupby("model"):
        assert len(g) == 15, model
