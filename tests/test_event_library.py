"""Historical cyclone event library — the rule, the assets and the frozen Mocha.

Risks: a new event's window tuned after seeing output; Mocha's frozen evidence
overwritten for consistency; an in-sample event presented as out-of-sample; an
unavailable event enabled; the library reaching the network or the model.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.events import library as L  # noqa: E402
from oceanembed.events import rule as R  # noqa: E402

ASSETS = ROOT / "web" / "public" / "assets" / "events"
FROZEN_TRACK = ROOT / "web" / "public" / "assets" / "event" / "track.json"
IBTRACS = ROOT / "data" / "raw" / "ibtracs" / "ibtracs.NI.list.v04r01.csv"


def fix(time, wind=None, pres=None, land=500.0, lat=15.0, lon=88.0):
    return {"time": time, "lat": lat, "lon": lon, "imd_wind_kt": wind,
            "imd_pressure_hpa": pres, "usa_wind_kt": None, "nature": "TS",
            "dist2land_km": land}


def asset(event_id):
    return json.loads((ASSETS / f"{event_id}.json").read_text(encoding="utf-8"))


class TestRule:
    def test_rule_reproduces_the_frozen_mocha_window_from_ibtracs(self):
        if not IBTRACS.is_file():
            pytest.skip("local IBTrACS copy not present")
        from oceanembed.poc.app import EVENT
        reader = csv.DictReader(io.StringIO(IBTRACS.read_text(encoding="utf-8", errors="replace")))
        next(reader)
        rows = [r for r in reader if r["NAME"].strip() == "MOCHA" and r["SEASON"].strip() == "2023"]
        chron = R.chronology(R.fixes_from_rows(rows))
        assert (chron.window_start, chron.window_end) == (EVENT["window_start"], EVENT["window_end"])
        assert (chron.peak, chron.landfall) == (EVENT["peak"], EVENT["landfall"])
        assert list(chron.segments) == EVENT["segments"]

    def test_every_new_event_window_follows_the_rule_from_its_own_track(self):
        for event_id in L.load_index()["events"]:
            a = asset(event_id)
            if a["frozen"]:
                continue
            chron = R.chronology(a["track"]["points"])
            assert (a["replay_start"], a["replay_end"]) == (chron.window_start, chron.window_end)
            assert a["segments"] == list(chron.segments)
            assert (a["peak"], a["landfall"], a["formation"]) == \
                (chron.peak, chron.landfall, chron.formation)

    def test_storms_the_rule_cannot_window_are_excluded(self):
        with pytest.raises(R.RuleExclusion, match="IMD"):
            R.chronology([fix("2023-05-10 00:00:00")])
        with pytest.raises(R.RuleExclusion, match="landfall"):
            R.chronology([fix("2023-05-10 00:00:00", 40), fix("2023-05-11 00:00:00", 60)])
        with pytest.raises(R.RuleExclusion, match="after the landfall"):
            R.chronology([fix("2023-05-10 00:00:00", 40, land=0),
                          fix("2023-05-12 00:00:00", 90, land=0)])

    def test_peak_ties_prefer_lower_pressure_then_the_earliest_fix(self):
        fixes = [fix("2023-05-10 00:00:00", 40), fix("2023-05-11 00:00:00", 90, 960),
                 fix("2023-05-12 00:00:00", 90, 950), fix("2023-05-13 00:00:00", 90, 950),
                 fix("2023-05-14 00:00:00", 50, land=0)]
        assert R.peak_fix(fixes)["time"] == "2023-05-12 00:00:00"

    def test_split_labels_follow_the_frozen_splits(self):
        assert R.split_for("2019-04-22", "2019-05-11") == "train"
        assert R.split_for("2021-05-10", "2021-05-25") == "validation"
        assert R.split_for("2023-05-05", "2023-05-22") == "test"
        assert R.split_for("2020-12-20", "2021-01-05") == "mixed"


class TestAssets:
    def test_all_six_candidates_were_checked_and_reported(self):
        index = L.load_index()
        names = {(c["name"].upper(), str(c["season"])) for c in index["candidates"]}
        assert names == set(R.CANDIDATES)
        for c in index["candidates"]:
            assert c["enabled"] == (c["event_id"] in index["events"])
            assert c["enabled"] or c["exclusion_reasons"]
        assert len(index["events"]) >= 2  # more than one historical cyclone supported

    def test_enabled_events_have_a_complete_input_record(self):
        for event_id in L.load_index()["events"]:
            avail = asset(event_id)["availability"]
            assert avail["missing_dates"] == [] and avail["zero_input_dates"] == []
            assert avail["valid_cells_min"] > 0
            assert "no inference" in avail["checked"]

    def test_mocha_asset_is_the_frozen_evidence_unchanged(self):
        from oceanembed.poc.app import EVENT
        a = asset("mocha-2023")
        assert a["frozen"] is True
        assert a["segments"] == EVENT["segments"]
        assert (a["replay_start"], a["replay_end"]) == (EVENT["window_start"], EVENT["window_end"])
        assert a["track"] == json.loads(FROZEN_TRACK.read_text(encoding="utf-8"))
        assert "EVENT_SELECTION.md" in a["phase_rule"]

    def test_in_sample_events_say_so(self):
        for event_id in L.load_index()["events"]:
            e = L.get_event(event_id)
            assert e["in_sample"] == (e["split"] == "train")
            if e["in_sample"]:
                assert "IN-SAMPLE" in e["split_note"]
        assert L.get_event("mocha-2023")["split"] == "test"

    def test_tracks_are_ibtracs_with_imd_agency_values(self):
        for event_id in L.load_index()["events"]:
            track = L.get_event(event_id)["track"]
            assert track["dataset"].startswith("IBTrACS v04r01")
            assert "IMD / RSMC New Delhi" in track["agency"]
            assert "never used in inference" in track["role"]

    def test_manifest_checksums_match_the_bundled_assets(self):
        manifest = json.loads((ROOT / "outputs/events/event_library_manifest.json")
                              .read_text(encoding="utf-8"))
        for name, sha in manifest["assets"].items():
            assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == sha
        assert manifest["frozen_mocha_track_sha256"] == \
            hashlib.sha256(FROZEN_TRACK.read_bytes()).hexdigest()

    def test_unknown_event_is_not_served(self):
        with pytest.raises(L.EventNotFound):
            L.get_event("not-a-cyclone-2099")

    def test_library_modules_touch_no_network_and_no_model(self):
        for name in ("library.py", "rule.py", "series.py", "track_analysis.py"):
            text = (ROOT / "src/oceanembed/events" / name).read_text(encoding="utf-8")
            for banned in ("urllib", "requests", "httpx", "_infer(", "embed_field",
                           "forward_from_z", "import torch"):
                assert banned not in text, (name, banned)
