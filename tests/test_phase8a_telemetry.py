"""Phase 8A guards — NRT input telemetry, and everything it must NOT do.

The risks these target: the frozen L2 being run on an incomplete NRT stack to
put a temperature on the latest screen; a latest D26/TCHP or hazard label
appearing; cached telemetry being passed off as fresh; a source valid time
merged with a local retrieval time; an auth failure reported as "offline";
Historical Replay going down because the network did; and the reserved Phase 8B
wording appearing early.

Network is never required: every test here either uses fixtures or a
deliberately severed connection.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.nrt import telemetry as T  # noqa: E402
from oceanembed.nrt.registry import PRODUCTS  # noqa: E402

RESILIENCE = ROOT / "outputs" / "phase8a" / "demo_resilience_test.json"
_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


@pytest.fixture
def offline(monkeypatch):
    """Make the sources fail INSTANTLY, at the same seam a real outage hits.

    Severing DNS for real costs ~60 s per call, because the provider client
    retries with backoff. These tests are about how the state machine and the
    payload behave once a source has failed, not about the vendor's retry
    schedule. The genuine severed-network path is rehearsed end to end by
    scripts/poc/run_demo_resilience_test.py, whose artifact is asserted below.
    """
    def failed(key: str) -> dict:
        return {"provider": "Copernicus Marine", "product_key": key,
                "product_id": PRODUCTS[key]["product_id"],
                "dataset_id": PRODUCTS[key]["dataset_id"],
                "query_time": pd.Timestamp.utcnow().tz_localize(None),
                "success": False,
                "error": "OSError: blocked: name resolution failure",
                "newest_valid_time": None, "revision": None, "granule_id": None}
    monkeypatch.setattr(T, "poll_product", failed)


@pytest.fixture
def no_network(monkeypatch):
    """Sever REMOTE access only; loopback and local machinery keep working."""
    real_gai, real_conn = socket.getaddrinfo, socket.create_connection

    def gai(host, *a, **k):
        if str(host) not in _LOCAL:
            raise OSError(f"blocked: {host}")
        return real_gai(host, *a, **k)

    def conn(address, *a, **k):
        if str(address[0]) not in _LOCAL:
            raise OSError(f"blocked: {address[0]}")
        return real_conn(address, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", gai)
    monkeypatch.setattr(socket, "create_connection", conn)


def source(**kw) -> T.SourceTelemetry:
    base = dict(channel="sst", product_key="sst_nrt", product_id="P",
                dataset_id="D", doi=None, provider="Copernicus Marine")
    return T.SourceTelemetry(**{**base, **kw})


# ------------------------------------------------------- scope: telemetry only
class TestTelemetryOnly:
    def test_module_imports_no_model_replay_or_diagnostics(self):
        """Structural: it cannot produce a reconstruction because it cannot
        reach one. Checked on imports and calls, not on words in prose — the
        docstring legitimately names what the module refuses to do."""
        src = Path(T.__file__).read_text(encoding="utf-8")
        imports = [ln for ln in src.splitlines()
                   if ln.startswith(("import ", "from ")) or " import " in ln]
        for line in imports:
            for banned in ("..ml", "..replay", "..diagnostics", "l2_model",
                           "torch"):
                assert banned not in line, f"telemetry imports {banned!r}: {line}"
        for call in ("replay_field(", "d26_tchp(", "categorize(", "embed_field(",
                     "forward_from_z(", "field_diagnostics("):
            assert call not in src, f"telemetry calls {call}"

    def test_payload_carries_no_scientific_value_only_refusals(self, offline):
        """No key may name a diagnostic, and every textual mention must be a
        statement that it is NOT produced."""
        payload = T.telemetry_payload(with_region=False)

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    for banned in ("d26", "tchp", "hazard", "temperature",
                                   "thermal"):
                        assert banned not in key.lower(), f"key {key!r}"
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, str):
                low = node.lower()
                if any(w in low for w in ("d26", "tchp", "hazard")):
                    assert ("no latest" in low or "not " in low
                            or "remain" in low), f"unqualified mention: {node!r}"

        walk(payload)
        assert "latest qualified" not in json.dumps(payload).lower()

    def test_not_certified_is_always_stated(self, offline):
        payload = T.telemetry_payload(with_region=False)
        assert payload["subsurface_reconstruction"] == \
            "SUBSURFACE NRT RECONSTRUCTION NOT YET CERTIFIED"

    def test_reserved_phase8b_wording_is_absent(self):
        for rel in ("src/oceanembed/nrt/telemetry.py",
                    "web/src/components/LatestInputs.tsx",
                    "src/oceanembed/poc/app.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            assert "Latest Qualified Ocean State" not in text
            assert "Live Ocean Right Now" not in text

    def test_scope_is_the_two_ablation_channels(self):
        assert T.CHANNELS == ("sst_nrt", "sla_nrt")
        assert PRODUCTS["sst_nrt"]["channel"] == "sst"
        assert PRODUCTS["sla_nrt"]["channel"] == "sla"
        assert PRODUCTS["sst_nrt"]["role"] == PRODUCTS["sla_nrt"]["role"] == "nrt"

    def test_channel_rationale_is_stated_without_overclaiming(self):
        why = T.WHY_THESE_INPUTS
        assert "does NOT mean" in why
        for forbidden in ("only sst", "useless", "do not matter"):
            assert forbidden not in why.lower()


# ------------------------------------------------------- state machine
class TestStateMachine:
    def test_all_retrieved_is_current(self):
        s = [source(state=T.SourceState.OK.value),
             source(state=T.SourceState.OK.value)]
        assert T.overall_state(s) is T.OverallState.ONLINE_CURRENT

    def test_catalogue_only_is_current_not_offline(self):
        """The provider answered. Reporting that as offline would be a lie."""
        s = [source(state=T.SourceState.CATALOGUE_ONLY.value),
             source(state=T.SourceState.CATALOGUE_ONLY.value)]
        assert T.overall_state(s) is T.OverallState.ONLINE_CURRENT

    def test_one_source_short_is_partial_not_offline(self):
        s = [source(state=T.SourceState.OK.value),
             source(state=T.SourceState.UNREACHABLE.value)]
        assert T.overall_state(s) is T.OverallState.ONLINE_PARTIAL

    def test_coverage_failure_is_partial_not_offline(self):
        s = [source(state=T.SourceState.OK.value),
             source(state=T.SourceState.COVERAGE_UNAVAILABLE.value)]
        assert T.overall_state(s) is T.OverallState.ONLINE_PARTIAL

    def test_nothing_answered_is_offline(self):
        s = [source(state=T.SourceState.UNREACHABLE.value),
             source(state=T.SourceState.AUTH_FAILED.value)]
        assert T.overall_state(s) is T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE

    def test_auth_failure_is_not_reported_as_unreachable(self):
        """A rejected login and a dead network are different operator problems."""
        for message in ("401 Unauthorized", "invalid credentials",
                        "authentication failed", "403 Forbidden"):
            assert T._classify_error(message) is T.SourceState.AUTH_FAILED
        for message in ("connection timed out", "name resolution failure"):
            assert T._classify_error(message) is T.SourceState.UNREACHABLE


# ------------------------------------------------------- honesty about time
class TestTimeHonesty:
    def test_valid_time_and_retrieval_time_are_separate_fields(self):
        s = source()
        assert hasattr(s, "product_valid_time") and hasattr(s, "local_retrieval_time")
        assert s.product_valid_time != s.local_retrieval_time or \
            s.product_valid_time is None

    def test_generated_time_is_null_unless_the_provider_states_one(self, offline):
        payload = T.telemetry_payload(with_region=False)
        for s in payload["sources"]:
            assert s["product_generated_time"] is None, \
                "an acquisition time was invented"

    def test_unknown_coverage_is_null_not_zero(self, offline):
        payload = T.telemetry_payload(with_region=False)
        rows = payload.get("live_attempt_sources") or payload["sources"]
        for s in rows:
            if s["state"] != T.SourceState.OK.value:
                assert s["nio_coverage_fraction"] is None
                assert s["nio_coverage_fraction"] != 0


# ------------------------------------------------------- offline behaviour
class TestOfflineBehaviour:
    def test_offline_never_raises_and_reports_a_state(self, offline):
        payload = T.telemetry_payload(with_region=True)
        assert payload["state"] in {
            T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE.value,
            T.OverallState.CACHED_TELEMETRY_NOT_CURRENT.value}

    def test_cached_telemetry_is_labelled_and_never_shown_as_fresh(
            self, offline, tmp_path):
        snap = tmp_path / "snapshot.json"
        snap.write_text(json.dumps({
            "mode": "LATEST_INPUTS", "phase": "8A", "state": "ONLINE_CURRENT",
            "generated_utc": (pd.Timestamp.utcnow().tz_localize(None)
                              - pd.Timedelta(hours=30)).isoformat(),
            "sources": [{"channel": "sst", "state": "OK"}],
        }), encoding="utf-8")
        payload = T.telemetry_payload(with_region=True, snapshot_path=snap)
        assert payload["is_cached"] is True
        assert payload["state"] == T.OverallState.CACHED_TELEMETRY_NOT_CURRENT.value
        assert "NOT CURRENT" in payload["cache_label"]
        assert payload["cached_staleness_hours"] > 29
        # The failed live attempt is kept, separate from the cached reading.
        assert payload["live_attempt_sources"]

    def test_no_cache_gives_an_informative_state_not_a_blank(
            self, offline, tmp_path):
        payload = T.telemetry_payload(with_region=True,
                                      snapshot_path=tmp_path / "absent.json")
        assert payload["is_cached"] is False
        assert payload["unavailable_label"] == "DATA SOURCE CURRENTLY UNAVAILABLE"

    def test_failure_never_writes_a_snapshot(self, offline, tmp_path):
        """Only a real successful retrieval may become the cache."""
        snap = tmp_path / "never.json"
        T.telemetry_payload(with_region=True, snapshot_path=snap)
        assert not snap.exists()

    def test_historical_replay_is_unaffected_by_a_dead_network(self, no_network):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            view = e.replay_field("2021-06-15")
            assert view.temperature.shape == (101, 241, 15)
        finally:
            e.close()


# ------------------------------------------------------- transport
class TestTransport:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from oceanembed.poc import app as poc
        with TestClient(poc.app) as c:
            yield c

    def test_cached_endpoint_never_touches_the_network(self, client, offline):
        r = client.get("/api/latest/cached")
        assert r.status_code == 200
        assert r.json()["is_cached"] is True

    def test_latest_endpoint_degrades_rather_than_erroring(self, client, offline):
        r = client.get("/api/latest", params={"region": False})
        assert r.status_code == 200
        assert r.json()["state"] in {
            T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE.value,
            T.OverallState.CACHED_TELEMETRY_NOT_CURRENT.value}

    def test_telemetry_endpoints_do_not_take_the_engine_lock(self):
        """A slow provider must never be able to block Historical Replay."""
        from oceanembed.poc.app import UNLOCKED_PREFIXES
        assert "/api/latest" in UNLOCKED_PREFIXES

    def test_historical_endpoints_still_work_offline(self, client, no_network):
        r = client.get("/api/replay/view", params={"date": "2021-06-15"})
        assert r.status_code == 200
        assert r.json()["shape"] == [101, 241, 15]

    def test_hazard_stays_historical_with_no_latest_variant(self, client, no_network):
        payload = client.get("/api/replay/view",
                             params={"date": "2023-05-13"}).json()
        assert payload["hazard"]["available"] is True
        text = json.dumps(payload).lower()
        assert "latest" not in text or "latest qualified" not in text


# ------------------------------------------------------- resilience artifact
class TestResilienceArtifact:
    def test_rehearsal_was_run_and_passed(self):
        assert RESILIENCE.is_file(), "run scripts/poc/run_demo_resilience_test.py"
        record = json.loads(RESILIENCE.read_text(encoding="utf-8"))
        assert record["result"] == "PASS"
        assert record["application_crashed"] is False
        for key in ("tested_at", "failure_method", "historical_replay_available",
                    "latest_tab_rendered", "cached_snapshot_used",
                    "cached_snapshot_label_visible", "unavailable_state_rendered"):
            assert key in record, f"resilience artifact missing {key}"

    def test_rehearsal_covers_recovery_without_restart(self):
        record = json.loads(RESILIENCE.read_text(encoding="utf-8"))
        assert record["recovery_without_restart"] is True
        assert record["historical_replay_available_after_failure"] is True

    def test_rehearsal_states_it_was_deliberate(self):
        record = json.loads(RESILIENCE.read_text(encoding="utf-8"))
        assert "deliberately unavailable" in record["statement"]


# ------------------------------------------------------- discipline
class TestStillNotAuthorized:
    def test_no_latest_subsurface_inference_anywhere(self):
        """The Phase 8A telemetry endpoint runs no model.

        Phase-boundary note (Phase 8B): this also banned `latest_qualified_field`
        anywhere in the app, correct while 8B was unauthorised. 8B qualified a
        latest mode and provides a gated latest path (nrt/latest.py, pinned in
        tests/test_phase8b_latest.py), so the ban was narrowed to what 8A itself
        guarantees: the telemetry endpoint never reaches inference.
        """
        app = (ROOT / "src/oceanembed/poc/app.py").read_text(encoding="utf-8")
        assert "def latest(" in app
        body = app.split("def latest(")[1][:600]
        for banned in ("replay_field", "run_prepared", "_infer"):
            assert banned not in body, banned

    def test_no_sss_fallback_or_quantile_mapping_introduced(self):
        for rel in ("src/oceanembed/nrt/telemetry.py",
                    "src/oceanembed/poc/app.py"):
            text = (ROOT / rel).read_text(encoding="utf-8").lower()
            for banned in ("quantile", "cdf mapping", "zero-fill", "mean-fill",
                           "climatological sss"):
                assert banned not in text

    def test_frozen_core_and_holdout_untouched(self):
        from oceanembed.replay.engine import ReplayEngine
        e = ReplayEngine(use_cache=False)
        try:
            assert e.l2_state_dict_sha256 == \
                "b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d"
        finally:
            e.close()
        src = Path(T.__file__).read_text(encoding="utf-8").lower()
        assert "argo" not in src

    def test_phase7_manifest_still_says_nrt_not_started_for_phase7(self):
        """Phase 7's freeze describes Phase 7; 8A does not rewrite it."""
        manifest = json.loads(
            (ROOT / "outputs/phase7/FINAL_POC_MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["status"]["nrt_status"] == "NOT STARTED"
        assert manifest["status"]["argo_2024_status"] == "PROTECTED"
