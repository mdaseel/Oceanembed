"""Historical cyclone event rule — external chronology only.

Frozen in ``outputs/events/EVENT_LIBRARY_RULE.md`` before any reconstruction of
a newly added event existed. Applied to Mocha it reproduces the Phase 7D
pre-registered window and segments exactly; that equality is pinned by tests.
Nothing here reads an OceanEmbed output.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

RULE_DOC = "outputs/events/EVENT_LIBRARY_RULE.md"

#: Named by the phase request, not chosen here.
CANDIDATES = (("MOCHA", "2023"), ("BIPARJOY", "2023"), ("TAUKTAE", "2021"),
              ("YAAS", "2021"), ("AMPHAN", "2020"), ("FANI", "2019"))

PRE_DAYS = 4       # window starts this many days before formation
POST_DAYS = 8      # and ends this many days after landfall
WAKE_DAYS = 4      # wake = landfall+1 .. landfall+WAKE_DAYS

DOMAIN = {"south": 5.0, "north": 30.0, "west": 45.0, "east": 105.0}
RECORD_START = pd.Timestamp("2015-01-01")
RECORD_END = pd.Timestamp("2024-12-15")
SPLITS = (("train", "2015-01-01", "2020-12-31"),
          ("validation", "2021-01-01", "2021-12-31"),
          ("test", "2022-01-01", "2024-12-15"))
SPLIT_NOTES = {
    "train": ("Training-period dates: this reconstruction is IN-SAMPLE. The frozen "
              "L2 saw these days when it was fitted."),
    "validation": ("Validation-period dates: used for model selection, not for "
                   "fitting weights. Not a locked out-of-sample test."),
    "test": "Locked test-split dates: out-of-sample for the frozen L2.",
    "mixed": "The window spans more than one data split.",
}
SUBBASIN_NAMES = {"BB": "Bay of Bengal", "AS": "Arabian Sea"}


class RuleExclusion(ValueError):
    """The rule cannot define a window for this storm; it is excluded, not improvised."""


def _number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def fixes_from_rows(rows) -> list[dict]:
    """IBTrACS CSV rows -> time-sorted fixes carrying only the fields the rule uses."""
    fixes = []
    for row in rows:
        lat, lon = _number(row.get("LAT")), _number(row.get("LON"))
        if lat is None or lon is None:
            continue
        fixes.append({
            "time": str(row["ISO_TIME"]).strip(),
            "lat": lat,
            "lon": lon,
            "imd_wind_kt": _number(row.get("NEWDELHI_WIND")),
            "imd_pressure_hpa": _number(row.get("NEWDELHI_PRES")),
            "usa_wind_kt": _number(row.get("USA_WIND")),
            "nature": (row.get("NATURE") or "").strip(),
            "dist2land_km": _number(row.get("DIST2LAND")),
        })
    fixes.sort(key=lambda p: p["time"])
    return fixes


@dataclass(frozen=True)
class Chronology:
    formation: str
    peak: str
    peak_time: str
    landfall: str
    landfall_time: str
    window_start: str
    window_end: str
    segments: tuple


def _day(time: str) -> pd.Timestamp:
    return pd.Timestamp(time).normalize()


def _iso(ts: pd.Timestamp) -> str:
    return str(ts.date())


def peak_fix(fixes: list[dict]) -> dict:
    """Highest IMD wind; ties -> lower IMD pressure, then the earliest fix."""
    imd = [p for p in fixes if p["imd_wind_kt"] is not None]
    if not imd:
        raise RuleExclusion("no fix carries an IMD agency wind value")
    return sorted(imd, key=lambda p: (
        -p["imd_wind_kt"],
        p["imd_pressure_hpa"] if p["imd_pressure_hpa"] is not None else float("inf"),
        p["time"]))[0]


def chronology(fixes: list[dict]) -> Chronology:
    imd = [p for p in fixes if p["imd_wind_kt"] is not None]
    if not imd:
        raise RuleExclusion("no fix carries an IMD agency wind value")
    formation = _day(imd[0]["time"])
    peak = peak_fix(fixes)
    land = [p for p in fixes if p["dist2land_km"] == 0]
    if not land:
        raise RuleExclusion("no landfall fix (DIST2LAND == 0)")
    peak_day, landfall = _day(peak["time"]), _day(land[0]["time"])
    if peak_day > landfall:
        raise RuleExclusion("peak intensity falls after the landfall date")
    one = pd.Timedelta(days=1)
    start, end = formation - PRE_DAYS * one, landfall + POST_DAYS * one
    spans = (("Pre-event", start, formation - one),
             ("Approach / intensification", formation, peak_day - one),
             ("Event", peak_day, landfall),
             ("Wake", landfall + one, landfall + WAKE_DAYS * one),
             ("Recovery", landfall + (WAKE_DAYS + 1) * one, end))
    segments = tuple({"label": label, "start": _iso(a), "end": _iso(b)}
                     for label, a, b in spans if a <= b)
    return Chronology(_iso(formation), _iso(peak_day), peak["time"], _iso(landfall),
                      land[0]["time"], _iso(start), _iso(end), segments)


def split_for(start: str, end: str) -> str:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    for name, a, b in SPLITS:
        if pd.Timestamp(a) <= s and e <= pd.Timestamp(b):
            return name
    return "mixed"


def inside_domain(lat: float, lon: float) -> bool:
    return (DOMAIN["south"] <= lat <= DOMAIN["north"]
            and DOMAIN["west"] <= lon <= DOMAIN["east"])


def window_dates(start: str, end: str) -> list[str]:
    return [str(d.date()) for d in pd.date_range(start, end, freq="D")]
