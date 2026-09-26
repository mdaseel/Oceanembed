"""Model Science: attribution and occlusion over the frozen L2.

Risks: an experiment silently becomes the production path; a channel is dropped
or mislabelled; attribution wording drifts into causation; a cached result
survives a model change; occlusion leaks into a served field or neutralises more
than one channel; target data reaches an attribution input.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.replay.engine import (DEPTHS, EXPECTED_L2_ENCODER,  # noqa: E402
                                      EXPECTED_L2_STATE_DICT, state_dict_sha256)
from oceanembed.science import attribution, channels, frozen, occlusion  # noqa: E402

DATE = "2023-05-12"


@pytest.fixture(scope="module")
def engine():
    from oceanembed.replay.engine import ReplayEngine
    return ReplayEngine()


@pytest.fixture(scope="module")
def inputs(engine):
    return frozen.historical_inputs(engine, DATE)


def supported_cell(siv):
    rows, cols = np.nonzero(siv)
    i = len(rows) // 3
    return int(rows[i]), int(cols[i])


def test_exactly_seven_channels_in_the_frozen_order():
    assert channels.CHANNELS == ("sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v")
    assert len(channels.LABELS) == 7 and len(channels.SHORT) == 7


def test_forward_field_is_the_engine_inference(engine, inputs):
    field, siv, when = inputs
    ds = engine._store(when.year)
    ref, siv_ref = engine._infer(ds, engine._time_index(ds, when), when)
    mine = frozen.forward_field(engine, field, siv, when)
    assert np.array_equal(siv, siv_ref)
    assert np.array_equal(np.isnan(mine), np.isnan(ref))
    assert np.nanmax(np.abs(mine - ref)) == 0.0


def test_neutralize_changes_exactly_one_plane_and_never_the_mask(inputs):
    field = inputs[0]
    for k, ch in enumerate(channels.CHANNELS):
        out = channels.neutralize(field, [ch])
        changed = [i for i in range(field.shape[0]) if not np.array_equal(out[i], field[i])]
        assert changed in ([k], [])            # a plane already at the mean stays equal
        assert np.array_equal(out[7], field[7])
    assert np.array_equal(field, inputs[0])    # input not modified in place
    kept = channels.keep_only(field, ["sst"])
    assert np.array_equal(kept[0], field[0]) and not kept[1:7].any()


def test_attribution_shape_units_determinism_and_completeness(engine, inputs, tmp_path):
    field, siv, when = inputs
    r, c = supported_cell(siv)
    a = attribution.attribute_cell(engine, field, siv, when, r, c, cache_dir=tmp_path)
    b = attribution.attribute_cell(engine, field, siv, when, r, c, use_cache=False)
    assert a["channels"] == list(channels.CHANNELS)
    assert np.asarray(a["net_c"]).shape == (len(DEPTHS), 7)
    assert a["depths_m"] == list(DEPTHS)
    assert np.allclose(a["net_c"], b["net_c"], atol=1e-5)
    share = np.asarray(a["gross_share"])
    assert np.allclose(share.sum(1), 1.0, atol=1e-5)
    # prediction equals the frozen field at this cell and depth
    ref = frozen.forward_field(engine, field, siv, when)[r, c]
    assert np.allclose(a["prediction_c"], ref, atol=2e-3)
    # Integrated Gradients completeness holds to a small residual
    assert max(a["completeness_residual_c"]) < 0.05


def test_attribution_is_never_called_causal():
    text = (attribution.WORDING + attribution.__doc__).lower()
    assert "sensitivity" in text and "not causal" in text
    assert "causes subsurface" not in attribution.WORDING.replace("not say a surface variable causes", "")


def test_attribution_cache_identity_includes_model_hash(engine):
    k1 = attribution.cache_key(engine.l2_state_dict_sha256, DATE, 10, 20)
    k2 = attribution.cache_key("0" * 64, DATE, 10, 20)
    assert k1["model_sha256"] == EXPECTED_L2_STATE_DICT
    assert attribution._cache_path(k1) != attribution._cache_path(k2)
    for field in ("date", "row", "col", "method", "steps", "baseline", "version"):
        assert field in k1


def test_attribution_reads_no_target_variable():
    tree = ast.parse(Path(attribution.__file__).read_text(encoding="utf-8"))
    names = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any(s.startswith(("temp_", "target_valid_")) for s in names)
    frozen_src = Path(frozen.__file__).read_text(encoding="utf-8")
    assert "temp_" not in frozen_src and "target_valid" not in frozen_src


def test_occlusion_one_channel_per_run_base_unchanged_and_not_production(engine, inputs):
    field, siv, when = inputs
    r, c = supported_cell(siv)
    p1 = occlusion.occlusion_payload(engine, field, siv, when, r, c)
    occlusion._FIELDS.clear()
    p2 = occlusion.occlusion_payload(engine, field, siv, when, r, c)
    assert p1["production_field"] is False and p1["method"]["one_channel_per_run"]
    assert set(p1["point"]) == set(channels.CHANNELS)
    for ch in channels.CHANNELS:
        assert p1["point"][ch]["delta_c"] == p2["point"][ch]["delta_c"]
    base = frozen.forward_field(engine, field, siv, when)[r, c]
    assert np.allclose([x for x in p1["original_c"]], base, atol=1e-3)
    # the production inference is untouched afterwards
    ds = engine._store(when.year)
    ref, _ = engine._infer(ds, engine._time_index(ds, when), when)
    assert np.allclose(ref[r, c], base)


def test_occlusion_tchp_is_recomputed_from_the_occluded_profile_only(engine, inputs):
    from oceanembed.diagnostics.thermal import d26_tchp
    field, siv, when = inputs
    fields = occlusion.occluded_fields(engine, field, siv, when)
    r, c = supported_cell(siv)
    point = occlusion.point_summary(fields, r, c)
    prof = fields["sla"][r, c]
    direct = d26_tchp(prof, DEPTHS)
    if point["sla"]["tchp_occluded"] is not None:
        assert abs(point["sla"]["tchp_occluded"] - round(float(direct.tchp), 2)) < 0.011


def test_frozen_model_hashes_unchanged_after_experiments(engine):
    sd = engine.model.state_dict()
    enc = {k[len("encoder."):]: v for k, v in sd.items() if k.startswith("encoder.")}
    assert state_dict_sha256(sd) == EXPECTED_L2_STATE_DICT
    assert state_dict_sha256(enc) == EXPECTED_L2_ENCODER
