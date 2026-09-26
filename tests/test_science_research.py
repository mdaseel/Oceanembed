"""Retrospective RI study and subsurface thermal extremes."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.science import extremes as X  # noqa: E402
from oceanembed.science import ri_study as R  # noqa: E402

PREREG = (ROOT / "outputs" / "science" / "PREREGISTRATION.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ RI
def test_ri_definition_matches_the_frozen_preregistration():
    assert "ΔV24 ≥ 30 kt" in PREREG and R.RI_KT == 30
    assert "exactly 24 h apart" in PREREG and R.WINDOW_HOURS == 24
    assert "≥ 34 kt" in PREREG and R.MIN_PEAK_KT == 34
    assert "date(t) − 1 day" in PREREG and R.SAMPLE_OFFSET_DAYS == 1
    assert "2,000 resamples, seed 20260914" in PREREG and R.BOOTSTRAP == 2000 and R.SEED == 20260914
    assert "8 variables" in PREREG and len(R.VARIABLES) == 8


def fix(time, lat, lon, imd, land=100, usa=None):
    return {"ISO_TIME": time, "LAT": str(lat), "LON": str(lon), "NEWDELHI_WIND": "" if imd is None else str(imd),
            "NEWDELHI_PRES": "", "USA_WIND": "" if usa is None else str(usa), "NATURE": "TS",
            "DIST2LAND": str(land)}


def storm(rows, season=2021):
    return {"sid": "X", "name": "TEST", "season": season, "subbasin": "BB", "rows": rows}


def test_eligibility_is_deterministic_and_picks_the_largest_change():
    rows = [fix("2021-05-20 00:00:00", 14, 88, 35), fix("2021-05-20 12:00:00", 15, 88, 45),
            fix("2021-05-21 00:00:00", 16, 88, 70), fix("2021-05-21 12:00:00", 17, 88, 90)]
    a = R.storm_record(storm(rows))
    b = R.storm_record(storm(rows))
    assert a == b
    assert a["eligible"] and a["ri"] and a["max_dv_kt"] == 45
    assert a["pair"]["t0"] == "2021-05-20 12:00:00" and a["pair"]["sample_date"] == "2021-05-19"
    assert [p["time"] for p in a["path"]] == ["2021-05-20 12:00:00", "2021-05-21 00:00:00",
                                              "2021-05-21 12:00:00"]


def test_exclusions_are_explicit():
    weak = R.storm_record(storm([fix("2021-05-20 00:00:00", 14, 88, 25),
                                 fix("2021-05-21 00:00:00", 15, 88, 30)]))
    assert not weak["eligible"] and "34 kt" in weak["exclusion"]
    landed = R.storm_record(storm([fix("2021-05-20 00:00:00", 14, 88, 40, land=0),
                                   fix("2021-05-21 00:00:00", 15, 88, 80)]))
    assert not landed["eligible"] and "over water" in landed["exclusion"]
    old = R.storm_record(storm([fix("2012-05-20 00:00:00", 14, 88, 40)], season=2012))
    assert "season" in old["exclusion"]


def test_intensity_never_reaches_the_ocean_sampler():
    src = Path(R.__file__).read_text(encoding="utf-8")
    body = src.split("def weighted_path_values")[1].split("def holm")[0]
    assert "wind" not in body and "dv" not in body


def test_holm_and_no_probability_or_classifier():
    assert R.holm([0.01, 0.04, None, 0.03]) == [0.03, 0.06, None, 0.06]
    src = Path(R.__file__).read_text(encoding="utf-8").lower()
    for banned in ("logistic", "sklearn", "classifier(", "predict_proba", "roc_auc"):
        assert banned not in src
    assert "not a predictor" in src


def test_null_result_is_supported_cleanly():
    records = [{"ri": i < 6, "values": {k: 1.0 for k, *_ in R.VARIABLES}} for i in range(14)]
    out = R.compare_groups(records)
    assert out["tests_run"] and out["n_ri"] == 6 and out["n_non_ri"] == 8
    tchp = out["variables"][0]
    assert tchp["median_difference"] == 0.0 and tchp["p_value"] >= 0.99
    small = R.compare_groups(records[:3] + records[6:8])
    assert not small["tests_run"] and small["variables"][0]["p_value"] is None


def test_published_summary_counts_are_consistent_when_present():
    path = R.OUT / "ri_summary.json"
    if not path.exists():
        pytest.skip("RI study not run")
    s = json.loads(path.read_text(encoding="utf-8"))
    imd = s["results"]["imd"]
    c = imd["counts"]
    assert c["eligible"] == c["ri"] + c["non_ri"]
    assert c["storms_in_file_2015_2024"] == c["eligible"] + c["excluded"]
    assert sum(imd["exclusion_reasons"].values()) == c["excluded"]
    assert s["no_probability"] and s["no_classifier"] and s["exploratory"]
    assert not re.search(r"\d+(\.\d+)?\s*%\s*(chance|probability|likelihood)", json.dumps(s).lower())


# ------------------------------------------------------------------ thermal extremes
def test_named_subsurface_thermal_extreme_not_marine_heatwave():
    assert X.NAME == "SUBSURFACE THERMAL EXTREME"
    assert "30 years" in X.MHW_DECISION and "SUBSURFACE THERMAL EXTREME" in X.MHW_DECISION
    assert X.EXTREME_DEPTHS == (0, 50, 75, 100, 125, 150)
    assert X.PERCENTILE == 90 and X.HALF_WINDOW == 5 and X.SMOOTH_DAYS == 31


def test_duration_rule_requires_five_days():
    four = np.array([0, 1, 1, 1, 1], dtype=bool)[:, None]
    five = np.array([0, 1, 1, 1, 1, 1], dtype=bool)[:, None]
    assert not X.trailing_events(four)["active"][0]
    r = X.trailing_events(five)
    assert r["active"][0] and r["duration"][0] == 5 and not r["censored"][0]


def test_gap_of_two_days_bridges_two_events_but_three_does_not():
    bridged = np.array([1] * 5 + [0, 0] + [1] * 5, dtype=bool)[:, None]
    r = X.trailing_events(bridged)
    assert r["active"][0] and r["duration"][0] == 12 and r["censored"][0]
    split = np.array([0] + [1] * 5 + [0, 0, 0] + [1] * 5, dtype=bool)[:, None]
    r = X.trailing_events(split)
    assert r["active"][0] and r["duration"][0] == 5


def test_invalid_days_never_count_as_exceedance():
    ex = np.ones((6, 1), dtype=bool)
    valid = np.ones((6, 1), dtype=bool)
    valid[3] = False
    assert not X.trailing_events(ex, valid)["active"][0]


def test_circular_smoothing_is_nan_aware_and_wraps():
    v = np.zeros((366, 1), dtype="float64")
    v[0] = 31.0
    s = X.smooth_circular(v, 31)
    assert abs(s[365, 0] - 1.0) < 1e-12 and abs(s[15, 0] - 1.0) < 1e-12 and s[16, 0] == 0
    v[:, 0] = np.nan
    assert np.isnan(X.smooth_circular(v, 31)).all()


def test_baseline_percentile_matches_its_definition_when_built():
    try:
        thr, recon, dates, meta = X.baseline()
    except X.BaselineUnavailable:
        pytest.skip("baseline not built")
    assert meta["baseline"] == ["2015-01-01", "2020-12-31"] and len(dates) == 2192
    assert meta["samples_per_doy_min"] >= 60
    assert all(d.year <= 2020 for d in dates)
    r, c = 60, 150
    doy = dates.dayofyear.to_numpy()
    raw = []
    for d in range(1, 367):
        dist = np.minimum(np.abs(doy - d), 366 - np.abs(doy - d))
        raw.append(np.nanpercentile(np.asarray(recon[dist <= 5, 3, r, c]), 90))
    smooth = X.smooth_circular(np.array(raw)[:, None], 31)[:, 0]
    assert np.allclose(smooth, np.asarray(thr[:, 3, r, c]), atol=1e-3, equal_nan=True)
