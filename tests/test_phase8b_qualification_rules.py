"""Phase 8B: the frozen decision rules behave exactly as the protocol states.

These pin the transcription of the pre-registered rules (commit 5b69dda). If a
rule is edited to suit a result, one of these fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from oceanembed.nrt import qualification as Q  # noqa: E402

PROTOCOL = ROOT / "outputs" / "phase8b" / "NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md"


class TestStackVerdictIsThe6CDRule:
    @pytest.mark.parametrize("b100,worst,cov,want", [
        ("MINOR", "MATERIAL", 0.01, Q.STACK_VIABLE_RAW),
        ("NEGLIGIBLE", "MINOR", 0.049, Q.STACK_VIABLE_RAW),
        ("MINOR", "MATERIAL", 0.05, Q.STACK_VIABLE_WITH_MONITORING),   # coverage boundary
        ("MATERIAL", "MATERIAL", 0.0, Q.STACK_VIABLE_WITH_MONITORING),
        ("MINOR", "SEVERE", 0.0, Q.STACK_NOT_VIABLE_RAW),
        ("SEVERE", "SEVERE", 0.977, Q.STACK_NOT_VIABLE_RAW),
    ])
    def test_verdicts(self, b100, worst, cov, want):
        assert Q.stack_verdict(b100, worst, cov) == want

    def test_reproduces_the_executed_6cd_verdict(self):
        """6C-D's own ALL_NRT_RAW row must come out as 6C-D recorded it."""
        import pandas as pd
        s = pd.read_csv(ROOT / "outputs" / "tables" / "phase6cd_substitution_summary.csv")
        row = s[s["run"] == "ALL_NRT_RAW"].iloc[0]
        assert Q.stack_verdict(row["band_100m"], row["worst_band"],
                               row["coverage_loss"]) == Q.STACK_NOT_VIABLE_RAW


class TestSkillGates:
    def _rm(self, n_better):
        l0 = {d: 1.0 for d in Q.SKILL_DEPTHS_0_200}
        n = {d: (0.9 if i < n_better else 1.1)
             for i, d in enumerate(Q.SKILL_DEPTHS_0_200)}
        return n, l0

    def test_g3_needs_six_of_eleven(self):
        assert Q.gate_g3(*self._rm(6)) == (True, 6)
        assert Q.gate_g3(*self._rm(5)) == (False, 5)

    def test_g4_needs_interval_entirely_below_zero(self):
        n = {75: 0.9, 100: 0.9, 125: 0.9}
        l0 = {75: 1.0, 100: 1.0, 125: 1.0}
        assert Q.gate_g4(n, l0, {75: -0.01, 100: -0.2, 125: -0.05})[0]
        # an interval touching zero is NOT significant
        assert not Q.gate_g4(n, l0, {75: -0.01, 100: 0.0, 125: -0.05})[0]
        # a point estimate that loses fails even with a (nonsensical) negative CI
        assert not Q.gate_g4({**n, 125: 1.1}, l0, {75: -1, 100: -1, 125: -1})[0]

    def test_g5_needs_both_basins(self):
        assert Q.gate_g5(0.9, 1.0, 0.9, 1.0)
        assert not Q.gate_g5(0.9, 1.0, 1.1, 1.0)
        assert not Q.gate_g5(1.1, 1.0, 0.9, 1.0)


class TestCategories:
    ALL = {g: True for g in ("G1", "G2", "G3", "G4", "G5")}

    def test_all_gates_give_limitations_never_plain_qualified(self):
        assert Q.temperature_category(56, self.ALL) == Q.QUALIFIED_WITH_LIMITATIONS
        assert Q.QUALIFIED_REACHABLE is False

    @pytest.mark.parametrize("gate", ["G1", "G2", "G3", "G4", "G5"])
    def test_any_failed_gate_is_not_qualified(self, gate):
        assert Q.temperature_category(56, {**self.ALL, gate: False}) == Q.NOT_QUALIFIED

    def test_too_few_dates_is_blocked_not_a_verdict(self):
        assert Q.temperature_category(27, self.ALL) == Q.BLOCKED
        assert Q.temperature_category(28, self.ALL) == Q.QUALIFIED_WITH_LIMITATIONS
        assert Q.temperature_category(56, None) == Q.BLOCKED

    def test_non_inferiority_only_rejects_detectably_worse(self):
        assert Q.non_inferior(-0.2, 0.1)      # spans zero
        assert Q.non_inferior(-0.2, -0.1)     # better
        assert not Q.non_inferior(0.01, 0.3)  # detectably worse


class TestProtocolIsFrozen:
    def test_protocol_exists_and_states_the_rules(self):
        text = PROTOCOL.read_text(encoding="utf-8")
        for needle in ("COMMON_VALID_DATE", "SSS_MULTIOBS_NRT_SAME_DATE",
                       "fewer than **28**", "≥ 6", "75, 100 and 125 m",
                       "NRT_STACK_VIABLE_WITH_MONITORING", "not reachable in Phase 8B",
                       "2024 Argo is not opened"):
            assert needle in text, needle

    def test_protocol_was_committed_before_the_sss_download(self):
        """The SSS manifest must name the protocol commit it followed."""
        import json
        man = ROOT / "outputs" / "phase8b" / "fetch_manifest.json"
        if not man.exists():
            pytest.skip("SSS candidate not yet acquired")
        assert json.loads(man.read_text())["downloaded_after_protocol_commit"] == "5b69dda"

    def test_rules_module_cites_the_protocol_commit(self):
        src = (ROOT / "src" / "oceanembed" / "nrt" / "qualification.py").read_text(
            encoding="utf-8")
        assert "5b69dda" in src
