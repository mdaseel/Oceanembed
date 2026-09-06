"""Phase 6B-B guards for the L2 spatial Satellite Embedding Engine.

The specific ways this phase could produce a wrong-but-plausible number:
a patch that is off-centre or transposed, land silently entering the CNN as a
real zero, the fast whole-field path diverging from true patch extraction,
temperature leaking into the encoder, or an embedding that is not reproducible.
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
from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.ml.l2_dataset import DayFieldSampler  # noqa: E402
from oceanembed.ml.l2_model import (CONTEXT_DIM, Decoder, L2EmbeddingModel,  # noqa: E402
                                    SpatialEncoder, dilation_schedule)
from oceanembed.ml.model import masked_mse, set_seed  # noqa: E402
from oceanembed.ml.patches import (N_CHANNELS, N_DATA_CHANNELS, centre_value,  # noqa: E402
                                   day_field, extract_patch)
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402

BASE = ROOT / "outputs" / "baselines"
MODELS = ROOT / "outputs" / "models"
DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
PATCH = 17
HALF = PATCH // 2


# ------------------------------------------------------- receptive field
@pytest.mark.parametrize("patch", [9, 17, 33])
def test_dilation_schedule_gives_exact_receptive_field(patch):
    dil = dilation_schedule(patch)
    assert 1 + 2 * sum(dil) == patch


@pytest.mark.parametrize("patch", [9, 17, 33])
def test_encoder_collapses_patch_to_single_vector(patch):
    set_seed(0)
    enc = SpatialEncoder(patch=patch)
    z = enc.forward_patch(torch.randn(4, N_CHANNELS, patch, patch))
    assert z.shape == (4, enc.latent)
    assert enc.receptive_field == patch


def test_dilation_schedule_rejects_even_patch():
    with pytest.raises(ValueError):
        dilation_schedule(16)


# ----------------------------------------------- patch geometry / centring
def _blank_field(nlat=20, nlon=25, patch=PATCH):
    h = patch // 2
    return np.zeros((N_CHANNELS, nlat + 2 * h, nlon + 2 * h), dtype="float32"), nlat, nlon


def test_patch_has_expected_shape():
    f, _, _ = _blank_field()
    p = extract_patch(f, 3, 4, PATCH)
    assert p.shape == (N_CHANNELS, PATCH, PATCH)


def test_patch_centre_is_the_requested_cell():
    f, _, _ = _blank_field()
    f[0, HALF + 6, HALF + 9] = 7.0                 # mark domain cell (6, 9)
    assert extract_patch(f, 6, 9, PATCH)[0, HALF, HALF] == 7.0


def test_neighbouring_centres_shift_by_exactly_one_cell():
    f, _, _ = _blank_field()
    f[0, HALF + 6, HALF + 9] = 7.0
    p = extract_patch(f, 6, 10, PATCH)             # centre one cell east
    assert p[0, HALF, HALF] == 0.0
    loc = np.argwhere(p[0] == 7.0)[0]
    assert tuple(loc) == (HALF, HALF - 1), "marked cell must sit one column west"


def test_latitude_orientation_is_preserved_in_the_patch():
    """Row index increases northward, matching the ascending canonical lat."""
    f, _, _ = _blank_field()
    f[0, HALF + 7, HALF + 9] = 1.0                 # one cell NORTH of (6, 9)
    p = extract_patch(f, 6, 9, PATCH)
    assert p[0, HALF + 1, HALF] == 1.0, "north must be at a larger row index"


def test_longitude_orientation_is_preserved_in_the_patch():
    f, _, _ = _blank_field()
    f[0, HALF + 6, HALF + 10] = 1.0                # one cell EAST of (6, 9)
    p = extract_patch(f, 6, 9, PATCH)
    assert p[0, HALF, HALF + 1] == 1.0, "east must be at a larger column index"


def test_centre_value_helper_matches_manual_indexing():
    f, _, _ = _blank_field()
    f[0, HALF + 2, HALF + 2] = 5.0
    p = extract_patch(f, 2, 2, PATCH)
    assert centre_value(p, PATCH)[0] == 5.0


# --------------------------------------------------- domain-edge handling
def _toy_ds(nlat=20, nlon=25, n_days=2):
    t = pd.date_range("2015-01-01", periods=n_days, freq="D")
    lat = 5.0 + 0.25 * np.arange(nlat)
    lon = 45.0 + 0.25 * np.arange(nlon)
    shp = (n_days, nlat, nlon)
    rng = np.random.default_rng(0)
    ds = xr.Dataset(coords={"time": t, "lat": lat, "lon": lon})
    for v in SURFACE:
        ds[v] = (("time", "lat", "lon"), rng.normal(size=shp))
    # a land block: NaN in every surface channel
    for v in SURFACE:
        ds[v].values[:, 0:3, 0:3] = np.nan
    for d in DEPTHS:
        ds[f"temp_{d}m"] = (("time", "lat", "lon"), rng.normal(20, 2, size=shp))
        tv = np.ones(shp, bool)
        if d >= 500:
            tv[:, :, 0:2] = False
            ds[f"temp_{d}m"].values[:, :, 0:2] = np.nan
        ds[f"target_valid_{d}m"] = (("time", "lat", "lon"), tv)
    siv = np.ones(shp, bool)
    siv[:, 0:3, 0:3] = False
    ds["surface_input_valid"] = (("time", "lat", "lon"), siv)
    ds["ocean_mask"] = (("time", "lat", "lon"), np.ones(shp, bool))
    return ds


def _scalers():
    fs = ZScoreScaler(np.zeros(11), np.ones(11),
                      SURFACE + ["lat", "lon", "doy_sin", "doy_cos"])
    ts = ZScoreScaler(np.zeros(15), np.ones(15), [f"temp_{d}m" for d in DEPTHS])
    return fs, ts


def test_field_is_padded_so_every_cell_has_a_patch():
    ds = _toy_ds()
    fs, _ = _scalers()
    f = day_field(ds, 0, fs, PATCH)
    nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]
    assert f.shape == (N_CHANNELS, nlat + 2 * HALF, nlon + 2 * HALF)
    for i, j in [(0, 0), (nlat - 1, nlon - 1), (0, nlon - 1)]:
        assert extract_patch(f, i, j, PATCH).shape == (N_CHANNELS, PATCH, PATCH)


def test_edge_padding_is_marked_invalid_not_fabricated():
    """Padding must be flagged by the mask, so the CNN can tell it apart from
    observed ocean. Reflection/replication would invent plausible data."""
    ds = _toy_ds()
    fs, _ = _scalers()
    f = day_field(ds, 0, fs, PATCH)
    assert f[N_DATA_CHANNELS, 0, 0] == 0.0, "corner padding must have mask 0"
    assert np.all(f[:N_DATA_CHANNELS, 0, 0] == 0.0), "padding data must be 0"
    corner = extract_patch(f, 0, 0, PATCH)
    assert corner[N_DATA_CHANNELS, :HALF, :].sum() == 0.0


def test_land_cells_are_masked_not_silently_zero_filled():
    ds = _toy_ds()
    fs, _ = _scalers()
    f = day_field(ds, 0, fs, PATCH)
    mask = f[N_DATA_CHANNELS]
    # domain cell (0,0) is land in the toy dataset
    assert mask[HALF + 0, HALF + 0] == 0.0
    assert mask[HALF + 10, HALF + 10] == 1.0
    # its data channels are zero, but the mask distinguishes that from real 0
    assert np.all(f[:N_DATA_CHANNELS, HALF + 0, HALF + 0] == 0.0)


def test_no_nan_reaches_the_network():
    ds = _toy_ds()
    fs, _ = _scalers()
    f = day_field(ds, 0, fs, PATCH)
    assert np.isfinite(f).all(), "field fed to the CNN must contain no NaN"


def test_mask_channel_is_binary():
    ds = _toy_ds()
    fs, _ = _scalers()
    m = day_field(ds, 0, fs, PATCH)[N_DATA_CHANNELS]
    assert set(np.unique(m)).issubset({0.0, 1.0})


def test_channel_count_is_seven_data_plus_one_mask():
    assert N_DATA_CHANNELS == len(SURFACE) == 7
    assert N_CHANNELS == 8


# --------------------------- field path == patch path (the core correctness claim)
def test_field_path_equals_patch_extraction():
    """The whole-field pass must be numerically identical to extracting each
    17x17 patch separately. This is the correctness basis for the ~289x
    speedup that makes the experiment affordable."""
    set_seed(2)
    m = L2EmbeddingModel(patch=PATCH).eval()
    nlat, nlon = 12, 14
    field = torch.randn(1, N_CHANNELS, nlat + 2 * HALF, nlon + 2 * HALF)
    with torch.no_grad():
        zf = m.embed_field(field)[0]
        idx = [(i, j) for i in range(nlat) for j in range(nlon)]
        P = torch.stack([field[0, :, i:i + PATCH, j:j + PATCH] for i, j in idx])
        zp = m.embed_patch(P)
    zf_flat = torch.stack([zf[:, i, j] for i, j in idx])
    assert torch.allclose(zf_flat, zp, atol=1e-5)


def test_field_output_has_one_embedding_per_domain_cell():
    set_seed(0)
    m = L2EmbeddingModel(patch=PATCH)
    nlat, nlon = 20, 25
    z = m.embed_field(torch.randn(1, N_CHANNELS, nlat + 2 * HALF, nlon + 2 * HALF))
    assert z.shape == (1, m.latent_dim, nlat, nlon)


# --------------------------------------------------------- model contracts
def test_embedding_dimension_is_as_configured():
    for latent in (16, 32):
        m = L2EmbeddingModel(latent=latent, patch=PATCH)
        assert m.latent_dim == latent
        assert m.embed_patch(torch.randn(3, N_CHANNELS, PATCH, PATCH)).shape == (3, latent)


def test_decoder_output_width_is_fifteen():
    m = L2EmbeddingModel(patch=PATCH)
    out = m(torch.randn(5, N_CHANNELS, PATCH, PATCH), torch.randn(5, CONTEXT_DIM))
    assert out.shape == (5, 15)


def test_decoder_consumes_embedding_plus_four_context_features():
    d = Decoder(latent=32, context=CONTEXT_DIM)
    assert d.net[0].in_features == 32 + 4


def test_encoder_input_channels_exclude_any_temperature():
    """The encoder must see only surface channels plus the validity mask."""
    m = L2EmbeddingModel(patch=PATCH)
    assert m.encoder.conv[0].in_channels == N_CHANNELS == len(SURFACE) + 1


def test_embedding_is_deterministic():
    set_seed(5)
    m = L2EmbeddingModel(patch=PATCH).eval()
    x = torch.randn(4, N_CHANNELS, PATCH, PATCH)
    with torch.no_grad():
        a, b = m.embed_patch(x), m.embed_patch(x)
    assert torch.equal(a, b)


def test_forward_from_z_matches_full_forward():
    set_seed(6)
    m = L2EmbeddingModel(patch=PATCH).eval()
    x = torch.randn(6, N_CHANNELS, PATCH, PATCH)
    ctx = torch.randn(6, CONTEXT_DIM)
    with torch.no_grad():
        assert torch.allclose(m(x, ctx), m.forward_from_z(m.embed_patch(x), ctx), atol=1e-6)


def test_checkpoint_roundtrip_is_exact(tmp_path):
    set_seed(9)
    m = L2EmbeddingModel(patch=PATCH).eval()
    x = torch.randn(8, N_CHANNELS, PATCH, PATCH)
    ctx = torch.randn(8, CONTEXT_DIM)
    with torch.no_grad():
        before = m(x, ctx)
    p = tmp_path / "l2.pt"
    torch.save({"state_dict": m.state_dict(), "patch": PATCH, "latent": m.latent_dim}, p)
    ck = torch.load(p, map_location="cpu", weights_only=False)
    m2 = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m2.load_state_dict(ck["state_dict"])
    m2.eval()
    with torch.no_grad():
        after = m2(x, ctx)
    assert torch.equal(before, after)


# ------------------------------------------------------------- data path
def test_sampler_targets_and_masks_match_l1_conventions():
    ds = _toy_ds()
    fs, ts = _scalers()
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=PATCH)
    field, ctx, Yz, M, Y = smp.day(0)
    assert field.shape[0] == N_CHANNELS
    assert Yz.shape == (smp.n_cells, 15)
    assert M.shape == Yz.shape
    assert ctx.shape == (smp.n_cells, CONTEXT_DIM)
    assert np.isfinite(Yz).all(), "standardised targets must be finite"
    assert np.isfinite(Y[M]).all(), "every unmasked target must be finite"


def test_sampler_excludes_surface_invalid_cells():
    ds = _toy_ds()
    fs, ts = _scalers()
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=PATCH)
    assert smp.n_cells == ds.sizes["lat"] * ds.sizes["lon"] - 9


def test_sampler_keeps_cells_missing_deep_targets():
    ds = _toy_ds()
    fs, ts = _scalers()
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=PATCH)
    _, _, _, M, _ = smp.day(0)
    i500 = DEPTHS.index(500)
    assert (~M[:, i500]).any() and M[:, 0].all()


def test_sampler_uses_only_the_requested_day():
    """No future-day access: the field for day t must depend only on day t."""
    ds = _toy_ds(n_days=3)
    fs, ts = _scalers()
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=PATCH)
    f0 = smp.day(0)[0].copy()
    ds2 = ds.copy(deep=True)
    for v in SURFACE:
        ds2[v].values[1:] = 999.0            # corrupt every later day
    smp2 = DayFieldSampler(ds2, DEPTHS, fs, ts, patch=PATCH)
    assert np.array_equal(f0, smp2.day(0)[0]), "day 0 must not see later days"


def test_sampler_field_centre_matches_the_cell_value():
    ds = _toy_ds()
    fs, ts = _scalers()
    smp = DayFieldSampler(ds, DEPTHS, fs, ts, patch=PATCH)
    f = smp.day(0)[0]
    i, j = 10, 12
    expect = float(ds[SURFACE[0]].isel(time=0).values[i, j])
    assert np.isclose(f[0, HALF + i, HALF + j], expect, atol=1e-5)


def test_masked_loss_is_unchanged_from_phase6b_a():
    p = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    t = torch.zeros(2, 2)
    m = torch.tensor([[True, False], [True, True]])
    assert float(masked_mse(p, t, m)) == pytest.approx(10.5)


# ------------------------------------------------------------ provenance
def test_split_lock_still_enforced():
    with pytest.raises(PermissionError):
        splits.open_split("test")


@pytest.mark.skipif(not (BASE / "phase6b_feature_scaler.json").exists(),
                    reason="scalers not fitted")
def test_l2_uses_the_frozen_train_only_scalers():
    for f in ("phase6b_feature_scaler.json", "phase6b_target_scaler.json"):
        assert json.load(open(BASE / f, encoding="utf-8"))["fitted_on"] == "train"


@pytest.mark.skipif(not (MODELS / "phase6b_l2_final.pt").exists(),
                    reason="final L2 not trained yet")
def test_final_l2_checkpoint_metadata():
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    assert ck["depths"] == DEPTHS
    assert ck["receptive_field"] == ck["patch"]
    assert "encoder_state_dict" in ck, "encoder must be saved separately for reuse"
    m = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    m.load_state_dict(ck["state_dict"])
    out = m(torch.zeros(2, N_CHANNELS, ck["patch"], ck["patch"]), torch.zeros(2, CONTEXT_DIM))
    assert out.shape == (2, 15)


@pytest.mark.skipif(not (MODELS / "phase6b_l2_final.pt").exists(),
                    reason="final L2 not trained yet")
def test_saved_encoder_reproduces_the_full_model_embedding():
    ck = torch.load(MODELS / "phase6b_l2_final.pt", map_location="cpu", weights_only=False)
    full = L2EmbeddingModel(latent=ck["latent"], patch=ck["patch"])
    full.load_state_dict(ck["state_dict"])
    full.eval()
    enc = SpatialEncoder(latent=ck["latent"], patch=ck["patch"])
    enc.load_state_dict(ck["encoder_state_dict"])
    enc.eval()
    x = torch.randn(3, N_CHANNELS, ck["patch"], ck["patch"])
    with torch.no_grad():
        assert torch.equal(full.embed_patch(x), enc.forward_patch(x))
