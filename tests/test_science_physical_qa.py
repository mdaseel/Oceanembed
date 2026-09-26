"""Physical plausibility QA - synthetic profiles with known answers, plus the
real summary artefact when present."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.science import physical_qa as Q  # noqa: E402

DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]


def profile(values):
    return np.asarray(values, dtype="float64")[None]


def test_inversion_is_detected_above_tolerance_only():
    t = np.linspace(29, 5, 15)
    t[6] = t[5] + 0.3            # 50 -> 75 m warms by 0.3 degC: an inversion
    t[9] = t[8] + 0.05           # 125 -> 150 m warms by 0.05: below tolerance
    use = Q.usable_levels(profile(t), DEPTHS)
    d = Q.profile_diagnostics(profile(t), DEPTHS, use)
    assert int(d["inversion_count"][0]) == 1
    assert d["inversion"][0][5] and not d["inversion"][0][8]
    assert abs(float(d["max_inversion_c"][0]) - 0.3) < 1e-9
    assert int(d["strong_count"][0]) == 0


def test_gradient_and_strongest_depth():
    t = np.array([29, 29, 29, 28.9, 28.8, 27, 20, 17, 15, 14, 12, 10, 8, 6, 5], dtype=float)
    d = Q.profile_diagnostics(profile(t), DEPTHS, Q.usable_levels(profile(t), DEPTHS))
    assert abs(float(d["strongest_gradient"][0]) - (20 - 27) / 25) < 1e-12
    assert float(d["strongest_gradient_depth"][0]) == 62.5


def test_bathymetric_support_ends_the_profile():
    t = np.linspace(29, 5, 15)
    use = Q.usable_levels(profile(t), DEPTHS, water_depth=np.array([80.0]))
    assert use[0].tolist() == [True] * 7 + [False] * 8
    d = Q.profile_diagnostics(profile(t), DEPTHS, use)
    assert int(d["n_pairs"][0]) == 6


def test_a_gap_is_not_bridged_and_invalid_columns_are_excluded():
    t = np.linspace(29, 5, 15)
    t[3] = np.nan
    use = Q.usable_levels(profile(t), DEPTHS)
    assert use[0].sum() == 3
    empty = Q.profile_diagnostics(profile(np.full(15, np.nan)), DEPTHS,
                                  Q.usable_levels(profile(np.full(15, np.nan)), DEPTHS))
    assert int(empty["n_pairs"][0]) == 0 and np.isnan(empty["strongest_gradient"][0])


def test_no_mandatory_monotonic_rule():
    src = Path(Q.__file__).read_text(encoding="utf-8").lower()
    assert "no monotonic-decrease rule" in src
    t = np.linspace(29, 5, 15)
    t[2] = t[1] + 1.0
    single = Q.single_profile(t, DEPTHS, 4000.0)
    assert single["inversion_count"] == 1 and single["strong_inversion_count"] == 1
    assert "score" not in json.dumps(single).lower()


def test_basin_summaries_reproducible_when_present():
    path = ROOT / "outputs" / "science" / "physical_qa_summary.json"
    if not path.exists():
        pytest.skip("physical QA not computed")
    s = json.loads(path.read_text(encoding="utf-8"))
    assert s["no_single_score"] is True
    assert set(s["reconstruction"]) == {"nio", "arabian_sea", "bay_of_bengal"}
    assert "2024" not in s["dates"]["last"][:4]
    for region in s["gradient_envelope"].values():
        assert 0 <= region["fraction_within_reference_envelope"] <= 1
    assert s["argo"]["period"].startswith("2022-01-01..2023-12-31")
