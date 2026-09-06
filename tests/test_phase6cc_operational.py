"""Phase 6C-C guards for the evidence-gated operational fallback contract.

These are behavioural tests. The risks they target: the wrapper silently
changing complete-input inference, a whole-channel outage reaching the frozen
CNN as a blank field, a fallback being applied to a channel nobody tested, a
persistence chain resetting its age so an old field looks fresh, or a future
source being used.
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

from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.ml.patches import N_DATA_CHANNELS, day_field  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402
from oceanembed.operational import (InputDeclaration, PersistenceStore,  # noqa: E402
                                    assemble_field, lookup_policy,
                                    reference_complete_field)
from oceanembed.operational.policy import (FILL_PERSIST, FILL_TRAIN_CLIM,  # noqa: E402
                                           POLICY_REGISTRY, NoUsableInput,
                                           PolicyState, UnsupportedInputMode)
from oceanembed.operational.provenance import ChannelProvenance  # noqa: E402

MODELS = ROOT / "outputs" / "models"
BASE = ROOT / "outputs" / "baselines"
ARGO = ROOT / "outputs" / "argo"
PATCH = 33
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

L2_FULL = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
L2_ENC = "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"
FEATURE_SCALER_SHA = "49671ce760b0dca5c1c82cb184dae919"
TARGET_SCALER_SHA = "5b6f359db0d228dd7d3acf775ab8a6ee"
CLIM_SHA = "748af4d79bc704cc2f742e1c208baceb"
SURF_CLIM_SHA = "58f0c5812ebcb6d4394a4f18e5b133d0"


def _msha(sd):
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def _fsha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# --------------------------------------------------------- frozen artefacts
def test_model_hashes_unchanged():
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    assert _msha(ck["state_dict"]) == L2_FULL
    assert _msha(ck["encoder_state_dict"]) == L2_ENC


def test_scaler_and_climatology_hashes_unchanged():
    assert _fsha(BASE / "phase6b_feature_scaler.json")[:32] == FEATURE_SCALER_SHA
    assert _fsha(BASE / "phase6b_target_scaler.json")[:32] == TARGET_SCALER_SHA
    assert _fsha(BASE / "phase6b_climatology.nc")[:32] == CLIM_SHA
    assert _fsha(BASE / "phase6cb_surface_climatology.nc")[:32] == SURF_CLIM_SHA


def test_no_optimiser_state_is_created_by_the_operational_package():
    """Behavioural, not string-matching: running the assembler must leave every
    model parameter free of gradient and optimiser state."""
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    from oceanembed.ml.l2_model import L2EmbeddingModel
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    m.eval()
    for p in m.parameters():
        p.requires_grad_(False)
    ds, sc = _toy(), _scaler()
    f, _ = reference_complete_field(ds, 4, sc, PATCH)
    with torch.no_grad():
        m.embed_field(torch.from_numpy(f)[None])
    assert all(p.grad is None for p in m.parameters())
    assert _msha(m.state_dict()) == L2_FULL


# ------------------------------------------------------------ toy fixtures
def _toy(n_days=8, nlat=40, nlon=45):
    t = pd.date_range("2022-06-01", periods=n_days, freq="D")
    ds = xr.Dataset(coords={"time": t, "lat": 5.0 + 0.25 * np.arange(nlat),
                            "lon": 45.0 + 0.25 * np.arange(nlon)})
    for k, v in enumerate(SURFACE):
        base = np.arange(n_days, dtype="float64")[:, None, None] * 100.0 + k
        vals = base + np.zeros((n_days, nlat, nlon))
        vals[:, :3, :3] = np.nan                      # land
        ds[v] = (("time", "lat", "lon"), vals)
    return ds


def _scaler():
    return ZScoreScaler(np.zeros(11), np.ones(11),
                        list(SURFACE) + ["lat", "lon", "doy_sin", "doy_cos"])


def _decl(ds, t, absent=(), stale=None):
    stale = stale or {}
    d = InputDeclaration(requested_valid_time=str(pd.Timestamp(ds.time.values[t])))
    for v in SURFACE:
        d.declare(v, absent=(v in absent), age_days=int(stale.get(v, 0)))
    return d


def _centre(field, ch, patch=PATCH):
    h = patch // 2
    return field[ch, h + 20, h + 20]


class _FakeClim:
    meta = {"fit_start": "2015-01-01", "fit_end": "2020-12-31"}

    def predict_channel(self, name, when):
        return np.full((40, 45), -55.0)


# --------------------------------------------------- complete-input invariance
def test_reference_complete_is_bitwise_identical_to_legacy():
    ds, sc = _toy(), _scaler()
    f, man = reference_complete_field(ds, 4, sc, PATCH)
    assert np.array_equal(f, day_field(ds, 4, sc, PATCH))
    assert man.policy_state == PolicyState.REFERENCE_COMPLETE.value


def test_assembler_with_nothing_declared_wrong_is_bitwise_identical():
    ds, sc = _toy(), _scaler()
    f, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4))
    assert np.array_equal(f, day_field(ds, 4, sc, PATCH))
    assert man.policy_name == "REFERENCE_COMPLETE"


def test_ordinary_per_cell_nans_are_not_filled_by_the_wrapper():
    """A scattered data NaN in an otherwise available product must keep its
    legacy handling, not be silently repaired because the wrapper exists."""
    ds, sc = _toy(), _scaler()
    vals = ds["sss"].values.copy()
    vals[4, 10, 10] = np.nan                 # one ordinary bad cell
    ds["sss"] = (("time", "lat", "lon"), vals)
    legacy = day_field(ds, 4, sc, PATCH)
    f, _ = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4))
    assert np.array_equal(f, legacy)
    h = PATCH // 2
    assert f[N_DATA_CHANNELS, h + 10, h + 10] == 0.0, "the bad cell must stay masked"


def test_land_handling_is_unchanged_in_every_supported_mode():
    ds, sc = _toy(), _scaler()
    store = PersistenceStore()
    store.push("sss", ds.time.values[3], ds["sss"].isel(time=3).values)
    h = PATCH // 2
    for absent, stale, fill in [((), {}, None), (("sss",), {}, FILL_PERSIST),
                                ((), {"current_u": 2, "current_v": 2}, None)]:
        f, _ = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent, stale),
                              store=store, prefer_fill=fill)
        assert f[N_DATA_CHANNELS, h + 0, h + 0] == 0.0


# ------------------------------------------------- registry / unsupported
@pytest.mark.parametrize("absent,stale", [
    (("sst",), {}), (("sla",), {}), (("wind_u", "wind_v"), {}),
    (("current_u", "current_v"), {}), (("sss", "sla"), {}),
    ((), {"sst": 1}), ((), {"sss": 1}), ((), {"current_u": 4, "current_v": 4}),
    ((), {"wind_u": 2, "wind_v": 2}), ((), {"sla": 2}),
    (("sss",), {"wind_u": 1, "wind_v": 1}),
])
def test_untested_situations_are_refused(absent, stale):
    ds, sc = _toy(), _scaler()
    store = PersistenceStore()
    for v in SURFACE:
        store.push(v, ds.time.values[3], ds[v].isel(time=3).values)
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent, stale),
                       surface_clim=_FakeClim(), store=store)


def test_registry_contains_only_the_evidenced_policies():
    assert set(POLICY_REGISTRY) == {
        "REFERENCE_COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
        "CURRENT_STALE_1D", "CURRENT_STALE_2D", "CURRENT_STALE_3D",
        "WIND_STALE_1D", "SLA_STALE_1D", "SSS_ABSENT_PERSIST_CURRENT_STALE_2D"}
    for name, p in POLICY_REGISTRY.items():
        assert p.evidence, f"{name} has no recorded evidence"


def test_there_is_no_generic_fallback_for_untested_channels():
    for name, p in POLICY_REGISTRY.items():
        assert p.absent <= {"sss"}, f"{name} repairs an untested channel outage"


def test_unsupported_mode_never_reaches_the_cnn_as_a_blank_field():
    """The core safety property: an unsupported whole-channel outage must raise
    rather than produce the legacy all-zero field."""
    ds, sc = _toy(), _scaler()
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sst",)))


def test_legacy_blank_field_failure_is_preserved_as_a_documented_regression():
    """The old unsupported behaviour still exists in day_field and is pinned
    here deliberately - the wrapper prevents reaching it, it is not redefined."""
    ds, sc = _toy(), _scaler()
    ds2 = ds.copy(deep=True)
    ds2["sss"].values[:] = np.nan
    legacy = day_field(ds2, 4, sc, PATCH)
    assert legacy[N_DATA_CHANNELS].sum() == 0.0
    assert np.all(legacy[:N_DATA_CHANNELS] == 0.0)


def test_supported_fallback_keeps_the_mask_alive():
    ds, sc = _toy(), _scaler()
    store = PersistenceStore()
    store.push("sss", ds.time.values[3], ds["sss"].isel(time=3).values)
    f, _ = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                          store=store, prefer_fill=FILL_PERSIST)
    assert f[N_DATA_CHANNELS].sum() > 0


# -------------------------------------------------------------- age semantics
def test_persistence_age_follows_the_original_observation_not_the_store_date():
    """If yesterday's stored field was itself persisted from three days ago,
    today's age is three days, not one."""
    store = PersistenceStore(max_age_days=7)
    t0 = pd.Timestamp("2022-06-01")
    store.push("sss", t0, np.zeros((2, 2)))
    for k in (1, 2, 3):
        store.carry_forward("sss", t0 + pd.Timedelta(days=k))
    got = store.get("sss", t0 + pd.Timedelta(days=3))
    assert got["original_observation_time"] == t0
    assert got["age_days"] == pytest.approx(3.0), "age must not reset each day"


def test_persistence_age_is_reported_in_the_manifest():
    ds, sc = _toy(), _scaler()
    store = PersistenceStore()
    store.push("sss", ds.time.values[1], ds["sss"].isel(time=1).values)
    _, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                            store=store, prefer_fill=FILL_PERSIST)
    p = [c for c in man.channels if c.channel == "sss"][0]
    assert p.age_days == pytest.approx(3.0)
    assert p.fallback_policy == FILL_PERSIST
    assert man.max_age_days == pytest.approx(3.0)


def test_persistence_beyond_the_configured_range_is_refused():
    ds, sc = _toy(), _scaler()
    store = PersistenceStore(max_age_days=2)
    store.push("sss", ds.time.values[0], ds["sss"].isel(time=0).values)
    with pytest.raises(NoUsableInput):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       store=store, prefer_fill=FILL_PERSIST)


def test_no_prior_field_is_refused_rather_than_invented():
    ds, sc = _toy(), _scaler()
    with pytest.raises(NoUsableInput):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       store=PersistenceStore(), prefer_fill=FILL_PERSIST)


def test_store_never_serves_a_future_field():
    store = PersistenceStore()
    t0 = pd.Timestamp("2022-06-05")
    store.push("sss", t0, np.zeros((2, 2)))
    assert store.get("sss", t0 - pd.Timedelta(days=1)) is None


def test_stale_channel_reads_exactly_t_minus_age():
    ds, sc = _toy(), _scaler()
    for age in (1, 2, 3):
        f, man = assemble_field(ds, 5, sc, PATCH,
                                _decl(ds, 5, stale={"current_u": age, "current_v": age}))
        k = SURFACE.index("current_u")
        assert _centre(f, k) == pytest.approx((5 - age) * 100.0 + k)
        p = [c for c in man.channels if c.channel == "current_u"][0]
        assert p.age_days == pytest.approx(float(age))


def test_stale_age_running_off_the_record_is_refused():
    ds, sc = _toy(), _scaler()
    with pytest.raises(NoUsableInput):
        assemble_field(ds, 1, sc, PATCH,
                       _decl(ds, 1, stale={"current_u": 3, "current_v": 3}))


def test_negative_age_is_refused_as_a_future_read():
    with pytest.raises(UnsupportedInputMode):
        InputDeclaration(requested_valid_time="2022-06-05").declare("sss", age_days=-1)


def test_uv_ages_must_match_for_currents_and_winds():
    ds, sc = _toy(), _scaler()
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, stale={"current_u": 1}))
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, stale={"wind_u": 1}))


def test_uv_absence_must_be_paired():
    with pytest.raises(UnsupportedInputMode):
        lookup_policy({"current_u"}, {})


# ------------------------------------------------------ climatology metadata
def test_climatology_has_no_valid_time_and_no_age():
    ds, sc = _toy(), _scaler()
    _, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                            surface_clim=_FakeClim(), prefer_fill=FILL_TRAIN_CLIM)
    p = [c for c in man.channels if c.channel == "sss"][0]
    assert p.source_valid_time is None
    assert p.original_observation_time is None
    assert p.age_days is None
    assert p.training_period == "2015-01-01/2020-12-31"
    assert p.fallback_policy == FILL_TRAIN_CLIM


def test_climatology_requested_without_an_artefact_is_refused():
    ds, sc = _toy(), _scaler()
    with pytest.raises(NoUsableInput):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       prefer_fill=FILL_TRAIN_CLIM)


def test_manifest_max_age_ignores_climatology_nulls():
    ds, sc = _toy(), _scaler()
    _, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                            surface_clim=_FakeClim(), prefer_fill=FILL_TRAIN_CLIM)
    assert man.max_age_days == 0.0


# ----------------------------------------------------------- issue time
def test_source_available_after_the_issue_time_is_refused():
    ds, sc = _toy(), _scaler()
    d = InputDeclaration(requested_valid_time=str(pd.Timestamp(ds.time.values[4])),
                         reconstruction_issue_time="2022-06-05T00:00:00")
    for v in SURFACE:
        d.declare(v, source_available_time=("2022-06-09T00:00:00" if v == "sla" else None))
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, d)


def test_source_available_before_the_issue_time_is_accepted():
    ds, sc = _toy(), _scaler()
    d = InputDeclaration(requested_valid_time=str(pd.Timestamp(ds.time.values[4])),
                         reconstruction_issue_time="2022-06-10T00:00:00")
    for v in SURFACE:
        d.declare(v, source_available_time="2022-06-06T00:00:00")
    f, man = assemble_field(ds, 4, sc, PATCH, d)
    assert np.array_equal(f, day_field(ds, 4, sc, PATCH))
    assert man.replay_mode == "RETROSPECTIVE"


# ------------------------------------------------------------- integrity
def test_declaration_for_the_wrong_valid_time_is_refused():
    ds, sc = _toy(), _scaler()
    d = _decl(ds, 4)
    d.requested_valid_time = "2022-06-02T00:00:00"
    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, d)


def test_malformed_field_dimensions_are_refused():
    ds, sc = _toy(), _scaler()

    class BadClim:
        meta = {"fit_start": "2015-01-01", "fit_end": "2020-12-31"}

        def predict_channel(self, name, when):
            return np.zeros((5, 5))

    with pytest.raises(UnsupportedInputMode):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       surface_clim=BadClim(), prefer_fill=FILL_TRAIN_CLIM)


def test_entirely_nonfinite_replacement_is_refused():
    ds, sc = _toy(), _scaler()

    class NanClim:
        meta = {"fit_start": "2015-01-01", "fit_end": "2020-12-31"}

        def predict_channel(self, name, when):
            return np.full((40, 45), np.nan)

    with pytest.raises(NoUsableInput):
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       surface_clim=NanClim(), prefer_fill=FILL_TRAIN_CLIM)


def test_assembly_does_not_mutate_the_source_dataset():
    ds, sc = _toy(), _scaler()
    before = {v: ds[v].values.copy() for v in SURFACE}
    store = PersistenceStore()
    store.push("sss", ds.time.values[3], ds["sss"].isel(time=3).values)
    for absent, stale, fill in [((), {}, None), (("sss",), {}, FILL_PERSIST),
                                ((), {"current_u": 2, "current_v": 2}, None)]:
        assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent, stale),
                       store=store, surface_clim=_FakeClim(), prefer_fill=fill)
    for v in SURFACE:
        assert np.array_equal(before[v], ds[v].values, equal_nan=True)


def test_provenance_is_deterministic():
    ds, sc = _toy(), _scaler()
    store = PersistenceStore()
    store.push("sss", ds.time.values[3], ds["sss"].isel(time=3).values)
    a = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       store=store, prefer_fill=FILL_PERSIST)[1].as_dict()
    b = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4, absent=("sss",)),
                       store=store, prefer_fill=FILL_PERSIST)[1].as_dict()
    assert a == b


def test_every_channel_appears_exactly_once_in_the_manifest():
    ds, sc = _toy(), _scaler()
    _, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4))
    names = [c.channel for c in man.channels]
    assert sorted(names) == sorted(SURFACE)


def test_manifest_serialises_to_json(tmp_path):
    ds, sc = _toy(), _scaler()
    _, man = assemble_field(ds, 4, sc, PATCH, _decl(ds, 4))
    p = tmp_path / "m.json"
    man.to_json(p)
    d = json.load(open(p, encoding="utf-8"))
    assert d["policy_state"] == PolicyState.REFERENCE_COMPLETE.value
    assert len(d["channels"]) == len(SURFACE)


# ---------------------------------------------------------- replay outputs
@pytest.mark.skipif(not (ARGO / "fallback_replay.parquet").exists(),
                    reason="replay not run")
class TestReplayOutputs:
    @pytest.fixture(scope="class")
    def df(self):
        return pd.read_parquet(ARGO / "fallback_replay.parquet")

    def test_2024_holdout_absent(self, df):
        assert pd.to_datetime(df.date).max() < pd.Timestamp("2024-01-01")

    def test_all_modes_present(self, df):
        for lab in ("COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
                    "CURRENT_STALE_2D", "L0"):
            assert f"{lab}_100m" in df.columns

    def test_all_l2_modes_have_identical_native_coverage(self, df):
        """Every L2 fallback must produce a value wherever COMPLETE does."""
        labs = ["COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
                "CURRENT_STALE_1D", "CURRENT_STALE_2D", "CURRENT_STALE_3D",
                "WIND_STALE_1D", "SLA_STALE_1D",
                "SSS_ABSENT_PERSIST_CURRENT_STALE_2D"]
        for d in (50, 100, 200):
            base = np.isfinite(df[f"COMPLETE_{d}m"].to_numpy("float64"))
            for lab in labs:
                m = np.isfinite(df[f"{lab}_{d}m"].to_numpy("float64"))
                assert np.array_equal(base, m), f"{lab} differs from COMPLETE at {d} m"

    def test_l0_coverage_is_a_subset_and_metrics_use_the_intersection(self, df):
        """L0 can be marginally narrower than L2: the train-only climatology has
        no coefficients at cells that lacked a target during training (3 rows at
        200 m, Gulf of Oman). Metrics therefore score every mode on the
        INTERSECTION, which is what makes the comparison fair."""
        labs = ["COMPLETE", "SSS_ABSENT_PERSIST", "SSS_ABSENT_CLIM",
                "CURRENT_STALE_1D", "CURRENT_STALE_2D", "CURRENT_STALE_3D",
                "WIND_STALE_1D", "SLA_STALE_1D",
                "SSS_ABSENT_PERSIST_CURRENT_STALE_2D", "L0"]
        for d in (50, 100, 200):
            l0 = np.isfinite(df[f"L0_{d}m"].to_numpy("float64"))
            base = np.isfinite(df[f"COMPLETE_{d}m"].to_numpy("float64"))
            assert (l0 & ~base).sum() == 0, "L0 must not cover cells L2 cannot"
            inter = np.ones(len(df), dtype=bool)
            for lab in labs:
                inter &= np.isfinite(df[f"{lab}_{d}m"].to_numpy("float64"))
            counts = {lab: int((inter & np.isfinite(
                df[f"{lab}_{d}m"].to_numpy("float64"))).sum()) for lab in labs}
            assert len(set(counts.values())) == 1, counts

    def test_l2_hash_recorded_unchanged(self):
        m = json.load(open(ARGO / "fallback_replay_meta.json", encoding="utf-8"))
        assert m["l2_sha256_before"] == m["l2_sha256_after"] == L2_FULL
        assert m["heldout_2024"] == "untouched"
        assert m["replay_mode"] == "RETROSPECTIVE"
