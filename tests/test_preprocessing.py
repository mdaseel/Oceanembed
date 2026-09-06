"""Guards against silent scientific preprocessing errors.

The point is not software coverage. Each test targets one way the pipeline
could produce a plausible-looking but wrong field: a flipped axis, a 0-360
longitude left unconverted, a depth silently snapped to the nearest level,
a merge that quietly misaligns coordinates.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oceanembed.config import DEBUG_DEPTHS, EAST, FINAL_DEPTHS, NORTH, SOUTH, WEST  # noqa: E402
from oceanembed.grid import canonical_grid, canonical_lat, canonical_lon  # noqa: E402
from oceanembed.preprocessing import standardize as st  # noqa: E402
from oceanembed.preprocessing.regrid import bracketing_levels, interp_depths  # noqa: E402

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed" / \
    "oceanembed_smoketest_2020_01_dev.nc"


# ------------------------------------------------------------------ grid
def test_canonical_grid_shape_is_derived_not_assumed():
    lat, lon = canonical_lat(), canonical_lon()
    # Recompute independently of grid.py's own arithmetic.
    assert lat.size == int(round((NORTH - SOUTH) / 0.25)) + 1 == 101
    assert lon.size == int(round((EAST - WEST) / 0.25)) + 1 == 241
    assert lat.size * lon.size == 24341


def test_canonical_grid_endpoints_inclusive():
    lat, lon = canonical_lat(), canonical_lon()
    assert lat[0] == pytest.approx(SOUTH) and lat[-1] == pytest.approx(NORTH)
    assert lon[0] == pytest.approx(WEST) and lon[-1] == pytest.approx(EAST)


def test_canonical_grid_spacing_is_uniform_quarter_degree():
    for ax in (canonical_lat(), canonical_lon()):
        assert np.allclose(np.diff(ax), 0.25)


def test_canonical_grid_latitude_ascending():
    assert np.all(np.diff(canonical_lat()) > 0)
    assert canonical_grid().attrs["lat_order"] == "ascending"


# --------------------------------------------------- longitude normalisation
def test_longitude_0_360_is_converted_and_sorted():
    ds = xr.Dataset(
        {"x": ("lon", np.arange(4, dtype="float64"))},
        coords={"lon": ("lon", np.array([0.0, 90.0, 200.0, 359.0]))},
    )
    out, converted = st.normalise_longitude(ds)
    assert converted is True
    assert float(out.lon.max()) <= 180.0
    assert np.all(np.diff(out.lon.values) > 0), "must be re-sorted after wrapping"
    # 200E -> -160, 359E -> -1 : both must survive with their values attached
    assert float(out.sel(lon=-160.0)["x"]) == 2.0
    assert float(out.sel(lon=-1.0)["x"]) == 3.0


def test_longitude_already_in_range_is_left_alone():
    ds = xr.Dataset({"x": ("lon", [1.0, 2.0])},
                    coords={"lon": ("lon", [45.0, 105.0])})
    out, converted = st.normalise_longitude(ds)
    assert converted is False
    assert list(out.lon.values) == [45.0, 105.0]


# ------------------------------------------------------- latitude ordering
def test_descending_latitude_is_flipped_with_data():
    ds = xr.Dataset({"x": ("lat", [10.0, 20.0, 30.0])},
                    coords={"lat": ("lat", [3.0, 2.0, 1.0])})
    out, flipped = st.ensure_ascending_lat(ds)
    assert flipped is True
    assert list(out.lat.values) == [1.0, 2.0, 3.0]
    # the data must travel with the coordinate, not stay behind
    assert list(out["x"].values) == [30.0, 20.0, 10.0]


def test_ascending_latitude_is_not_touched():
    ds = xr.Dataset({"x": ("lat", [1.0, 2.0])}, coords={"lat": ("lat", [5.0, 6.0])})
    out, flipped = st.ensure_ascending_lat(ds)
    assert flipped is False
    assert list(out["x"].values) == [1.0, 2.0]


# --------------------------------------------------- time standardisation
def test_time_is_floored_to_the_day():
    ds = xr.Dataset(coords={"time": ("time", pd.to_datetime(
        ["2020-01-01T12:00", "2020-01-02T18:30"]).values)})
    out = st.normalise_time_daily(ds)
    assert [str(t)[:19] for t in out.time.values] == \
        ["2020-01-01T00:00:00", "2020-01-02T00:00:00"]


def test_cftime_julian_calendar_is_converted():
    cftime = pytest.importorskip("cftime")
    ds = xr.Dataset(coords={"time": ("time", np.array(
        [cftime.DatetimeJulian(2020, 1, 1), cftime.DatetimeJulian(2020, 1, 2)],
        dtype=object))})
    out = st.normalise_time_daily(ds)
    assert np.issubdtype(out.time.dtype, np.datetime64)
    assert str(out.time.values[0])[:10] == "2020-01-01"


# ---------------------------------------------------------- unit conversion
def test_kelvin_to_celsius_converts_and_records_provenance():
    da = xr.DataArray([300.15], attrs={"units": "kelvin"})
    out = st.kelvin_to_celsius(da)
    assert float(out[0]) == pytest.approx(27.0)
    assert out.attrs["units"] == "degC"
    assert out.attrs["original_units"] == "kelvin"
    assert "273.15" in out.attrs["unit_conversion"]


# ---------------------------------------------------- duplicate coordinates
def test_duplicate_coordinates_are_rejected():
    ds = xr.Dataset(coords={"lat": ("lat", [1.0, 1.0, 2.0])})
    with pytest.raises(ValueError, match="duplicate"):
        st.check_no_duplicate_coords(ds)


def test_clean_coordinates_pass():
    ds = xr.Dataset(coords={"lat": ("lat", [1.0, 2.0]), "lon": ("lon", [3.0, 4.0])})
    st.check_no_duplicate_coords(ds)  # must not raise


# ----------------------------------------------- GLORYS depth interpolation
GLORYS_NATIVE = np.array([0.494, 47.374, 55.764, 92.326, 109.729,
                          453.938, 541.089, 902.339, 1062.440])


def test_bracketing_levels_straddle_the_target():
    lo, hi = bracketing_levels(GLORYS_NATIVE, 50.0)
    assert lo == 47.374 and hi == 55.764
    lo, hi = bracketing_levels(GLORYS_NATIVE, 100.0)
    assert lo == 92.326 and hi == 109.729
    lo, hi = bracketing_levels(GLORYS_NATIVE, 1000.0)
    assert lo == 902.339 and hi == 1062.440


def test_zero_metre_is_reported_as_clamped_not_interpolated():
    """0 m sits above GLORYS's shallowest level - this must never look like
    interpolation, and must not silently become NaN."""
    da = xr.DataArray(np.linspace(30, 5, GLORYS_NATIVE.size),
                      dims="depth", coords={"depth": GLORYS_NATIVE})
    out, prov = interp_depths(da, [0.0, 50.0])
    assert prov[0.0]["clamped"] is True
    assert "clamp" in prov[0.0]["method"]
    assert prov[50.0]["clamped"] is False
    # the clamped value equals the shallowest native value, and is finite
    assert np.isfinite(float(out.sel(depth=0.0)))
    assert float(out.sel(depth=0.0)) == pytest.approx(float(da.isel(depth=0)))


def test_interpolated_depth_lies_between_its_bracketing_values():
    da = xr.DataArray([30.0, 25.0, 20.0, 15.0, 10.0, 8.0, 7.0, 6.0, 5.0],
                      dims="depth", coords={"depth": GLORYS_NATIVE})
    out, prov = interp_depths(da, [50.0])
    v = float(out.sel(depth=50.0))
    assert 20.0 <= v <= 25.0, "must lie between the two bracketing native values"
    assert prov[50.0]["native_below_m"] == 47.374


def test_requested_depths_are_relabelled_to_what_was_asked_for():
    da = xr.DataArray(np.linspace(30, 5, GLORYS_NATIVE.size),
                      dims="depth", coords={"depth": GLORYS_NATIVE})
    out, _ = interp_depths(da, [float(d) for d in DEBUG_DEPTHS])
    assert [float(d) for d in out.depth.values] == [float(d) for d in DEBUG_DEPTHS]


# ------------------------------------------------------------ merged output
@pytest.mark.skipif(not PROCESSED.exists(),
                    reason="run scripts/preprocess/build_phase6a.py first")
class TestMergedDataset:
    @pytest.fixture(scope="class")
    def ds(self):
        d = xr.open_dataset(PROCESSED)
        yield d
        d.close()

    def test_canonical_variable_names(self, ds):
        expected = {"sst", "sss", "sla", "current_u", "current_v",
                    "wind_u", "wind_v"} | {f"temp_{int(d)}m" for d in DEBUG_DEPTHS}
        assert set(ds.data_vars) == expected

    def test_dims_are_time_lat_lon(self, ds):
        for v in ds.data_vars:
            assert ds[v].dims == ("time", "lat", "lon")

    def test_grid_matches_canonical(self, ds):
        assert np.allclose(ds.lat.values, canonical_lat())
        assert np.allclose(ds.lon.values, canonical_lon())

    def test_all_variables_share_identical_coordinates(self, ds):
        for v in ds.data_vars:
            assert np.array_equal(ds[v].time.values, ds.time.values)
            assert np.array_equal(ds[v].lat.values, ds.lat.values)
            assert np.array_equal(ds[v].lon.values, ds.lon.values)

    def test_no_duplicate_coordinates(self, ds):
        st.check_no_duplicate_coords(ds)

    def test_time_is_daily_midnight_and_ascending(self, ds):
        t = pd.DatetimeIndex(ds.time.values)
        assert (t == t.normalize()).all()
        assert t.is_monotonic_increasing and t.is_unique

    def test_no_variable_is_entirely_nan(self, ds):
        for v in ds.data_vars:
            assert np.isfinite(ds[v].values).any(), f"{v} is all-NaN"

    def test_temperature_decreases_with_depth_in_the_domain_mean(self, ds):
        means = [float(ds[f"temp_{int(d)}m"].mean(skipna=True)) for d in (100, 500, 1000)]
        assert means == sorted(means, reverse=True), \
            "domain-mean temperature must fall from 100 m to 1000 m"

    def test_surface_temperature_products_agree(self, ds):
        """OSTIA sst and GLORYS temp_0m are independent products; a large
        disagreement would mean the alignment is wrong."""
        diff = (ds["sst"] - ds["temp_0m"]).values
        diff = diff[np.isfinite(diff)]
        assert np.abs(np.mean(diff)) < 1.0, f"mean sst-temp_0m offset {np.mean(diff):.2f} degC"

    def test_no_land_filling_happened(self, ds):
        """Every variable must retain missing values - a 0% NaN field over a
        domain containing land would mean land was filled."""
        for v in ds.data_vars:
            pct = 100 * np.isnan(ds[v].values).mean()
            assert pct > 10.0, f"{v} has only {pct:.1f}% NaN - land may have been filled"

    def test_final_depth_list_is_the_documented_fifteen(self):
        assert FINAL_DEPTHS == [0, 5, 10, 20, 30, 50, 75, 100, 125, 150,
                                200, 300, 500, 700, 1000]
        assert len(FINAL_DEPTHS) == 15
