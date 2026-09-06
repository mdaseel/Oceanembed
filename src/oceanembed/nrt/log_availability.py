"""One-shot availability poll. Run repeatedly to accumulate a latency record.

    python -m oceanembed.nrt.log_availability

Scheduling is deliberately OUT of scope: this is compatibility research
infrastructure, not a production scheduler. To build a latency record, invoke
this command on a cadence of your choosing (for example daily via cron or Task
Scheduler). Every invocation appends one poll cycle; ``first_seen`` for an
already-seen valid time is never overwritten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from ..config import REPO_ROOT
from .discover import poll_product
from .latency import append_poll, summarise
from .registry import PRODUCTS

OUT = REPO_ROOT / "outputs" / "nrt"
LOG = OUT / "latency_log.parquet"


def main(keys=None) -> int:
    keys = keys or [k for k, v in PRODUCTS.items() if v["role"] != "reference"] + \
        ["sst_reference", "sla_reference", "currents_reference", "wind_reference"]
    rows = []
    for k in keys:
        r = poll_product(k)
        nv = r["newest_valid_time"]
        lat = ("" if nv is None else
               f"  newest={str(nv)[:10]}  snapshot_latency="
               f"{(pd.Timestamp(r['query_time']) - pd.Timestamp(nv)).total_seconds()/86400:.2f}d")
        print(f"  {k:20s} {'OK ' if r['success'] else 'FAIL'}{lat}"
              f"{'' if r['success'] else '  ' + str(r['error'])[:60]}", flush=True)
        rows.append(r)
    df = append_poll(LOG, rows)
    s = summarise(LOG)
    OUT.mkdir(parents=True, exist_ok=True)
    s.to_csv(OUT / "latency_summary.csv", index=False)
    (REPO_ROOT / "outputs" / "tables").mkdir(parents=True, exist_ok=True)
    s.to_csv(REPO_ROOT / "outputs" / "tables" / "phase6cd_latency_summary.csv", index=False)
    snap = {"snapshot_time": str(pd.Timestamp.utcnow().tz_localize(None)),
            "poll_cycles_recorded": int(df["poll_cycle"].nunique()),
            "sources": {r["product_key"]: {
                "dataset_id": r["dataset_id"],
                "newest_valid_time": str(r["newest_valid_time"]),
                "snapshot_latency_days": r["measured_latency_days"]}
                for _, r in df[df.poll_cycle == df.poll_cycle.max()].iterrows()}}
    json.dump(snap, open(OUT / "source_availability_snapshot.json", "w"), indent=2)
    print(f"\nlog now holds {len(df)} rows over {df['poll_cycle'].nunique()} poll cycle(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or None))
