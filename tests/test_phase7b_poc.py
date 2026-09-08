"""Phase 7B transport integrity against real frozen replay, without data mutation."""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from oceanembed.poc import app as poc
from oceanembed.replay import api
from oceanembed.replay.engine import ReplayEngine


@pytest.fixture(scope="module")
def engine():
    e = ReplayEngine(use_cache=False)
    yield e
    e.close()


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setattr(api, "_engine", engine)
    with TestClient(poc.app) as c:
        yield c


@pytest.fixture(scope="module")
def field(engine):
    return engine.replay_field("2021-06-15")


@pytest.fixture
def payload(client, field, monkeypatch):
    monkeypatch.setattr(api.engine(), "replay_field", lambda *a, **k: field)
    response = client.get("/api/replay/view", params={"date": field.date})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("name", ["temperature", "climatology", "anomaly"])
def test_transport_is_exact_field(payload, field, name):
    np.testing.assert_array_equal(np.asarray(payload[name], dtype=float), getattr(field, name))


def test_surface_and_profile_match_phase7a_point(payload, engine):
    point = engine.replay_point("2021-06-15", 15.25, 87.75)
    r, c = point.location.grid_row, point.location.grid_col
    for name, item in point.surface_inputs.items():
        assert payload["surface_inputs"][name]["values"][r][c] == item["value"]
    assert payload["temperature"][r][c] == [x["prediction_c"] for x in point.profile]


def test_complete_transport_calls_field_only_once(client, engine, monkeypatch):
    original = engine.replay_field
    calls = []
    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(engine, "replay_field", spy)
    response = client.get("/api/replay/view?date=2021-06-15&force_recompute=true")
    assert len(calls) == 1
    assert calls[0][1]["force_recompute"] is True
    assert response.json()["provenance"]["inference_source"] == "LIVE_MODEL_RUN"


def test_climatology_absence_does_not_suppress_l2(payload, field):
    absent = np.isfinite(field.temperature) & ~field.climatology_defined
    assert absent.any()
    assert np.isfinite(np.asarray(payload["temperature"], dtype=float)[absent]).all()
    assert np.isnan(np.asarray(payload["anomaly"], dtype=float)[absent]).all()


@pytest.mark.parametrize("date", ["2015-06-15", "2023-06-15"])
def test_date_own_mask(client, engine, date):
    response = client.get("/api/replay/view", params={"date": date}).json()
    view = engine.replay_field(date)
    np.testing.assert_array_equal(response["surface_input_valid"], view.surface_input_valid)
    assert response["date"] == date


@pytest.mark.parametrize("date", ["garbage", "NaT", "2014-01-01", "2025-01-01"])
def test_bad_dates_have_explicit_error(client, date):
    assert client.get("/api/replay/view", params={"date": date}).status_code == 422


def test_netcdf_is_full_precision_field(client, field, monkeypatch):
    monkeypatch.setattr(api.engine(), "replay_field", lambda *a, **k: field)
    response = client.get("/api/export/field.nc?date=2021-06-15")
    assert response.status_code == 200
    with xr.open_dataset(io.BytesIO(response.content), engine="scipy") as ds:
        for name in ("temperature", "climatology", "anomaly"):
            np.testing.assert_array_equal(ds[name].values, getattr(field, name))
        assert ds.attrs["date"] == field.date
        assert "NASA PO.DAAC" in ds.attrs["credits"]
        assert json.loads(ds.attrs["provenance_json"])["l2_state_dict_sha256"] == field.provenance["l2_state_dict_sha256"]


def test_evidence_exact_artifact_rows(client):
    import csv
    body = client.get("/api/evidence").json()
    for key, path in poc.TABLES.items():
        with (ROOT / path).open(encoding="utf-8-sig", newline="") as f:
            assert body["tables"][key]["rows"] == list(csv.DictReader(f))
    assert body["manifest"]["holdout_status"]["argo_2024"] == "PROTECTED"


def test_document_allowlist(client):
    assert client.get("/api/evidence/document/closure").json()["source"] == "ARCHITECTURE_CLOSURE_REPORT.md"
    assert client.get("/api/evidence/document/secrets").status_code == 404


def test_legacy_api_and_static_build(client):
    assert client.get("/api/health").json()["depths_m"] == [0,5,10,20,30,50,75,100,125,150,200,300,500,700,1000]
    response = client.get("/")
    if (ROOT / "web/dist/index.html").is_file():
        assert response.status_code == 200
        assert "OceanEmbed" in response.text
    else:
        assert response.status_code == 503
