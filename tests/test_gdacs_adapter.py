"""GDACS external cyclone context — parsing and states from recorded responses.

No test here touches the internet. Risks: forecast positions shown as observed;
latitude/longitude swapped; wind or pressure invented; an archived storm shown as
live; an outage hidden; GDACS/JTWC geometry labelled as an IMD official track.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.cyclones import gdacs as G  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "gdacs"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def event(eventdata, episode):
    p = load(eventdata)["properties"]
    return {"eventid": p["eventid"], "episodeid": episode, "name": p["eventname"],
            "source": p["source"]}


def parse(eventdata, geometry, episode):
    return G.parse_geometry(load(geometry), event(eventdata, episode), "recorded", G.LIVE)


def test_observed_and_forecast_positions_follow_the_advisory_time():
    adv = parse("mocha_eventdata.json", "mocha_geometry_ep6.json", 6)
    assert adv.advisory_issued_at == "2023-05-12T06:00:00Z"
    assert len(adv.observed_points) == 6 and len(adv.forecast_points) == 5
    assert all(p.valid_time <= adv.advisory_issued_at for p in adv.observed_points)
    assert all(p.valid_time > adv.advisory_issued_at for p in adv.forecast_points)
    assert adv.forecast_flag_disagreements == []   # GDACS segment flags agree


@pytest.mark.parametrize("geometry,episode,forecast", [
    ("mocha_geometry_ep15.json", 15, 2), ("biparjoy_geometry_ep12.json", 12, 7)])
def test_other_episodes_parse_with_their_own_forecast_counts(geometry, episode, forecast):
    data = "mocha_eventdata.json" if "mocha" in geometry else "biparjoy_eventdata.json"
    adv = parse(data, geometry, episode)
    assert len(adv.forecast_points) == forecast
    times = [p.valid_time for p in adv.points]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_coordinates_are_latitude_longitude_not_swapped():
    adv = parse("mocha_eventdata.json", "mocha_geometry_ep6.json", 6)
    first = adv.observed_points[0]
    assert (first.valid_time, first.lat, first.lon) == ("2023-05-11T00:00:00Z", 11.1, 88.2)
    assert all(0 < p.lat < 35 and 60 < p.lon < 100 for p in adv.points)


def test_missing_fields_are_never_fabricated():
    adv = parse("mocha_eventdata.json", "mocha_geometry_ep6.json", 6)
    assert all(p.wind_kt is None and p.pressure_hpa is None for p in adv.points)


def test_provenance_names_gdacs_and_its_source_never_imd():
    adv = parse("biparjoy_eventdata.json", "biparjoy_geometry_ep12.json", 12)
    assert adv.track_source == "JTWC"
    assert "GDACS" in adv.provenance_label and "JTWC" in adv.provenance_label
    assert "IMD" not in adv.provenance_label and "official" not in adv.provenance_label.lower()
    assert "not connected" in G.IMD_STATUS


def test_malformed_responses_are_refused_not_guessed():
    with pytest.raises(G.GdacsParseError):
        G.parse_event_list({"type": "FeatureCollection"})
    with pytest.raises(G.GdacsParseError):
        G.parse_geometry({"features": []}, event("mocha_eventdata.json", 6), "x")


def test_no_active_north_indian_cyclone_is_reported_as_such(tmp_path):
    def fetch(url):
        if "EVENTS4APP" in url:
            return load("current_events4app.json")
        pytest.fail("a non-North-Indian current storm still needs its geometry checked")

    def fetch_with_geometry(url):
        if "EVENTS4APP" in url:
            return load("current_events4app.json")
        # NORBERT-26 geometry is not recorded; stand in with an East Pacific shape.
        g = load("mocha_geometry_ep6.json")
        for f in g["features"]:
            geom = f["geometry"]
            if geom["type"] == "Polygon":
                geom["coordinates"] = [[[c[0] - 220.0, c[1]] for c in ring]
                                       for ring in geom["coordinates"]]
        return g

    result = G.current_cyclones(fetch=fetch_with_geometry, cache_path=tmp_path / "c.json",
                                now=lambda: "2026-09-14T00:00:00+00:00")
    assert result["state"] == G.NONE_ACTIVE
    assert result["advisories"] == []
    assert result["current_outside_north_indian"] == ["NORBERT-26"]
    assert "No active North Indian Ocean cyclone" in result["message"]


def test_live_multi_date_wind_buffers_do_not_break_the_advisory_time(tmp_path):
    """Recorded during the controlled live check on 2026-09-14: NORBERT-26 ep16.

    Its wind-buffer polygons carry one polygondate per forecast time, which once
    turned a healthy source into SOURCE_UNAVAILABLE. The advisory time is the
    track features' single polygondate.
    """
    geometry = load("norbert_geometry_ep16_live.json")
    buffer_dates = {f["properties"]["polygondate"] for f in geometry["features"]
                    if f["properties"].get("Class") in ("Poly_Green", "Poly_Orange", "Poly_Red")}
    assert len(buffer_dates) > 1
    adv = G.parse_geometry(geometry, {"eventid": 1001320, "episodeid": 16, "name": "NORBERT-26",
                                      "source": "NOAA"}, "recorded", G.LIVE)
    assert adv.advisory_issued_at == "2026-09-13T15:00:00Z"
    assert adv.observed_points and adv.forecast_points
    assert all(p.valid_time <= adv.advisory_issued_at for p in adv.observed_points)
    assert not G.is_north_indian(adv)

    def fetch(url):
        return load("current_events4app_2026-09-14.json") if "EVENTS4APP" in url else geometry

    result = G.current_cyclones(fetch=fetch, cache_path=tmp_path / "c.json",
                                now=lambda: "2026-09-14T00:00:00+00:00")
    assert result["state"] == G.NONE_ACTIVE
    assert result["current_outside_north_indian"] == ["NORBERT-26"]
    assert "No active North Indian Ocean cyclone reported by connected source" in result["message"]


def test_an_active_north_indian_event_is_detected(tmp_path):
    current = load("search_tc_2023-05.json")
    for f in current["features"]:
        f["properties"]["iscurrent"] = "true" if f["properties"]["eventname"] == "MOCHA-23" else "false"
        if f["properties"]["eventname"] == "MOCHA-23":
            f["properties"]["episodeid"] = 6

    def fetch(url):
        if "EVENTS4APP" in url:
            return current
        assert "eventid=1000970&episodeid=6" in url
        return load("mocha_geometry_ep6.json")

    result = G.current_cyclones(fetch=fetch, cache_path=tmp_path / "c.json",
                                now=lambda: "2023-05-12T07:00:00+00:00")
    assert result["state"] == G.ACTIVE
    assert result["advisories"][0]["storm_name"] == "MOCHA-23"
    assert result["advisories"][0]["status"] == G.LIVE


def test_an_outage_uses_the_cache_only_as_not_current(tmp_path):
    cache = tmp_path / "c.json"
    current = load("search_tc_2023-05.json")
    for f in current["features"]:
        f["properties"]["iscurrent"] = "true" if f["properties"]["eventname"] == "MOCHA-23" else "false"
        f["properties"]["episodeid"] = 6
    G.current_cyclones(fetch=lambda u: current if "EVENTS4APP" in u else load("mocha_geometry_ep6.json"),
                       cache_path=cache, now=lambda: "2023-05-12T07:00:00+00:00")

    def down(url):
        raise OSError("network unreachable")

    result = G.current_cyclones(fetch=down, cache_path=cache, now=lambda: "2023-05-13T07:00:00+00:00")
    assert result["state"] == G.CACHED_STATE and result["cached"] is True
    assert result["retrieved_at"] == "2023-05-12T07:00:00+00:00"
    assert "not current" in result["message"]
    assert all(a["status"] == G.CACHED for a in result["advisories"])

    fresh = G.current_cyclones(fetch=down, cache_path=tmp_path / "none.json")
    assert fresh["state"] == G.UNAVAILABLE
    assert fresh["message"] == "Cyclone advisory source currently unavailable."


def test_the_archived_event_is_always_labelled_as_a_test():
    payload = G.archived_test_advisory()
    assert payload["state"] == G.TEST
    assert payload["label"] == "HISTORICAL / TEST EVENT"
    assert payload["advisories"][0]["status"] == G.TEST
    assert "not a current advisory" in payload["note"]
