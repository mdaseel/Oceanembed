"""Event library, cyclone context and scenario endpoints — served through the app.

Risks: the generic path disagreeing with the frozen Mocha series; a date outside
an event window replayed; the external track entering or labelled as model
output; comparison arithmetic wrong; a scenario presented as a forecast; a live
cyclone fabricated; the frozen model changing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

L2 = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
ENCODER = "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"
FIX = ROOT / "tests" / "fixtures" / "gdacs"


@pytest.fixture(scope="module")
def client():
    if not (ROOT / "data/processed/model_ready/oceanembed_2023.zarr").exists():
        pytest.skip("model-ready store not present")
    from fastapi.testclient import TestClient
    from oceanembed.poc import app as poc
    with TestClient(poc.app) as c:
        yield c


def test_event_index_lists_more_than_one_enabled_cyclone(client):
    body = client.get("/api/events").json()
    ids = [e["event_id"] for e in body["events"]]
    assert "mocha-2023" in ids and len(ids) >= 2
    assert len(body["candidates"]) == 6
    assert all("split" in e and "in_sample" in e for e in body["events"])


def test_generic_mocha_equals_the_frozen_event(client):
    frozen = client.get("/api/event").json()
    generic = client.get("/api/events/mocha-2023").json()
    for key in ("window_start", "window_end", "peak", "landfall", "segments", "track"):
        assert generic[key] == frozen[key], key
    assert client.get("/api/events/unknown-1999").status_code == 404


def test_generic_series_reproduces_the_frozen_mocha_series(client):
    frozen = client.get("/api/event/series").json()["series"]
    generic = client.get("/api/events/mocha-2023/series").json()
    assert [r["date"] for r in generic["series"]] == [r["date"] for r in frozen]
    for g, f in zip(generic["series"], frozen):
        for key in ("n_cells", "sst_nominal_0m_c", "temp_100m_c", "anomaly_100m_c",
                    "d26_m", "tchp_kj_cm2", "category_counts"):
            assert g[key] == f[key], (g["date"], key)
    m = generic["metrics"]
    assert m["tchp_change"] == pytest.approx(m["wake_min_tchp"]["value"] - m["pre_event_tchp"])


def test_track_analysis_is_bounded_to_the_window_and_labelled_external(client):
    assert client.get("/api/events/mocha-2023/track-analysis?date=2023-06-30").status_code == 422
    body = client.get("/api/events/mocha-2023/track-analysis?date=2023-05-13").json()
    assert body["date"] == "2023-05-13"
    assert "external historical observation" in body["labels"]["track"]
    assert "OceanEmbed" in body["labels"]["thermal_state"]
    again = client.get("/api/events/mocha-2023/track-analysis?date=2023-05-13").json()
    assert again["summary"] == body["summary"]  # deterministic


def test_section_has_the_15_model_depths(client):
    body = client.get("/api/events/mocha-2023/section?date=2023-05-13&mode=anomaly").json()
    assert len(body["depths_m"]) == 15 and len(body["values"]) == 15
    assert client.get("/api/events/mocha-2023/section?date=2023-05-13&mode=salt").status_code == 422


def test_difference_is_between_frozen_segment_composites(client):
    body = client.get("/api/events/mocha-2023/difference?to_segment=Wake&depth=100").json()
    assert body["from_segment"] == "Pre-event" and body["to_segment"] == "Wake"
    assert body["from_dates"] == ["2023-05-05", "2023-05-06", "2023-05-07", "2023-05-08"]
    assert len(body["grid"]["values"]) == 101
    assert "does not establish its cause" in body["caution"]
    assert client.get("/api/events/mocha-2023/difference?depth=90").status_code == 422


def test_compare_needs_two_to_four_events_and_ranks_nothing(client):
    assert client.get("/api/events/compare?ids=mocha-2023").status_code == 422
    body = client.get("/api/events/compare?ids=mocha-2023,biparjoy-2023").json()
    assert [e["event_id"] for e in body["events"]] == ["mocha-2023", "biparjoy-2023"]
    assert "do not rank cyclone danger" in body["note"]
    for e in body["events"]:
        m = e["metrics"]
        if m["tchp_change"] is not None and m["pre_event_tchp"]:
            assert m["tchp_change_pct"] == pytest.approx(m["tchp_change"] / m["pre_event_tchp"] * 100)
        assert "rank" not in json.dumps(e).lower()


def test_brief_states_limitations_and_the_frozen_model(client):
    body = client.get("/api/events/mocha-2023/brief").json()
    assert body["title"] == "CYCLONE OCEAN RESPONSE BRIEF"
    assert body["provenance"]["l2_state_dict_sha256"] == L2
    assert body["provenance"]["l2_encoder_sha256"] == ENCODER
    assert any("does not forecast" in s for s in body["limitations"])
    text = json.dumps(body).lower()
    for banned in ("probability of", "recovered", "risk score", "will intensify"):
        assert banned not in text


def test_archived_cyclone_is_a_labelled_test_on_its_own_historical_date(client):
    body = client.get("/api/cyclones/archived-test").json()
    assert body["state"] == "HISTORICAL_TEST_EVENT"
    assert body["label"] == "HISTORICAL / TEST EVENT"
    assert body["labels"]["track"].startswith("HISTORICAL / TEST EVENT")
    assert "JTWC" in body["labels"]["track"] and "IMD" not in body["labels"]["track"]
    assert body["thermal_field"]["valid_date"] == "2023-05-12"
    assert body["analysis"]["summary"]["n_samples"] > 0


def test_current_cyclones_report_no_active_storm_from_recorded_source(client, monkeypatch, tmp_path):
    from oceanembed.cyclones import gdacs
    east_pacific = json.loads((FIX / "mocha_geometry_ep6.json").read_text(encoding="utf-8"))
    for f in east_pacific["features"]:
        if f["geometry"]["type"] == "Polygon":
            f["geometry"]["coordinates"] = [[[c[0] - 220.0, c[1]] for c in ring]
                                            for ring in f["geometry"]["coordinates"]]
    current = json.loads((FIX / "current_events4app.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(gdacs, "fetch_json",
                        lambda url, timeout=0: current if "EVENTS4APP" in url else east_pacific)
    monkeypatch.setattr(gdacs, "CACHE_FILE", tmp_path / "cache.json")
    body = client.get("/api/cyclones/current").json()
    assert body["state"] == "NO_ACTIVE_NORTH_INDIAN_CYCLONE"
    analysis = client.get("/api/cyclones/current/thermal-analysis").json()
    assert analysis["analysis"] is None and analysis["advisory"] is None


def test_scenario_is_badged_not_a_forecast_and_deterministic(client):
    body = {"field": "historical", "date": "2023-05-13",
            "points": [{"lat": 12, "lon": 86}, {"lat": 17, "lon": 90}]}
    first = client.post("/api/scenario/analysis", json=body).json()
    second = client.post("/api/scenario/analysis", json=body).json()
    assert first["badge"] == "USER-DRAWN SCENARIO - NOT AN OFFICIAL FORECAST"
    assert "not an observed or forecast track" in first["labels"]["path"]
    assert first["analysis"]["summary"] == second["analysis"]["summary"]
    assert "track" not in first["labels"]
    assert client.post("/api/scenario/analysis", json={**body, "points": []}).status_code == 422
    assert client.post("/api/scenario/analysis", json={**body, "field": "forecast"}).status_code == 422


def test_frozen_hashes_unchanged_through_the_new_paths(client):
    from oceanembed.replay import api as replay_api
    engine = replay_api.engine()
    assert engine.l2_state_dict_sha256 == L2
    assert engine.l2_encoder_sha256 == ENCODER
