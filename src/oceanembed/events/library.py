"""The enabled historical cyclone events, read from bundled build-time assets.

No network access and no inference: every asset was produced by
``scripts/poc/build_event_library.py`` from IBTrACS under the frozen rule in
``outputs/events/EVENT_LIBRARY_RULE.md``. The response for each event keeps the
exact shape the dashboard already reads for Mocha, so one UI serves all events.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import REPO_ROOT

ASSET_DIR = REPO_ROOT / "web" / "public" / "assets" / "events"

INDEPENDENCE_NOTE = (
    "Every date is an independent replay_field call. No temporal model, no "
    "sequence input, and no state carried between days. This is a strip of "
    "independent daily reconstructions, never a forecast.")
CLAIM_NOTE = (
    "OceanEmbed reconstructs the subsurface ocean thermal state the cyclone "
    "encountered. It did not predict the storm's genesis, track, landfall, "
    "category or intensity.")


class EventNotFound(KeyError):
    """No enabled event with this id."""


_CACHE: dict[Path, tuple[float, dict]] = {}


def _read(path: Path) -> dict:
    stamp = path.stat().st_mtime
    hit = _CACHE.get(path)
    if hit is None or hit[0] != stamp:
        _CACHE[path] = hit = (stamp, json.loads(path.read_text(encoding="utf-8")))
    return hit[1]


def load_index(asset_dir: Path | None = None) -> dict:
    path = (asset_dir or ASSET_DIR) / "index.json"
    if not path.is_file():
        return {"events": [], "candidates": [], "rule": None, "source": None}
    return _read(path)


def _asset(event_id: str, asset_dir: Path | None = None) -> dict:
    base = asset_dir or ASSET_DIR
    if event_id not in load_index(base).get("events", []):
        raise EventNotFound(event_id)
    return _read(base / f"{event_id}.json")


def get_event(event_id: str, asset_dir: Path | None = None) -> dict:
    """One enabled event in the dashboard's event shape, plus its provenance."""
    a = _asset(event_id, asset_dir)
    return {
        "event_id": a["event_id"],
        "name": a["display_name"],
        "short_name": a["name"],
        "season": a["season"],
        "basin": a["basin"],
        "window_start": a["replay_start"],
        "window_end": a["replay_end"],
        "formation": a["formation"],
        "peak": a["peak"],
        "landfall": a["landfall"],
        "segments": a["segments"],
        "selection": a["phase_rule"],
        "frozen": a["frozen"],
        "split": a["split"],
        "in_sample": a["in_sample"],
        "split_note": a["split_note"],
        "external_metadata": a["external_metadata"],
        "availability": a["availability"],
        "track_fixes_inside_domain": a["track_fixes_inside_domain"],
        "track_fixes_total": a["track_fixes_total"],
        "independence_note": INDEPENDENCE_NOTE,
        "claim_note": CLAIM_NOTE,
        "track_available": bool(a.get("track")),
        "track": a.get("track"),
    }


def list_events(asset_dir: Path | None = None) -> dict:
    """Enabled events (summaries) and every candidate with its exclusion reason."""
    index = load_index(asset_dir)
    events = []
    for event_id in index.get("events", []):
        e = get_event(event_id, asset_dir)
        events.append({k: e[k] for k in (
            "event_id", "name", "short_name", "season", "basin", "window_start",
            "window_end", "peak", "landfall", "split", "in_sample", "split_note",
            "frozen", "external_metadata", "track_fixes_inside_domain",
            "track_fixes_total")} | {
            "track_source": (e["track"] or {}).get("dataset"),
            "track_agency": (e["track"] or {}).get("agency"),
            "replay_days": e["availability"]["days"],
        })
    return {"events": events, "candidates": index.get("candidates", []),
            "rule": index.get("rule"), "source": index.get("source")}
