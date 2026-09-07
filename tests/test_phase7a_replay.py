"""Phase 7A guards — authoritative historical replay of the frozen L2 core.

The risks these target: a second inference implementation drifting from the
frozen path, a point profile disagreeing with the field it is supposed to come
from, a target or Argo dependency creeping into normal replay, a frozen artifact
being mutated, a fabricated value entering the cache, and a requested location
being silently swapped for a different ocean cell.

Target-leakage proofs here are NON-DESTRUCTIVE: they monkeypatch paths and
inspect what the code opens. No real project file is deleted, renamed, moved,
corrupted or overwritten.
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

from oceanembed.config import EAST, NORTH, REPO_ROOT, SOUTH, WEST  # noqa: E402
from oceanembed.ml.features import SURFACE, cyclic_doy  # noqa: E402
from oceanembed.ml.patches import N_DATA_CHANNELS, day_field  # noqa: E402
from oceanembed.replay import cache as cache_mod  # noqa: E402
from oceanembed.replay import engine as engine_mod  # noqa: E402
from oceanembed.replay.contract import (ALLOWED_STORE_VARS, DEPTHS, FieldView,  # noqa: E402
                                        LocationStatus, OutsideDomain)
from oceanembed.replay.engine import ReplayEngine, file_sha256  # noqa: E402

DATA = REPO_ROOT / "data" / "processed" / "model_ready"
PHASE7 = REPO_ROOT / "outputs" / "phase7"

#: A deterministic Bay-of-Bengal ocean point inside the PoC region.
DATE = "2021-06-15"
LAT, LON = 15.25, 87.75

needs_data = pytest.mark.skipif(
    not (DATA / "oceanembed_2021.zarr").exists(),
    reason="model-ready store not present (see Phase 7A data prerequisites)")


@pytest.fixture(scope="module")
def eng():
    e = ReplayEngine(use_cache=False)
    yield e
    e.close()


@pytest.fixture(scope="module")
def view(eng):
    return eng.replay_field(DATE)


# ============================================================ frozen artifacts
FROZEN_EXPECTED = {
    REPO_ROOT / "outputs" / "models" / "phase6b_l2_final.pt":
        "81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35",
    REPO_ROOT / "outputs" / "models" / "phase6b_l1_mlp.pt":
        "fefebd216536b9a1b8383ae41b5d35057b8b46ed1b4b77a9642a514bc9c92b5b",
    REPO_ROOT / "outputs" / "baselines" / "phase6b_feature_scaler.json":
        "49671ce760b0dca5c1c82cb184dae91908cc064abfdea8cc7eb2f5bc3c320467",
    REPO_ROOT / "outputs" / "baselines" / "phase6b_target_scaler.json":
        "5b6f359db0d228dd7d3acf775ab8a6eea76dd521e7b4568ff1873c832e89e93b",
    REPO_ROOT / "outputs" / "baselines" / "phase6b_climatology.nc":
        "748af4d79bc704cc2f742e1c208bacebe781131c5ff142cddc7c334963903cd5",
}


@pytest.mark.parametrize("path,expected", list(FROZEN_EXPECTED.items()),
                         ids=[p.name for p in FROZEN_EXPECTED])
def test_frozen_artifact_unchanged(path, expected):
    assert path.exists(), f"{path.name} is missing"
    assert file_sha256(path) == expected, f"{path.name} CHANGED"


@needs_data
def test_engine_pins_the_frozen_l2_and_encoder_hashes(eng):
    assert eng.l2_state_dict_sha256 == engine_mod.EXPECTED_L2_STATE_DICT
    assert eng.l2_encoder_sha256 == engine_mod.EXPECTED_L2_ENCODER
    assert eng.patch == 33 and eng.latent == 32 and eng.receptive_field == 33
    assert eng.n_params == 136335


@needs_data
def test_a_changed_frozen_hash_is_a_hard_failure(monkeypatch):
    monkeypatch.setattr(engine_mod, "EXPECTED_L2_STATE_DICT", "0" * 64)
    with pytest.raises(engine_mod.FrozenArtifactChanged):
        ReplayEngine(use_cache=False)


@needs_data
def test_model_weights_unchanged_by_running_replay(eng):
    before = engine_mod.state_dict_sha256(eng.model.state_dict())
    eng.replay_field(DATE)
    eng.replay_point(DATE, LAT, LON)
    assert engine_mod.state_dict_sha256(eng.model.state_dict()) == before


# ================================================================ field replay
@needs_data
def test_field_has_all_fifteen_depths_in_the_mandated_order(view):
    assert view.depths == DEPTHS
    assert view.depths == [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300,
                           500, 700, 1000]
    assert view.temperature.shape == (101, 241, 15)
    view.validate()


@needs_data
def test_field_view_contract_shapes_and_grid(view):
    assert view.lat.shape == (101,) and view.lon.shape == (241,)
    assert float(view.lat[0]) == SOUTH and float(view.lat[-1]) == NORTH
    assert float(view.lon[0]) == WEST and float(view.lon[-1]) == EAST
    for name in ("climatology", "anomaly"):
        assert getattr(view, name).shape == view.temperature.shape
    assert view.ocean_mask.shape == (101, 241)
    assert view.surface_input_valid.shape == (101, 241)


@needs_data
def test_a_malformed_field_view_is_rejected(view):
    bad = FieldView(view.date, view.temperature[:, :, :14], view.climatology,
                    view.anomaly, view.lat, view.lon, DEPTHS, view.ocean_mask,
                    view.surface_input_valid)
    with pytest.raises(ValueError):
        bad.validate()


@needs_data
def test_predictions_exist_exactly_on_the_supported_cells(view):
    finite = np.isfinite(view.temperature).all(axis=2)
    assert np.array_equal(finite, view.surface_input_valid)
    # off-support cells are NaN, never zero
    off = ~view.surface_input_valid
    assert np.isnan(view.temperature[off]).all()


@needs_data
def test_support_is_a_subset_of_ocean(view):
    assert not (view.surface_input_valid & ~view.ocean_mask).any()


@needs_data
def test_field_uses_the_exact_frozen_l2_path(eng, view):
    """Recompute inline from the frozen primitives and require equality.

    This is the anti-drift test: if replay ever grew its own preprocessing,
    context construction, scaler use or decode order, this diverges.
    """
    when = pd.Timestamp(DATE)
    ds = eng._store(when.year)
    t = eng._time_index(ds, when)
    siv = np.asarray(ds["surface_input_valid"].isel(time=t).values, dtype=bool)
    rows, cols = np.nonzero(siv)

    field = day_field(ds, t, eng.feature_scaler, eng.patch)
    s, c = cyclic_doy(pd.DatetimeIndex([when]))
    raw = np.column_stack([eng.lat[rows], eng.lon[cols],
                           np.full(rows.size, s[0]), np.full(rows.size, c[0])])
    ctx = ((raw - eng.feature_scaler.mean[N_DATA_CHANNELS:])
           / eng.feature_scaler.std[N_DATA_CHANNELS:]).astype("float32")
    with torch.no_grad():
        z = eng.model.embed_field(torch.from_numpy(field)[None])[0]
        pred = eng.model.forward_from_z(z[:, rows, cols].T,
                                        torch.from_numpy(ctx)).numpy().astype("float64")
    expected = eng.target_scaler.inverse_transform(pred)
    assert np.allclose(view.temperature[rows, cols, :], expected,
                       rtol=0, atol=1e-12)


@needs_data
def test_day_field_joint_mask_equals_surface_input_valid(eng):
    """The decode cell set and the encoder's mask channel must agree."""
    when = pd.Timestamp(DATE)
    ds = eng._store(when.year)
    t = eng._time_index(ds, when)
    field = day_field(ds, t, eng.feature_scaler, eng.patch)
    half = eng.patch // 2
    mask_channel = field[N_DATA_CHANNELS,
                         half:half + 101, half:half + 241].astype(bool)
    siv = np.asarray(ds["surface_input_valid"].isel(time=t).values, dtype=bool)
    assert np.array_equal(mask_channel, siv)


# ======================================================= climatology + anomaly
@needs_data
def test_climatology_equals_the_frozen_l0(eng, view):
    ref = eng.climatology.predict(pd.DatetimeIndex([view.date]))[0]
    ref = np.moveaxis(ref, 0, -1)
    assert np.allclose(view.climatology, ref, equal_nan=True, rtol=0, atol=0)


@needs_data
def test_anomaly_is_prediction_minus_climatology(view):
    expected = view.temperature - view.climatology
    assert np.allclose(view.anomaly, expected, equal_nan=True, rtol=0, atol=0)


@needs_data
def test_climatology_defined_mask_marks_below_seafloor(view):
    """L0's NaN pattern is a valid-water-depth mask and must shrink with depth."""
    defined = view.climatology_defined
    counts = [int(defined[:, :, k].sum()) for k in range(len(DEPTHS))]
    assert counts[0] > counts[-1], "deep water should be defined in fewer cells"
    assert all(a >= b for a, b in zip(counts, counts[1:])), \
        "valid water depth must be monotonically non-increasing with depth"


@needs_data
def test_deep_l2_output_is_not_suppressed(view):
    """7B.3: deep predictions must still be returned, not replaced by L0."""
    deep = view.layer(1000)
    assert np.isfinite(deep).sum() == int(view.surface_input_valid.sum())
    on = view.surface_input_valid & view.climatology_defined[:, :, -1]
    assert not np.allclose(deep[on], view.layer(1000, "climatology")[on]), \
        "deep L2 output appears to have been replaced by climatology"


# ================================================= MANDATORY point == field
@needs_data
def test_point_equals_field_at_the_resolved_cell(eng, view):
    """MANDATORY Phase 7A test — replay_point samples the authoritative field."""
    res = eng.replay_point(DATE, LAT, LON)
    assert res.location.status is LocationStatus.OK
    r, c = res.location.grid_row, res.location.grid_col
    for k, row in enumerate(res.profile):
        assert row["depth_m"] == view.depths[k]
        for key, arr in (("prediction_c", view.temperature),
                         ("climatology_c", view.climatology),
                         ("anomaly_c", view.anomaly)):
            ref = arr[r, c, k]
            got = row[key]
            if not np.isfinite(ref):
                assert got is None
            else:
                assert got == pytest.approx(float(ref), rel=0, abs=0.0)


@needs_data
def test_point_runs_no_inference_of_its_own(eng, monkeypatch):
    """replay_point must reach the network only via replay_field."""
    calls = {"n": 0}
    real = eng.model.embed_field

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(eng.model, "embed_field", counting)
    eng.replay_point(DATE, LAT, LON)
    assert calls["n"] == 1, f"expected exactly one whole-field encode, got {calls['n']}"


@needs_data
def test_point_profile_is_finite_and_json_serialisable(eng):
    res = eng.replay_point(DATE, LAT, LON)
    blob = json.dumps(res.as_dict())
    back = json.loads(blob)
    assert len(back["profile"]) == 15
    assert back["status"]["target_used_for_inference"] is False
    assert back["status"]["argo_used_for_inference"] is False
    assert "nominal_zero_m_note" in back and back["nominal_zero_m_note"]
    for row in back["profile"]:
        for k in ("prediction_c", "climatology_c", "anomaly_c"):
            assert row[k] is None or np.isfinite(row[k])


# ============================================================ location handling
@needs_data
def test_requested_and_resolved_coordinates_are_both_returned(eng, view):
    loc = eng.resolve(view, 15.31, 87.69)
    assert loc.requested_lat == 15.31 and loc.requested_lon == 87.69
    assert loc.grid_lat == pytest.approx(15.25)
    assert loc.grid_lon == pytest.approx(87.75)


@needs_data
@pytest.mark.parametrize("lat,lon", [(45.0, 85.0), (0.0, 85.0), (15.0, 20.0),
                                     (15.0, 130.0), (-5.0, 60.0)])
def test_outside_domain_is_refused(eng, view, lat, lon):
    loc = eng.resolve(view, lat, lon)
    assert loc.status is LocationStatus.OUTSIDE_DOMAIN
    assert loc.grid_lat is None


@needs_data
def test_land_cell_is_reported_not_silently_moved(eng, view):
    land = np.argwhere(~view.ocean_mask)
    r, c = land[len(land) // 2]
    loc = eng.resolve(view, float(view.lat[r]), float(view.lon[c]))
    assert loc.status is LocationStatus.INVALID_OCEAN_CELL
    # the resolved cell is still the REQUESTED one
    assert loc.grid_lat == pytest.approx(float(view.lat[r]))
    assert loc.grid_lon == pytest.approx(float(view.lon[c]))
    if loc.nearest_usable_lat is not None:
        assert (loc.nearest_usable_lat, loc.nearest_usable_lon) != \
               (loc.grid_lat, loc.grid_lon)


@needs_data
def test_ocean_cell_without_valid_input_is_its_own_status(eng, view):
    gap = view.ocean_mask & ~view.surface_input_valid
    if not gap.any():
        pytest.skip("no ocean cell lacks surface input on this date")
    r, c = np.argwhere(gap)[0]
    loc = eng.resolve(view, float(view.lat[r]), float(view.lon[c]))
    assert loc.status is LocationStatus.INPUT_NOT_VALID


@needs_data
def test_date_outside_the_processed_record_is_refused(eng):
    for bad in ("2010-01-01", "2030-01-01", "2024-12-31"):
        with pytest.raises(OutsideDomain):
            eng.replay_field(bad)


# ============================================================== multi-date
@needs_data
def test_multi_date_replay_is_independent_per_day(eng):
    res = eng.replay_range("2021-06-15", "2021-06-18", LAT, LON)
    assert [r.date for r in res] == ["2021-06-15", "2021-06-16", "2021-06-17",
                                     "2021-06-18"]
    single = eng.replay_point("2021-06-17", LAT, LON)
    same = [r for r in res if r.date == "2021-06-17"][0]
    assert [x["prediction_c"] for x in same.profile] == \
           [x["prediction_c"] for x in single.profile]


@needs_data
def test_no_future_day_is_read(eng, monkeypatch):
    """Only the requested date's time index may be indexed out of the store."""
    when = pd.Timestamp(DATE)
    ds = eng._store(when.year)
    wanted = eng._time_index(ds, when)
    seen: list[int] = []
    real = engine_mod.day_field

    def spy(store, t, scaler, patch):
        seen.append(int(t))
        return real(store, t, scaler, patch)

    monkeypatch.setattr(engine_mod, "day_field", spy)
    eng.replay_field(DATE, force_recompute=True)
    assert seen == [wanted]


# ====================================================== no target / Argo leakage
def test_allowed_store_vars_excludes_every_target():
    assert ALLOWED_STORE_VARS == frozenset(set(SURFACE) |
                                           {"ocean_mask", "surface_input_valid"})
    assert not any(v.startswith(("temp_", "target_valid_"))
                   for v in ALLOWED_STORE_VARS)


@needs_data
def test_opened_store_carries_no_target_variable(eng):
    ds = eng._store(2021)
    assert set(ds.data_vars) <= ALLOWED_STORE_VARS
    assert not any(str(v).startswith(("temp_", "target_valid_"))
                   for v in ds.data_vars)


@needs_data
def test_replay_works_with_targets_cache_and_argo_paths_removed(monkeypatch,
                                                               tmp_path):
    """Non-destructive: point the caches at empty temp dirs, not the real ones."""
    missing = tmp_path / "definitely-not-here"
    monkeypatch.setenv("OCEANEMBED_TARGETS_CACHE", str(missing))
    monkeypatch.setattr("oceanembed.ml.embedding_cache.TargetCache",
                        _forbidden("TargetCache"))
    e = ReplayEngine(use_cache=False)
    try:
        res = e.replay_point(DATE, LAT, LON)
        assert len(res.profile) == 15
        assert res.profile[7]["prediction_c"] is not None
    finally:
        e.close()
    # the real caches were never touched
    assert (REPO_ROOT / "outputs" / "targets_cache").exists()


def _forbidden(name):
    def boom(*a, **kw):
        raise AssertionError(f"replay must not construct {name}")
    return boom


@needs_data
def test_replay_never_opens_a_target_or_argo_file(eng, monkeypatch):
    """Spy on xarray/pandas openers and assert nothing forbidden is read."""
    opened: list[str] = []
    for mod, fn in (("xarray", "open_zarr"), ("xarray", "open_dataset"),
                    ("xarray", "open_mfdataset"), ("pandas", "read_parquet")):
        real = getattr(__import__(mod), fn)

        def spy(*a, _real=real, **kw):
            if a:
                opened.append(str(a[0]))
            return _real(*a, **kw)

        monkeypatch.setattr(f"{mod}.{fn}", spy)

    e = ReplayEngine(use_cache=False)
    try:
        e.replay_point(DATE, LAT, LON)
    finally:
        e.close()
    joined = " | ".join(opened).lower()
    for forbidden in ("targets_cache", "argo", "embeddings"):
        assert forbidden not in joined, f"replay opened {forbidden}: {opened}"


# ==================================================================== caching
@needs_data
def test_cache_round_trip_is_bit_identical(tmp_path):
    e = ReplayEngine(cache_root=tmp_path, use_cache=True)
    try:
        live = e.replay_field(DATE, force_recompute=True)
        assert live.provenance["inference_source"] == "LIVE_MODEL_RUN"
        cached = e.replay_field(DATE)
        assert cached.provenance["inference_source"] == "VALIDATED_CACHE"
        assert np.array_equal(live.temperature, cached.temperature, equal_nan=True)
        assert np.array_equal(live.climatology, cached.climatology, equal_nan=True)
        assert np.array_equal(live.anomaly, cached.anomaly, equal_nan=True)
    finally:
        e.close()


@needs_data
def test_force_recompute_bypasses_a_populated_cache(tmp_path):
    e = ReplayEngine(cache_root=tmp_path, use_cache=True)
    try:
        e.replay_field(DATE)
        again = e.replay_field(DATE, force_recompute=True)
        assert again.provenance["inference_source"] == "LIVE_MODEL_RUN"
        assert again.provenance["compute_seconds"] is not None
    finally:
        e.close()


@needs_data
def test_cache_identity_changes_with_the_model_hash(eng):
    prov = eng.provenance
    a = cache_mod.identity_key(cache_mod.cache_identity(DATE, prov))
    b = cache_mod.identity_key(cache_mod.cache_identity(
        DATE, {**prov, "l2_state_dict_sha256": "0" * 64}))
    assert a != b, "a different model must not reuse a cached field"


@needs_data
def test_a_tampered_cache_sidecar_is_a_miss_not_a_silent_hit(tmp_path):
    e = ReplayEngine(cache_root=tmp_path, use_cache=True)
    try:
        e.replay_field(DATE)
        meta = next(tmp_path.glob("*.json"))
        doc = json.loads(meta.read_text())
        doc["identity"]["l2_state_dict_sha256"] = "0" * 64
        meta.write_text(json.dumps(doc))
        again = e.replay_field(DATE)
        assert again.provenance["inference_source"] == "LIVE_MODEL_RUN"
    finally:
        e.close()


# =================================================================== manifest
@pytest.mark.skipif(not (PHASE7 / "final_core_manifest.json").exists(),
                    reason="manifest not written yet")
def test_manifest_records_the_frozen_core_truthfully():
    m = json.loads((PHASE7 / "final_core_manifest.json").read_text(encoding="utf-8"))
    assert m["model"]["l2_state_dict_sha256"] == engine_mod.EXPECTED_L2_STATE_DICT
    assert m["model"]["l2_encoder_sha256"] == engine_mod.EXPECTED_L2_ENCODER
    assert m["targets"]["depths_m"] == DEPTHS
    assert m["inputs"]["seven_physical_inputs"] == list(SURFACE)
    assert m["grid"]["shape"] == [101, 241]
    assert m["holdout_status"]["argo_2024"] == "PROTECTED"
    assert "0.494" in m["targets"]["nominal_zero_m_note"]
    assert m["replay"]["point_derives_from_field"] is True


# ======================================================================== API
# The HTTP layer is transport only. These tests assert exactly that: it returns
# the same numbers the Python primitives do, and it introduces no inference.
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from oceanembed.replay import api as api_mod  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(api_mod.app)


@needs_data
def test_health_reports_the_frozen_hashes(client):
    r = client.get("/health")
    assert r.status_code == 200
    b = r.json()
    assert b["l2_state_dict_sha256"] == engine_mod.EXPECTED_L2_STATE_DICT
    assert b["depths_m"] == DEPTHS
    assert b["grid"]["shape"] == [101, 241]
    assert b["target_used_for_inference"] is False


@needs_data
def test_api_point_matches_the_python_primitive(client, eng):
    r = client.get("/replay/point", params={"date": DATE, "lat": LAT, "lon": LON})
    assert r.status_code == 200
    got = r.json()
    ref = eng.replay_point(DATE, LAT, LON).as_dict()
    assert [x["depth_m"] for x in got["profile"]] == DEPTHS
    for a, b in zip(got["profile"], ref["profile"]):
        assert a["prediction_c"] == pytest.approx(b["prediction_c"])


@needs_data
def test_api_field_slice_matches_replay_field(client, view):
    r = client.get("/replay/field", params={"date": DATE, "depth_m": 100})
    assert r.status_code == 200
    b = r.json()
    assert b["shape"] == [101, 241]
    arr = np.array([[np.nan if v is None else v for v in row] for row in b["field"]])
    assert np.allclose(arr, view.layer(100), equal_nan=True)


@needs_data
def test_api_full_field_matches_the_canonical_contract(client, view):
    r = client.get("/replay/field", params={"date": DATE})
    assert r.status_code == 200
    b = r.json()
    assert b["shape"] == [101, 241, 15]
    assert b["depths_m"] == DEPTHS
    assert len(b["lat"]) == 101 and len(b["lon"]) == 241


@needs_data
def test_api_rejects_a_non_mandated_depth_and_a_bad_date(client):
    assert client.get("/replay/field",
                      params={"date": DATE, "depth_m": 42}).status_code == 422
    assert client.get("/replay/point",
                      params={"date": "2030-01-01", "lat": LAT,
                              "lon": LON}).status_code == 422


@needs_data
def test_api_reports_outside_domain_without_erroring(client):
    r = client.get("/replay/point", params={"date": DATE, "lat": 45.0, "lon": 85.0})
    assert r.status_code == 200
    assert r.json()["location"]["status"] == "OUTSIDE_DOMAIN"
    assert r.json()["profile"] == []
