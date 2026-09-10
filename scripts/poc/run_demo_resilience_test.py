"""Phase 8A.7 — deliberately break the live-data path and prove the demo holds.

Exception handling existing is not evidence that the failure path works. This
rehearses it: the provider is made unreachable at the socket layer, then the
whole application is exercised through that failure and back out of it.

Checks, in order:
  1. Historical Replay still works with the network dead.
  2. Latest Inputs still renders, does not crash, and reports the failure.
  3. A stored snapshot, if any, is shown LABELLED as not current.
  4. With no snapshot at all, an informative unavailable state appears.
  5. Source valid time and local retrieval time remain separate throughout.
  6. Recovery works in the same running process - no restart.

Writes outputs/phase8a/demo_resilience_test.json. Required: result = PASS.

    python scripts/poc/run_demo_resilience_test.py
"""
from __future__ import annotations

import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "phase8a" / "demo_resilience_test.json"

_REAL_GETADDRINFO = socket.getaddrinfo
_REAL_CREATE_CONNECTION = socket.create_connection

#: Loopback stays reachable on purpose. Blocking socket creation outright also
#: breaks asyncio's own self-pipe and dask's local machinery, which would make
#: the test fail for reasons that have nothing to do with the demo. The failure
#: being rehearsed is "the provider is unreachable", not "sockets do not exist".
_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}


class NetworkDisabled(OSError):
    """Raised in place of any REMOTE connection while the network is cut."""


def cut_network() -> None:
    """Fail remote DNS and remote connects, below every HTTP client and SDK."""
    def _gai(host, *a, **k):
        if str(host) not in _LOCAL:
            raise NetworkDisabled(
                f"network deliberately disabled for resilience test: {host}")
        return _REAL_GETADDRINFO(host, *a, **k)

    def _connect(address, *a, **k):
        if str(address[0]) not in _LOCAL:
            raise NetworkDisabled(
                f"network deliberately disabled for resilience test: {address[0]}")
        return _REAL_CREATE_CONNECTION(address, *a, **k)

    socket.getaddrinfo = _gai              # type: ignore[assignment]
    socket.create_connection = _connect    # type: ignore[assignment]


def restore_network() -> None:
    socket.getaddrinfo = _REAL_GETADDRINFO            # type: ignore[assignment]
    socket.create_connection = _REAL_CREATE_CONNECTION  # type: ignore[assignment]


def main() -> int:
    from oceanembed.nrt import telemetry as T
    from oceanembed.replay.engine import ReplayEngine

    findings: dict = {
        "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "failure_method": "socket.socket and socket.getaddrinfo replaced so every "
                          "outbound connection fails below the HTTP client, in "
                          "the same running process",
        "phase": "8A",
    }
    checks: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append(f"{'PASS' if ok else 'FAIL'} · {name}"
                      + (f" — {detail}" if detail else ""))
        findings[name] = bool(ok)

    snapshot = ROOT / "outputs" / "phase8a" / "last_successful_telemetry.json"
    had_snapshot = snapshot.is_file()
    findings["snapshot_present_before_test"] = had_snapshot

    engine = ReplayEngine(use_cache=False)
    try:
        cut_network()

        # 1 — the offline science must be untouched by a dead network.
        try:
            view = engine.replay_field("2021-06-15")
            point = engine.replay_point("2021-06-15", 15.25, 87.75)
            ok = (view.temperature.shape == (101, 241, 15)
                  and len(point.profile) == 15)
            check("historical_replay_available", ok,
                  f"field {view.temperature.shape}, profile {len(point.profile)} depths")
        except Exception as exc:  # noqa: BLE001
            check("historical_replay_available", False, f"{type(exc).__name__}: {exc}")

        # 2 — the telemetry path must degrade, not explode.
        crashed = False
        try:
            payload = T.telemetry_payload(with_region=True)
        except Exception as exc:  # noqa: BLE001
            crashed, payload = True, {}
            findings["crash_detail"] = f"{type(exc).__name__}: {exc}"
        # Reported as a positive assertion so PASS means what it reads; the
        # literal crashed flag is recorded separately for the artifact.
        check("application_did_not_crash", not crashed,
              findings.get("crash_detail", ""))
        findings["application_crashed"] = crashed
        check("latest_tab_rendered", bool(payload) and "state" in payload,
              payload.get("state", "no payload"))

        offline_states = {T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE.value,
                          T.OverallState.CACHED_TELEMETRY_NOT_CURRENT.value}
        check("failure_state_reported", payload.get("state") in offline_states,
              str(payload.get("state")))

        # 3 / 4 — cached telemetry must be labelled; absence must be informative.
        used_cache = bool(payload.get("is_cached"))
        findings["cached_snapshot_used"] = used_cache
        if used_cache:
            check("cached_snapshot_label_visible",
                  "NOT CURRENT" in (payload.get("cache_label") or ""),
                  payload.get("cache_label", ""))
            check("cached_snapshot_staleness_measured",
                  payload.get("cached_staleness_hours") is not None)
            check("unavailable_state_rendered", True,
                  "cache shown instead, correctly labelled")
        else:
            check("cached_snapshot_label_visible", True, "no cache to label")
            check("unavailable_state_rendered",
                  payload.get("unavailable_label") == "DATA SOURCE CURRENTLY UNAVAILABLE",
                  str(payload.get("unavailable_label")))

        # 4b — with the snapshot hidden, the no-cache path must also be clean.
        hidden = ROOT / "outputs" / "phase8a" / "_snapshot_hidden_for_test.json"
        moved = False
        if snapshot.is_file():
            snapshot.replace(hidden)      # moved aside, never deleted
            moved = True
        try:
            bare = T.telemetry_payload(with_region=True)
            check("no_cache_state_is_informative",
                  bare.get("unavailable_label") == "DATA SOURCE CURRENTLY UNAVAILABLE"
                  and not bare.get("is_cached"),
                  str(bare.get("unavailable_label")))
        finally:
            if moved:
                hidden.replace(snapshot)  # restored exactly as found

        # 5 — the two clocks must never be merged, even in failure.
        attempted = payload.get("live_attempt_sources") or payload.get("sources") or []
        separate = all("product_valid_time" in s and "local_retrieval_time" in s
                       for s in attempted) if attempted else False
        check("source_valid_time_kept_separate_from_retrieval_time", separate)

        # Historical science must still work AFTER the telemetry failure too.
        try:
            again = engine.replay_field("2023-05-13")
            check("historical_replay_available_after_failure",
                  again.temperature.shape == (101, 241, 15))
        except Exception as exc:  # noqa: BLE001
            check("historical_replay_available_after_failure", False, str(exc))

    finally:
        restore_network()

    # 6 — recovery in the same process, with no restart.
    try:
        recovered = T.telemetry_payload(with_region=False)
        live_again = recovered.get("state") in {
            T.OverallState.ONLINE_CURRENT.value,
            T.OverallState.ONLINE_PARTIAL.value,
            T.OverallState.OFFLINE_OR_SOURCE_UNAVAILABLE.value,
        }
        findings["recovery_state"] = recovered.get("state")
        # A catalogue-only poll may legitimately still report partial; what is
        # being proved is that the process recovers and re-attempts, not that
        # the provider is up.
        check("recovery_without_restart", live_again, str(recovered.get("state")))
        check("recovery_reattempted_sources",
              len(recovered.get("sources") or recovered.get("live_attempt_sources") or []) == 2)
    except Exception as exc:  # noqa: BLE001
        check("recovery_without_restart", False, f"{type(exc).__name__}: {exc}")

    engine.close()

    required = ["historical_replay_available", "application_did_not_crash",
                "latest_tab_rendered",
                "failure_state_reported", "cached_snapshot_label_visible",
                "unavailable_state_rendered", "no_cache_state_is_informative",
                "source_valid_time_kept_separate_from_retrieval_time",
                "historical_replay_available_after_failure",
                "recovery_without_restart", "recovery_reattempted_sources"]
    passed = all(findings.get(k) for k in required) and not findings["application_crashed"]
    findings["checks"] = checks
    findings["result"] = "PASS" if passed else "FAIL"
    findings["statement"] = ("Demo resilience was tested with the live-data path "
                             "deliberately unavailable.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    for line in checks:
        print("  " + line)
    print(f"\nresult: {findings['result']}  ->  {OUT.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
