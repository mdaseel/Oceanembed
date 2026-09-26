"""Ocean Thermal Hazard Intelligence dashboard — the scientific boundary.

The dashboard is a presentation layer over frozen science. The risks these
target: a threshold or basin copied into the frontend where it could drift; a
composite risk score, probability or danger-zone wording creeping in; a live or
forecast cyclone track fetched ad hoc; playback that interpolates frames or
fills missing days; a second map / 3D renderer; and any disturbance of the
frozen model, the Phase 8B decision or the 2024 Argo holdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

WEB = ROOT / "web" / "src"
DASHBOARD = [WEB / "components" / "Hazard.tsx",
             WEB / "field" / "hazardIntelligence.ts",
             *sorted((WEB / "components" / "hazard").glob("*.ts*")),
             # the workspace shell (Ocean State, Model Science, research panels) is
             # held to the same boundary as the hazard dashboard
             *sorted((WEB / "components" / "workspace").glob("*.ts*"))]
L2 = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
ENCODER = "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Strip comments so a rule stated in a comment is not mistaken for code."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def test_dashboard_files_exist():
    assert len(DASHBOARD) >= 10
    for path in DASHBOARD:
        assert path.is_file(), path


class TestNoNewScience:
    def test_basins_are_served_from_the_existing_definition(self):
        from oceanembed.ml.metrics import BASINS
        from oceanembed.poc import app as poc
        served = poc.basins()
        assert served["source"] == "oceanembed.ml.metrics.BASINS"
        assert served["basins"] == {k: {"lat": list(v["lat"]), "lon": list(v["lon"])}
                                    for k, v in BASINS.items()}

    def test_frontend_holds_no_threshold_or_basin_numbers(self):
        raw = json.loads((ROOT / "outputs/phase7/HAZARD_THRESHOLDS.json")
                         .read_text(encoding="utf-8"))["boundaries"]
        literals = {f"{v:.1f}" for v in raw.values()} | {f"{v:.2f}" for v in raw.values()}
        for path in DASHBOARD:
            text = code_only(source(path))
            for literal in literals:
                assert not re.search(rf"(?<![\d.]){re.escape(literal)}(?!\d)", text), \
                    (path.name, literal)
            # basin boxes arrive from /api/basins, never typed in
            assert not re.search(r"arabian_sea|bay_of_bengal", text), path.name

    def test_no_categorisation_in_the_frontend(self):
        for path in DASHBOARD:
            text = code_only(source(path))
            # a category is only ever READ from hazard.category
            assert not re.search(r"(>=|>)\s*t(hresholds)?\.p(50|75|90)", text), path.name

    def test_no_composite_risk_score_probability_or_danger_wording(self):
        for path in DASHBOARD:
            text = source(path)
            lower = text.lower()
            for banned in ("risk score", "riskscore", "danger zone", "cyclone-risk zone",
                           "cyclone risk zone", "evacuate", "landfall expected",
                           "will intensify", "marine heatwave detected"):
                assert banned not in lower, (path.name, banned)
            assert not re.search(r"\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)", lower)
            # no weighted formula over thermal quantities
            assert not re.search(r"\d?\.\d+\s*\*\s*\w*(tchp|anomaly|d26)", lower), path.name

    def test_no_recovery_category_is_invented(self):
        for path in DASHBOARD:
            text = source(path)
            for banned in ("NOT RECOVERED", "PARTIALLY RECOVERED", "NEAR PRE-EVENT STATE",
                           "FULLY RECOVERED"):
                assert banned not in text, (path.name, banned)


class TestNoLiveTrackAndNoInterpolation:
    def test_no_external_or_live_cyclone_track_source(self):
        for path in DASHBOARD:
            text = code_only(source(path))
            assert not re.search(r"https?://", text), path.name
            for banned in ("jtwc", "nhc.noaa", "rsmcnewdelhi", "mausam.imd", "imd.gov"):
                assert banned not in text.lower(), (path.name, banned)
            for call in re.findall(r"(?:getJson|fetch)\s*(?:<[^>]*>)?\(\s*[`\"']([^`\"']*)",
                                   text):
                assert call.startswith("/api/"), (path.name, call)

    def test_latest_mode_says_the_official_track_is_not_connected(self):
        text = source(WEB / "components" / "Hazard.tsx")
        assert "Official cyclone-track overlay: Not connected in this build" in text

    def test_playback_uses_real_dates_and_never_interpolates(self):
        for path in DASHBOARD:
            text = code_only(source(path)).lower()
            for banned in (r"interpolate\(", r"\blerp\(", r"\btween", r"\bffill\b",
                           r"carry_forward", r"fillmissing"):
                assert not re.search(banned, text), (path.name, banned)
        hazard = source(WEB / "components" / "Hazard.tsx")
        assert "eventDates(" in hazard and "loadReplay(" in hazard
        hook = source(WEB / "components" / "hazard" / "useNrtStates.ts")
        assert "/api/latest/qualified?date=" in hook
        assert "adaptReplay" in hook


class TestSharedRenderer:
    def test_dashboard_mounts_no_map_or_renderer_of_its_own(self):
        for path in DASHBOARD:
            text = code_only(source(path))
            for banned in ("<DepthRenderer", "<MapView", "<DiagnosticMap", "<Profile",
                           "from \"three\"", "WebGL"):
                assert banned not in text, (path.name, banned)

    def test_app_still_owns_exactly_one_map_renderer_and_profile(self):
        app = source(WEB / "App.tsx")
        assert app.count("<DepthRenderer") == 1
        assert app.count("<MapView") == 1
        assert app.count("<Profile") == 1
        assert "renderMapPanel={renderMapPanel}" in app


class TestFrozenState:
    def test_event_segmentation_is_the_pre_registered_one(self):
        from oceanembed.poc import app as poc
        assert [s["label"] for s in poc.EVENT["segments"]] == [
            "Pre-event", "Approach / intensification", "Event", "Wake", "Recovery"]
        assert poc.EVENT["window_start"] == "2023-05-05"
        assert poc.EVENT["window_end"] == "2023-05-22"

    def test_latest_d26_withheld_and_tchp_qualified(self):
        d = json.loads((ROOT / "outputs/phase8b/qualification_decision.json")
                       .read_text(encoding="utf-8"))
        assert d["d26_category"] == "NOT QUALIFIED"
        assert d["tchp_category"] == "QUALIFIED"
        assert d["l2_state_dict_sha256_after"] == L2
        assert d["l2_encoder_sha256_after"] == ENCODER

    def test_hazard_thresholds_untouched(self):
        raw = json.loads((ROOT / "outputs/phase7/HAZARD_THRESHOLDS.json")
                         .read_text(encoding="utf-8"))
        assert raw["reference_period"] == "2015-01-01..2020-12-31 (TRAIN split only)"
        b = raw["boundaries"]
        assert b["p50"] < b["p75"] < b["p90"]

    def test_2024_argo_untouched(self):
        mp = ROOT / "outputs" / "argo" / "matched_profiles.parquet"
        if not mp.exists():
            pytest.skip("Argo matches not present")
        dates = pd.to_datetime(pd.read_parquet(mp, columns=["date"])["date"])
        assert dates.max() < pd.Timestamp("2024-01-01")
