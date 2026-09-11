"""Phase 8B: the authoritative latest qualified field path.

The live providers are replaced by fetchers that serve the hindcast's own
on-disk NRT fields, so every test is offline and deterministic. That also makes
the strongest check possible: a "latest" field for a hindcast date must equal
the hindcast's N for that date, because both go through the same inference.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import xarray as xr  # noqa: E402

from oceanembed.nrt import latest as LQ  # noqa: E402
from oceanembed.replay.contract import DEPTHS  # noqa: E402
from oceanembed.replay.engine import ReplayEngine  # noqa: E402

NRT = ROOT / "data" / "processed" / "nrt"
HINDCAST_CACHE = ROOT / "data" / "interim" / "phase8b_hindcast"
DAY = pd.Timestamp("2024-12-13")
L2 = "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"

pytestmark = pytest.mark.skipif(
    not all((NRT / f"{k}_canonical.nc").exists() for k in LQ.PRODUCT_CHANNELS),
    reason="hindcast NRT fields not present locally")


@pytest.fixture(scope="module")
def engine():
    e = ReplayEngine()
    yield e
    e.close()


@pytest.fixture(scope="module")
def canonical():
    out = {}
    for k in LQ.PRODUCT_CHANNELS:
        d = xr.open_dataset(NRT / f"{k}_canonical.nc")
        d = d.assign_coords(time=pd.DatetimeIndex(d.time.values).normalize())
        out[k] = d.sel(time=[DAY]).load()
        d.close()
    return out


def poll_ok(key):
    return {"success": True, "newest_valid_time": DAY + pd.Timedelta(hours=23),
            "error": None}


class Calls:
    def __init__(self):
        self.n = 0


def make_fetchers(canonical, calls=None, override=None):
    override = override or {}

    def fetch(key):
        def f(day, workdir):
            if calls is not None:
                calls.n += 1
            if key in override:
                return override[key](canonical[key])
            return canonical[key]
        return f
    return {k: fetch(k) for k in LQ.PRODUCT_CHANNELS}


@pytest.fixture()
def no_infer(engine, monkeypatch):
    """Fail loudly if inference is reached on a path that must refuse."""
    def boom(*a, **k):
        raise AssertionError("inference ran on a stack that must be refused")
    monkeypatch.setattr(engine, "_infer", boom)


# ------------------------------------------------------------- same path
class TestSameInferencePath:
    def test_latest_equals_the_hindcast_field_for_that_date(self, engine, canonical,
                                                             tmp_path):
        cached = HINDCAST_CACHE / f"N_{DAY.date()}.npy"
        if not cached.exists():
            pytest.skip("hindcast cache not present")
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        n = np.load(cached).astype("float64")
        t = r.view.temperature
        assert np.array_equal(np.isnan(t), np.isnan(n))
        assert np.nanmax(np.abs(t - n)) < 1e-4      # float32 cache precision

    def test_field_contract(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        v = r.view
        assert v.temperature.shape == (101, 241, 15)
        assert v.depths == DEPTHS
        both = np.isfinite(v.temperature) & np.isfinite(v.climatology)
        assert np.allclose(v.anomaly[both], (v.temperature - v.climatology)[both])
        assert v.provenance["operating_mode"] == LQ.OPERATING_MODE
        assert v.provenance["l2_state_dict_sha256"] == L2

    def test_point_profile_is_a_sample_of_the_field(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        row, col = map(int, np.argwhere(r.view.surface_input_valid)[100])
        prof = r.view.profile_at(row, col)["prediction_c"]
        assert np.array_equal(prof, r.view.temperature[row, col, :])


# ------------------------------------------------------------- refusals
class TestRefusals:
    def test_not_qualified_decision_refuses_before_any_retrieval(
            self, engine, canonical, tmp_path, no_infer):
        d = json.loads(LQ.DECISION_PATH.read_text(encoding="utf-8"))
        d["temperature_category"] = "NOT QUALIFIED"
        p = tmp_path / "decision.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        calls = Calls()
        with pytest.raises(LQ.LatestRefused, match="not qualified"):
            LQ.latest_qualified_field(engine, make_fetchers(canonical, calls),
                                      poll_ok, decision_path=p, workdir=tmp_path)
        assert calls.n == 0

    def test_missing_sss_refuses_with_no_fallback(self, engine, canonical, tmp_path,
                                                  no_infer):
        def dead(_):
            raise OSError("provider unreachable")
        with pytest.raises(LQ.LatestRefused) as exc:
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sss_nrt_multiobs": dead}),
                poll_ok, workdir=tmp_path)
        assert any("sss" in r for r in exc.value.reasons)
        states = {s["product_key"]: s["state"] for s in exc.value.sources}
        assert states["sss_nrt_multiobs"] == "UNREACHABLE"
        assert states["sst_nrt"] == "OK"      # the others still reported honestly

    @pytest.mark.parametrize("key", list(LQ.PRODUCT_CHANNELS))
    def test_any_single_missing_product_blocks_inference(self, engine, canonical,
                                                         tmp_path, no_infer, key):
        def dead(_):
            raise OSError("down")
        with pytest.raises(LQ.LatestRefused):
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={key: dead}), poll_ok,
                workdir=tmp_path)

    def test_channel_on_a_different_date_is_refused(self, engine, canonical, tmp_path,
                                                    no_infer):
        def shifted(ds):
            return ds.assign_coords(time=[DAY - pd.Timedelta(days=1)])
        with pytest.raises(LQ.LatestRefused) as exc:
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sst_nrt": shifted}),
                poll_ok, workdir=tmp_path)
        assert any(s["state"] == "NOT_ON_COMMON_DATE" for s in exc.value.sources)

    def test_low_coverage_is_refused(self, engine, canonical, tmp_path, no_infer):
        def holed(ds):
            ds = ds.copy(deep=True)
            ds["sst"][:, :60, :] = np.nan
            return ds
        with pytest.raises(LQ.LatestRefused, match="L4"):
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sst_nrt": holed}),
                poll_ok, workdir=tmp_path)

    def test_poll_failure_means_no_common_date(self, engine, canonical, tmp_path,
                                               no_infer):
        def poll(key):
            if key == "currents_nrt":
                return {"success": False, "error": "OSError: timed out"}
            return poll_ok(key)
        calls = Calls()
        with pytest.raises(LQ.LatestRefused, match="no common valid date"):
            LQ.latest_qualified_field(engine, make_fetchers(canonical, calls), poll,
                                      workdir=tmp_path)
        assert calls.n == 0

    def test_auth_failure_is_not_reported_as_an_outage(self):
        assert LQ._state_from_error("HTTPError: 401 Unauthorized") == "AUTH_FAILED"
        assert LQ._state_from_error("OSError: timed out") == "UNREACHABLE"


# ------------------------------------------------------------- alignment
class TestTemporalAlignment:
    def test_common_date_is_the_slowest_product(self):
        newest = {"sst_nrt": "2026-09-10", "sss_nrt_multiobs": "2026-09-05",
                  "sla_nrt": "2026-09-10", "currents_nrt": "2026-09-08",
                  "wind_nrt": "2026-09-10T23:00"}

        def poll(key):
            return {"success": True, "newest_valid_time": pd.Timestamp(newest[key])}
        day, _ = LQ.resolve_common_date(poll)
        assert day == pd.Timestamp("2026-09-05")

    def test_wind_day_counts_only_once_complete(self):
        assert LQ._complete_day("wind_nrt", pd.Timestamp("2026-09-10T22:00")) == \
            pd.Timestamp("2026-09-09")
        assert LQ._complete_day("wind_nrt", pd.Timestamp("2026-09-10T23:00")) == \
            pd.Timestamp("2026-09-10")
        assert LQ._complete_day("sst_nrt", pd.Timestamp("2026-09-10T12:00")) == \
            pd.Timestamp("2026-09-10")

    def test_provenance_keeps_every_clock_separate(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        for s in r.sources:
            assert s["product_valid_time"] == DAY.isoformat()
            assert s["local_retrieval_time"] and s["local_retrieval_time"] != \
                s["product_valid_time"]
            assert s["age_hours"] > 0
        m = r.meta
        assert m["persisted_inputs"].startswith("none")
        assert m["oldest_input_age_hours"] >= m["newest_input_age_hours"]
        assert m["reconstruction_lag_hours"] > 0
        assert m["policy"]["persistence_envelope_days"] == 0
        assert m["d26_category"] == "NOT QUALIFIED"


# ------------------------------------------------------------- snapshot
class TestSnapshot:
    def test_roundtrip_is_exact_and_labelled(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        LQ.save_snapshot(r, tmp_path / "snap")
        s = LQ.load_snapshot(engine, tmp_path / "snap")
        assert np.array_equal(s.view.temperature, r.view.temperature, equal_nan=True)
        assert s.view.provenance["inference_source"] == \
            "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT"
        assert s.meta["snapshot_staleness_hours"] is not None
        ident = s.meta["identity"]
        for k in ("l2_state_dict_sha256", "feature_scaler_sha256", "processing_version",
                  "grid_version", "policy_version", "source_products",
                  "source_valid_times", "source_ages_hours", "persisted_inputs",
                  "effective_date", "decision_sha256"):
            assert k in ident, k

    def test_only_a_live_qualified_run_can_become_a_snapshot(self, engine, canonical,
                                                             tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        LQ.save_snapshot(r, tmp_path / "a")
        s = LQ.load_snapshot(engine, tmp_path / "a")
        with pytest.raises(ValueError):
            LQ.save_snapshot(s, tmp_path / "b")

    def test_snapshot_is_invalid_once_the_decision_changes(self, engine, canonical,
                                                           tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical), poll_ok,
                                      workdir=tmp_path)
        LQ.save_snapshot(r, tmp_path / "snap")
        other = tmp_path / "decision.json"
        shutil.copy(LQ.DECISION_PATH, other)
        other.write_text(other.read_text(encoding="utf-8") + " ", encoding="utf-8")
        assert LQ.load_snapshot(engine, tmp_path / "snap", decision_path=other) is None


# ------------------------------------------------------------- API
@pytest.fixture()
def client(engine, canonical, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from oceanembed.poc import app as A
    from oceanembed.replay import api as replay_api
    monkeypatch.setattr(replay_api, "engine", lambda: engine)
    monkeypatch.setattr(LQ, "poll_product", poll_ok)
    monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(canonical))
    monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
    monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")
    return TestClient(A.app)


def _fail(monkeypatch, canonical):
    def dead(_):
        raise OSError("network deliberately down")
    monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(
        canonical, override={k: dead for k in LQ.PRODUCT_CHANNELS}))


class TestApi:
    def test_qualification_drives_the_tab_name(self, client):
        q = client.get("/api/latest/qualification").json()
        assert q["qualified"] is True
        assert q["temperature_category"] == "QUALIFIED WITH LIMITATIONS"
        assert q["tab_name"] == "Latest Qualified Ocean State"
        assert q["d26_category"] == "NOT QUALIFIED"
        assert any("observational" in x for x in q["limitations"])
        # Hardening: qualification, timeliness, D26/TCHP and hazard transfer are
        # stated as separate claims, and none widens a frozen category.
        assert "Operational timeliness has not been separately certified" in \
            q["timeliness_note"]
        assert "not exposed as a qualified D26 product" in q["d26_tchp_explanation"]
        assert "not observationally validated as a cyclone forecast" in \
            q["hazard_transfer_note"]
        for note in (q["timeliness_note"], q["d26_tchp_explanation"],
                     q["hazard_transfer_note"]):
            assert note in q["limitations"]

    def test_live_payload_uses_the_historical_transport(self, client):
        p = client.get("/api/latest/qualified").json()
        assert p["state"] == LQ.LIVE_STATE
        f = p["field"]
        assert f["schema"] == "oceanembed.field-view.v1"
        assert f["shape"] == [101, 241, 15]
        assert f["depths_m"] == DEPTHS
        # D26 is withheld: no value anywhere. TCHP is qualified and present.
        assert f["diagnostics"]["withheld"] == ["d26"]
        assert all(v is None for row in f["diagnostics"]["d26_m"] for v in row)
        assert any(v is not None for row in f["diagnostics"]["tchp_kj_cm2"] for v in row)
        assert "does not predict" in f["hazard"]["non_prediction_statement"].lower()
        assert f["hazard"]["scope_note"].startswith(
            "Latest qualified mode. Qualified by transfer from the frozen TCHP rule; "
            "not observationally validated as a cyclone forecast.")
        assert "probability" not in json.dumps(f["hazard"]["category_counts"]).lower()
        assert f["provenance"]["operating_mode"] == LQ.OPERATING_MODE
        assert set(f["surface_inputs"]) == {"sst", "sss", "sla", "current_u",
                                            "current_v", "wind_u", "wind_v"}

    def test_refusal_serves_the_snapshot_labelled_not_current(self, client,
                                                             monkeypatch, canonical):
        assert client.get("/api/latest/qualified").json()["state"] == LQ.LIVE_STATE
        _fail(monkeypatch, canonical)
        p = client.get("/api/latest/qualified").json()
        assert p["state"] == LQ.SNAPSHOT_STATE
        assert "NOT CURRENT" in p["label"]
        assert p["live_attempt"]["attempted"] is True and p["live_attempt"]["reasons"]
        assert p["field"]["provenance"]["inference_source"] == \
            "LAST_SUCCESSFUL_QUALIFIED_SNAPSHOT"

    def test_no_snapshot_means_informative_unavailable(self, client, monkeypatch,
                                                       canonical):
        _fail(monkeypatch, canonical)
        p = client.get("/api/latest/qualified").json()
        assert p["state"] == LQ.UNAVAILABLE_STATE
        assert p["label"] == "LATEST QUALIFIED OCEAN STATE CURRENTLY UNAVAILABLE"
        assert p["field"] is None

    def test_recovery_without_restart(self, client, monkeypatch, canonical):
        _fail(monkeypatch, canonical)
        assert client.get("/api/latest/qualified").json()["state"] == LQ.UNAVAILABLE_STATE
        monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(canonical))
        p = client.get("/api/latest/qualified").json()
        assert p["state"] == LQ.LIVE_STATE
        assert p["field"]["provenance"]["inference_source"] == "LIVE_MODEL_RUN"

    def test_historical_replay_unaffected_by_a_latest_failure(self, client,
                                                             monkeypatch, canonical):
        _fail(monkeypatch, canonical)
        client.get("/api/latest/qualified")
        r = client.get("/api/replay/view", params={"date": "2021-06-15"})
        assert r.status_code == 200
        assert r.json()["hazard"]["scope_note"].startswith("Historical only")

    def test_not_qualified_artifact_exposes_nothing(self, client, monkeypatch, tmp_path):
        d = json.loads(LQ.DECISION_PATH.read_text(encoding="utf-8"))
        d["temperature_category"] = "NOT QUALIFIED"
        p = tmp_path / "decision.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        monkeypatch.setattr(LQ, "DECISION_PATH", p)
        q = client.get("/api/latest/qualification").json()
        assert q["tab_name"] == "Latest Inputs" and q["qualified"] is False
        body = client.get("/api/latest/qualified").json()
        assert body["state"] == "NOT_QUALIFIED" and body["field"] is None


class TestDiscipline:
    def test_no_argo_and_no_fallbacks_in_the_latest_path(self):
        """No Argo access and no fallback. Mentioning that Argo is protected, in a
        limitation shown to the user, is required disclosure and is allowed."""
        src = (ROOT / "src/oceanembed/nrt/latest.py").read_text(encoding="utf-8").lower()
        for banned in ("outputs/argo", "data/raw/argo", "_prof.nc", "gdac",
                       "matched_profiles", "argo_"):
            assert banned not in src, banned
        for banned in ("quantile", "zero-fill", "mean-fill", "climatological sss",
                       "sss_nrt_smos", "sss_nrt_smap"):
            assert banned not in src, banned

    def test_the_frontend_never_hard_codes_the_qualified_tab_name(self):
        """The name may only arrive from the decision artifact."""
        for path in (*(ROOT / "web/src").rglob("*.tsx"), *(ROOT / "web/src").rglob("*.ts")):
            if "test" in path.parts:
                continue
            assert "Latest Qualified Ocean State" not in path.read_text(encoding="utf-8"), \
                path.name

    def test_live_ocean_right_now_wording_never_used(self):
        for rel in ("src/oceanembed/nrt/latest.py", "src/oceanembed/poc/app.py"):
            assert "Live Ocean Right Now" not in (ROOT / rel).read_text(encoding="utf-8")
