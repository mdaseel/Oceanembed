"""Phase 8B gate: the evidence the final report rests on exists and agrees.

These read artifacts, not source strings: the rehearsal record, the live-run
provenance, the decision and the generated manifest must all say the same thing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

P8B = ROOT / "outputs" / "phase8b"
L2 = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
ENC = "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"


def load(name):
    p = P8B / name
    if not p.is_file():
        pytest.skip(f"{name} not produced yet")
    return json.loads(p.read_text(encoding="utf-8"))


class TestResilience:
    REQUIRED = ["tested_at", "initial_latest_state_available", "failure_method",
                "historical_replay_available_during_failure",
                "historical_hazard_indicators_available_during_failure",
                "stale_snapshot_displayed", "stale_snapshot_label_visible",
                "unavailable_state_rendered", "recovery_without_restart",
                "complete_stack_requalified_after_recovery",
                "new_l2_inference_after_recovery", "partial_stack_inference_blocked",
                "result"]

    def test_every_field_the_master_prompt_names_is_recorded(self):
        r = load("operational_resilience_test.json")
        for k in self.REQUIRED:
            assert k in r, k

    def test_result_is_pass(self):
        assert load("operational_resilience_test.json")["result"] == "PASS"

    def test_partial_stack_never_inferred(self):
        assert load("operational_resilience_test.json")[
            "partial_stack_inference_blocked"] is True


class TestLiveRun:
    def test_a_real_complete_stack_was_qualified(self):
        live = load("latest_live_run.json")
        assert live["state"] == "LATEST_QUALIFIED"
        assert len(live["sources"]) == 5
        chans = {c for s in live["sources"] for c in s["channels"]}
        assert chans == {"sst", "sss", "sla", "current_u", "current_v", "wind_u", "wind_v"}
        for s in live["sources"]:
            assert s["state"] == "OK"
            assert s["product_valid_time"].startswith(live["effective_date"])
            assert s["local_retrieval_time"] != s["product_valid_time"]
            assert s["age_hours"] > 0

    def test_live_run_used_the_frozen_model_and_withheld_d26(self):
        live = load("latest_live_run.json")
        assert live["l2_state_dict_sha256"] == L2
        assert live["l2_encoder_sha256"] == ENC
        assert live["diagnostics_withheld"] == ["d26"]
        assert live["argo_opened"] is False


class TestManifest:
    def test_manifest_agrees_with_the_decision(self):
        m = load("FINAL_NRT_OPERATING_MANIFEST.json")
        d = load("qualification_decision.json")
        s = m["status"]
        assert s["latest_15_depth_reconstruction"] == d["temperature_category"]
        assert s["latest_d26"] == d["d26_category"]
        assert s["latest_tchp"] == d["tchp_category"]
        assert s["latest_ocean_hazard_indicators"] == d["latest_hazard_indicators"]
        assert s["frozen_l2_preserved"] is True
        assert s["argo_2024"] == "PROTECTED"
        assert m["persistence_envelope_days"] == 0

    def test_hashed_artifacts_still_match(self):
        import hashlib
        m = load("FINAL_NRT_OPERATING_MANIFEST.json")
        for rel, want in m["artifacts"].items():
            if rel.endswith(("FINAL_NRT_OPERATING_MANIFEST.json",)):
                continue
            got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            assert got == want, rel


class TestSharedRenderer:
    def test_no_new_3d_module_since_the_phase7_freeze(self):
        """The shared renderer is a module family (DepthRenderer plus its prism,
        probe, frame, terrain and material helpers). Reuse means that family is
        exactly what it was at the Phase 7 source freeze - no module that talks
        to three.js was added for the latest mode."""
        import subprocess

        def three_users(listing: str) -> set[str]:
            return {line.split(":", 1)[-1] for line in listing.splitlines()
                    if line and "/test/" not in line}
        frozen = subprocess.run(
            ["git", "grep", "-l", "-E", "from ['\"]three", "9fb32ba", "--", "web/src"],
            cwd=ROOT, capture_output=True, text=True).stdout
        now = {str(p.relative_to(ROOT)).replace("\\", "/")
               for p in (ROOT / "web/src").rglob("*.ts*")
               if "test" not in p.parts
               and re.search(r"from ['\"]three", p.read_text(encoding="utf-8"))}
        assert three_users(frozen), "could not read the freeze commit"
        assert now == three_users(frozen), now ^ three_users(frozen)

    def test_latest_tab_imports_no_renderer_of_its_own(self):
        src = (ROOT / "web/src/components/LatestQualified.tsx").read_text(encoding="utf-8")
        for banned in ("three", "DepthRenderer", "MapView", "canvas", "WebGL"):
            assert banned not in src, banned
        assert "adaptReplay" in src     # the same adapter as Historical Replay

    def test_app_mounts_the_renderer_once_for_both_sources(self):
        app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
        assert app.count("<DepthRenderer") == 1
        assert app.count("<MapView") == 1


class TestHoldout:
    def test_2024_argo_still_untouched(self):
        mp = ROOT / "outputs" / "argo" / "matched_profiles.parquet"
        if not mp.exists():
            pytest.skip("Argo matches not present")
        dates = pd.to_datetime(pd.read_parquet(mp, columns=["date"])["date"])
        assert dates.max() < pd.Timestamp("2024-01-01")
        d = load("qualification_decision.json")
        assert d["argo_opened"] is False
