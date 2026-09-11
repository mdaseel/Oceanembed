"""Phase 8B.11 — demo-day rehearsal of the latest qualified mode, end to end.

Drives the REAL application (the FastAPI app, its real endpoints, the real
frozen engine and the real providers) in one running process:

  1. online  -> a genuine latest qualified reconstruction from the live stack
  2. network cut at the socket layer (remote only; loopback kept, as in 8A)
       - Historical Replay and historical Ocean Hazard Indicators still work
       - the latest state becomes the snapshot, labelled NOT CURRENT
       - with no snapshot, the unavailable state is informative
  3. PARTIAL outage: only NASA Earthdata (OSCAR currents) unreachable
       - no latest inference happens on the incomplete stack
  4. network restored -> Retry -> the complete stack is re-qualified and a NEW
     frozen-L2 inference runs, with no restart

Inference is counted by instrumenting the engine's single inference method, so
"no inference ran" is measured rather than inferred from a status string.

Writes outputs/phase8b/operational_resilience_test.json (required: PASS) and
outputs/phase8b/latest_live_run.json (the provenance of the real live run).

    python scripts/nrt8b/run_operational_resilience_test.py
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "phase8b" / "operational_resilience_test.json"
LIVE_RUN = ROOT / "outputs" / "phase8b" / "latest_live_run.json"

_REAL_GAI = socket.getaddrinfo
_REAL_CONN = socket.create_connection
_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}
NASA = ("earthdata.nasa.gov", "nasa.gov", "podaac", "earthaccess")


class NetworkDisabled(OSError):
    """Raised in place of a blocked REMOTE connection."""


def cut(block) -> None:
    """Fail DNS and connects for hosts ``block(host)`` selects, below every client."""
    def gai(host, *a, **k):
        if str(host) not in _LOCAL and block(str(host)):
            raise NetworkDisabled(f"network deliberately disabled for rehearsal: {host}")
        return _REAL_GAI(host, *a, **k)

    def conn(address, *a, **k):
        if str(address[0]) not in _LOCAL and block(str(address[0])):
            raise NetworkDisabled(f"network deliberately disabled: {address[0]}")
        return _REAL_CONN(address, *a, **k)
    socket.getaddrinfo = gai               # type: ignore[assignment]
    socket.create_connection = conn        # type: ignore[assignment]


def restore() -> None:
    socket.getaddrinfo = _REAL_GAI         # type: ignore[assignment]
    socket.create_connection = _REAL_CONN  # type: ignore[assignment]


def main() -> int:
    from fastapi.testclient import TestClient

    from oceanembed.nrt import latest as LQ
    from oceanembed.poc import app as A
    from oceanembed.replay import api as replay_api

    findings: dict = {
        "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": "8B",
        "failure_method": (
            "socket.getaddrinfo and socket.create_connection replaced in the SAME "
            "running process so remote DNS/connects fail below every HTTP client and "
            "SDK (loopback kept). Full cut for the outage; NASA Earthdata hosts only "
            "for the partial-stack check."),
    }
    checks: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        findings[name] = bool(ok)
        checks.append(f"{'PASS' if ok else 'FAIL'} · {name}" + (f" — {detail}" if detail else ""))

    engine = replay_api.engine()
    calls = {"n": 0}
    real_infer = engine._infer

    def counted(*a, **k):
        calls["n"] += 1
        return real_infer(*a, **k)
    engine._infer = counted                # instance attribute: the one inference path

    client = TestClient(A.app)

    def latest():
        return client.get("/api/latest/qualified").json()

    # 1 — online: a genuine latest qualified reconstruction.
    before = calls["n"]
    first = latest()
    ok = first.get("state") == LQ.LIVE_STATE and calls["n"] > before
    detail = (f"valid {first.get('effective_date')}" if ok else
              "; ".join((first.get("live_attempt") or {}).get("reasons") or [first.get("state", "?")]))
    check("initial_latest_state_available", ok, detail)
    if ok:
        f = first["field"]
        LIVE_RUN.write_text(json.dumps({
            "state": first["state"], "effective_date": first["effective_date"],
            "sources": first["sources"], "meta": first["meta"],
            "policy": first["policy"],
            "qualification": {k: first["qualification"][k] for k in
                              ("temperature_category", "d26_category", "tchp_category",
                               "latest_hazard_indicators", "decision_sha256")},
            "l2_state_dict_sha256": f["provenance"]["l2_state_dict_sha256"],
            "l2_encoder_sha256": f["provenance"]["l2_encoder_sha256"],
            "n_supported_cells": f["provenance"]["n_supported_cells"],
            "compute_seconds": f["provenance"]["compute_seconds"],
            "diagnostics_withheld": f["diagnostics"]["withheld"],
            "hazard_category_counts": (f.get("hazard") or {}).get("category_counts"),
            "argo_opened": False,
        }, indent=2, default=str), encoding="utf-8")

    try:
        # 2 — full outage.
        cut(lambda host: True)
        r = client.get("/api/replay/view", params={"date": "2021-06-15"})
        hist_ok = r.status_code == 200 and r.json()["shape"] == [101, 241, 15]
        check("historical_replay_available_during_failure", hist_ok, str(r.status_code))
        hz = r.json().get("hazard") if hist_ok else None
        check("historical_hazard_indicators_available_during_failure",
              bool(hz and hz.get("available") and hz.get("category_counts")))

        n0 = calls["n"]
        stale = latest()
        check("stale_snapshot_displayed",
              stale.get("state") == LQ.SNAPSHOT_STATE and stale.get("field") is not None
              and calls["n"] == n0, stale.get("state", ""))
        check("stale_snapshot_label_visible", "NOT CURRENT" in (stale.get("label") or ""),
              stale.get("label") or "")
        findings["stale_snapshot_inference_source"] = (
            (stale.get("field") or {}).get("provenance", {}).get("inference_source"))

        real_dir = LQ.SNAPSHOT_DIR
        with tempfile.TemporaryDirectory() as empty:
            LQ.SNAPSHOT_DIR = Path(empty)
            try:
                bare = latest()
            finally:
                LQ.SNAPSHOT_DIR = real_dir
        check("unavailable_state_rendered",
              bare.get("state") == LQ.UNAVAILABLE_STATE
              and bare.get("label") == LQ.UNAVAILABLE_LABEL and bare.get("field") is None,
              bare.get("label") or "")
        restore()

        # 3 — partial outage: OSCAR (NASA) unreachable, Copernicus reachable.
        cut(lambda host: any(k in host for k in NASA))
        n1 = calls["n"]
        partial = latest()
        blocked = partial.get("state") != LQ.LIVE_STATE and calls["n"] == n1
        check("partial_stack_inference_blocked", blocked,
              "; ".join((partial.get("live_attempt") or {}).get("reasons") or [])[:200])
        restore()

        # 4 — recovery in the same process.
        n2 = calls["n"]
        rec = latest()
        new_run = rec.get("state") == LQ.LIVE_STATE and calls["n"] > n2
        check("recovery_without_restart", rec.get("state") in
              (LQ.LIVE_STATE, LQ.SNAPSHOT_STATE, LQ.UNAVAILABLE_STATE), rec.get("state", ""))
        check("complete_stack_requalified_after_recovery",
              new_run and all(s["state"] == "OK" for s in rec.get("sources", [])))
        check("new_l2_inference_after_recovery", new_run and
              rec["field"]["provenance"]["inference_source"] == "LIVE_MODEL_RUN")
    finally:
        restore()
        engine._infer = real_infer

    required = ["initial_latest_state_available",
                "historical_replay_available_during_failure",
                "historical_hazard_indicators_available_during_failure",
                "stale_snapshot_displayed", "stale_snapshot_label_visible",
                "unavailable_state_rendered", "recovery_without_restart",
                "complete_stack_requalified_after_recovery",
                "new_l2_inference_after_recovery", "partial_stack_inference_blocked"]
    findings["inference_calls_total"] = calls["n"]
    findings["checks"] = checks
    findings["result"] = "PASS" if all(findings.get(k) for k in required) else "FAIL"
    findings["statement"] = ("The latest qualified mode was rehearsed with the live-data "
                             "path deliberately unavailable, fully and partially.")
    OUT.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    for line in checks:
        print("  " + line)
    print(f"\nresult: {findings['result']}  ->  {OUT.relative_to(ROOT)}")
    return 0 if findings["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
