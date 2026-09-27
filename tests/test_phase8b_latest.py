"""Phase 8B: the authoritative latest qualified field path, and its date logic.

The live providers are replaced by fetchers that serve the hindcast's own
on-disk NRT fields, so every test is offline and deterministic. That also makes
the strongest check possible: a "latest" field for a hindcast date must equal
the hindcast's N for that date, because both go through the same inference.

The date-resolution tests are regressions for the 2026-09-12 follow-up, where
the newest common date must come from the INTERSECTION of what every channel
actually holds, never from `min` of the per-product newest dates.
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
DAY2 = pd.Timestamp("2024-12-10")
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
        out[k] = d.assign_coords(
            time=pd.DatetimeIndex(d.time.values).normalize()).load()
        d.close()
    return out


def dates_for(*days) -> dict:
    """Every product holds exactly these valid dates."""
    return {k: {pd.Timestamp(d).normalize() for d in days}
            for k in LQ.PRODUCT_CHANNELS}


class Calls:
    def __init__(self):
        self.n = 0


def make_fetchers(canonical, calls=None, override=None):
    override = override or {}

    def fetch(key):
        def f(day, workdir):
            if calls is not None:
                calls.n += 1
            ds = canonical[key].sel(time=[pd.Timestamp(day).normalize()])
            return override[key](ds) if key in override else ds
        return f
    return {k: fetch(k) for k in LQ.PRODUCT_CHANNELS}


@pytest.fixture()
def no_infer(engine, monkeypatch):
    """Fail loudly if inference is reached on a path that must refuse."""
    def boom(*a, **k):
        raise AssertionError("inference ran on a stack that must be refused")
    monkeypatch.setattr(engine, "_infer", boom)


@pytest.fixture(autouse=True)
def clean_discovery():
    LQ.refresh_discovery()
    yield
    LQ.refresh_discovery()


# ------------------------------------------------------------- date resolution
class TestDateResolution:
    def test_newest_common_date_is_the_intersection_not_the_min(self):
        """The 2026-09-12 regression.

        A product missing an INTERIOR day must remove that day, and a product
        whose newest day is old must not define the answer alone. `min` of the
        per-product newest dates gets the second case right by accident and the
        first case wrong.
        """
        sets = dates_for("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04")
        sets["currents_nrt"] = {pd.Timestamp("2026-09-01"),
                                pd.Timestamp("2026-09-03")}
        assert LQ.common_dates(sets) == {pd.Timestamp("2026-09-01"),
                                         pd.Timestamp("2026-09-03")}
        newest, records = LQ.resolve_common_date(sets, {})
        assert newest == pd.Timestamp("2026-09-03")
        # the interior gap is not the newest date, and is excluded
        assert pd.Timestamp("2026-09-02") not in LQ.common_dates(sets)
        assert records["currents_nrt"].newest_valid_time.startswith("2026-09-03")

    def test_one_stalled_channel_holds_the_whole_stack_back(self):
        sets = dates_for("2026-09-10", "2026-09-11", "2026-09-12")
        sets["currents_nrt"] = {pd.Timestamp("2026-09-03")}
        newest, _ = LQ.resolve_common_date(sets, {})
        assert newest is None  # 09-03 is not in the other channels' window

    def test_time_axis_order_cannot_change_the_newest_date(self, monkeypatch):
        """Ascending or descending, the newest date is the same."""
        axis = pd.to_datetime(["2026-09-03", "2026-09-01", "2026-09-02"])

        class FakeDS:
            def __init__(self, times):
                self.time = xr.DataArray(times)

            def close(self):
                pass
        for order in (axis, axis.sort_values(), axis.sort_values(ascending=False)):
            monkeypatch.setattr("copernicusmarine.open_dataset",
                                lambda dataset_id, o=order: FakeDS(o))
            LQ.refresh_discovery()
            assert max(LQ._cmems_dates("sst_nrt")) == pd.Timestamp("2026-09-03")

    def test_incomplete_wind_day_is_excluded(self, monkeypatch):
        """A day is usable only once its 23:00 field exists."""
        times = list(pd.date_range("2026-09-10", "2026-09-11 23:00", freq="h"))
        times += list(pd.date_range("2026-09-12", "2026-09-12 22:00", freq="h"))

        class FakeDS:
            time = xr.DataArray(pd.DatetimeIndex(times))

            def close(self):
                pass
        monkeypatch.setattr("copernicusmarine.open_dataset",
                            lambda dataset_id: FakeDS())
        days = LQ._cmems_dates("wind_nrt")
        assert pd.Timestamp("2026-09-11") in days
        assert pd.Timestamp("2026-09-12") not in days   # only reaches 22:00

    def test_stale_discovery_cannot_permanently_hold_the_latest_date(self, monkeypatch):
        """A cached catalogue answer must not pin the newest date forever."""
        state = {"days": {pd.Timestamp("2026-09-03")}}

        class FakeDS:
            def __init__(self, d):
                self.time = xr.DataArray(pd.DatetimeIndex(sorted(d)))

            def close(self):
                pass
        monkeypatch.setattr("copernicusmarine.open_dataset",
                            lambda dataset_id: FakeDS(state["days"]))
        assert max(LQ._cmems_dates("sst_nrt")) == pd.Timestamp("2026-09-03")
        first = LQ._cached("dates:sst_nrt", lambda: LQ._cmems_dates("sst_nrt"))
        state["days"] = {pd.Timestamp("2026-09-03"), pd.Timestamp("2026-09-12")}
        # still cached...
        assert LQ._cached("dates:sst_nrt", lambda: LQ._cmems_dates("sst_nrt")) == first
        # ...but a refresh must pick the newer date up
        LQ.refresh_discovery()
        assert max(LQ._cached("dates:sst_nrt",
                              lambda: LQ._cmems_dates("sst_nrt"))) == \
            pd.Timestamp("2026-09-12")

    def test_persisted_discovery_is_served_when_memory_is_cold(self, monkeypatch,
                                                               tmp_path):
        """A restart must not make the first caller wait for every provider."""
        f = tmp_path / "discovery.json"
        f.write_text(json.dumps({
            "generated_utc": str(pd.Timestamp.utcnow().tz_localize(None)),
            "dates": {k: ["2026-09-02", "2026-09-03"] for k in LQ.PRODUCT_CHANNELS},
            "errors": {}}), encoding="utf-8")
        monkeypatch.setattr(LQ, "DISCOVERY_FILE", f)
        monkeypatch.setattr(LQ, "_cmems_dates",
                            lambda k: pytest.fail("provider read on the fast path"))
        LQ.refresh_discovery()
        sets, errors = LQ.channel_dates()
        assert max(sets["sst_nrt"]) == pd.Timestamp("2026-09-03")
        assert LQ.DISCOVERY_AGE["from_disk"] is True

    def test_a_stale_persisted_discovery_is_not_served(self, monkeypatch, tmp_path):
        """It decides which date to ask for, so it may never be old."""
        f = tmp_path / "discovery.json"
        old = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=2)
        f.write_text(json.dumps({
            "generated_utc": str(old),
            "dates": {k: ["2026-01-01"] for k in LQ.PRODUCT_CHANNELS},
            "errors": {}}), encoding="utf-8")
        monkeypatch.setattr(LQ, "DISCOVERY_FILE", f)
        monkeypatch.setattr(LQ, "_cmems_dates", lambda k: {pd.Timestamp("2026-09-10")})
        monkeypatch.setattr(LQ, "_oscar_dates",
                            lambda a, b: {pd.Timestamp("2026-09-10")})
        LQ.refresh_discovery()
        sets, _ = LQ.channel_dates()
        assert max(sets["sst_nrt"]) == pd.Timestamp("2026-09-10")   # real read
        assert LQ.DISCOVERY_AGE["from_disk"] is False

    def test_warm_up_forces_a_real_discovery_read(self, engine, monkeypatch):
        """The warm-up is what refreshes a cold server, so it must not be
        served the persisted fast path."""
        seen = {}

        def fake(window_days=LQ.LOOKBACK_DAYS, allow_persisted=True):
            seen["allow_persisted"] = allow_persisted
            return {}, {"currents_nrt": "stopped here"}
        monkeypatch.setattr(LQ, "channel_dates", fake)
        LQ.warm_recent_states(engine, 7)
        assert seen["allow_persisted"] is False

    def test_discovery_ttl_is_bounded(self):
        assert 0 < LQ.DISCOVERY_TTL_SECONDS <= 3600


# ------------------------------------------------------------- 7-day window
class TestAvailableWindow:
    def test_window_is_ordered_deterministic_and_ends_at_the_newest(self):
        sets = dates_for(*[f"2026-09-{d:02d}" for d in range(1, 11)])
        sets["currents_nrt"] = {pd.Timestamp(f"2026-09-{d:02d}") for d in range(1, 9)}
        w1 = LQ.available_window(7, sets, {})
        w2 = LQ.available_window(7, sets, {})
        assert w1 == w2                                   # deterministic
        days = [d["date"] for d in w1["days"]]
        assert days == sorted(days) and len(days) == 7    # ordered, 7 long
        assert w1["newest_qualified_date"] == "2026-09-08"
        assert days[-1] == "2026-09-08"
        assert [d for d in w1["days"] if d["is_newest"]][0]["date"] == "2026-09-08"

    def test_unavailable_days_are_visible_and_name_the_missing_channel(self):
        sets = dates_for(*[f"2026-09-{d:02d}" for d in range(1, 9)])
        sets["currents_nrt"].discard(pd.Timestamp("2026-09-05"))
        w = LQ.available_window(7, sets, {})
        row = {d["date"]: d for d in w["days"]}["2026-09-05"]
        assert row["status"] == "UNAVAILABLE"
        assert "currents_nrt" in row["reason"] and row["missing_channels"] == ["currents_nrt"]
        # it is still listed, so the operational record stays visible
        assert "2026-09-05" in [d["date"] for d in w["days"]]

    def test_a_day_before_the_discovery_window_says_so(self):
        """Regression, 2026-09-12 live check: when a stalled channel pulls the
        newest common date back, the oldest day in the 7-day window can predate
        the discovery lookback. That must read as "not determined", never as
        "missing from every channel"."""
        sets = dates_for(*[f"2026-09-{d:02d}" for d in range(1, 4)])
        LQ._WINDOW_START["start"] = pd.Timestamp("2026-08-30")
        try:
            w = LQ.available_window(7, sets, {})
        finally:
            LQ._WINDOW_START.pop("start", None)
        rows = {d["date"]: d for d in w["days"]}
        edge = rows["2026-08-28"]
        assert edge["status"] == "UNAVAILABLE"
        assert "discovery window" in edge["reason"]
        assert edge["missing_channels"] == []          # not blamed on the providers
        # a day inside the window that a channel really lacks still names it
        inside = rows["2026-08-31"]
        assert inside["missing_channels"]

    def test_lookback_covers_the_seven_day_window_with_a_stalled_channel(self):
        assert LQ.LOOKBACK_DAYS >= 14

    def test_discovery_error_is_reported_per_channel(self):
        sets = dates_for("2026-09-01")
        del sets["currents_nrt"]
        w = LQ.available_window(3, sets, {"currents_nrt": "OSError: timed out"})
        assert w["newest_qualified_date"] is None
        assert all(d["status"] == "UNAVAILABLE" for d in w["days"])
        assert any("currents_nrt" in d["reason"] for d in w["days"])


# ------------------------------------------------------------- same path
class TestSameInferencePath:
    def test_latest_equals_the_hindcast_field_for_that_date(self, engine, canonical,
                                                            tmp_path):
        cached = HINDCAST_CACHE / f"N_{DAY.date()}.npy"
        if not cached.exists():
            pytest.skip("hindcast cache not present")
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        n = np.load(cached).astype("float64")
        t = r.view.temperature
        assert np.array_equal(np.isnan(t), np.isnan(n))
        assert np.nanmax(np.abs(t - n)) < 1e-4      # float32 cache precision

    def test_field_contract(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        v = r.view
        assert v.temperature.shape == (101, 241, 15)
        assert v.depths == DEPTHS
        both = np.isfinite(v.temperature) & np.isfinite(v.climatology)
        assert np.allclose(v.anomaly[both], (v.temperature - v.climatology)[both])
        assert v.provenance["operating_mode"] == LQ.OPERATING_MODE
        assert v.provenance["l2_state_dict_sha256"] == L2

    def test_point_profile_is_a_sample_of_the_field(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        row, col = map(int, np.argwhere(r.view.surface_input_valid)[100])
        prof = r.view.profile_at(row, col)["prediction_c"]
        assert np.array_equal(prof, r.view.temperature[row, col, :])


# ------------------------------------------------------------- per-date fields
class TestPerDateFields:
    def test_each_date_is_its_own_independent_field(self, engine, canonical, tmp_path):
        a = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY, DAY2), workdir=tmp_path, day=DAY)
        b = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY, DAY2), workdir=tmp_path, day=DAY2)
        assert a.view.date == str(DAY.date()) and b.view.date == str(DAY2.date())
        assert not np.allclose(np.nan_to_num(a.view.temperature),
                               np.nan_to_num(b.view.temperature))

    def test_reselecting_a_date_reproduces_the_same_field(self, engine, canonical,
                                                          tmp_path):
        first = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                          dates_for(DAY, DAY2), workdir=tmp_path,
                                          day=DAY2)
        LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                  dates_for(DAY, DAY2), workdir=tmp_path, day=DAY)
        again = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                          dates_for(DAY, DAY2), workdir=tmp_path,
                                          day=DAY2)
        assert np.array_equal(first.view.temperature, again.view.temperature,
                              equal_nan=True)

    def test_no_temporal_state_between_dates(self, engine, canonical, tmp_path):
        """Selecting A then B must equal B computed on its own."""
        alone = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                          dates_for(DAY2), workdir=tmp_path, day=DAY2)
        LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                  dates_for(DAY, DAY2), workdir=tmp_path, day=DAY)
        after = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                          dates_for(DAY, DAY2), workdir=tmp_path,
                                          day=DAY2)
        assert np.array_equal(alone.view.temperature, after.view.temperature,
                              equal_nan=True)

    def test_a_date_no_channel_can_supply_is_refused_without_inference(
            self, engine, canonical, tmp_path, no_infer):
        calls = Calls()
        with pytest.raises(LQ.LatestRefused, match="not a qualified common date"):
            LQ.latest_qualified_field(engine, make_fetchers(canonical, calls),
                                      dates_for(DAY), workdir=tmp_path,
                                      day=pd.Timestamp("2024-12-11"))
        assert calls.n == 0

    def test_a_date_one_channel_lacks_is_refused(self, engine, canonical, tmp_path,
                                                 no_infer):
        sets = dates_for(DAY, DAY2)
        sets["currents_nrt"] = {DAY}
        with pytest.raises(LQ.LatestRefused) as exc:
            LQ.latest_qualified_field(engine, make_fetchers(canonical), sets,
                                      workdir=tmp_path, day=DAY2)
        assert "currents_nrt" in str(exc.value)


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
                                      dates_for(DAY), decision_path=p,
                                      workdir=tmp_path)
        assert calls.n == 0

    def test_missing_sss_refuses_with_no_fallback(self, engine, canonical, tmp_path,
                                                  no_infer):
        def dead(_):
            raise OSError("provider unreachable")
        with pytest.raises(LQ.LatestRefused) as exc:
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sss_nrt_multiobs": dead}),
                dates_for(DAY), workdir=tmp_path)
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
                engine, make_fetchers(canonical, override={key: dead}),
                dates_for(DAY), workdir=tmp_path)

    def test_channel_on_a_different_date_is_refused(self, engine, canonical, tmp_path,
                                                    no_infer):
        """No carry-forward: a field stamped another day cannot stand in."""
        def shifted(ds):
            return ds.assign_coords(time=[DAY - pd.Timedelta(days=1)])
        with pytest.raises(LQ.LatestRefused) as exc:
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sst_nrt": shifted}),
                dates_for(DAY), workdir=tmp_path)
        assert any(s["state"] == "NOT_ON_COMMON_DATE" for s in exc.value.sources)

    def test_low_coverage_is_refused(self, engine, canonical, tmp_path, no_infer):
        def holed(ds):
            ds = ds.copy(deep=True)
            ds["sst"][:, :60, :] = np.nan
            return ds
        with pytest.raises(LQ.LatestRefused, match="L4"):
            LQ.latest_qualified_field(
                engine, make_fetchers(canonical, override={"sst_nrt": holed}),
                dates_for(DAY), workdir=tmp_path)

    def test_no_common_date_means_no_retrieval(self, engine, canonical, tmp_path,
                                               no_infer):
        sets = dates_for(DAY)
        sets["currents_nrt"] = set()
        calls = Calls()
        with pytest.raises(LQ.LatestRefused, match="no common valid date"):
            LQ.latest_qualified_field(engine, make_fetchers(canonical, calls), sets,
                                      workdir=tmp_path)
        assert calls.n == 0

    def test_auth_failure_is_not_reported_as_an_outage(self):
        assert LQ._state_from_error("HTTPError: 401 Unauthorized") == "AUTH_FAILED"
        assert LQ._state_from_error("OSError: timed out") == "UNREACHABLE"


# ------------------------------------------------------------- alignment
class TestTemporalAlignment:
    def test_provenance_keeps_every_clock_separate(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
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


# ------------------------------------------------------------- snapshot/cache
class TestSnapshot:
    def test_roundtrip_is_exact_and_labelled(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
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

    def test_a_cached_field_is_never_served_as_another_date(self, engine, canonical,
                                                            tmp_path):
        """Cache identity includes the valid date."""
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        LQ.save_snapshot(r, LQ.daily_cache_dir(DAY, tmp_path))
        assert LQ.load_daily(engine, DAY, tmp_path) is not None
        assert LQ.load_daily(engine, DAY2, tmp_path) is None

    def test_daily_cache_reuse_is_exact(self, engine, canonical, tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        LQ.save_snapshot(r, LQ.daily_cache_dir(DAY, tmp_path))
        back = LQ.load_daily(engine, DAY, tmp_path)
        assert np.array_equal(back.view.temperature, r.view.temperature, equal_nan=True)
        assert back.view.provenance["inference_source"] == "VALIDATED_DAILY_CACHE"

    def test_only_a_live_qualified_run_can_become_a_snapshot(self, engine, canonical,
                                                             tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        LQ.save_snapshot(r, tmp_path / "a")
        s = LQ.load_snapshot(engine, tmp_path / "a")
        with pytest.raises(ValueError):
            LQ.save_snapshot(s, tmp_path / "b")

    def test_snapshot_is_invalid_once_the_decision_changes(self, engine, canonical,
                                                           tmp_path):
        r = LQ.latest_qualified_field(engine, make_fetchers(canonical),
                                      dates_for(DAY), workdir=tmp_path)
        LQ.save_snapshot(r, tmp_path / "snap")
        other = tmp_path / "decision.json"
        shutil.copy(LQ.DECISION_PATH, other)
        other.write_text(other.read_text(encoding="utf-8") + " ", encoding="utf-8")
        assert LQ.load_snapshot(engine, tmp_path / "snap", decision_path=other) is None


# ------------------------------------------------------------- warm-up
class TestWarmUp:
    def test_warm_produces_every_available_date_and_skips_cached(
            self, engine, canonical, monkeypatch, tmp_path):
        monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", tmp_path / "daily")
        monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
        monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")
        calls = Calls()
        monkeypatch.setattr(LQ, "default_fetchers",
                            lambda: make_fetchers(canonical, calls))
        LQ.WARM_STATUS.clear()
        sets = dates_for(DAY, DAY2)
        LQ.warm_recent_states(engine, 7, sets, {})
        assert LQ.is_cached(DAY) and LQ.is_cached(DAY2)
        assert LQ.WARM_STATUS[str(DAY.date())] == "ready"
        assert LQ.WARM_STATUS[str(DAY2.date())] == "ready"
        first = calls.n
        assert first > 0
        # a second pass must reuse the immutable cache, not refetch
        LQ.warm_recent_states(engine, 7, sets, {})
        assert calls.n == first

    def test_warm_never_produces_an_unavailable_date(self, engine, canonical,
                                                     monkeypatch, tmp_path, no_infer):
        monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", tmp_path / "daily")
        monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
        monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")
        monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(canonical))
        LQ.WARM_STATUS.clear()
        sets = dates_for(DAY)
        sets["currents_nrt"] = set()          # nothing is a common date
        LQ.warm_recent_states(engine, 7, sets, {})
        assert not LQ.is_cached(DAY)          # no_infer would have fired otherwise

    def test_warm_records_a_refusal_instead_of_crashing(self, engine, canonical,
                                                        monkeypatch, tmp_path):
        monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", tmp_path / "daily")
        monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
        monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")

        def dead(_):
            raise OSError("provider down")
        monkeypatch.setattr(LQ, "default_fetchers",
                            lambda: make_fetchers(canonical,
                                                  override={"sla_nrt": dead}))
        LQ.WARM_STATUS.clear()
        LQ.warm_recent_states(engine, 7, dates_for(DAY), {})
        assert LQ.WARM_STATUS[str(DAY.date())].startswith("refused")
        assert not LQ.is_cached(DAY)

    def test_window_reports_readiness_per_date(self, engine, canonical, monkeypatch,
                                               tmp_path):
        monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", tmp_path / "daily")
        monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
        monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")
        monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(canonical))
        LQ.WARM_STATUS.clear()
        sets = dates_for(DAY, DAY2)
        before = {d["date"]: d for d in LQ.available_window(7, sets, {})["days"]}
        assert before[str(DAY.date())]["cached"] is False
        assert before[str(DAY.date())]["warm"] == "pending"
        LQ.warm_recent_states(engine, 7, sets, {})
        after = {d["date"]: d for d in LQ.available_window(7, sets, {})["days"]}
        assert after[str(DAY.date())]["cached"] is True
        assert after[str(DAY.date())]["warm"] == "ready"


# ------------------------------------------------------------- API
@pytest.fixture()
def client(engine, canonical, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from oceanembed.poc import app as A
    from oceanembed.replay import api as replay_api
    monkeypatch.setattr(replay_api, "engine", lambda: engine)
    monkeypatch.setattr(LQ, "channel_dates",
                        lambda *a, **k: (dates_for(DAY, DAY2), {}))
    monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(canonical))
    monkeypatch.setattr(LQ, "SNAPSHOT_DIR", tmp_path / "snap")
    monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", tmp_path / "daily")
    monkeypatch.setattr(LQ, "WORK_DIR", tmp_path / "work")
    return TestClient(A.app)


def _fail(monkeypatch, canonical):
    def dead(_):
        raise OSError("network deliberately down")
    monkeypatch.setattr(LQ, "default_fetchers", lambda: make_fetchers(
        canonical, override={k: dead for k in LQ.PRODUCT_CHANNELS}))


class TestApi:
    def test_manual_window_refresh_bypasses_persisted_discovery(self, client, monkeypatch):
        calls = []
        def discover(*args, allow_persisted=True):
            calls.append(allow_persisted)
            return dates_for(DAY2 if allow_persisted else DAY), {}
        monkeypatch.setattr(LQ, "channel_dates", discover)
        window = client.get("/api/latest/available-dates?refresh=true").json()
        assert calls == [False]
        assert window["newest_qualified_date"] == str(DAY.date())

    def test_manual_field_refresh_bypasses_persisted_discovery(self, client, monkeypatch):
        calls = []
        def discover(*args, allow_persisted=True):
            calls.append(allow_persisted)
            return dates_for(DAY2 if allow_persisted else DAY), {}
        monkeypatch.setattr(LQ, "channel_dates", discover)
        # Refuse a date outside the intersection without running inference.
        p = client.get("/api/latest/qualified?refresh=true&date=2024-12-01").json()
        assert calls == [False]
        assert p["newest_qualified_date"] == str(DAY.date())
        assert p["field"] is None

    def test_qualification_drives_the_tab_name(self, client):
        q = client.get("/api/latest/qualification").json()
        assert q["qualified"] is True
        assert q["temperature_category"] == "QUALIFIED WITH LIMITATIONS"
        assert q["tab_name"] == "Latest Qualified Ocean State"
        assert q["d26_category"] == "NOT QUALIFIED"
        assert any("observational" in x for x in q["limitations"])
        assert "Operational timeliness has not been separately certified" in \
            q["timeliness_note"]
        assert "not exposed as a qualified D26 product" in q["d26_tchp_explanation"]
        assert "not observationally validated as a cyclone forecast" in \
            q["hazard_transfer_note"]
        for note in (q["timeliness_note"], q["d26_tchp_explanation"],
                     q["hazard_transfer_note"]):
            assert note in q["limitations"]

    def test_available_dates_lists_the_window(self, client):
        w = client.get("/api/latest/available-dates").json()
        assert w["newest_qualified_date"] == str(DAY.date())
        rows = {d["date"]: d for d in w["days"]}
        assert len(w["days"]) == 7
        assert rows[str(DAY.date())]["status"] == "AVAILABLE"
        assert rows[str(DAY.date())]["is_newest"] is True
        assert rows[str(DAY2.date())]["status"] == "AVAILABLE"
        # a day no channel holds is listed as unavailable, with a reason
        gap = rows["2024-12-12"]
        assert gap["status"] == "UNAVAILABLE" and gap["reason"]

    def test_prewarm_returns_immediately_and_reports_status(self, client):
        r = client.get("/api/latest/prewarm").json()
        assert "running" in r or r.get("started") is not None

    def test_available_dates_carries_readiness(self, client):
        w = client.get("/api/latest/available-dates").json()
        rows = {d["date"]: d for d in w["days"] if d["status"] == "AVAILABLE"}
        assert all("cached" in d and "warm" in d for d in rows.values())
        assert "warm_status" in w

    def test_live_payload_uses_the_historical_transport(self, client):
        p = client.get("/api/latest/qualified").json()
        assert p["state"] == LQ.LIVE_STATE
        assert p["selected_date"] == str(DAY.date())
        assert p["newest_qualified_date"] == str(DAY.date())
        assert p["is_newest"] is True
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
        assert f["provenance"]["operating_mode"] == LQ.OPERATING_MODE
        assert set(f["surface_inputs"]) == {"sst", "sss", "sla", "current_u",
                                            "current_v", "wind_u", "wind_v"}

    def test_selecting_an_older_date_serves_that_date_only(self, client):
        p = client.get("/api/latest/qualified",
                       params={"date": str(DAY2.date())}).json()
        assert p["state"] == LQ.DATED_STATE
        assert p["selected_date"] == str(DAY2.date())
        assert p["is_newest"] is False
        assert p["field"]["date"] == str(DAY2.date())
        assert p["newest_qualified_date"] == str(DAY.date())
        # its diagnostics come from ITS OWN field
        newest = client.get("/api/latest/qualified").json()
        assert p["field"]["diagnostics"]["tchp_kj_cm2"] != \
            newest["field"]["diagnostics"]["tchp_kj_cm2"]
        assert p["field"]["hazard"]["category_counts"] != \
            newest["field"]["hazard"]["category_counts"]
        assert p["field"]["diagnostics"]["withheld"] == ["d26"]

    def test_an_unqualified_date_runs_no_inference(self, client, engine, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("inference ran for an unavailable date")
        monkeypatch.setattr(engine, "_infer", boom)
        p = client.get("/api/latest/qualified", params={"date": "2024-12-12"}).json()
        assert p["state"] == "DATE_NOT_QUALIFIED"
        assert p["field"] is None
        assert p["missing_channels"] and p["reason"]
        assert "carried forward" in p["note"]

    def test_refusal_serves_the_snapshot_labelled_not_current(self, client,
                                                             monkeypatch, canonical):
        assert client.get("/api/latest/qualified").json()["state"] == LQ.LIVE_STATE
        _fail(monkeypatch, canonical)
        monkeypatch.setattr(LQ, "DAILY_CACHE_DIR", Path("/nonexistent-daily"))
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
        assert p["field"]["provenance"]["inference_source"] in (
            "LIVE_MODEL_RUN", "VALIDATED_DAILY_CACHE")

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
        window = client.get("/api/latest/available-dates").json()
        assert window["days"] == []

    def test_frozen_hashes_unchanged_after_serving_dates(self, client, engine):
        from oceanembed.replay.engine import (EXPECTED_L2_STATE_DICT,
                                              state_dict_sha256)
        client.get("/api/latest/qualified")
        client.get("/api/latest/qualified", params={"date": str(DAY2.date())})
        assert state_dict_sha256(engine.model.state_dict()) == EXPECTED_L2_STATE_DICT


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

    def test_no_temporal_model_was_introduced(self):
        """Each date is an independent frozen-L2 run: no sequence model, no
        smoothing between dates, and no channel carried across days.

        Checked at the syntax-tree level rather than by substring, because the
        word "persist" legitimately appears in the snapshot docstring.
        """
        import ast
        src = (ROOT / "src/oceanembed/nrt/latest.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for banned in ("GRU", "LSTM", "ConvLSTM", "rolling", "ewm", "interpolate",
                       "ffill", "bfill", "fillna", "shift", "carry_forward"):
            assert banned not in used, banned
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                    for a in n.names}
        imported |= {n.module for n in ast.walk(tree)
                     if isinstance(n, ast.ImportFrom) and n.module}
        assert not any("torch" in m or "keras" in m for m in imported)
        # and the policy still declares a zero-day persistence envelope
        assert '"persistence_envelope_days": 0' in src

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
