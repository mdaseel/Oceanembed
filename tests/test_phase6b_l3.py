"""Phase 6B-C guards for the L3 temporal memory ablation.

The ways this phase could produce a wrong-but-plausible number: the "frozen"
encoder quietly training, a sequence that reaches into the future or across a
split boundary, window lengths being compared on different target dates, a
cached embedding drifting from the encoder that made it, or the capacity
control not actually having the same capacity.
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

import yaml  # noqa: E402

from oceanembed.ml import splits  # noqa: E402
from oceanembed.ml.embedding_cache import (EmbeddingCache, TargetCache,  # noqa: E402
                                           encoder_fingerprint)
from oceanembed.ml.features import SURFACE, cyclic_doy  # noqa: E402
from oceanembed.ml.l2_dataset import DayFieldSampler  # noqa: E402
from oceanembed.ml.l2_model import CONTEXT_DIM, L2EmbeddingModel  # noqa: E402
from oceanembed.ml.model import masked_mse, set_seed  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402
from oceanembed.ml.temporal import TemporalHead, freeze_encoder  # noqa: E402
from oceanembed.ml.temporal_dataset import TemporalSequenceSampler  # noqa: E402

BASE = ROOT / "outputs" / "baselines"
MODELS = ROOT / "outputs" / "models"
EMB = ROOT / "outputs" / "embeddings"
TGT = ROOT / "outputs" / "targets_cache"
L2_CKPT = MODELS / "phase6b_l2_final.pt"
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
MAXH = 7

L3CFG = yaml.safe_load(open(ROOT / "config" / "phase6c_l3.yaml", encoding="utf-8"))
have_l2 = L2_CKPT.exists()
have_cache = (EMB / "validation" / "meta.json").exists()


# ------------------------------------------------------- config / registration
def test_windows_are_pre_registered():
    assert L3CFG["windows"] == {"control_1d": 1, "hist_3d": 3, "hist_7d": 7}
    assert L3CFG["max_history_days"] == 7


def test_stability_seeds_are_pre_declared():
    assert L3CFG["stability_seeds"] == [20260905, 20260906, 20260907]
    assert len(set(L3CFG["stability_seeds"])) == 3


def test_selection_does_not_use_test():
    assert L3CFG["selection_uses_test"] is False
    assert L3CFG["primary_selection_metric"] == "validation_masked_standardised_mse"


def test_common_dates_sacrifice_the_first_six_days():
    cd = L3CFG["common_dates"]
    for split in ("train", "validation", "test"):
        s = pd.Timestamp(cd[split]["start"])
        split_start = pd.Timestamp(splits.split_bounds(split)[0])
        assert (s - split_start).days == MAXH - 1, split
    assert cd["history_stays_within_split"] is True


# --------------------------------------------------------------- frozen encoder
@pytest.mark.skipif(not have_l2, reason="L2 checkpoint missing")
def test_l2_checkpoint_loads_with_expected_metadata():
    ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
    assert ck["patch"] == 33 and ck["latent"] == 32
    assert ck["receptive_field"] == ck["patch"]
    assert ck["dilations"] == [1, 2, 4, 8, 1]


@pytest.mark.skipif(not have_l2, reason="L2 checkpoint missing")
def test_freeze_encoder_sets_requires_grad_false():
    ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    freeze_encoder(m.encoder)
    assert all(not p.requires_grad for p in m.encoder.parameters())
    assert not m.encoder.training, "frozen encoder must be in eval mode"


@pytest.mark.skipif(not have_l2, reason="L2 checkpoint missing")
def test_frozen_encoder_receives_no_gradient():
    ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    freeze_encoder(m.encoder)
    x = torch.randn(2, 8, ck["patch"], ck["patch"])
    z = m.embed_patch(x)
    head = TemporalHead(latent=ck["latent"])
    out = head(z[:, None, :], torch.randn(2, CONTEXT_DIM))
    out.sum().backward()
    for n, p in m.encoder.named_parameters():
        assert p.grad is None, f"encoder {n} received a gradient"


@pytest.mark.skipif(not have_l2, reason="L2 checkpoint missing")
def test_encoder_weights_unchanged_after_optimiser_steps():
    """Simulates training: only the head is optimised, encoder must be bitwise
    identical afterwards."""
    ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    freeze_encoder(m.encoder)
    before = encoder_fingerprint(m.encoder.state_dict())
    head = TemporalHead(latent=ck["latent"])
    opt = torch.optim.Adam(head.parameters(), lr=1e-2)
    for _ in range(5):
        z = torch.randn(4, 3, ck["latent"])
        loss = masked_mse(head(z, torch.randn(4, CONTEXT_DIM)),
                          torch.randn(4, 15), torch.ones(4, 15, dtype=torch.bool))
        opt.zero_grad()
        loss.backward()
        opt.step()
    assert encoder_fingerprint(m.encoder.state_dict()) == before


def test_encoder_fingerprint_detects_any_weight_change():
    set_seed(0)
    m = L2EmbeddingModel(latent=8, patch=9)
    a = encoder_fingerprint(m.encoder.state_dict())
    with torch.no_grad():
        m.encoder.conv[0].weight[0, 0, 0, 0] += 1e-6
    assert encoder_fingerprint(m.encoder.state_dict()) != a


# ------------------------------------------------------------- temporal module
def test_gru_input_width_equals_latent_width():
    h = TemporalHead(latent=32)
    assert h.gru.input_size == 32 and h.gru.hidden_size == 32


def test_trainable_parameter_count_identical_across_windows():
    """The capacity control only works if 1D/3D/7D have the same trainable
    parameters, so any difference is history rather than model size."""
    counts = set()
    for T in (1, 3, 7):
        set_seed(0)
        h = TemporalHead(latent=32)
        h(torch.randn(2, T, 32), torch.randn(2, CONTEXT_DIM))
        counts.add(h.n_trainable)
    assert len(counts) == 1, counts


def test_gru_weights_are_shared_across_timesteps():
    """One GRU cell is applied at every step - there is no per-timestep CNN or
    per-timestep parameter set."""
    h = TemporalHead(latent=32)
    n_gru = sum(p.numel() for p in h.gru.parameters())
    assert h.gru.num_layers == 1
    # 3*(in*hid + hid*hid + hid + hid) for a single shared cell
    assert n_gru == 3 * (32 * 32 + 32 * 32 + 32 + 32)


def test_decoder_output_width_is_fifteen():
    h = TemporalHead(latent=32)
    assert h(torch.randn(6, 3, 32), torch.randn(6, CONTEXT_DIM)).shape == (6, 15)


def test_current_day_is_the_last_sequence_element():
    """The GRU final hidden state must be driven by z_t, not z_(t-k)."""
    set_seed(1)
    h = TemporalHead(latent=8).eval()
    base = torch.zeros(1, 3, 8)
    with torch.no_grad():
        a = h(base, torch.zeros(1, CONTEXT_DIM))
        last = base.clone()
        last[0, -1] = 5.0                      # perturb the CURRENT day
        b = h(last, torch.zeros(1, CONTEXT_DIM))
        first = base.clone()
        first[0, 0] = 5.0                      # perturb the OLDEST day
        c = h(first, torch.zeros(1, CONTEXT_DIM))
    assert not torch.allclose(a, b), "current day must affect the prediction"
    assert (b - a).abs().sum() > (c - a).abs().sum(), \
        "the current day should influence the output more than the oldest day"


@pytest.mark.skipif(not have_l2, reason="L2 checkpoint missing")
def test_decoder_initialises_from_l2_decoder():
    ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
    dec = {k.replace("decoder.", ""): v for k, v in ck["state_dict"].items()
           if k.startswith("decoder.")}
    h = TemporalHead(latent=ck["latent"])
    h.init_decoder_from(dec)
    for k, v in dec.items():
        assert torch.equal(dict(h.decoder.state_dict())[k], v)


def test_checkpoint_roundtrip_is_exact(tmp_path):
    set_seed(4)
    h = TemporalHead(latent=32).eval()
    z, ctx = torch.randn(5, 3, 32), torch.randn(5, CONTEXT_DIM)
    with torch.no_grad():
        before = h(z, ctx)
    p = tmp_path / "l3.pt"
    torch.save({"state_dict": h.state_dict(), "latent": 32, "window": 3}, p)
    ck = torch.load(p, map_location="cpu", weights_only=False)
    h2 = TemporalHead(latent=ck["latent"])
    h2.load_state_dict(ck["state_dict"])
    h2.eval()
    with torch.no_grad():
        assert torch.equal(before, h2(z, ctx))


def test_inference_is_deterministic():
    set_seed(8)
    h = TemporalHead(latent=32).eval()
    z, ctx = torch.randn(4, 7, 32), torch.randn(4, CONTEXT_DIM)
    with torch.no_grad():
        assert torch.equal(h(z, ctx), h(z, ctx))


def test_masked_loss_is_unchanged():
    p = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    t = torch.zeros(2, 2)
    m = torch.tensor([[True, False], [True, True]])
    assert float(masked_mse(p, t, m)) == pytest.approx(10.5)


# ------------------------------------------------------------- toy sequence data
class _FakeCache:
    """Cache stub whose z values encode (day, cell, dim) so ordering and cell
    alignment can be checked exactly."""

    def __init__(self, n_days, n_cells, latent, dates):
        self.z = np.zeros((n_days, n_cells, latent), dtype="float32")
        for t in range(n_days):
            for c in range(n_cells):
                self.z[t, c, 0] = t
                self.z[t, c, 1] = c
        self.dates = pd.DatetimeIndex(dates)
        self.r = np.arange(n_cells) // 3
        self.c = np.arange(n_cells) % 3
        self.meta = {"n_days": n_days, "n_cells": n_cells, "latent": latent}


def _toy_ds(n_days=20, nlat=3, nlon=3):
    t = pd.date_range("2015-01-01", periods=n_days, freq="D")
    shp = (n_days, nlat, nlon)
    rng = np.random.default_rng(0)
    ds = xr.Dataset(coords={"time": t, "lat": 5.0 + 0.25 * np.arange(nlat),
                            "lon": 45.0 + 0.25 * np.arange(nlon)})
    for v in SURFACE:
        ds[v] = (("time", "lat", "lon"), rng.normal(size=shp))
    for d in DEPTHS:
        ds[f"temp_{d}m"] = (("time", "lat", "lon"), rng.normal(20, 2, size=shp))
        tv = np.ones(shp, bool)
        if d >= 500:
            tv[:, 0, 0] = False
            ds[f"temp_{d}m"].values[:, 0, 0] = np.nan
        ds[f"target_valid_{d}m"] = (("time", "lat", "lon"), tv)
    ds["surface_input_valid"] = (("time", "lat", "lon"), np.ones(shp, bool))
    ds["ocean_mask"] = (("time", "lat", "lon"), np.ones(shp, bool))
    return ds


def _toy_sampler(window, n_days=20):
    ds = _toy_ds(n_days)
    cache = _FakeCache(n_days, 9, 32, ds.time.values)
    fs = ZScoreScaler(np.zeros(11), np.ones(11),
                      SURFACE + ["lat", "lon", "doy_sin", "doy_cos"])
    ts = ZScoreScaler(np.zeros(15), np.ones(15), [f"temp_{d}m" for d in DEPTHS])
    return TemporalSequenceSampler(ds, cache, DEPTHS, fs, ts, window, MAXH)


@pytest.mark.parametrize("window", [1, 3, 7])
def test_sequence_shape_matches_window(window):
    s = _toy_sampler(window)
    seq = s.sequence(int(s.target_idx[0]))
    assert seq.shape == (s.n_cells, window, 32)


@pytest.mark.parametrize("window", [1, 3, 7])
def test_sequence_is_contiguous_and_ends_on_the_current_day(window):
    s = _toy_sampler(window)
    t = int(s.target_idx[5])
    seq = s.sequence(t)
    day_ids = seq[0, :, 0]                    # channel 0 encodes the day index
    assert list(day_ids) == [float(x) for x in range(t - window + 1, t + 1)]
    assert day_ids[-1] == float(t), "last element must be the current day"


def test_sequence_never_reads_the_future():
    s = _toy_sampler(7)
    for t in s.target_idx:
        assert s.sequence(int(t))[0, :, 0].max() == float(t)


def test_all_windows_share_identical_target_dates():
    """Window length must not change the comparison population."""
    a, b, c = (_toy_sampler(w) for w in (1, 3, 7))
    assert list(a.target_dates) == list(b.target_dates) == list(c.target_dates)
    assert a.n_targets == b.n_targets == c.n_targets
    assert a.n_samples == b.n_samples == c.n_samples


def test_first_target_skips_max_history_minus_one_days():
    s = _toy_sampler(1)
    assert int(s.target_idx[0]) == MAXH - 1, "1-day control must not gain extra dates"


def test_cell_alignment_is_constant_across_the_sequence():
    s = _toy_sampler(7)
    seq = s.sequence(int(s.target_idx[3]))
    for ci in range(s.n_cells):
        assert set(seq[ci, :, 1]) == {float(ci)}, "cell index must not shift with time"


def test_reversed_and_repeated_diagnostics_reorder_correctly():
    s = _toy_sampler(7)
    t = int(s.target_idx[4])
    causal = s.sequence(t)[0, :, 0]
    rev = s.sequence(t, order="reversed")[0, :, 0]
    rep = s.sequence(t, order="repeat_current")[0, :, 0]
    assert list(rev) == list(causal)[::-1]
    assert set(rep) == {float(t)}
    assert len(rep) == len(causal)


def test_block_batches_equal_direct_sequences():
    s = _toy_sampler(7)
    direct = {int(t): s.sequence(int(t)) for t in s.target_idx}
    for t, (seq, _, _, _, _) in s.batches(shuffle=False):
        assert np.array_equal(seq, direct[t])


def test_batches_cover_every_target_exactly_once_when_shuffled():
    s = _toy_sampler(3)
    seen = [t for t, _ in s.batches(shuffle=True, seed=0)]
    assert sorted(seen) == sorted(int(x) for x in s.target_idx)
    assert len(seen) == len(set(seen))


def test_targets_correspond_to_the_current_day():
    s = _toy_sampler(7)
    t = int(s.target_idx[2])
    _, _, _, M, Y = s.day(t)
    expect = s.ds["temp_100m"].isel(time=t).values[s.r, s.c]
    assert np.allclose(Y[:, DEPTHS.index(100)], expect, equal_nan=True)


def test_no_nan_enters_the_gru():
    s = _toy_sampler(7)
    for t, (seq, ctx, Yz, M, _) in s.batches():
        assert np.isfinite(seq).all()
        assert np.isfinite(ctx).all()
        assert np.isfinite(Yz).all()


def test_missing_deep_targets_are_masked_not_fabricated():
    s = _toy_sampler(3)
    _, _, Yz, M, Y = s.day(int(s.target_idx[0]))
    i1000 = DEPTHS.index(1000)
    assert (~M[:, i1000]).any()
    assert M[:, 0].all()
    assert np.isfinite(Y[M]).all()


def test_current_day_lat_lon_context_is_correct():
    s = _toy_sampler(3)
    ctx = s.context(int(s.target_idx[0]))
    assert np.allclose(ctx[:, 0], s.cell_lat)
    assert np.allclose(ctx[:, 1], s.cell_lon)


def test_current_day_doy_encoding_is_correct():
    s = _toy_sampler(3)
    t = int(s.target_idx[4])
    sin_, cos_ = cyclic_doy(s.times[t:t + 1])
    ctx = s.context(t)
    assert np.allclose(ctx[:, 2], sin_[0])
    assert np.allclose(ctx[:, 3], cos_[0])


def test_target_temperature_never_appears_in_the_sequence():
    """The GRU input must be surface-derived embeddings only."""
    s = _toy_sampler(7)
    t = int(s.target_idx[3])
    seq, _, _, _, Y = s.day(t)
    for k in range(Y.shape[1]):
        col = Y[:, k]
        col = col[np.isfinite(col)]
        if col.size:
            assert not np.isclose(seq, col[0], atol=1e-6).any()


# ------------------------------------------------------------- real caches
@pytest.mark.skipif(not have_cache, reason="embedding cache not built")
class TestRealCaches:
    def test_embedding_cache_declares_no_targets(self):
        for sp in ("train", "validation"):
            m = json.load(open(EMB / sp / "meta.json", encoding="utf-8"))
            assert m["contains_targets"] is False
            assert m["contains_climatology"] is False
            assert "encoder_sha256" in m

    def test_target_cache_is_a_separate_store(self):
        assert (TGT / "validation" / "y.npy").exists()
        assert not (EMB / "validation" / "y.npy").exists(), \
            "targets must not live inside the embedding cache"

    def test_cache_provenance_matches_the_frozen_encoder(self):
        ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
        m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
        m.load_state_dict(ck["state_dict"])
        for sp in ("train", "validation"):
            EmbeddingCache(EMB, sp).load().verify_encoder(m.encoder.state_dict())

    def test_cache_rejects_a_different_encoder(self):
        set_seed(0)
        wrong = L2EmbeddingModel(latent=32, patch=33)
        with pytest.raises(RuntimeError, match="rebuild the cache"):
            EmbeddingCache(EMB, "validation").load().verify_encoder(
                wrong.encoder.state_dict())

    def test_cached_z_equals_direct_encoder_output(self):
        ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
        m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
        m.load_state_dict(ck["state_dict"])
        m.eval()
        fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
        ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
        ds = splits.open_split("validation")
        smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
        cache = EmbeddingCache(EMB, "validation").load()
        for t in (0, 100, 364):
            field, _, _, _, _ = smp.day(t)
            with torch.no_grad():
                z = m.embed_field(torch.from_numpy(field)[None])[0][:, smp.r, smp.c].T.numpy()
            assert np.allclose(z, np.asarray(cache.z[t]), atol=1e-6)

    def test_cache_cell_indexing_matches_the_sampler(self):
        ck = torch.load(L2_CKPT, map_location="cpu", weights_only=False)
        fs = ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json")
        ts = ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json")
        ds = splits.open_split("validation")
        smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=ck["patch"])
        cache = EmbeddingCache(EMB, "validation").load()
        assert np.array_equal(smp.r, cache.r) and np.array_equal(smp.c, cache.c)

    def test_validation_history_never_crosses_into_train(self):
        cache = EmbeddingCache(EMB, "validation").load()
        va_start = pd.Timestamp(splits.split_bounds("validation")[0])
        assert cache.dates.min() >= va_start, "validation cache holds only validation days"
        ds = splits.open_split("validation")
        tgt = TargetCache(TGT, "validation").load()
        s = TemporalSequenceSampler(
            ds, cache, DEPTHS,
            ZScoreScaler.from_json(BASE / "phase6b_feature_scaler.json"),
            ZScoreScaler.from_json(BASE / "phase6b_target_scaler.json"),
            7, MAXH, target_cache=tgt)
        earliest = s.target_idx.min() - 7 + 1
        assert earliest >= 0, "history would run off the start of the split"
        assert s.target_dates.min() >= va_start + pd.Timedelta(days=MAXH - 1)

    def test_no_test_dates_anywhere_in_the_l3_caches(self):
        for sp in ("train", "validation"):
            c = EmbeddingCache(EMB, sp).load()
            assert not splits.contains_test_dates(c.dates)

    def test_test_embeddings_are_not_precomputed_before_freeze(self):
        marker = MODELS / "phase6b_l3_selected.pt"
        if not marker.exists():
            assert not (EMB / "test" / "meta.json").exists(), \
                "test embeddings must not exist before the L3 architecture is frozen"


@pytest.mark.skipif(not have_cache, reason="split lock")
def test_split_lock_still_enforced():
    with pytest.raises(PermissionError):
        splits.open_split("test")


@pytest.mark.skipif(not (BASE / "phase6b_feature_scaler.json").exists(),
                    reason="scalers missing")
def test_scaler_and_climatology_provenance_is_train_only():
    for f in ("phase6b_feature_scaler.json", "phase6b_target_scaler.json"):
        assert json.load(open(BASE / f, encoding="utf-8"))["fitted_on"] == "train"
    from oceanembed.ml.climatology import HarmonicClimatology
    c = HarmonicClimatology.load(BASE / "phase6b_climatology.nc")
    assert c.meta["fitted_on"] == "train"
    assert c.meta["fit_end"] == splits.split_bounds("train")[1]


@pytest.mark.skipif(not (MODELS / "phase6b_l3_selected.pt").exists(),
                    reason="L3 not yet selected")
def test_selected_checkpoint_records_validation_only_selection():
    ck = torch.load(MODELS / "phase6b_l3_selected.pt", map_location="cpu",
                    weights_only=False)
    assert "validation only" in ck["selection"]
    assert ck["window"] in (1, 3, 7)
    assert ck["depths"] == DEPTHS
    assert ck["n_frozen"] == 113152
