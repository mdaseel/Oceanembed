"""Prospective provider-availability logger.

Why prospective. A file downloaded today from a revised historical archive says
nothing about what an operator could have obtained on the original date, so
historical latency CANNOT be reconstructed from today's archive state. The only
honest measurement is to start watching now and record, for each product, the
first moment OceanEmbed itself saw a given valid time appear in the catalogue.

    measured_availability_latency = first_seen_by_oceanembed - newest_valid_time

The log is APPEND-ONLY and ``first_seen_by_oceanembed`` is never overwritten on
a later poll. A short observation history is reported as a short observation
history - it is not extrapolated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LOG_COLUMNS = [
    "provider", "product_key", "product_id", "dataset_id",
    "query_time", "newest_valid_time", "provider_issue_time",
    "first_seen_by_oceanembed", "download_time", "revision", "granule_id",
    "checksum", "success", "error", "measured_latency_days", "poll_cycle",
]


def _now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


def load_log(path) -> pd.DataFrame:
    p = Path(path)
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=LOG_COLUMNS)


def append_poll(path, rows: list[dict]) -> pd.DataFrame:
    """Append poll results, preserving the original first_seen for a valid time.

    A (product_key, newest_valid_time) pair that has been seen before keeps its
    ORIGINAL first_seen_by_oceanembed. Only genuinely new valid times get a new
    first_seen, which is what makes the latency measurement meaningful.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = load_log(p)
    seen = {}
    if len(old):
        for _, r in old.iterrows():
            key = (r["product_key"], str(r["newest_valid_time"]))
            if key not in seen:
                seen[key] = r["first_seen_by_oceanembed"]

    cycle = 0 if not len(old) else int(pd.to_numeric(old["poll_cycle"]).max()) + 1
    out = []
    for r in rows:
        r = dict(r)
        key = (r["product_key"], str(r.get("newest_valid_time")))
        if key in seen:
            r["first_seen_by_oceanembed"] = seen[key]   # never overwritten
        else:
            r["first_seen_by_oceanembed"] = r.get("query_time")
        nv, fs = r.get("newest_valid_time"), r.get("first_seen_by_oceanembed")
        r["measured_latency_days"] = (
            float((pd.Timestamp(fs) - pd.Timestamp(nv)).total_seconds() / 86400.0)
            if (nv is not None and fs is not None and pd.notna(nv)) else None)
        r["poll_cycle"] = cycle
        for c in LOG_COLUMNS:
            r.setdefault(c, None)
        out.append({c: r[c] for c in LOG_COLUMNS})

    new = pd.concat([old, pd.DataFrame(out)], ignore_index=True) if len(old) \
        else pd.DataFrame(out)
    for c in ("query_time", "newest_valid_time", "first_seen_by_oceanembed",
              "download_time", "provider_issue_time"):
        new[c] = pd.to_datetime(new[c], errors="coerce")
    new.to_parquet(p, index=False)
    return new


def summarise(path) -> pd.DataFrame:
    """Per-product summary of what has ACTUALLY been observed so far."""
    df = load_log(path)
    if not len(df):
        return pd.DataFrame()
    rows = []
    for key, g in df.groupby("product_key"):
        firsts = g.drop_duplicates(subset=["newest_valid_time"], keep="first")
        ok = g[g["success"] == True]  # noqa: E712
        rows.append({
            "product_key": key,
            "provider": g["provider"].iloc[0],
            "dataset_id": g["dataset_id"].iloc[0],
            "n_polls": int(len(g)),
            "n_poll_cycles": int(g["poll_cycle"].nunique()),
            "n_distinct_valid_times_seen": int(g["newest_valid_time"].nunique()),
            "first_poll": g["query_time"].min(),
            "last_poll": g["query_time"].max(),
            "observation_span_days": float(
                (g["query_time"].max() - g["query_time"].min()).total_seconds() / 86400.0),
            "newest_valid_time_now": g["newest_valid_time"].max(),
            "latency_at_first_sight_days": float(firsts["measured_latency_days"].median())
            if firsts["measured_latency_days"].notna().any() else None,
            "min_latency_days": float(firsts["measured_latency_days"].min())
            if firsts["measured_latency_days"].notna().any() else None,
            "max_latency_days": float(firsts["measured_latency_days"].max())
            if firsts["measured_latency_days"].notna().any() else None,
            "poll_success_rate": float(len(ok) / len(g)) if len(g) else 0.0,
            "caveat": "SNAPSHOT latency: newest valid time minus the first poll that "
                      "saw it. With few poll cycles this is an UPPER BOUND on true "
                      "provider latency, since the field may have appeared earlier.",
        })
    return pd.DataFrame(rows).sort_values("product_key")
