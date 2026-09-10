"""Phase 7C corrective pass — physical water-column support.

The risks these target: a temperature or diagnostic presented over water that
does not exist; a second, competing bathymetry implementation drifting from the
one the 3D view uses; a raw L2 value being edited instead of qualified; the
frozen Phase 7C evaluation being silently rerun or overwritten; and the
distinct validity concepts (land, missing input, missing climatology, no
isotherm, no water column) being collapsed into one another.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.diagnostics import (D26Status, PHYSICAL_SUPPORT_RULE,  # noqa: E402
                                    PhysicalSupport, ThermalResult,
                                    bathymetry_provenance, d26_tchp,
                                    depth_physically_valid, local_water_depth,
                                    qualify)
from oceanembed.replay.contract import DEPTHS  # noqa: E402

BATHY_DIR = ROOT / "web" / "public" / "assets" / "bathymetry"


def thermal(status, d26, tchp) -> ThermalResult:
    return ThermalResult(np.array(d26, dtype="float64"),
                         np.array(tchp, dtype="float64"),
                         np.array(status, dtype="int8"))


# ------------------------------------------------------- one physical truth
class TestSingleSourceOfTruth:
    def test_backend_reads_the_same_artifact_the_3d_view_reads(self):
        """Not a second bathymetry implementation - a second reader of one file."""
        raw = (BATHY_DIR / "depth.bin").read_bytes()
        meta = json.loads((BATHY_DIR / "metadata.json").read_text(encoding="utf-8"))
        assert hashlib.sha256(raw).hexdigest() == meta["depthSha256"]
        depth = local_water_depth()
        np.testing.assert_array_equal(
            depth, np.frombuffer(raw, dtype="<f8").reshape(101, 241))

    def test_canonical_grid_and_sign(self):
        depth = local_water_depth()
        assert depth.shape == (101, 241)
        finite = depth[np.isfinite(depth)]
        assert (finite >= 0).all(), "water depth is positive-down metres"
        assert finite.max() > 3000, "the deep basins must survive the regrid"

    def test_provenance_is_stateable(self):
        p = bathymetry_provenance()
        assert p["available"] is True
        assert "ETOPO" in p["dataset"]
        assert p["rule"] == PHYSICAL_SUPPORT_RULE
        assert "climatology_defined" in p["not_bathymetry_note"]
        assert "cell centres" in p["sampling_caveat"]


# ------------------------------------------------------- the depth rule
class TestDepthValidity:
    def test_footprint_contracts_monotonically_with_depth(self):
        depth = local_water_depth()
        ocean = np.isfinite(depth) & (depth > 0)
        counts = [int(depth_physically_valid(d, depth, ocean).sum()) for d in DEPTHS]
        assert counts == sorted(counts, reverse=True)
        assert counts[-1] < counts[0], "1000 m must cover less ocean than 0 m"
        assert counts[-1] > 0

    def test_exact_boundary_is_inclusive(self):
        depth = np.array([[100.0]])
        assert depth_physically_valid(100, depth)[0, 0]
        assert depth_physically_valid(99.9, depth)[0, 0]
        assert not depth_physically_valid(100.1, depth)[0, 0]

    def test_shallow_shelf_fails_at_depth_but_passes_at_surface(self):
        depth = np.array([[45.0]])
        assert depth_physically_valid(0, depth)[0, 0]
        assert depth_physically_valid(30, depth)[0, 0]
        assert not depth_physically_valid(100, depth)[0, 0]
        assert not depth_physically_valid(1000, depth)[0, 0]

    def test_missing_bathymetry_fails_closed(self):
        """Never assume support. An unverified cell is not a supported cell."""
        assert not depth_physically_valid(0, None, np.ones((2, 2), bool)).any()
        assert not depth_physically_valid(0, np.array([[np.nan]]))[0, 0]

    def test_land_is_excluded(self):
        depth = np.array([[3000.0, 3000.0]])
        ocean = np.array([[True, False]])
        got = depth_physically_valid(1000, depth, ocean)
        assert got[0, 0] and not got[0, 1]

    def test_independent_of_climatology(self):
        """climatology_defined is L0 coefficient availability, not the seabed."""
        depth = np.array([[2000.0]])
        # No climatology argument exists on this API at all, by design.
        assert depth_physically_valid(1000, depth)[0, 0]


class TestPhysicalIsNotDisplay:
    """The distinction this contract exists to protect.

    A deep cell whose surface input is missing is STILL deep water. Its reason
    for not being drawn is MISSING INPUT, never BELOW SEAFLOOR. Merging the two
    would make the map lie about why a cell is blank, and would make a satellite
    outage look like bathymetry.
    """

    deep = np.array([[3000.0]])
    ocean = np.array([[True]])
    no_input = np.array([[False]])
    has_input = np.array([[True]])

    def test_depth_physically_valid_takes_no_surface_input_argument(self):
        """Structural: the conflation cannot be reintroduced by passing it."""
        import inspect
        params = inspect.signature(depth_physically_valid).parameters
        assert "surface_input_valid" not in params
        assert list(params) == ["depth_m", "water_depth", "ocean_mask"]

    def test_deep_water_stays_physically_deep_without_surface_input(self):
        assert depth_physically_valid(1000, self.deep, self.ocean)[0, 0]

    def test_display_excludes_it_but_physics_does_not(self):
        from oceanembed.diagnostics import display_valid
        assert depth_physically_valid(1000, self.deep, self.ocean)[0, 0]
        assert not display_valid(1000, self.deep, self.ocean, self.no_input)[0, 0]
        assert display_valid(1000, self.deep, self.ocean, self.has_input)[0, 0]

    def test_display_is_exactly_the_composition(self):
        from oceanembed.diagnostics import display_valid
        for siv in (self.no_input, self.has_input):
            for d in (100, 1000, 4000):
                expected = (depth_physically_valid(d, self.deep, self.ocean)
                            & siv.astype(bool))
                np.testing.assert_array_equal(
                    display_valid(d, self.deep, self.ocean, siv), expected)

    def test_a_shallow_cell_is_unsupported_for_a_real_bathymetric_reason(self):
        shallow = np.array([[45.0]])
        assert not depth_physically_valid(1000, shallow, self.ocean)[0, 0]

    def test_qualify_never_blames_bathymetry_for_a_missing_input(self):
        """A deep cell with no surface input has no profile, so the diagnostic
        does not exist for a NON-bathymetric reason: NOT_APPLICABLE."""
        t = thermal([D26Status.NO_VALID_LEVELS], [np.nan], [np.nan])
        d26p, tchpp = qualify(t, np.array([3000.0]))
        assert d26p[0] == PhysicalSupport.NOT_APPLICABLE
        assert tchpp[0] == PhysicalSupport.NOT_APPLICABLE
        assert d26p[0] != PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT

    def test_qualify_depends_only_on_bathymetry_for_resolved_diagnostics(self):
        """Diagnostic existence comes from the existing input/diagnostic path;
        the physical verdict comes from bathymetry alone."""
        t = thermal([D26Status.OK], [82.0], [55.0])
        assert qualify(t, np.array([3000.0]))[0][0] == PhysicalSupport.SUPPORTED
        assert qualify(t, np.array([45.0]))[0][0] == \
            PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT

    def test_rule_strings_state_the_separation(self):
        from oceanembed.diagnostics import DISPLAY_VALID_RULE
        assert "surface" not in PHYSICAL_SUPPORT_RULE
        assert "surface_input_valid" in DISPLAY_VALID_RULE
        assert PHYSICAL_SUPPORT_RULE in DISPLAY_VALID_RULE


# ------------------------------------------------------- D26 / TCHP
class TestDiagnosticQualification:
    def test_d26_below_seabed_is_unsupported(self):
        t = thermal([D26Status.OK], [82.0], [55.0])
        d26p, tchpp = qualify(t, np.array([45.0]))
        assert d26p[0] == PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT
        assert tchpp[0] == PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT

    def test_d26_above_seabed_is_supported(self):
        t = thermal([D26Status.OK], [82.0], [55.0])
        d26p, tchpp = qualify(t, np.array([300.0]))
        assert d26p[0] == PhysicalSupport.SUPPORTED
        assert tchpp[0] == PhysicalSupport.SUPPORTED

    def test_exact_equality_is_supported(self):
        t = thermal([D26Status.OK], [120.0], [70.0])
        assert qualify(t, np.array([120.0]))[0][0] == PhysicalSupport.SUPPORTED

    def test_raw_values_are_never_altered(self):
        """No clamping to the seabed, no zeroing, no fabricated crossing."""
        t = thermal([D26Status.OK], [82.0], [55.0])
        before_d26, before_tchp = t.d26.copy(), t.tchp.copy()
        qualify(t, np.array([45.0]))
        np.testing.assert_array_equal(t.d26, before_d26)
        np.testing.assert_array_equal(t.tchp, before_tchp)
        assert t.d26[0] == 82.0, "D26 must keep its Phase 7C value"

    def test_tchp_inherits_d26_verdict_rather_than_a_second_threshold(self):
        for water, expected in [(45.0, PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT),
                                (300.0, PhysicalSupport.SUPPORTED)]:
            t = thermal([D26Status.OK], [82.0], [55.0])
            d26p, tchpp = qualify(t, np.array([water]))
            assert d26p[0] == tchpp[0] == expected

    def test_surface_below_26_is_not_a_support_failure(self):
        """TCHP is exactly 0 there by definition, whatever the water depth."""
        t = thermal([D26Status.SURFACE_BELOW_26], [np.nan], [0.0])
        d26p, tchpp = qualify(t, np.array([12.0]))
        assert tchpp[0] == PhysicalSupport.SUPPORTED
        assert d26p[0] == PhysicalSupport.NOT_APPLICABLE
        assert t.tchp[0] == 0.0

    def test_other_invalid_statuses_get_no_bathymetric_verdict(self):
        for st in (D26Status.NO_CROSSING_IN_SUPPORT, D26Status.INSUFFICIENT_SUPPORT,
                   D26Status.NO_VALID_LEVELS):
            t = thermal([st], [np.nan], [np.nan])
            d26p, tchpp = qualify(t, np.array([2000.0]))
            assert d26p[0] == tchpp[0] == PhysicalSupport.NOT_APPLICABLE

    def test_unverified_when_bathymetry_missing(self):
        t = thermal([D26Status.OK, D26Status.SURFACE_BELOW_26],
                    [82.0, np.nan], [55.0, 0.0])
        d26p, tchpp = qualify(t, None)
        assert d26p[0] == PhysicalSupport.UNVERIFIED
        assert tchpp[0] == tchpp[1] == PhysicalSupport.UNVERIFIED

    def test_phase7c_statuses_are_untouched(self):
        """The frozen diagnostic enum gains no members and changes no values."""
        assert [s.name for s in D26Status] == [
            "OK", "SURFACE_BELOW_26", "NO_CROSSING_IN_SUPPORT",
            "INSUFFICIENT_SUPPORT", "NO_VALID_LEVELS"]
        assert [int(s) for s in D26Status] == [0, 1, 2, 3, 4]

    def test_real_field_has_both_supported_and_unsupported_cells(self):
        from oceanembed.replay.engine import ReplayEngine
        engine = ReplayEngine(use_cache=False)
        try:
            view = engine.replay_field("2021-06-15")
        finally:
            engine.close()
        res = d26_tchp(view.temperature, view.depths)
        d26p, _ = qualify(res, local_water_depth())
        assert (d26p == PhysicalSupport.SUPPORTED).sum() > 1000
        assert (d26p == PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT).sum() > 0
        # And the unsupported ones really are below the seabed.
        bad = d26p == PhysicalSupport.INSUFFICIENT_WATER_COLUMN_SUPPORT
        assert np.all(res.d26[bad] > local_water_depth()[bad])


# ------------------------------------------------------- transport / export
class TestTransport:
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

    def test_existing_fields_are_not_broken(self, payload):
        for key in ("schema", "date", "shape", "lat", "lon", "depths_m",
                    "temperature", "climatology", "anomaly", "ocean_mask",
                    "surface_input_valid", "climatology_defined",
                    "surface_inputs", "provenance", "credits", "diagnostics"):
            assert key in payload, f"{key} disappeared from the transport"
        assert payload["schema"] == "oceanembed.field-view.v1"

    def test_physical_status_served_and_matches_backend(self, payload, engine):
        view = engine.replay_field("2021-06-15")
        expected_d26, expected_tchp = qualify(
            d26_tchp(view.temperature, view.depths), local_water_depth())
        np.testing.assert_array_equal(
            np.array(payload["diagnostics"]["d26_physical_status"]), expected_d26)
        np.testing.assert_array_equal(
            np.array(payload["diagnostics"]["tchp_physical_status"]), expected_tchp)

    def test_bathymetry_block_is_complete(self, payload):
        b = payload["bathymetry"]
        assert b["available"] is True
        assert b["rule"] == PHYSICAL_SUPPORT_RULE
        assert "surface" not in b["rule"]
        assert "surface_input_valid" in b["display_rule"]
        assert "BELOW SEAFLOOR" in b["separation_note"]
        assert len(b["local_water_depth_m"]) == 101
        assert len(b["local_water_depth_m"][0]) == 241
        counts = b["depth_physically_valid_counts"]
        assert [counts[str(d)] for d in DEPTHS] == \
            sorted([counts[str(d)] for d in DEPTHS], reverse=True)

    def test_physical_and_display_counts_are_reported_separately(self, payload):
        """Physical support cannot be smaller than what is actually drawn."""
        b = payload["bathymetry"]
        physical = b["depth_physically_valid_counts"]
        shown = b["display_valid_counts"]
        for d in DEPTHS:
            assert shown[str(d)] <= physical[str(d)], (
                f"at {d} m more cells are drawn than have water under them")
        # On a real date some deep cells genuinely lack surface input, so the
        # two counts must not be identical - that is the whole distinction.
        assert any(shown[str(d)] < physical[str(d)] for d in DEPTHS)

    def test_exported_physical_validity_excludes_only_bathymetry(self, client, engine):
        """A deep cell with no surface input stays 1 in depth_physically_valid."""
        import io
        import xarray as xr
        r = client.get("/api/export/field.nc", params={"date": "2021-06-15"})
        ds = xr.open_dataset(io.BytesIO(r.content))
        water = local_water_depth()
        siv = ds["surface_input_valid"].values.astype(bool)
        ocean = ds["ocean_mask"].values.astype(bool)
        deep_no_input = ocean & ~siv & np.isfinite(water) & (water >= 1000)
        assert deep_no_input.any(), "the test date should contain such cells"
        k = DEPTHS.index(1000)
        assert ds["depth_physically_valid"].values[:, :, k][deep_no_input].all(), \
            "deep water with a missing input must not be labelled below-seafloor"

    def test_served_bathymetry_equals_the_frontend_asset(self, payload):
        """The API array and the file the browser loads must be one truth."""
        raw = np.frombuffer((BATHY_DIR / "depth.bin").read_bytes(),
                            dtype="<f8").reshape(101, 241)
        served = np.array([[np.nan if v is None else v for v in row]
                           for row in payload["bathymetry"]["local_water_depth_m"]])
        np.testing.assert_allclose(served, raw, equal_nan=True, rtol=0, atol=0)

    def test_raw_temperature_transport_is_unchanged(self, payload, engine):
        """Qualification must not have edited a single model value."""
        view = engine.replay_field("2021-06-15")
        served = np.array([[[np.nan if v is None else v for v in col]
                            for col in row] for row in payload["temperature"]])
        np.testing.assert_allclose(served, view.temperature, equal_nan=True,
                                   rtol=0, atol=0)

    def test_export_carries_support_beside_the_raw_values(self, client, engine):
        import io
        import xarray as xr
        r = client.get("/api/export/field.nc", params={"date": "2021-06-15"})
        assert r.status_code == 200
        ds = xr.open_dataset(io.BytesIO(r.content))
        view = engine.replay_field("2021-06-15")
        # raw preserved
        np.testing.assert_allclose(ds["temperature"].values, view.temperature,
                                   equal_nan=True, rtol=0, atol=0)
        # support alongside
        for name in ("local_water_depth", "depth_physically_valid",
                     "d26_physical_status", "tchp_physical_status"):
            assert name in ds, f"{name} missing from the export"
        assert ds["depth_physically_valid"].shape == (101, 241, 15)
        assert ds["local_water_depth"].attrs["units"] == "m"
        assert "not climatology_defined" in ds["local_water_depth"].attrs["description"]
        counts = [int(ds["depth_physically_valid"].values[:, :, k].sum())
                  for k in range(15)]
        assert counts == sorted(counts, reverse=True)


# ------------------------------------------------------- frozen artifacts
class TestFrozenPhase7C:
    def test_original_metrics_table_is_unchanged(self):
        """The preregistered A/B/C experiment must not be rerun or overwritten."""
        import pandas as pd
        m = pd.read_csv(ROOT / "outputs" / "tables" / "phase7c_d26_tchp_metrics.csv")
        nio = m[m.region == "whole_nio"].set_index(["quantity", "pair"])["mae"]
        assert round(float(nio[("d26", "A_vs_B")]), 2) == 1.26
        assert round(float(nio[("d26", "B_vs_C")]), 2) == 9.24
        assert round(float(nio[("d26", "A_vs_C")]), 2) == 9.69
        assert round(float(nio[("tchp", "A_vs_B")]), 2) == 1.70
        assert round(float(nio[("tchp", "B_vs_C")]), 2) == 11.47
        assert round(float(nio[("tchp", "A_vs_C")]), 2) == 12.40

    def test_original_run_record_is_unchanged(self):
        run = json.loads((ROOT / "outputs" / "phase7c" / "evaluation_run.json")
                         .read_text(encoding="utf-8"))
        assert run["dates_evaluated"] == 216 and run["failed_dates"] == []
        assert run["argo_used"] is False
        assert run["argo_2024_status"].startswith("PROTECTED")

    def test_original_status_counts_and_protocol_still_present(self):
        for rel in ("outputs/tables/phase7c_d26_tchp_status_counts.csv",
                    "outputs/tables/phase7c_d26_crossing_disagreement.csv",
                    "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md"):
            assert (ROOT / rel).exists(), f"{rel} must not be removed"
        # The corrective pass introduces no bathymetric rule into the frozen
        # protocol; that document describes the experiment as it was run.
        protocol = (ROOT / "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md"
                    ).read_text(encoding="utf-8")
        assert "ETOPO" not in protocol

    def test_original_figures_still_present(self):
        figs = ROOT / "outputs" / "figures" / "phase7c"
        for name in ("01_d26_three_stages.png", "02_tchp_three_stages.png",
                     "03_error_attribution.png", "04_representative_profile.png"):
            assert (figs / name).exists()


# ------------------------------------------------------- frozen core
class TestNothingScientificMoved:
    def test_frozen_hashes_unchanged(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            assert e.l2_state_dict_sha256 == \
                "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
            assert e.l2_encoder_sha256 == \
                "30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808"
        finally:
            e.close()

    def test_no_argo_is_read_by_the_support_path(self):
        import oceanembed.diagnostics.bathymetry as b
        source = Path(b.__file__).read_text(encoding="utf-8").lower()
        assert "argo" not in source
        assert "2024" not in source

    def test_diagnostics_package_never_imports_replay_transport(self):
        """Support stays a function of a profile and a depth, not of a wire format."""
        import oceanembed.diagnostics.bathymetry as b
        source = Path(b.__file__).read_text(encoding="utf-8")
        assert "from ..replay" not in source and "import replay" not in source
