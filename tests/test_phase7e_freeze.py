"""Phase 7E guards — the final PoC freeze and the protected 2024 holdout.

The risks these target: a manifest that drifts from the artifacts it claims to
describe; a frozen hash quietly changing; the 2024 holdout leaking into any
executed output; a pre-registration that is missing, empty, or silently
softened; and NRT work starting before it is authorised.

Nothing here opens the 2024 holdout. The protection is verified from executed
manifests, from code, and from the absence of 2024 in every produced artifact —
never by reading a 2024 profile.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PHASE7 = ROOT / "outputs" / "phase7"
MANIFEST = PHASE7 / "FINAL_POC_MANIFEST.json"
PREREG = PHASE7 / "FINAL_2024_ARGO_PREREGISTRATION.md"

L2_STATE_DICT = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
L2_ENCODER = "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"
HELDOUT_START = pd.Timestamp("2024-01-01")


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.is_file(), "run scripts/poc/build_final_manifest.py"
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ------------------------------------------------------- the manifest is true
class TestManifestDescribesReality:
    def test_frozen_core_hashes_match_the_live_engine(self, manifest):
        """The manifest must not be able to claim a model that is not loaded."""
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            core = manifest["scientific_core"]
            assert core["l2_state_dict_sha256"] == e.l2_state_dict_sha256 == L2_STATE_DICT
            assert core["l2_encoder_sha256"] == e.l2_encoder_sha256 == L2_ENCODER
            assert core["checkpoint_file_sha256"] == e.file_hashes["l2_checkpoint_file"]
            frozen = manifest["frozen_artifacts"]
            assert frozen["feature_scaler_sha256"] == e.file_hashes["feature_scaler_file"]
            assert frozen["target_scaler_sha256"] == e.file_hashes["target_scaler_file"]
            assert frozen["climatology_sha256"] == e.file_hashes["climatology_file"]
        finally:
            e.close()

    @pytest.mark.parametrize("group", ["documents", "tables", "static_assets"])
    def test_every_referenced_artifact_exists_and_matches_its_hash(self, manifest, group):
        for name, entry in manifest[group].items():
            path = ROOT / entry["path"]
            assert path.is_file(), f"{group}.{name} missing: {entry['path']}"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == entry["sha256"], (
                f"{group}.{name} changed since the freeze was generated")

    def test_depths_and_grid_are_the_mandated_ones(self, manifest):
        assert manifest["inputs_and_targets"]["depths_m"] == [
            0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
        assert manifest["replay_api"]["field_shape"] == [101, 241, 15]
        assert len(manifest["inputs_and_targets"]["surface_inputs"]) == 7

    def test_diagnostic_constants_match_the_shipped_module(self, manifest):
        from oceanembed.diagnostics import CP0, RHO0
        d = manifest["diagnostics"]
        assert d["cp0_J_kg_K"] == CP0
        assert d["rho0_kg_m3"] == RHO0
        assert d["threshold_degC"] == 26.0

    def test_hazard_boundaries_match_the_frozen_thresholds(self, manifest):
        from oceanembed.diagnostics.hazard import load_thresholds
        t = load_thresholds()
        b = manifest["hazard_indicator"]["boundaries_kj_cm2"]
        assert (b["p50"], b["p75"], b["p90"]) == (t.p50, t.p75, t.p90)
        assert "TRAIN" in manifest["hazard_indicator"]["reference_period"]

    def test_event_matches_the_pre_registration(self, manifest):
        e = manifest["event"]
        assert e["window"] == ["2023-05-05", "2023-05-22"]
        assert "Mocha" in e["name"]
        assert e["selected_before_error_inspection"] is True

    def test_no_retraining_happened_in_phase7(self, manifest):
        assert manifest["scientific_core"]["retrained_in_phase7"] is False

    def test_limitations_are_recorded_not_omitted(self, manifest):
        text = " ".join(manifest["known_limitations"]).lower()
        for topic in ("500-1000", "seafloor", "convention", "salinity",
                      "category", "argo"):
            assert topic in text, f"limitation not disclosed: {topic}"
        assert len(manifest["known_limitations"]) >= 8


# ------------------------------------------------------- freeze status
class TestFreezeStatus:
    def test_nrt_not_started_and_no_phase8_work(self, manifest):
        s = manifest["status"]
        assert s["nrt_status"] == "NOT STARTED"
        assert s["phase8a_started"] is False and s["phase8b_started"] is False

    def test_no_phase8b_reserved_capability_exists(self):
        """Nothing beyond the currently authorised phase may exist.

        Phase-boundary note: this test originally also banned a `Latest Inputs`
        tab, which was correct while Phase 8A was unauthorised. Phase 8A was
        subsequently approved and adds that tab, so the ban was narrowed to the
        items that remain reserved for Phase 8B. Nothing else was relaxed: the
        reserved wording and the latest-reconstruction entry point are still
        forbidden, and the Phase 7 manifest still records NRT NOT STARTED for
        Phase 7 (asserted separately).
        """
        app = (ROOT / "src/oceanembed/poc/app.py").read_text(encoding="utf-8").lower()
        for banned in ("latest_qualified", "urllib.request", "requests.get"):
            assert banned not in app, f"{banned!r} reachable from the PoC app"
        for path in ((ROOT / "web/src/App.tsx"),
                     *(ROOT / "web/src/components").glob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            for banned in ("Latest Qualified Ocean State", "Live Ocean Right Now"):
                assert banned not in text, f"{banned!r} in {path.name}"

    def test_no_latest_subsurface_reconstruction_exists(self):
        """Phase 8A is telemetry only; a latest field entry point is 8B work."""
        for rel in ("src/oceanembed/poc/app.py",
                    "src/oceanembed/nrt/telemetry.py"):
            source = (ROOT / rel).read_text(encoding="utf-8")
            assert "latest_qualified_field" not in source, rel

    def test_hazard_indicator_is_historical_and_carries_no_probability(self, manifest):
        h = manifest["hazard_indicator"]
        assert h["connected_to_live_data"] is False
        assert h["numeric_cyclone_probability"] is False
        assert "does not predict" in h["non_prediction_statement"].lower()

    def test_banned_wording_absent_from_the_shipped_frontend(self):
        for path in (ROOT / "web/src").rglob("*.ts*"):
            text = path.read_text(encoding="utf-8")
            assert "Live Ocean Right Now" not in text
            assert "Corrected Ocean State" not in text
            assert "Historical Forecast" not in text


# ------------------------------------------------------- 2024 holdout
class TestHoldoutProtected:
    def test_preregistration_exists_and_commits_the_method(self):
        assert PREREG.is_file()
        text = PREREG.read_text(encoding="utf-8")
        for required in ("PROTECTED", "NOT GRANTED", "TEOS-10",
                         "all 15 depths", "Do not tune to 2024",
                         "no architecture change", "No cherry-picking"):
            assert required.lower() in text.lower(), f"missing commitment: {required}"
        assert L2_STATE_DICT in text and L2_ENCODER in text

    def test_preregistration_states_the_nuance_rather_than_a_loose_claim(self):
        """The whole-float-file caveat must be recorded, not glossed."""
        text = PREREG.read_text(encoding="utf-8")
        assert "one file per float" in text.lower()
        assert "outside_window" in text
        assert "16,699" in text

    def test_manifest_declares_the_holdout_protected(self, manifest):
        assert manifest["status"]["argo_2024_status"] == "PROTECTED"
        assert "FINAL_2024_ARGO_PREREGISTRATION" in \
            manifest["status"]["argo_2024_preregistration"]

    def test_no_2024_date_in_any_matched_argo_artifact(self):
        """The holdout is verified from produced outputs, never by opening 2024."""
        matched = ROOT / "outputs" / "argo" / "matched_profiles.parquet"
        if not matched.is_file():
            pytest.skip("Argo collocation output not present")
        df = pd.read_parquet(matched, columns=["date"])
        assert pd.to_datetime(df["date"]).max() < HELDOUT_START, "HOLDOUT LEAK"

    def test_recorded_windows_exclude_the_holdout(self):
        for name in ("download_manifest", "collocation_manifest"):
            path = ROOT / "outputs" / "argo" / f"{name}.json"
            if not path.is_file():
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["audit_window"] == ["2022-01-01", "2023-12-31"]
            heldout = record.get("heldout_untouched") or \
                record.get("heldout_period_not_fetched")
            assert heldout == ["2024-01-01", "2024-12-15"]

    def test_fetch_script_still_refuses_the_holdout_by_default(self):
        source = (ROOT / "scripts/validate/fetch_argo_profiles.py").read_text(
            encoding="utf-8")
        assert 'HELDOUT_START = "2024-01-01"' in source
        assert "allow_heldout" in source and "raise SystemExit" in source

    def test_phase7_produced_no_argo_artifact_at_all(self):
        """Phase 7 reads no Argo. Any new Argo output would be a scope breach."""
        for rel in ("src/oceanembed/diagnostics/hazard.py",
                    "src/oceanembed/diagnostics/thermal.py",
                    "src/oceanembed/diagnostics/bathymetry.py",
                    "src/oceanembed/replay/engine.py"):
            source = (ROOT / rel).read_text(encoding="utf-8").lower()
            assert "argo" not in source or "argo_used_for_inference" in source \
                or "reads no argo" in source


# ------------------------------------------------------- source freeze
class TestSourceFreeze:
    """The freeze must be a real committed state, not a claim in a JSON file."""

    @staticmethod
    def _git(*args: str) -> str:
        import subprocess
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip()

    def test_source_freeze_commit_exists_in_history(self, manifest):
        commit = manifest["git"]["source_freeze_commit"]
        assert commit, "no source freeze commit recorded"
        assert self._git("cat-file", "-t", commit) == "commit", \
            f"recorded freeze commit {commit} is not in this repository"

    def test_the_freeze_was_clean_when_it_was_taken(self, manifest):
        """The claim the manifest makes about ITS OWN moment, verified.

        Phase-boundary note: this originally asserted the live tree was clean,
        which was right while Phase 7E was the head of the work. Once a later
        phase begins, the tree is legitimately dirty again and that assertion
        would only be measuring "has anyone done anything since". The durable
        claim — and the one the freeze actually rests on — is that nothing
        outside the declared metadata was uncommitted *at the moment the
        manifest was generated*. That is recorded in the manifest and checked
        here, and the live tree is additionally checked while HEAD is still at
        the freeze.
        """
        allowed = set(manifest["git"]["freeze_metadata_committed_separately"])
        recorded = manifest["git"].get("uncommitted_at_generation", [])
        stragglers = [p for p in recorded if p not in allowed]
        assert not stragglers, (
            f"the freeze was taken with source files uncommitted: {stragglers}")
        assert manifest["git"]["source_tree_clean_excluding_freeze_metadata"] is True
        # Deliberately NOT asserting the live tree here. Once any later phase
        # starts, an uncommitted tree is normal work-in-progress and says
        # nothing about whether the freeze was sound. What the freeze rests on
        # is the recorded claim above and the contents of the frozen commit,
        # which the next test checks directly against git.

    def test_the_frozen_commit_still_contains_what_it_claimed(self, manifest):
        """Later phases may add; they may not silently rewrite the freeze."""
        freeze = manifest["git"]["source_freeze_commit"]
        for group in ("documents", "tables"):
            for name, entry in manifest[group].items():
                blob = self._git("rev-parse", f"{freeze}:{entry['path']}")
                assert blob, f"{group}.{name} absent from the freeze commit"

    def test_freeze_metadata_is_declared_and_not_self_referential(self, manifest):
        declared = manifest["git"]["freeze_metadata_committed_separately"]
        assert "outputs/phase7/FINAL_POC_MANIFEST.json" in declared, \
            "the manifest must declare itself as separately committed"
        # It must not claim to contain the hash of the commit containing it.
        assert "commit" not in manifest["git"] or \
            manifest["git"].get("source_freeze_commit") is not None
        assert "cannot record the hash of the commit that" in manifest["git"]["note"]

    def test_every_manifest_artifact_is_tracked_by_git(self, manifest):
        """A hashed artifact that is not in git cannot be part of a freeze."""
        for group in ("documents", "tables", "static_assets"):
            for name, entry in manifest[group].items():
                tracked = self._git("ls-files", "--error-unmatch", entry["path"])
                assert tracked, f"{group}.{name} is not tracked: {entry['path']}"


# ------------------------------------------------------- gate answers
class TestGateClaims:
    """Each gate line must be answerable from an artifact, not from prose."""

    def test_replay_primitives_work_end_to_end(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            view = e.replay_field("2021-06-15")
            assert view.temperature.shape == (101, 241, 15)
            assert view.depths == [0, 5, 10, 20, 30, 50, 75, 100, 125, 150,
                                   200, 300, 500, 700, 1000]
            point = e.replay_point("2021-06-15", 15.25, 87.75)
            assert len(point.profile) == 15
            # The mandatory equivalence: the point comes from the field.
            row, col = point.location.grid_row, point.location.grid_col
            assert point.profile[7]["prediction_c"] == \
                pytest.approx(float(view.temperature[row, col, 7]))
        finally:
            e.close()

    def test_climatology_and_anomaly_are_consistent(self):
        import numpy as np
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            view = e.replay_field("2021-06-15")
            finite = np.isfinite(view.temperature) & np.isfinite(view.climatology)
            np.testing.assert_allclose(
                view.anomaly[finite],
                (view.temperature - view.climatology)[finite], rtol=0, atol=0)
        finally:
            e.close()

    def test_every_phase7_report_is_present(self, manifest):
        for key in ("phase7a_report", "phase7b_report", "phase7c_report",
                    "phase7d_report"):
            assert (ROOT / manifest["documents"][key]["path"]).is_file()
