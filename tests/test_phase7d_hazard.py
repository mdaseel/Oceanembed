"""Phase 7D guards — historical event replay and Ocean Hazard Indicators.

The risks these target: a hazard label appearing where no diagnostic or no water
column supports it; thresholds drifting from the pre-registered rule or being
re-derived on the event; a numeric cyclone probability appearing anywhere; the
event strip being presented as a temporal forecast; NRT/live code creeping in;
and the frozen Phase 7C artifacts being disturbed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import (D26Status, PhysicalSupport,  # noqa: E402
                                    ThermalResult, d26_tchp, local_water_depth,
                                    qualify)
from oceanembed.diagnostics.hazard import (INDICATOR_NAME,  # noqa: E402
                                           NON_PREDICTION_STATEMENT,
                                           HazardThresholds, ThermalSupport,
                                           categorize, explain, load_thresholds,
                                           not_categorized_reason)

EVENT_SELECTION = ROOT / "outputs" / "phase7" / "EVENT_SELECTION.md"
PROTOCOL = ROOT / "outputs" / "phase7" / "HAZARD_INDICATOR_PROTOCOL.md"
THRESHOLDS = ROOT / "outputs" / "phase7" / "HAZARD_THRESHOLDS.json"
TRACK = ROOT / "web" / "public" / "assets" / "event" / "track.json"

T = HazardThresholds(p50=50.0, p75=80.0, p90=100.0,
                     reference_period="test", n_dates=1, n_samples=1)


def cells(tchp, status, physical):
    return (np.array(tchp, dtype="float64"),
            np.array(status, dtype="int8"),
            np.array(physical, dtype="int8"))


# ------------------------------------------------------- pre-registration
class TestPreRegistration:
    def test_event_selected_before_any_event_output(self):
        assert EVENT_SELECTION.exists()
        text = EVENT_SELECTION.read_text(encoding="utf-8")
        assert "MOCHA" in text
        assert "2023-05-05" in text and "2023-05-22" in text
        # The rule must be external and must not mention model performance.
        assert "IMD" in text and "IBTrACS" in text
        for forbidden in ("low model error", "best skill", "lowest RMSE"):
            assert forbidden not in text.lower()

    def test_indicator_protocol_fixes_the_rule(self):
        assert PROTOCOL.exists()
        text = PROTOCOL.read_text(encoding="utf-8")
        for required in ("TRAIN", "p50", "p75", "p90", "NOT CATEGORIZED",
                         "does not predict", "2024 Argo remains PROTECTED"):
            assert required in text, f"protocol does not record {required!r}"

    def test_frozen_part_of_protocol_contains_no_computed_threshold_numbers(self):
        """The rule was frozen before the numbers existed; it must stay that way.

        Scoped to the text ABOVE any post-freeze correction section. A dated
        correction may legitimately quote the boundaries in order to state that
        they are unchanged; the claim being pinned is that the pre-registration
        itself was not written backwards from results.
        """
        text = PROTOCOL.read_text(encoding="utf-8")
        frozen_part = text.split("## Post-freeze corrections")[0]
        assert len(frozen_part) > 3000, "the frozen pre-registration went missing"
        frozen = json.loads(THRESHOLDS.read_text(encoding="utf-8"))["boundaries"]
        for value in frozen.values():
            assert f"{value:.2f}" not in frozen_part, (
                "a derived boundary was written back into the pre-registration")

    def test_post_freeze_corrections_change_no_rule(self):
        """Corrections may fix wording; they may never move a boundary."""
        text = PROTOCOL.read_text(encoding="utf-8")
        if "## Post-freeze corrections" not in text:
            pytest.skip("no corrections recorded")
        note = text.split("## Post-freeze corrections")[1]
        assert "No rule, population, boundary, quantity or" in note
        # The served thresholds must still be the originally derived ones.
        record = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        t = load_thresholds()
        assert t.p50 == record["boundaries"]["p50"]
        assert t.p75 == record["boundaries"]["p75"]
        assert t.p90 == record["boundaries"]["p90"]

    def test_conventions_are_not_conflated_in_the_event_record(self):
        """Wind figures must always carry their averaging period."""
        text = EVENT_SELECTION.read_text(encoding="utf-8")
        assert "3-minute" in text
        # If a 1-minute figure appears it must be labelled as such, and no
        # Saffir-Simpson category label may be applied to this basin's record.
        if "145 kt" in text:
            assert "1-minute" in text
        frozen_part = text.split("## Post-freeze correction")[0]
        note = text.split("## Post-freeze correction")[-1]
        if "Category-5" in frozen_part:
            assert "Category-5" in note, (
                "an unlabelled category claim must carry a correction")

    def test_thresholds_came_from_the_train_split_only(self):
        record = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        assert "2015-01-01" in record["reference_period"]
        assert "2020-12-31" in record["reference_period"]
        assert "TRAIN" in record["reference_period"]
        # Not one test-split date may contribute.
        assert "2022" not in record["reference_period"]
        assert record["failed_dates"] == []
        assert record["n_samples"] > 1_000_000
        assert record["argo_used"] is False

    def test_literature_anchor_is_disclosure_only(self):
        record = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        anchor = record["literature_anchor"]
        assert anchor["value_kj_cm2"] == 50.0
        assert "DISCLOSURE ONLY" in anchor["role"]
        assert 0.0 <= anchor["percentile_of_this_distribution"] <= 100.0

    def test_boundaries_are_ordered_and_loadable(self):
        t = load_thresholds()
        assert t.p50 < t.p75 < t.p90
        assert t.n_dates > 400


# ------------------------------------------------------- category logic
class TestCategorisation:
    def test_boundaries_are_inclusive_upward(self):
        tchp, status, phys = cells(
            [49.9, 50.0, 79.9, 80.0, 99.9, 100.0],
            [D26Status.OK] * 6, [PhysicalSupport.SUPPORTED] * 6)
        got = [ThermalSupport(int(c)) for c in categorize(tchp, status, phys, T)]
        assert got == [ThermalSupport.LOW, ThermalSupport.MODERATE,
                       ThermalSupport.MODERATE, ThermalSupport.ELEVATED,
                       ThermalSupport.ELEVATED, ThermalSupport.HIGH]

    def test_below_seafloor_is_never_categorised(self):
        tchp, status, phys = cells(
            [95.0], [D26Status.OK],
            [PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT])
        assert ThermalSupport(int(categorize(tchp, status, phys, T)[0])) is \
            ThermalSupport.NOT_CATEGORIZED

    def test_unverified_bathymetry_is_never_categorised(self):
        tchp, status, phys = cells([95.0], [D26Status.OK],
                                   [PhysicalSupport.UNVERIFIED])
        assert ThermalSupport(int(categorize(tchp, status, phys, T)[0])) is \
            ThermalSupport.NOT_CATEGORIZED

    def test_invalid_diagnostics_are_never_categorised(self):
        for st in (D26Status.NO_CROSSING_IN_SUPPORT,
                   D26Status.INSUFFICIENT_SUPPORT, D26Status.NO_VALID_LEVELS):
            tchp, status, phys = cells([np.nan], [st],
                                       [PhysicalSupport.NOT_APPLICABLE])
            assert ThermalSupport(int(categorize(tchp, status, phys, T)[0])) is \
                ThermalSupport.NOT_CATEGORIZED

    def test_surface_below_26_is_categorised_low_not_withheld(self):
        """TCHP = 0 exactly is a real answer: zero heat is the least support."""
        tchp, status, phys = cells([0.0], [D26Status.SURFACE_BELOW_26],
                                   [PhysicalSupport.SUPPORTED])
        assert ThermalSupport(int(categorize(tchp, status, phys, T)[0])) is \
            ThermalSupport.LOW

    def test_missing_thresholds_yield_no_labels_at_all(self):
        tchp, status, phys = cells([95.0], [D26Status.OK],
                                   [PhysicalSupport.SUPPORTED])
        assert ThermalSupport(int(categorize(tchp, status, phys, None)[0])) is \
            ThermalSupport.NOT_CATEGORIZED

    def test_reasons_stay_distinct(self):
        assert "no water column" in not_categorized_reason(
            D26Status.OK, PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT)
        assert "unverified" in not_categorized_reason(
            D26Status.OK, PhysicalSupport.UNVERIFIED)
        assert "diagnostic unavailable" in not_categorized_reason(
            D26Status.NO_VALID_LEVELS, PhysicalSupport.NOT_APPLICABLE)
        assert "thresholds unavailable" in not_categorized_reason(
            D26Status.OK, PhysicalSupport.SUPPORTED, thresholds_available=False)

    def test_explanation_quotes_the_actual_boundary(self):
        assert "80.0" in explain(85.0, T)
        assert "100.0" in explain(85.0, T)
        assert "below" in explain(10.0, T)

    def test_module_produces_no_probability_and_only_forbids_one(self):
        """The word may appear only inside the sentence that rules it out."""
        import oceanembed.diagnostics.hazard as h
        source = Path(h.__file__).read_text(encoding="utf-8").lower()
        # No identifier, field or computation named after one.
        for banned in ("def probability", "probability =", '"probability"',
                       "'probability'", "% chance", "forecast"):
            assert banned not in source, f"{banned!r} must not appear"
        # Every mention is a negation.
        for line in source.splitlines():
            if "probability" in line:
                assert "no numeric cyclone probability" in line, (
                    f"unqualified mention of probability: {line.strip()!r}")
        assert "does not predict" in NON_PREDICTION_STATEMENT.lower()
        assert INDICATOR_NAME == "Ocean Thermal Support for Cyclone Intensification"


# ------------------------------------------------------- track
class TestEventTrack:
    def test_bundled_track_matches_the_pre_registered_event(self):
        assert TRACK.exists(), "run scripts/poc/build_event_track.py"
        track = json.loads(TRACK.read_text(encoding="utf-8"))
        assert "Mocha" in track["event"]
        assert track["n_points"] > 20
        assert track["first_time"].startswith("2023-05")
        assert track["last_time"].startswith("2023-05")

    def test_track_intensity_matches_the_external_record(self):
        """Cross-check against the IMD values the selection document cites."""
        track = json.loads(TRACK.read_text(encoding="utf-8"))
        assert track["min_imd_pressure_hpa"] == 938.0
        # 115 kt ~ 213 km/h, the IMD peak quoted as 215 km/h.
        assert track["peak_imd_wind_kt"] >= 110

    def test_track_is_labelled_as_context_not_a_model_quantity(self):
        track = json.loads(TRACK.read_text(encoding="utf-8"))
        assert "not a model input" in track["role"]
        assert "IBTrACS" in track["dataset"]
        assert track["source_sha256"]
        assert "public domain" in track["licence"]

    def test_track_points_lie_inside_the_domain(self):
        track = json.loads(TRACK.read_text(encoding="utf-8"))
        for p in track["points"]:
            assert 5.0 <= p["lat"] <= 30.0 and 45.0 <= p["lon"] <= 105.0


# ------------------------------------------------------- real field
class TestOnRealField:
    @pytest.fixture(scope="class")
    def engine(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        yield e
        e.close()

    def test_event_dates_categorise_with_all_classes_present(self, engine):
        view = engine.replay_field("2023-05-13")   # peak intensity day
        res = d26_tchp(view.temperature, view.depths)
        _, tchp_phys = qualify(res, local_water_depth())
        category = categorize(res.tchp, res.status, tchp_phys, load_thresholds())
        counts = {c.name: int((category == c).sum()) for c in ThermalSupport}
        assert counts["HIGH"] > 0 and counts["LOW"] > 0
        assert counts["NOT_CATEGORIZED"] > 0
        # A category may never appear where the diagnostic could not be used.
        unusable = tchp_phys != PhysicalSupport.SUPPORTED
        assert (category[unusable] == ThermalSupport.NOT_CATEGORIZED).all()

    def test_category_is_a_pure_function_of_tchp_where_usable(self, engine):
        view = engine.replay_field("2023-05-13")
        res = d26_tchp(view.temperature, view.depths)
        _, tchp_phys = qualify(res, local_water_depth())
        t = load_thresholds()
        category = categorize(res.tchp, res.status, tchp_phys, t)
        usable = (tchp_phys == PhysicalSupport.SUPPORTED) & np.isfinite(res.tchp)
        expected = np.array([t.label_for(v) for v in res.tchp[usable]])
        np.testing.assert_array_equal(category[usable], expected)

    def test_every_window_date_is_available_and_independent(self, engine):
        """18 independent replays; no temporal state is carried between them."""
        dates = pd.date_range("2023-05-05", "2023-05-22", freq="D")
        assert len(dates) == 18
        first = engine.replay_field(dates[0])
        again = engine.replay_field(dates[0])
        np.testing.assert_array_equal(first.temperature, again.temperature)
        last = engine.replay_field(dates[-1])
        assert not np.array_equal(first.temperature, last.temperature)


# ------------------------------------------------------- transport
class TestTransport:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from oceanembed.poc import app as poc
        from oceanembed.replay import api
        from oceanembed.replay.engine import ReplayEngine
        api._engine = ReplayEngine(use_cache=False)
        with TestClient(poc.app) as c:
            yield c

    def test_hazard_block_served_with_the_field(self, client):
        payload = client.get("/api/replay/view",
                             params={"date": "2023-05-13"}).json()
        h = payload["hazard"]
        assert h["available"] is True
        assert h["indicator"] == INDICATOR_NAME
        assert len(h["category"]) == 101 and len(h["category"][0]) == 241
        assert h["thresholds"]["p50"] < h["thresholds"]["p75"]
        assert "does not predict" in h["non_prediction_statement"]
        assert "not distinguishable" in h["uncertainty_note"]
        assert "No numeric cyclone probability" in h["scope_note"]

    def test_served_categories_equal_the_backend_module(self, client):
        from oceanembed.replay import api
        payload = client.get("/api/replay/view",
                             params={"date": "2023-05-13"}).json()
        view = api.engine().replay_field("2023-05-13")
        res = d26_tchp(view.temperature, view.depths)
        _, tchp_phys = qualify(res, local_water_depth())
        expected = categorize(res.tchp, res.status, tchp_phys, load_thresholds())
        np.testing.assert_array_equal(np.array(payload["hazard"]["category"]),
                                      expected)

    def test_event_endpoint_reports_the_pre_registered_window(self, client):
        e = client.get("/api/event").json()
        assert e["window_start"] == "2023-05-05" and e["window_end"] == "2023-05-22"
        assert "Mocha" in e["name"]
        assert e["track_available"] is True
        assert "independent replay_field" in e["independence_note"]
        assert "did not predict" in e["claim_note"]
        assert len(e["segments"]) == 5

    def test_event_series_is_a_strip_of_independent_reconstructions(self, client):
        r = client.get("/api/event/series")
        assert r.status_code == 200
        body = r.json()
        assert len(body["series"]) == 18
        assert body["series"][0]["date"] == "2023-05-05"
        assert body["series"][-1]["date"] == "2023-05-22"
        assert "never enters inference" in body["corridor_note"]
        assert "independent replay_field" in body["independence_note"]
        for row in body["series"]:
            assert row["n_cells"] > 0
            assert row["tchp_kj_cm2"] is not None

    def test_no_probability_value_is_ever_served(self, client):
        """No key and no value may carry one; the only mention is the refusal."""
        payload = client.get("/api/replay/view",
                             params={"date": "2023-05-13"}).json()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert "probab" not in key.lower(), f"key {key!r}"
                    assert "chance" not in key.lower(), f"key {key!r}"
                    walk(value)
            elif isinstance(node, list):
                for item in node[:4]:      # arrays are homogeneous numerics
                    walk(item)
            elif isinstance(node, str) and "probability" in node.lower():
                assert "no numeric cyclone probability" in node.lower(), (
                    f"unqualified probability text served: {node!r}")

        walk(payload)


# ------------------------------------------------------- discipline
class TestDiscipline:
    def test_no_nrt_reaches_the_hazard_or_event_path(self):
        """The indicator and the event replay stay HISTORICAL.

        Phase-boundary note: this originally banned any NRT reference in
        `poc/app.py` too, which was correct while Phase 8A was unauthorised.
        Phase 8A was subsequently approved and adds telemetry endpoints to that
        module. The ban is therefore narrowed to what Phase 7D actually
        guarantees — that no live source reaches the hazard indicator or the
        event replay — and that guarantee is now checked at the function level
        rather than by the presence of a substring in a shared file.
        """
        for rel in ("src/oceanembed/diagnostics/hazard.py",
                    "src/oceanembed/diagnostics/thermal.py",
                    "scripts/poc/build_event_track.py"):
            source = (ROOT / rel).read_text(encoding="utf-8").lower()
            for banned in ("copernicusmarine", "earthaccess", "nrt", "telemetry"):
                assert banned not in source, f"{banned!r} in {rel}"

        app = (ROOT / "src/oceanembed/poc/app.py").read_text(encoding="utf-8")
        # The hazard block and the event series must not consume telemetry.
        for marker in ("def hazard_block(", "def event_series("):
            body = app.split(marker)[1].split("\n@app.")[0]
            for banned in ("telemetry", "nrt", "latest"):
                assert banned not in body.lower(), \
                    f"{banned!r} reached {marker.strip('def (')}"

    def test_only_the_build_script_touches_the_network(self):
        """The application must stay offline; only build time may fetch."""
        source = (ROOT / "src/oceanembed/poc/app.py").read_text(encoding="utf-8")
        for banned in ("urllib.request", "requests.get", "httpx.get"):
            assert banned not in source

    def test_no_argo_read_by_this_phase(self):
        for rel in ("src/oceanembed/diagnostics/hazard.py",
                    "scripts/diagnostics/build_hazard_thresholds.py",
                    "scripts/poc/build_event_track.py"):
            source = (ROOT / rel).read_text(encoding="utf-8").lower()
            assert "argo" not in source or "argo_used" in source
            assert "2024 argo" not in source

    def test_frozen_phase7c_artifacts_untouched(self):
        import pandas as pd
        m = pd.read_csv(ROOT / "outputs/tables/phase7c_d26_tchp_metrics.csv")
        nio = m[m.region == "whole_nio"].set_index(["quantity", "pair"])["mae"]
        assert round(float(nio[("d26", "B_vs_C")]), 2) == 9.24
        assert round(float(nio[("tchp", "B_vs_C")]), 2) == 11.47
        protocol = (ROOT / "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md"
                    ).read_text(encoding="utf-8")
        assert "hazard" not in protocol.lower()

    def test_frozen_model_hashes_unchanged(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            assert e.l2_state_dict_sha256 == \
                "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
            assert e.l2_encoder_sha256 == \
                "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"
        finally:
            e.close()
