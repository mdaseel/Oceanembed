"""GDACS tropical-cyclone adapter: discovery and track geometry, with provenance.

Decision and field semantics: ``outputs/cyclones/LIVE_SOURCE_DECISION.md``.

- GDACS (EC JRC / UN OCHA) is the machine-readable path. For North Indian Ocean
  storms its ``source`` field is typically JTWC. The track is labelled with that
  field and is NEVER called IMD, RSMC or official unless the field says so.
- A position is observed when its time is at or before the episode advisory time
  (``polygondate``) and forecast after it. GDACS segment ``forecast`` flags are
  cross-checked and disagreements are reported, not resolved silently.
- Wind and pressure are not given per position by this geometry and are left
  missing, never guessed.
- The external track is context. It never enters an OceanEmbed reconstruction.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import REPO_ROOT

API = "https://www.gdacs.org/gdacsapi/api"
PROVIDER = "GDACS (Global Disaster Alert and Coordination System, EC JRC / UN OCHA)"
ATTRIBUTION = "Track geometry: GDACS, EC Joint Research Centre / UN OCHA. gdacs.org"
NIO_BOX = {"lat": (0.0, 32.0), "lon": (40.0, 100.0)}
TIMEOUT_S = 25
TRACK_CLASSES = ("Point_Polygon_Point_", "Line_Line_", "Poly_Cones")
CACHE_FILE = REPO_ROOT / "outputs" / "cyclones" / "advisory_cache.json"
ARCHIVED_DIR = REPO_ROOT / "outputs" / "cyclones" / "archived"

LIVE = "LIVE"
CACHED = "CACHED_NOT_CURRENT"
TEST = "HISTORICAL_TEST_EVENT"

ACTIVE = "ACTIVE_NORTH_INDIAN_CYCLONE"
NONE_ACTIVE = "NO_ACTIVE_NORTH_INDIAN_CYCLONE"
UNAVAILABLE = "SOURCE_UNAVAILABLE"
CACHED_STATE = "CACHED_ADVISORY_NOT_CURRENT"

IMD_STATUS = ("IMD / RSMC New Delhi official track: not connected in this build. "
              "Official advisories are published as PDF bulletins, which are not a "
              "reliable machine-readable track source.")


class GdacsParseError(ValueError):
    """The response does not have the structure this adapter was verified against."""


@dataclass
class TrackPoint:
    valid_time: str
    lat: float
    lon: float
    point_type: str                 # "observed" | "forecast"
    source: str
    storm_class: str | None = None
    wind_kt: float | None = None    # not provided by GDACS geometry
    pressure_hpa: float | None = None


@dataclass
class Advisory:
    source: str
    provider: str
    track_source: str
    source_event_id: str
    episode_id: str
    storm_name: str
    basin: str
    advisory_issued_at: str
    retrieved_at: str
    status: str
    observed_points: list[TrackPoint] = field(default_factory=list)
    forecast_points: list[TrackPoint] = field(default_factory=list)
    forecast_flag_disagreements: list[dict] = field(default_factory=list)
    uncertainty_cone: list | None = None
    report_url: str | None = None
    attribution: str = ATTRIBUTION
    provenance_label: str = ""
    alert_level: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def points(self) -> list[TrackPoint]:
        return self.observed_points + self.forecast_points


def fetch_json(url: str, timeout: float = TIMEOUT_S):
    req = urllib.request.Request(url, headers={"User-Agent": "OceanEmbed/cyclone-context"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def provenance_label(track_source: str) -> str:
    return f"External track · GDACS (EC JRC / UN OCHA) · track source: {track_source or 'not stated'}"


def parse_event_list(payload) -> list[dict]:
    """Tropical-cyclone events from an EVENTS4APP / SEARCH response."""
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise GdacsParseError("event list has no 'features' array")
    events = []
    for feature in payload["features"]:
        p = feature.get("properties") or {}
        if p.get("eventtype") != "TC":
            continue
        events.append({
            "eventid": str(p.get("eventid")),
            "episodeid": str(p.get("episodeid")),
            "name": p.get("eventname") or p.get("name"),
            "iscurrent": str(p.get("iscurrent")).lower() == "true",
            "source": p.get("source") or "",
            "fromdate": p.get("fromdate"), "todate": p.get("todate"),
            "alertlevel": p.get("alertlevel"),
            "report_url": (p.get("url") or {}).get("report"),
        })
    return events


def _center(ring: list) -> tuple[float, float]:
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2


def _time_from_key(key: str, advisory: datetime) -> datetime:
    """``key`` is MMDDHHMM with no year; the year comes from the advisory time."""
    if not (isinstance(key, str) and len(key) == 8 and key.isdigit()):
        raise GdacsParseError(f"unexpected position key {key!r}")
    month, day, hour, minute = int(key[:2]), int(key[2:4]), int(key[4:6]), int(key[6:])
    year = advisory.year
    if month - advisory.month > 6:
        year -= 1
    elif advisory.month - month > 6:
        year += 1
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def parse_geometry(payload, event: dict, retrieved_at: str, status: str = LIVE) -> Advisory:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise GdacsParseError("geometry has no 'features' array")
    feats = payload["features"]
    # The advisory time is the polygondate of the TRACK features. Wind-buffer
    # polygons (Poly_Green / Poly_Orange / Poly_Red) carry one date per forecast
    # time and are not the advisory time (verified on live NORBERT-26 ep16).
    dates = {f["properties"].get("polygondate") for f in feats
             if (f.get("properties") or {}).get("polygondate")
             and str(f["properties"].get("Class", "")).startswith(TRACK_CLASSES)}
    if len(dates) != 1:
        raise GdacsParseError(f"expected one advisory time, found {sorted(dates)}")
    advisory = datetime.fromisoformat(dates.pop()).replace(tzinfo=timezone.utc)
    track_source = event.get("source") or ""

    positions = {}
    for f in feats:
        p = f.get("properties") or {}
        if not str(p.get("Class", "")).startswith("Point_Polygon_Point_"):
            continue
        if f.get("geometry", {}).get("type") != "Polygon":
            raise GdacsParseError("position radii is not a polygon")
        lat, lon = _center(f["geometry"]["coordinates"][0])
        when = _time_from_key(p.get("key"), advisory)
        positions[when] = (round(lat, 2), round(lon, 2))
    if not positions:
        raise GdacsParseError("no timed track positions")

    ordered = sorted(positions.items())
    classes: dict[tuple, str] = {}
    disagreements = []
    for f in feats:
        p = f.get("properties") or {}
        if not str(p.get("Class", "")).startswith("Line_Line_"):
            continue
        coords = f.get("geometry", {}).get("coordinates") or []
        if len(coords) != 2:
            continue
        end_lat, end_lon = coords[1][1], coords[1][0]
        match = [t for t, (la, lo) in ordered
                 if abs(la - end_lat) <= 0.06 and abs(lo - end_lon) <= 0.06]
        if not match:
            continue
        when = match[0]
        classes[(end_lat, end_lon)] = p.get("polygonlabel")
        derived = when > advisory
        flag = str(p.get("forecast")).lower() == "true"
        if flag != derived:
            disagreements.append({"segment": p.get("Class"), "end_time": when.isoformat(),
                                  "gdacs_forecast_flag": flag, "time_rule_forecast": derived})

    observed, forecast = [], []
    for when, (lat, lon) in ordered:
        storm_class = next((c for (la, lo), c in classes.items()
                            if abs(la - lat) <= 0.06 and abs(lo - lon) <= 0.06), None)
        point = TrackPoint(valid_time=when.isoformat().replace("+00:00", "Z"), lat=lat, lon=lon,
                           point_type="forecast" if when > advisory else "observed",
                           source=f"GDACS / {track_source or 'not stated'}",
                           storm_class=storm_class)
        (forecast if point.point_type == "forecast" else observed).append(point)

    cone = next((f["geometry"]["coordinates"] for f in feats
                 if (f.get("properties") or {}).get("Class") == "Poly_Cones"), None)
    return Advisory(
        source="GDACS", provider=PROVIDER, track_source=track_source,
        source_event_id=str(event.get("eventid")), episode_id=str(event.get("episodeid")),
        storm_name=str(event.get("name") or ""), basin="North Indian Ocean",
        advisory_issued_at=advisory.isoformat().replace("+00:00", "Z"),
        retrieved_at=retrieved_at, status=status,
        observed_points=observed, forecast_points=forecast,
        forecast_flag_disagreements=disagreements, uncertainty_cone=cone,
        report_url=event.get("report_url"), provenance_label=provenance_label(track_source),
        alert_level=event.get("alertlevel"))


def is_north_indian(advisory: Advisory) -> bool:
    (s, n), (w, e) = NIO_BOX["lat"], NIO_BOX["lon"]
    return any(s <= p.lat <= n and w <= p.lon <= e for p in advisory.points)


def _save_cache(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def current_cyclones(fetch: Callable = fetch_json, cache_path: Path | None = None,
                     now: Callable[[], str] = _now_iso) -> dict:
    """Active North Indian Ocean cyclones according to GDACS, or an explicit state."""
    cache = cache_path or CACHE_FILE
    retrieved = now()
    try:
        events = parse_event_list(fetch(f"{API}/events/geteventlist/EVENTS4APP"))
        current = [e for e in events if e["iscurrent"]]
        advisories, other = [], []
        for e in current:
            geometry = fetch(f"{API}/polygons/getgeometry?eventtype=TC"
                             f"&eventid={e['eventid']}&episodeid={e['episodeid']}")
            adv = parse_geometry(geometry, e, retrieved, LIVE)
            (advisories if is_north_indian(adv) else other).append(adv)
    except Exception as exc:  # noqa: BLE001 - an outage or a changed schema is a state
        error = f"{type(exc).__name__}: {exc}"
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"state": UNAVAILABLE, "provider": PROVIDER, "retrieved_at": None,
                    "checked_at": retrieved, "advisories": [], "error": error,
                    "message": "Cyclone advisory source currently unavailable.",
                    "imd_status": IMD_STATUS, "decision": "outputs/cyclones/LIVE_SOURCE_DECISION.md"}
        for adv in cached.get("advisories", []):
            adv["status"] = CACHED
        return {**cached, "state": CACHED_STATE if cached.get("advisories") else cached["state"],
                "cached": True, "checked_at": retrieved, "error": error,
                "message": "Cached advisory — not current. Source unavailable at "
                           f"{retrieved}; last retrieved {cached.get('retrieved_at')}."}

    result = {
        "state": ACTIVE if advisories else NONE_ACTIVE,
        "provider": PROVIDER, "retrieved_at": retrieved, "checked_at": retrieved,
        "cached": False, "tc_events_checked": len(events), "current_tc_events": len(current),
        "current_outside_north_indian": [a.storm_name for a in other],
        "advisories": [a.as_dict() for a in advisories],
        "message": (f"{len(advisories)} active North Indian Ocean cyclone(s) reported by GDACS."
                    if advisories else
                    "No active North Indian Ocean cyclone reported by connected source (GDACS)."),
        "imd_status": IMD_STATUS, "attribution": ATTRIBUTION,
        "decision": "outputs/cyclones/LIVE_SOURCE_DECISION.md",
    }
    _save_cache(result, cache)
    return result


def archived_test_advisory(directory: Path | None = None) -> dict:
    """Archived GDACS Mocha-23 episode 6, served ONLY as a labelled test event."""
    base = directory or ARCHIVED_DIR
    event_data = json.loads((base / "mocha-23_eventdata.json").read_text(encoding="utf-8"))
    geometry = json.loads((base / "mocha-23_geometry_ep6.json").read_text(encoding="utf-8"))
    props = event_data["properties"]
    event = {"eventid": props["eventid"], "episodeid": 6, "name": props["eventname"],
             "source": props.get("source"), "alertlevel": props.get("alertlevel"),
             "report_url": (props.get("url") or {}).get("report")}
    adv = parse_geometry(geometry, event, retrieved_at="archived response recorded 2026-09-14",
                         status=TEST)
    return {"state": TEST, "label": "HISTORICAL / TEST EVENT",
            "note": ("Archived GDACS response for Cyclone Mocha 2023, episode 6. Shown only "
                     "to exercise the external-track parser and the track x thermal "
                     "analysis. It is not a current advisory."),
            "advisories": [adv.as_dict()], "provider": PROVIDER, "imd_status": IMD_STATUS,
            "attribution": ATTRIBUTION}
