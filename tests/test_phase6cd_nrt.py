"""Phase 6C-D behavioural tests: NRT product compatibility and substitution.

These pin behaviour that a later edit could plausibly break, and in particular
the two things this phase's honesty rests on: that no target is ever read, and
that a substituted product goes through the UNMODIFIED frozen input contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.config import REPO_ROOT  # noqa: E402
from oceanembed.grid import canonical_lat, canonical_lon  # noqa: E402
from oceanembed.ml.features import SURFACE  # noqa: E402
from oceanembed.ml.patches import day_field  # noqa: E402
from oceanembed.ml.scaler import ZScoreScaler  # noqa: E402
from oceanembed.nrt import compatibility as compat  # noqa: E402
from oceanembed.nrt import harmonize, latency, registry, substitution  # noqa: E402

OUT = REPO_ROOT / "outputs" / "nrt"
TAB = REPO_ROOT / "outputs" / "tables"
BASE = REPO_ROOT / "outputs" / "baselines"


# ------------------------------------------------------------------- registry
def test_every_channel_has_a_reference_and_an_nrt_candidate():
    channels = {p["channel"] for p in registry.PRODUCTS.values()}
    for ch in channels:
        roles = {p["role"] for p in registry.PRODUCTS.values() if p["channel"] == ch}
        assert "reference" in roles, ch
        assert any(r.startswith("nrt") for r in roles), ch


def test_registry_records_that_channels_are_not_independent_measurements():
    doc = registry.PRODUCTS["currents_reference"]
    assert "DIAGNOSTIC" in doc["source_type"], \
        "OSCAR must stay documented as derived, not measured"


# -------------------------------------------------------------------- latency
def test_first_seen_is_never_overwritten_for_a_known_valid_time(tmp_path):
    p = tmp_path / "log.parquet"
    row = {"provider": "X", "product_key": "k", "product_id": "p",
           "dataset_id": "d", "query_time": pd.Timestamp("2026-01-01T00:00:00"),
           "newest_valid_time": pd.Timestamp("2025-12-31"), "success": True}
    latency.append_poll(p, [row])
    later = dict(row, query_time=pd.Timestamp("2026-01-05T00:00:00"))
    df = latency.append_poll(p, [later])
    firsts = df["first_seen_by_oceanembed"].unique()
    assert len(firsts) == 1, "a re-poll invented a new first_seen"
    assert pd.Timestamp(firsts[0]) == pd.Timestamp("2026-01-01T00:00:00")


def test_a_genuinely_new_valid_time_gets_its_own_first_seen(tmp_path):
    p = tmp_path / "log.parquet"
    base = {"provider": "X", "product_key": "k", "product_id": "p", "dataset_id": "d",
            "success": True}
    latency.append_poll(p, [dict(base, query_time=pd.Timestamp("2026-01-01"),
                                 newest_valid_time=pd.Timestamp("2025-12-31"))])
    df = latency.append_poll(p, [dict(base, query_time=pd.Timestamp("2026-01-02"),
                                      newest_valid_time=pd.Timestamp("2026-01-01"))])
    assert df["first_seen_by_oceanembed"].nunique() == 2


# ------------------------------------------------------- pre-registered bands
def test_bands_match_the_pre_registration_document():
    text = (OUT / "PREREGISTRATION_6CD.md").read_text(encoding="utf-8")
    for token in ("INTERCHANGEABLE", "USABLE_WITH_CAVEAT", "MARGINAL",
                  "INCOMPATIBLE_RAW", "NEGLIGIBLE", "MINOR", "MATERIAL", "SEVERE"):
        assert token in text
    assert "0.10" in text and "0.25" in text and "0.50" in text


def test_compatibility_band_is_assigned_top_down():
    assert compat.compatibility_band(0.05, 0.01, 0.99, 1.00) == "INTERCHANGEABLE"
    # correlation alone can demote a product whose moments look perfect
    assert compat.compatibility_band(0.05, 0.01, 0.80, 1.00) == "MARGINAL"
    assert compat.compatibility_band(0.20, 0.10, 0.95, 1.10) == "USABLE_WITH_CAVEAT"
    assert compat.compatibility_band(0.60, 0.01, 0.99, 1.00) == "INCOMPATIBLE_RAW"


def test_non_finite_statistics_are_incompatible_not_silently_good():
    assert compat.compatibility_band(np.nan, 0.0, 0.99, 1.0) == "INCOMPATIBLE_RAW"


def test_sensitivity_bands_are_monotone():
    xs = [0.0, 0.05, 0.15, 0.30, 0.90]
    got = [compat.sensitivity_band(x) for x in xs]
    order = [compat.SENS_BANDS.index(g) for g in got]
    assert order == sorted(order)


def test_worst_band_picks_the_most_severe():
    assert compat.worst_band(["NEGLIGIBLE", "MATERIAL", "MINOR"],
                             compat.SENS_BANDS) == "MATERIAL"


# --------------------------------------------------- no target may be opened
def test_substitution_refuses_a_target_variable():
    ds = xr.Dataset(coords={"lat": [1.0], "lon": [2.0]})
    with pytest.raises(PermissionError):
        substitution.assert_no_target_access(ds, ["temp_100m"])
    with pytest.raises(PermissionError):
        substitution.assert_no_target_access(ds, ["target_valid_100m"])
    substitution.assert_no_target_access(ds, ["sst", "sss"])


def test_run_metadata_records_that_no_target_was_opened():
    for name in ("substitution_meta.json", "compatibility_meta.json"):
        p = OUT / name
        if p.exists():
            assert json.loads(p.read_text())["targets_opened"] == []


# ------------------------------------------------ contract is not bent for NRT
def _toy_reference(nlat=12, nlon=14):
    rng = np.random.default_rng(0)
    data = {v: (("time", "lat", "lon"),
                rng.normal(size=(1, nlat, nlon)).astype("float64"))
            for v in SURFACE}
    return xr.Dataset(data, coords={"time": [np.datetime64("2024-07-01")],
                                    "lat": np.arange(nlat) * 0.25 + 5.0,
                                    "lon": np.arange(nlon) * 0.25 + 45.0})


def _scaler():
    return ZScoreScaler(np.zeros(11), np.ones(11),
                        list(SURFACE) + ["lat", "lon", "doy_sin", "doy_cos"])


def test_empty_substitution_reproduces_the_legacy_field_exactly():
    ds, sc = _toy_reference(), _scaler()
    a = day_field(ds, 0, sc, patch=5)
    b = substitution.substituted_field(ds, 0, sc, patch=5, replacements={})
    assert np.array_equal(a, b), "the no-op substitution changed the frozen field"


def test_a_nan_in_a_substituted_channel_blanks_the_cell_via_the_joint_mask():
    ds, sc = _toy_reference(), _scaler()
    rep = np.asarray(ds["sss"].isel(time=0).values, dtype="float64").copy()
    rep[3, 4] = np.nan
    f = substitution.substituted_field(ds, 0, sc, patch=5, replacements={"sss": rep})
    half = 5 // 2
    # every channel plus the mask must be zero at that cell - the single joint
    # mask cannot express a per-channel outage
    assert np.all(f[:, 3 + half, 4 + half] == 0.0)


def test_substitution_rejects_a_wrong_shaped_field():
    ds, sc = _toy_reference(), _scaler()
    with pytest.raises(ValueError):
        substitution.substituted_field(ds, 0, sc, patch=5,
                                       replacements={"sst": np.zeros((3, 3))})


def test_substitution_rejects_a_channel_outside_the_contract():
    ds, sc = _toy_reference(), _scaler()
    with pytest.raises(ValueError):
        substitution.substituted_field(ds, 0, sc, patch=5,
                                       replacements={"chlorophyll": np.zeros((12, 14))})


def test_joint_mask_matches_the_frozen_definition():
    ds = _toy_reference()
    arrays = {v: np.asarray(ds[v].isel(time=0).values, dtype="float64")
              for v in SURFACE}
    arrays["wind_v"][1, 1] = np.nan
    m = substitution.joint_mask(arrays)
    assert not m[1, 1] and m.sum() == m.size - 1


# ----------------------------------------------------------- harmonisation
def test_sst_kelvin_conversion_and_grid():
    lat = np.linspace(4.0, 31.0, 30)
    lon = np.linspace(44.0, 106.0, 40)
    ds = xr.Dataset(
        {"analysed_sst": (("time", "latitude", "longitude"),
                          np.full((1, 30, 40), 300.15))},
        coords={"time": [np.datetime64("2024-07-01")],
                "latitude": lat, "longitude": lon})
    out = harmonize.harmonise_sst(ds)
    assert out.sizes["lat"] == canonical_lat().size
    assert out.sizes["lon"] == canonical_lon().size
    assert np.allclose(np.nanmean(out["sst"].values), 27.0, atol=1e-4)


def test_smos_qc_rejects_dubious_retrievals_rather_than_repairing_them():
    lat = np.linspace(4.0, 31.0, 30)
    lon = np.linspace(44.0, 106.0, 40)
    sss = np.full((1, 30, 40), 35.0)
    qc = np.zeros((1, 30, 40))
    qc[0, :, :20] = 1                      # dubious half
    ds = xr.Dataset({"Sea_Surface_Salinity": (("time", "latitude", "longitude"), sss),
                     "Sea_Surface_Salinity_QC": (("time", "latitude", "longitude"), qc)},
                    coords={"time": [np.datetime64("2024-07-01")],
                            "latitude": lat, "longitude": lon})
    out = harmonize.harmonise_smos_sss(ds)
    v = out["sss"].values
    assert np.isnan(v).any(), "dubious retrievals were not dropped"
    assert np.nanmax(v) == pytest.approx(35.0)


def test_hourly_wind_is_averaged_as_u_and_v_independently():
    # a wind that veers 180 degrees over the day has zero vector mean but a
    # large scalar speed; averaging speed instead would hide the cancellation
    t = pd.date_range("2024-07-01", periods=24, freq="h")
    u = np.concatenate([np.full(12, 10.0), np.full(12, -10.0)])
    lat = np.linspace(4.0, 31.0, 12)
    lon = np.linspace(44.0, 106.0, 12)
    ds = xr.Dataset(
        {"eastward_wind": (("time", "latitude", "longitude"),
                           np.repeat(u[:, None, None], 12, 1).repeat(12, 2)),
         "northward_wind": (("time", "latitude", "longitude"),
                            np.zeros((24, 12, 12)))},
        coords={"time": t, "latitude": lat, "longitude": lon})
    out = harmonize.harmonise_wind_hourly(ds)
    assert out.sizes["time"] == 1
    assert abs(float(np.nanmean(out["wind_u"].values))) < 1e-6


def test_regridding_does_not_extrapolate_over_a_gap():
    lat = np.linspace(4.0, 31.0, 60)
    lon = np.linspace(44.0, 106.0, 80)
    a = np.full((1, 60, 80), 35.0)
    a[0, 20:40, 20:40] = np.nan
    ds = xr.Dataset({"sla": (("time", "latitude", "longitude"), a)},
                    coords={"time": [np.datetime64("2024-07-01")],
                            "latitude": lat, "longitude": lon})
    out = harmonize.to_canonical(harmonize.rename_coords(ds))
    assert np.isnan(out["sla"].values).any(), "a gap was filled by regridding"


# --------------------------------------------------------------- result files
@pytest.mark.skipif(not (TAB / "phase6cd_channel_compatibility.csv").exists(),
                    reason="compatibility table not built")
def test_compatibility_table_reports_every_pair_in_all_three_regions():
    d = pd.read_csv(TAB / "phase6cd_channel_compatibility.csv")
    for (ch, key), g in d.groupby(["channel", "nrt_key"]):
        assert set(g["region"]) == {"full_nio", "arabian_sea", "bay_of_bengal"}, (ch, key)
    assert set(d["compatibility_band"]) <= set(compat.COMPAT_BANDS)


@pytest.mark.skipif(not (TAB / "phase6cd_substitution_sensitivity.csv").exists(),
                    reason="substitution table not built")
def test_sensitivity_is_reported_at_every_depth_and_never_negative():
    d = pd.read_csv(TAB / "phase6cd_substitution_sensitivity.csv")
    assert (d["rmsd"] >= 0).all()
    assert set(d["sensitivity_band"]) <= set(compat.SENS_BANDS)
    for run, g in d.groupby("run"):
        assert len(g) == 15, run


@pytest.mark.skipif(not (Path(REPO_ROOT / "outputs" / "nrt"
                              / "overlap_manifest.json").exists()),
                    reason="overlap manifest not built")
def test_overlap_was_discovered_per_pair_not_assumed_universal():
    doc = json.loads((OUT / "overlap_manifest.json").read_text())
    pairs = doc["pairs"]
    assert set(pairs) == set(registry.PAIRS)
    spans = {(p["overlap_start"], p["overlap_end"]) for p in pairs.values()}
    assert len(spans) > 1, "every pair got the same window - overlap was assumed"
