"""Coastal context, validation context, integrity, stress test and endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.science import coastal, integrity, stress_test  # noqa: E402
from oceanembed.science import validation_context as vc  # noqa: E402

needs_coastal = pytest.mark.skipif(not (coastal.ARTIFACT_DIR / "meta.json").exists(),
                                   reason="coastal artefact not built")


def test_haversine_known_distance():
    assert abs(coastal.haversine_km(0, 0, 0, 1) - 111.195) < 0.01


@needs_coastal
@pytest.mark.parametrize("lat,lon,state,country", [
    (19.5, 86.5, "Odisha", "India"), (13.0, 80.75, "Tamil Nadu", "India"),
    (9.5, 75.75, "Kerala", "India"), (21.0, 90.0, None, "Bangladesh")])
def test_nearest_coast_state_and_distance(lat, lon, state, country):
    c = coastal.lookup(lat, lon)
    assert c["status"] == "OK" and c["country"] == country
    if state:
        assert c["coastal_state"] == state
    assert 0 < c["offshore_distance_km"] < 300
    assert abs(coastal.haversine_km(c["grid_lat"], c["grid_lon"], c["nearest_coast_lat"],
                                    c["nearest_coast_lon"]) - c["offshore_distance_km"]) < 2


@needs_coastal
def test_district_only_for_indian_coasts_and_land_refused():
    assert coastal.lookup(19.5, 86.5)["coastal_district"] == "Puri"
    assert coastal.lookup(21.0, 90.0)["coastal_district"] is None
    assert coastal.lookup(12.0, 93.0)["status"] == "LAND_OR_NO_OCEAN_CELL"
    assert coastal.lookup(40.0, 60.0)["status"] == "OUTSIDE_DOMAIN"


@needs_coastal
def test_source_version_license_and_no_risk_wording():
    meta = coastal.provenance()
    names = [s["name"] for s in meta["sources"]]
    assert any("Natural Earth" in n for n in names) and any("geoBoundaries" in n for n in names)
    assert all(s.get("sha256") and s.get("license") and s.get("version") for s in meta["sources"])
    text = (coastal.WORDING + json.dumps(coastal.lookup(19.5, 86.5))).lower()
    assert "does not predict coastal damage" in text
    for banned in ("at risk", "risk score", "danger", "damage expected"):
        assert banned not in text


def test_validation_context_is_never_an_uncertainty_interval():
    c = vc.context(100, 15.25, 87.75)
    assert c["depth_m"] == 100 and c["models"]["L2"]["n"] > 0
    assert "not a calibrated uncertainty interval" in c["wording"]
    assert "95%" not in json.dumps(c) and "±" not in json.dumps(c)
    assert "2024 protected" in c["period"]


def test_integrity_checks_are_computed():
    from oceanembed.replay.engine import ReplayEngine
    out = integrity.checks(ReplayEngine())
    states = {i["label"]: i["state"] for i in out["items"]}
    assert states["Frozen L2 model"] == "VERIFIED"
    assert states["Encoder hash"] == "VERIFIED"
    assert states["2024 Argo holdout"] == "PROTECTED"
    assert states["Latest D26"] == "WITHHELD"
    assert states["Target leakage guards"] == "PASS"
    assert [p["stage"] for p in out["pipeline"]][0] == "Historical training"


def test_stress_test_label_and_geometry_identity():
    assert stress_test.LABEL == "REPLAYED HISTORICAL GEOMETRY — NOT A FORECAST OR PREDICTION"
    pts = [{"lat": 10.0, "lon": 88.0}, {"lat": 12.0, "lon": 89.0}]
    assert stress_test.same_geometry(pts, [dict(p) for p in pts])
    assert not stress_test.same_geometry(pts, [{"lat": 10.25, "lon": 88.0}, pts[1]])
    for word in ("will", "predict intensity", "recur."):
        assert word not in stress_test.LABEL.lower()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from oceanembed.poc.app import app
    with TestClient(app) as c:
        yield c


def test_stress_test_endpoint_keeps_the_observed_geometry(client):
    from oceanembed.events import library
    ev = library.get_event("mocha-2023")
    r = client.get("/api/events/mocha-2023/stress-test")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == stress_test.LABEL
    assert body["geometry"]["translated"] is False and body["geometry"]["retimed"] is False
    assert [(p["lat"], p["lon"]) for p in body["geometry"]["points"]] == \
        [(p["lat"], p["lon"]) for p in ev["track"]["points"]]
    assert body["historical"]["date"] == ev["peak"]
    if body["latest"] is not None:
        hist = [(s["lat"], s["lon"]) for s in body["historical"]["analysis"]["samples"]]
        late = [(s["lat"], s["lon"]) for s in body["latest"]["analysis"]["samples"]]
        assert hist == late
        assert "d26" in body["latest"]["withheld"]
        again = client.get("/api/events/mocha-2023/stress-test").json()
        assert again["comparison"] == body["comparison"]
    text = json.dumps(body).lower()
    for banned in ("intensity forecast", "will intensify", "probability of"):
        assert banned not in text


def test_science_endpoints_answer(client):
    assert client.get("/api/science/channels").json()["n_channels"] == 7
    assert client.get("/api/science/integrity").status_code == 200
    v = client.get("/api/science/validation-context", params={"depth": 75, "lat": 15, "lon": 88})
    assert v.status_code == 200 and v.json()["depth_m"] == 75
    a = client.get("/api/science/attribution", params={"lat": 15.25, "lon": 87.75, "date": "2023-05-12"})
    assert a.status_code == 200 and len(a.json()["gross_share"]) == 15
    bad = client.get("/api/science/attribution", params={"lat": 15.25, "lon": 87.75})
    assert bad.status_code == 422
    rt = client.get("/api/science/retrained-ablation").json()
    assert set(rt["groups"]) == {"SST", "SSS", "SLA", "CURRENTS", "WINDS"}
