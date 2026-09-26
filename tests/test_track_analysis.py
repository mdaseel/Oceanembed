"""Track x ocean thermal state — deterministic sampling on a synthetic field.

Risks: a path changing the field it samples; values interpolated between cells or
depths; below-seafloor values presented; withheld D26 leaking; intersection
distances or the strongest segment computed by a hidden weighting; arithmetic
errors in change maps.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import local_water_depth  # noqa: E402
from oceanembed.events import track_analysis as T  # noqa: E402

DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
LAT = 5.0 + 0.25 * np.arange(101)
LON = 45.0 + 0.25 * np.arange(241)


def synthetic_view(warm_box=(14.0, 16.0, 87.0, 89.0), offset=0.0, date="2023-05-12"):
    """Cool everywhere (surface below 26 C) except a warm box with a deep warm layer."""
    cool = np.linspace(25.0, 5.0, len(DEPTHS))
    warm = np.array([30.0, 30.0, 30.0, 29.8, 29.5, 29.0, 28.0, 27.0, 25.0, 22.0,
                     18.0, 13.0, 9.0, 7.0, 5.0])
    t = np.broadcast_to(cool, (LAT.size, LON.size, len(DEPTHS))).copy()
    s, n, w, e = warm_box
    rows = (LAT >= s) & (LAT <= n)
    cols = (LON >= w) & (LON <= e)
    t[np.ix_(rows, cols)] = warm
    t = t + offset
    clim = np.full_like(t, 20.0)
    water = local_water_depth(strict=False)
    ocean = np.isfinite(water) if water is not None else np.ones((LAT.size, LON.size), bool)
    return SimpleNamespace(date=date, temperature=t, climatology=clim, anomaly=t - clim,
                           lat=LAT, lon=LON, depths=DEPTHS, ocean_mask=ocean,
                           surface_input_valid=ocean.copy())


PATH = [{"lat": 12.0, "lon": 88.0, "point_type": "observed"},
        {"lat": 15.0, "lon": 88.0, "point_type": "observed"},
        {"lat": 18.0, "lon": 88.0, "point_type": "forecast"}]


@pytest.fixture(scope="module")
def ctx():
    if local_water_depth(strict=False) is None:
        pytest.skip("local bathymetry artifact not present")
    return T.field_context(synthetic_view())


def test_haversine_matches_a_meridian_degree():
    assert T.haversine_km(10, 88, 11, 88) == pytest.approx(111.195, abs=0.01)
    assert T.haversine_km(15, 88, 15, 88) == 0.0


def test_resampling_places_points_on_the_path_only():
    samples, total = T.resample(PATH)
    assert total == pytest.approx(T.haversine_km(12, 88, 18, 88), rel=1e-9)
    gaps = np.diff([s["distance_km"] for s in samples])
    assert gaps.max() <= T.STEP_KM + 1e-9 and gaps.min() > 0
    assert all(abs(s["lon"] - 88.0) < 1e-6 for s in samples)  # on the meridian path
    assert sum(s["length_km"] for s in samples) == pytest.approx(total, rel=1e-9)
    assert samples[0]["point_type"] == "observed" and samples[-1]["point_type"] == "forecast"


def test_samples_read_the_nearest_cell_exactly(ctx):
    a = T.analyze(ctx, PATH)
    for s in a["samples"]:
        if s["row"] is None:
            continue
        assert s["grid_lat"] == LAT[s["row"]] and s["grid_lon"] == LON[s["col"]]
        assert abs(s["grid_lat"] - s["lat"]) <= 0.125 + 1e-9
        k = DEPTHS.index(100)
        level = s["levels"]["100"]
        if level["temperature"] is not None:
            assert level["temperature"] == ctx.view.temperature[s["row"], s["col"], k]


def test_heat_is_found_only_where_the_field_holds_it(ctx):
    s = T.analyze(ctx, PATH)["summary"]
    peak = s["tchp"]["max"]
    assert 14.0 <= peak["lat"] <= 16.0
    assert s["highest_category"] in ("ELEVATED", "HIGH")
    warm_km = sum(v for c, v in s["category_distance_km"].items() if c != "LOW")
    assert warm_km == pytest.approx(T.haversine_km(14.0, 88, 16.0, 88) + T.STEP_KM, abs=T.STEP_KM * 1.5)
    seg = s["strongest_segment"]
    assert seg["category"] == s["highest_category"]
    assert 14.0 <= seg["lat_range"][0] <= seg["lat_range"][1] <= 16.0
    assert seg["peak_tchp"] == peak["value"]
    assert "No weights" in seg["rule"]


def test_analysis_is_deterministic_and_leaves_the_field_untouched(ctx):
    before = ctx.view.temperature.copy()
    first, second = T.analyze(ctx, PATH), T.analyze(ctx, PATH)
    assert first == second
    assert np.array_equal(before, ctx.view.temperature)


def test_withheld_d26_never_appears(ctx):
    held = T.field_context(ctx.view, withheld=("d26",))
    a = T.analyze(held, PATH)
    assert all(s["d26"] is None for s in a["samples"])
    assert a["summary"]["d26"] == {"withheld": True}
    assert a["summary"]["tchp"]["max"] is not None


def test_positions_outside_the_domain_carry_no_values(ctx):
    a = T.analyze(ctx, [{"lat": 2.0, "lon": 88.0}, {"lat": 3.0, "lon": 88.0}])
    assert a["summary"]["n_in_domain"] == 0
    assert all(s["tchp"] is None and s["category"] is None for s in a["samples"])


def test_section_uses_the_15_model_depths_and_blanks_below_the_seafloor(ctx):
    sec = T.section(ctx, PATH, "temperature")
    assert sec["depths_m"] == DEPTHS
    assert len(sec["values"]) == 15
    assert all(len(row) == len(sec["distance_km"]) for row in sec["values"])
    for i, floor in enumerate(sec["water_depth_m"]):
        for k, depth in enumerate(DEPTHS):
            if floor is None or depth > floor:
                assert sec["values"][k][i] is None
    with pytest.raises(ValueError):
        T.section(ctx, PATH, "salinity")


def test_invalid_paths_are_refused():
    with pytest.raises(ValueError):
        T.resample([])
    with pytest.raises(ValueError):
        T.resample([{"lat": "north", "lon": 88}])
    with pytest.raises(ValueError):
        T.resample([{"lat": 12, "lon": 88}] * (T.MAX_POINTS + 1))


def test_change_maps_are_exact_differences_of_real_depths(ctx):
    warmer = T.field_context(synthetic_view(offset=1.0, date="2023-05-20"))
    a, b = T.composite([ctx]), T.composite([warmer])
    change = T.difference(a, b, ctx.water, depth_m=100, include_tchp_grid=True)
    for depth in ("0", "50", "75", "100"):
        stats = change["footprint"]["temperature"][depth]
        assert stats["min"]["value"] == pytest.approx(1.0)
        assert stats["max"]["value"] == pytest.approx(1.0)
    assert change["footprint"]["tchp"]["min"]["value"] >= 0
    values = [v for row in change["grid"]["values"] for v in row if v is not None]
    assert values and all(math.isclose(v, 1.0) for v in values)
    with pytest.raises(ValueError):
        T.difference(a, b, ctx.water, depth_m=90)


def test_composite_blanks_a_cell_missing_on_any_day(ctx):
    gap = synthetic_view(date="2023-05-13")
    gap.temperature[40, 170, :] = np.nan
    comp = T.composite([ctx, T.field_context(gap)])
    assert np.isnan(comp["temperature"][40, 170]).all()
    assert comp["dates"] == ["2023-05-12", "2023-05-13"]
