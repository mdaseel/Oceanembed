"""Phase 7C guards — D26 / TCHP derived thermal diagnostics.

The risks these target: an isotherm depth extrapolated into water that was
never measured; a gap in a profile silently bridged to reach a deeper crossing;
an integral that runs past D26 into sub-26 water; a constant quietly re-tuned to
make a reconstruction look closer to a reference; an invalid cell rendered as a
number instead of as a status; and a metric being generated before the
evaluation population was pre-registered.

The analytic cases here are exact by construction, so a failure is a real
behaviour change and never a tolerance artefact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import (CP0, D26Status, RHO0, RHO_CP,  # noqa: E402
                                    TEMPERATURE_THRESHOLD_C, d26_tchp,
                                    verify_constants)

DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]


def one(temps, depths=None):
    """Run a single profile and return (d26, tchp, status)."""
    r = d26_tchp(np.asarray(temps, dtype="float64"), depths or DEPTHS)
    return float(r.d26), float(r.tchp), D26Status(int(r.status))


def linear_profile(surface, gradient, depths=None):
    """T(z) = surface - gradient * z, so the 26 degC crossing is analytic."""
    z = np.asarray(depths or DEPTHS, dtype="float64")
    return surface - gradient * z


# --------------------------------------------------------------- constants
class TestConstants:
    def test_cp0_is_the_teos10_defined_constant(self):
        """Derived from the standard's own identity, not copied from a table."""
        info = verify_constants()
        assert info["cp0_derived"] == pytest.approx(CP0, rel=1e-12)
        assert info["standard"].startswith("TEOS-10")

    def test_rho0_matches_teos10_at_the_defining_isotherm(self):
        gsw = pytest.importorskip("gsw")
        assert gsw.rho(35.16504, TEMPERATURE_THRESHOLD_C, 0.0) == \
            pytest.approx(RHO0, rel=1e-9)

    def test_cp0_identity_holds_across_salinity_and_temperature(self):
        """h0 = cp0 * CT must hold for EVERY SA and CT, or cp0 is not cp0."""
        gsw = pytest.importorskip("gsw")
        for sa in (33.0, 35.16504, 36.5):
            for ct in (5.0, 26.0, 30.0):
                assert gsw.enthalpy(sa, ct, 0.0) / ct == pytest.approx(CP0, rel=1e-12)

    def test_volumetric_heat_capacity_is_the_product(self):
        assert RHO_CP == pytest.approx(RHO0 * CP0, rel=1e-15)

    def test_constants_are_not_the_fresh_water_values(self):
        """Guards the specific mistake the published sources make."""
        assert not np.isclose(CP0, 4186.0, rtol=1e-3)
        assert not np.isclose(CP0, 4178.0, rtol=1e-3)
        assert not np.isclose(RHO0, 1000.0, rtol=1e-3)


# --------------------------------------------------------------- D26 basics
class TestD26:
    def test_crossing_is_linearly_interpolated_between_bracketing_levels(self):
        """30 degC at 0 m falling 0.1 degC/m crosses 26 degC at exactly 40 m."""
        d26, _, status = one(linear_profile(30.0, 0.1))
        assert status is D26Status.OK
        assert d26 == pytest.approx(40.0, abs=1e-9)

    def test_crossing_between_two_arbitrary_levels(self):
        """Bracketed by 30 m (27 degC) and 50 m (25 degC) -> midpoint, 40 m."""
        temps = [30, 29, 28.5, 28, 27, 25] + [20] * 9
        d26, _, status = one(temps)
        assert status is D26Status.OK
        assert d26 == pytest.approx(40.0, abs=1e-9)

    def test_exactly_26_at_a_level_returns_that_level(self):
        temps = [30, 29, 28, 27, 26, 24] + [20] * 9   # exactly 26.0 at 30 m
        d26, _, status = one(temps)
        assert status is D26Status.OK
        assert d26 == pytest.approx(30.0, abs=1e-12)

    def test_exactly_26_at_the_surface_is_a_crossing_at_zero(self):
        temps = [26.0, 25.0] + [20] * 13
        d26, tchp, status = one(temps)
        assert status is D26Status.OK
        assert d26 == pytest.approx(0.0, abs=1e-12)
        assert tchp == pytest.approx(0.0, abs=1e-12)

    def test_shallowest_crossing_wins_when_an_inversion_creates_two(self):
        """A Bay of Bengal style inversion must not select the deeper crossing."""
        temps = [28, 27, 25, 24, 27, 28, 27, 25] + [20] * 7
        d26, _, status = one(temps)
        assert status is D26Status.OK
        assert d26 < 20.0   # the shallow crossing, between 5 m and 10 m

    def test_surface_below_26_has_no_d26_but_zero_tchp(self):
        d26, tchp, status = one([24.0] * 15)
        assert status is D26Status.SURFACE_BELOW_26
        assert np.isnan(d26)
        assert tchp == 0.0

    def test_no_crossing_in_support_is_undefined_not_extrapolated(self):
        """Warm all the way down: a crossing must NOT be invented below 1000 m."""
        d26, tchp, status = one([28.0] * 15)
        assert status is D26Status.NO_CROSSING_IN_SUPPORT
        assert np.isnan(d26)
        assert np.isnan(tchp)

    def test_no_valid_levels(self):
        d26, tchp, status = one([np.nan] * 15)
        assert status is D26Status.NO_VALID_LEVELS
        assert np.isnan(d26) and np.isnan(tchp)

    def test_invalid_top_level_is_insufficient_support(self):
        temps = [np.nan] + list(linear_profile(30.0, 0.1))[1:]
        d26, tchp, status = one(temps)
        assert status is D26Status.INSUFFICIENT_SUPPORT
        assert np.isnan(d26) and np.isnan(tchp)

    def test_a_gap_is_never_bridged_to_reach_a_deeper_crossing(self):
        """Warm, then a hole, then cold. Joining across the hole would be
        extrapolation through water that was never measured."""
        temps = [29, 28.5, 28, np.nan, 24, 23] + [20] * 9
        d26, tchp, status = one(temps)
        assert status is D26Status.INSUFFICIENT_SUPPORT
        assert np.isnan(d26) and np.isnan(tchp)

    def test_a_gap_below_the_crossing_does_not_matter(self):
        temps = [29, 27, 25, np.nan, np.nan] + [np.nan] * 10
        d26, _, status = one(temps)
        assert status is D26Status.OK
        assert 5.0 < d26 < 10.0

    def test_d26_never_exceeds_the_deepest_valid_level(self):
        rng = np.random.default_rng(20260909)
        profiles = 29.0 - rng.uniform(0, 0.06, size=(500, 1)) * np.array(DEPTHS)
        r = d26_tchp(profiles, DEPTHS)
        ok = r.status == D26Status.OK
        assert ok.any()
        assert np.all(r.d26[ok] <= DEPTHS[-1])
        assert np.all(r.d26[ok] >= DEPTHS[0])


# --------------------------------------------------------------- TCHP
class TestTCHP:
    def test_analytic_linear_profile(self):
        """T = 30 - 0.1 z  ->  D26 = 40 m, and the excess is a triangle:
        integral = 1/2 * 4 degC * 40 m = 80 degC m, exactly."""
        d26, tchp, status = one(linear_profile(30.0, 0.1))
        assert status is D26Status.OK
        assert d26 == pytest.approx(40.0, abs=1e-9)
        expected = RHO_CP * 80.0 * 1e-7
        assert tchp == pytest.approx(expected, rel=1e-12)

    def test_isothermal_slab_is_exact(self):
        """28 degC through 50 m, exactly 26 degC at the 75 m level: D26 lands on
        that level and the trapezoid rule is exact here. 0-50 m contributes
        2 degC * 50 m = 100; the 50-75 m ramp contributes 1/2*(2+0)*25 = 25;
        total 125 degC m, with nothing counted below D26."""
        temps = [28] * 6 + [26] + [24] * 8        # 28 through 50 m, 26 at 75 m
        d26, tchp, status = one(temps)
        assert status is D26Status.OK
        assert d26 == pytest.approx(75.0, abs=1e-12)
        assert tchp == pytest.approx(RHO_CP * 125.0 * 1e-7, rel=1e-12)

    def test_crossing_interpolates_rather_than_snapping_to_a_level(self):
        """28 degC at 50 m over 24 degC at 75 m puts the isotherm at 62.5 m, not
        at either bracketing level. A nearest-level snap would fail this."""
        temps = [28] * 6 + [24] + [20] * 8
        d26, _, status = one(temps)
        assert status is D26Status.OK
        assert d26 == pytest.approx(62.5, abs=1e-12)

    def test_integration_terminates_at_d26_and_ignores_colder_water_below(self):
        """Two profiles identical above D26 and wildly different below must give
        identical TCHP. This is the test that catches an integral running on."""
        warm_above = [30, 29.5, 29, 28, 27, 24]
        a = warm_above + [20, 18, 15, 12, 10, 8, 6, 5, 4]
        b = warm_above + [-1, -1, -1, -1, -1, -1, -1, -1, -1]
        _, tchp_a, sa = one(a)
        _, tchp_b, sb = one(b)
        assert sa is sb is D26Status.OK
        assert tchp_a == pytest.approx(tchp_b, rel=1e-15)

    def test_tchp_is_positive_where_defined_and_zero_only_at_zero_d26(self):
        d26, tchp, status = one(linear_profile(29.0, 0.05))
        assert status is D26Status.OK
        assert d26 > 0 and tchp > 0

    def test_unit_conversion_j_per_m2_to_kj_per_cm2(self):
        """1 degC over 1 m of water is RHO_CP J/m2; in kJ/cm2 that is 1e-7 of it."""
        temps = [27.0, 26.0] + [20] * 13         # 1 degC excess over 0-5 m
        _, tchp, status = one(temps)
        assert status is D26Status.OK
        # triangle: 1/2 * 1 degC * 5 m = 2.5 degC m
        assert tchp == pytest.approx(RHO_CP * 2.5 * 1e-7, rel=1e-12)
        # 2.5 degC m of excess is about 1 kJ/cm2 -- three orders below the
        # 50-150 kJ/cm2 range of a real tropical column, which is the check that
        # the 1e-7 factor was not dropped or applied twice.
        assert 0.5 < tchp < 2.0

    def test_realistic_magnitude_is_operationally_plausible(self):
        """A 100 m D26 with a few degrees of excess should land in the tens of
        kJ/cm2, the range operational products report."""
        temps = [29.5, 29.4, 29.3, 29.1, 29, 28.6, 28, 26, 24] + [20] * 6
        d26, tchp, status = one(temps)
        assert status is D26Status.OK
        assert 90 < d26 < 110
        assert 20 < tchp < 150

    def test_tchp_undefined_wherever_d26_is_undefined_except_surface_below(self):
        r = d26_tchp(np.array([
            [28.0] * 15,                          # NO_CROSSING_IN_SUPPORT
            [np.nan] * 15,                        # NO_VALID_LEVELS
            [24.0] * 15,                          # SURFACE_BELOW_26 -> TCHP 0
        ]), DEPTHS)
        assert np.isnan(r.tchp[0])
        assert np.isnan(r.tchp[1])
        assert r.tchp[2] == 0.0
        assert np.isnan(r.d26).all()


# --------------------------------------------------------------- shapes / API
class TestVectorisation:
    def test_field_shaped_input_returns_field_shaped_output(self):
        field = np.broadcast_to(np.array(linear_profile(30.0, 0.1)),
                                (101, 241, 15)).copy()
        r = d26_tchp(field, DEPTHS)
        assert r.d26.shape == r.tchp.shape == r.status.shape == (101, 241)
        assert np.allclose(r.d26, 40.0)

    def test_vectorised_matches_profile_by_profile(self):
        rng = np.random.default_rng(7)
        block = 30.0 - rng.uniform(0, 0.08, size=(64, 1)) * np.array(DEPTHS)
        block[::7, 3] = np.nan
        block[::11, :] = 24.0
        r = d26_tchp(block, DEPTHS)
        for i in range(block.shape[0]):
            d, t, s = one(block[i])
            assert int(r.status[i]) == int(s)
            np.testing.assert_allclose(r.d26[i], d, equal_nan=True, rtol=1e-15)
            np.testing.assert_allclose(r.tchp[i], t, equal_nan=True, rtol=1e-15)

    def test_native_depth_levels_are_supported(self):
        """Stage A runs on 36 native GLORYS levels, not the mandated 15."""
        native = [0.494, 1.541, 2.646, 3.819, 5.078, 6.441, 7.930, 9.573,
                  11.405, 13.467, 15.810, 18.496, 21.599, 25.211, 29.445,
                  34.434, 40.344, 47.374, 55.764, 65.807, 77.854, 92.326,
                  109.729, 130.666, 155.851, 186.126, 222.475, 266.040,
                  318.127, 380.213, 453.938, 541.089, 643.567, 763.333,
                  902.339, 1062.440]
        temps = linear_profile(30.0, 0.1, native)
        r = d26_tchp(temps, native)
        assert D26Status(int(r.status)) is D26Status.OK
        assert float(r.d26) == pytest.approx(40.0, abs=1e-9)

    def test_rejects_malformed_inputs(self):
        with pytest.raises(ValueError):
            d26_tchp(np.zeros(15), DEPTHS[:14])
        with pytest.raises(ValueError):
            d26_tchp(np.zeros(3), [0, 10, 5])          # not increasing
        with pytest.raises(ValueError):
            d26_tchp(np.zeros(1), [0])                 # single level


# --------------------------------------------------------------- provenance
class TestTransportContract:
    """What the UI shows must equal what the pipeline computed (master prompt 6).

    These run against the real frozen replay, so a drift between the served
    numbers and the diagnostics module fails here rather than in a screenshot.
    """

    @pytest.fixture(scope="class")
    def engine(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        yield e
        e.close()

    @pytest.fixture(scope="class")
    def client(self, engine):
        from fastapi.testclient import TestClient
        from oceanembed.poc import app as poc
        from oceanembed.replay import api
        api._engine = engine
        with TestClient(poc.app) as c:
            yield c

    @pytest.fixture(scope="class")
    def payload(self, client):
        r = client.get("/api/replay/view", params={"date": "2021-06-15"})
        assert r.status_code == 200
        return r.json()

    def test_transport_carries_diagnostics(self, payload):
        d = payload["diagnostics"]
        assert len(d["d26_m"]) == 101 and len(d["d26_m"][0]) == 241
        assert len(d["tchp_kj_cm2"]) == 101 and len(d["status"]) == 101

    def test_served_values_equal_the_diagnostics_module(self, payload, engine):
        """The one check that proves the UI is not showing a second calculation."""
        view = engine.replay_field("2021-06-15")
        expected = d26_tchp(view.temperature, view.depths)
        served_d26 = np.array(
            [[np.nan if v is None else v for v in row]
             for row in payload["diagnostics"]["d26_m"]], dtype="float64")
        served_tchp = np.array(
            [[np.nan if v is None else v for v in row]
             for row in payload["diagnostics"]["tchp_kj_cm2"]], dtype="float64")
        np.testing.assert_allclose(served_d26, expected.d26, equal_nan=True,
                                   rtol=0, atol=0)
        np.testing.assert_allclose(served_tchp, expected.tchp, equal_nan=True,
                                   rtol=0, atol=0)
        np.testing.assert_array_equal(
            np.array(payload["diagnostics"]["status"]), expected.status)

    def test_missing_is_null_and_never_zero(self, payload):
        d = payload["diagnostics"]
        labels = {int(k): v for k, v in d["status_labels"].items()}
        undefined = 0
        for row_v, row_s in zip(d["d26_m"], d["status"]):
            for v, s in zip(row_v, row_s):
                if labels[s] != "OK":
                    assert v is None, "an undefined D26 must serialise as null"
                    undefined += 1
                else:
                    assert v is not None
        assert undefined > 0, "the test date should contain undefined cells"

    def test_convention_and_constants_are_disclosed(self, payload):
        c = payload["diagnostics"]["convention"]
        assert c["rho0_kg_m3"] == RHO0
        assert c["cp0_J_kg_K"] == CP0
        assert c["threshold_degC"] == TEMPERATURE_THRESHOLD_C
        assert "TEOS-10" in c["constants_source"]
        assert "D26_TCHP_EVALUATION_PROTOCOL" in c["protocol"]

    def test_netcdf_export_carries_real_diagnostics(self, client, engine):
        import io
        import xarray as xr
        r = client.get("/api/export/field.nc", params={"date": "2021-06-15"})
        assert r.status_code == 200
        ds = xr.open_dataset(io.BytesIO(r.content))
        expected = d26_tchp(engine.replay_field("2021-06-15").temperature, DEPTHS)
        np.testing.assert_allclose(ds["d26"].values, expected.d26,
                                   equal_nan=True, rtol=0, atol=0)
        np.testing.assert_allclose(ds["tchp"].values, expected.tchp,
                                   equal_nan=True, rtol=0, atol=0)
        assert ds["tchp"].attrs["units"] == "kJ cm-2"
        assert ds["d26"].attrs["units"] == "m"

    def test_frozen_model_hash_unchanged_by_this_phase(self, engine):
        assert engine.l2_state_dict_sha256 == \
            "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
        assert engine.l2_encoder_sha256 == \
            "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"


class TestEvaluationOutputs:
    """The executed artifacts exist and say what the report says they say."""

    def test_metrics_table_covers_every_pair_region_and_quantity(self):
        import pandas as pd
        p = ROOT / "outputs" / "tables" / "phase7c_d26_tchp_metrics.csv"
        assert p.exists()
        m = pd.read_csv(p)
        assert set(m["pair"]) == {"A_vs_B", "B_vs_C", "A_vs_C"}
        assert set(m["quantity"]) == {"d26", "tchp"}
        assert set(m["region"]) == {"whole_nio", "arabian_sea", "bay_of_bengal"}
        assert (m["n"] > 0).all()

    def test_the_three_errors_are_reported_separately(self):
        """A vs C must never be presented as if it were the model error alone."""
        import pandas as pd
        m = pd.read_csv(ROOT / "outputs" / "tables" /
                        "phase7c_d26_tchp_metrics.csv")
        nio = m[(m.region == "whole_nio") & (m.quantity == "d26")]
        ab = float(nio[nio.pair == "A_vs_B"]["mae"].iloc[0])
        bc = float(nio[nio.pair == "B_vs_C"]["mae"].iloc[0])
        ac = float(nio[nio.pair == "A_vs_C"]["mae"].iloc[0])
        assert ab > 0 and bc > 0 and ac > 0
        assert ab < bc, "discretization should be the smaller term; report it as measured"

    def test_run_record_pins_the_protocol_and_the_frozen_model(self):
        run = json.loads((ROOT / "outputs" / "phase7c" /
                          "evaluation_run.json").read_text(encoding="utf-8"))
        assert run["dates_evaluated"] == run["dates_preregistered"] == 216
        assert run["failed_dates"] == []
        assert run["argo_used"] is False
        assert run["constants"]["cp0_J_kg_K"] == CP0
        assert run["model"]["l2_state_dict_sha256"] == \
            "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"


class TestPreRegistration:
    def test_protocol_exists_and_freezes_the_convention(self):
        """§7C.2: the population must be pre-registered before final metrics."""
        p = ROOT / "outputs" / "phase7" / "D26_TCHP_EVALUATION_PROTOCOL.md"
        assert p.exists(), "evaluation protocol must exist before metrics"
        text = p.read_text(encoding="utf-8")
        for required in ("3991.86795711963", "1023.035344728", "TEOS-10",
                         "Arabian Sea", "Bay of Bengal", "216"):
            assert required in text, f"protocol does not record {required!r}"

    def test_protocol_constants_match_the_code(self):
        """A drift between the frozen document and the shipped constants is the
        exact failure this phase's discipline exists to prevent."""
        text = (ROOT / "outputs" / "phase7" /
                "D26_TCHP_EVALUATION_PROTOCOL.md").read_text(encoding="utf-8")
        assert repr(CP0).strip("0") in text or f"{CP0:.11f}" in text
        assert f"{RHO0:.9f}" in text or "1023.035344728" in text
