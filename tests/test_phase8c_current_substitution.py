"""Phase 8C: the operational current-source qualification, and its refusal.

The candidate was REJECTED on the observational gate, so the invariants worth
pinning are that nothing changed as a result: OSCAR still drives both regimes,
no candidate dataset can reach the frozen model without an approving artifact,
and the historical benchmark and 2024 holdout are untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from oceanembed.nrt import latest as LQ  # noqa: E402
from oceanembed.nrt.registry import PRODUCTS  # noqa: E402

P8C = ROOT / "outputs" / "phase8c"
CANDIDATE_DATASET = "cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m"
L2 = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
APPROVING = ("SUBSTITUTE_APPROVED", "SUBSTITUTE_WITH_MONITORING")


def load(name):
    p = P8C / name
    if not p.is_file():
        pytest.skip(f"{name} not produced")
    return json.loads(p.read_text(encoding="utf-8"))


class TestDecision:
    def test_decision_is_rejected_on_the_observational_gate(self):
        d = load("decision.json")
        assert d["decision"] == "SUBSTITUTE_REJECTED"
        assert d["failed_gates"] == ["C8_observational_non_inferiority"]
        assert d["integration_permitted"] is False

    def test_the_gate_that_failed_was_the_pre_registered_one(self):
        a = load("argo_result.json")
        assert a["c8_allowed_degradation_pct"] == 0.68     # 6C-C weakest promoted
        assert a["c8_required_spanning"] == 4
        assert a["c8_spanning_zero"] < 4 or \
            a["c8_worst_degradation_pct"] > a["c8_allowed_degradation_pct"]
        assert a["C8_pass"] is False

    def test_model_level_gates_passing_did_not_override_the_observations(self):
        """The point of the phase: reanalysis-based gates all passed."""
        s = load("substitution_result.json")
        assert s["phase4_channel_decision"] in APPROVING
        assert s["phase5_gates"]["C5_pass"] and s["phase5_gates"]["C6_pass"]
        assert s["phase5_gates"]["C7_pass"]
        assert load("decision.json")["decision"] == "SUBSTITUTE_REJECTED"

    def test_secondary_variant_was_reported_and_not_decision_bearing(self):
        t = load("argo_result_total.json")
        assert "reported only" in t["variant_role"]
        assert t["variant"] == "total"
        # it also failed, so the rejection does not hinge on the tide choice
        assert t["C8_pass"] is False


class TestNothingWasSubstituted:
    def test_historical_replay_still_resolves_oscar(self):
        assert PRODUCTS["currents_reference"]["product_id"] == "OSCAR_L4_OC_FINAL_V2.0"
        import xarray as xr
        store = ROOT / "data" / "processed" / "model_ready" / "oceanembed_2024.zarr"
        if not store.exists():
            pytest.skip("model-ready store not present")
        ds = xr.open_zarr(store, consolidated=True)
        assert "OSCAR" in ds.attrs["source_currents"]
        assert "FINAL" in ds.attrs["source_currents"].upper()

    def test_latest_operational_mode_still_resolves_oscar(self):
        assert LQ.PRODUCT_CHANNELS["currents_nrt"] == ("current_u", "current_v")
        assert PRODUCTS["currents_nrt"]["product_id"] == "OSCAR_L4_OC_NRT_V2.0"
        decision = json.loads((ROOT / "outputs/phase8b/qualification_decision.json")
                              .read_text(encoding="utf-8"))
        assert decision["products"]["current_u"] == "currents_nrt"
        assert decision["products"]["current_v"] == "currents_nrt"

    def test_a_rejected_candidate_cannot_reach_the_frozen_model(self):
        """No operational code path references the candidate dataset."""
        for path in (ROOT / "src" / "oceanembed").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert CANDIDATE_DATASET not in text, path.name
        app = (ROOT / "src/oceanembed/poc/app.py").read_text(encoding="utf-8")
        assert CANDIDATE_DATASET not in app

    def test_registry_was_not_quietly_extended_with_the_candidate(self):
        ids = {p["dataset_id"] for p in PRODUCTS.values()}
        assert CANDIDATE_DATASET not in ids

    def test_one_production_model_and_no_retraining(self):
        d = load("decision.json")
        assert d["production_reconstruction_models"] == 1
        assert d["l2_retrained"] is False
        assert d["historical_replay_changed"] is False
        s = load("substitution_result.json")
        assert s["l2_state_dict_sha256_before"] == L2
        assert s["l2_state_dict_sha256_after"] == L2
        a = load("argo_result.json")
        assert a["l2_state_dict_sha256_before"] == a["l2_state_dict_sha256_after"] == L2


class TestExperimentIntegrity:
    def test_control_reproduced_the_executed_argo_evidence_exactly(self):
        """A collocation difference must not be mistakable for a current effect."""
        a = load("argo_result.json")
        for depth, rec in a["control_reproduces_executed_l2"].items():
            assert rec["max_abs_diff"] == 0.0, depth
            assert rec["n"] > 1000, depth

    def test_population_is_the_existing_2022_23_collocations(self):
        a = load("argo_result.json")
        assert a["population"]["window"] == ["2022-05-01", "2023-12-31"]
        assert a["population"]["profiles"] > 4000
        assert "on/after 2022-05-01" in a["population"]["subset_rule"]
        assert a["collocation_method"] == \
            "ocean_aware_bilinear_then_nearest_wet_within_1_cell"

    def test_evaluation_dates_are_the_pre_registered_ones(self):
        s = load("substitution_result.json")
        man = json.loads((ROOT / "outputs/nrt/fetch_manifest.json")
                         .read_text(encoding="utf-8"))
        assert set(s["dates"]).issubset(set(man["dates"]))
        assert s["n_dates"] >= 28

    def test_candidate_canonical_matches_the_frozen_input_contract(self):
        import xarray as xr
        f = ROOT / "data/processed/nrt/currents_candidate_d1_canonical.nc"
        if not f.exists():
            pytest.skip("candidate canonical field not present")
        ds = xr.open_dataset(f)
        assert ds.sizes["lat"] == 101 and ds.sizes["lon"] == 241
        assert np.allclose(ds.lat.values[:2], [5.0, 5.25])
        assert np.allclose(ds.lon.values[:2], [45.0, 45.25])
        for v in ("current_u", "current_v"):
            assert ds[v].attrs["units"] == "m s-1"
            assert ds[v].attrs["depth_m"] == 15.0
            assert "tide excluded" in ds[v].attrs["definition"]

    def test_preregistration_precedes_the_results(self):
        text = (P8C / "OPERATIONAL_CURRENT_SUBSTITUTION_PREREGISTRATION.md").read_text(
            encoding="utf-8")
        for needle in ("SUBSTITUTE_APPROVED", "SUBSTITUTE_WITH_MONITORING",
                       "SUBSTITUTE_REJECTED", "+0.68 %", "2022-05-01",
                       "tide excluded", "No retraining"):
            assert needle in text, needle
        for name in ("substitution_result.json", "argo_result.json", "decision.json"):
            assert load(name)["preregistration_commit"] == "c01c170"


class TestHoldout:
    def test_2024_argo_was_not_opened(self):
        a = load("argo_result.json")
        assert a["argo_2024_opened"] is False
        assert load("decision.json")["argo_2024_opened"] is False

    def test_no_2024_profile_in_any_phase8c_artifact(self):
        f = P8C / "argo_candidate_replay.parquet"
        if not f.exists():
            pytest.skip("replay artifact not present")
        dates = pd.to_datetime(pd.read_parquet(f, columns=["date"])["date"])
        assert dates.max() < pd.Timestamp("2024-01-01"), "HOLDOUT LEAK"
        assert dates.min() >= pd.Timestamp("2022-05-01")
