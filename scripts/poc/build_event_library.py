"""Bundle the historical cyclone event library offline, from IBTrACS (NOAA NCEI).

Build-time only, like ``build_event_track.py``: the running application
performs no network access for historical events. The candidate set, the
chronology rule and the eligibility checks are frozen in
``outputs/events/EVENT_LIBRARY_RULE.md``.

Eligibility reads ONLY the ``surface_input_valid`` and ``ocean_mask`` arrays of
the frozen model-ready stores. No model runs, no diagnostic is computed and no
reference is compared here.

Mocha is not re-derived: its asset carries the frozen Phase 7D window, segments
and bundled track verbatim, and the build aborts if the rule would disagree.

    python scripts/poc/build_event_library.py            # uses the local IBTrACS copy
    python scripts/poc/build_event_library.py --fetch    # downloads it first
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from oceanembed.events import rule as R  # noqa: E402

SOURCE_URL = ("https://www.ncei.noaa.gov/data/"
              "international-best-track-archive-for-climate-stewardship-ibtracs/"
              "v04r01/access/csv/ibtracs.NI.list.v04r01.csv")
LOCAL_CSV = ROOT / "data" / "raw" / "ibtracs" / "ibtracs.NI.list.v04r01.csv"
MODEL_READY = ROOT / "data" / "processed" / "model_ready"
OUT = ROOT / "web" / "public" / "assets" / "events"
FROZEN_TRACK = ROOT / "web" / "public" / "assets" / "event" / "track.json"
MANIFEST = ROOT / "outputs" / "events" / "event_library_manifest.json"

CITATION = ("Knapp, K. R., M. C. Kruk, D. H. Levinson, H. J. Diamond and "
            "C. J. Neumann (2010), The International Best Track Archive for "
            "Climate Stewardship (IBTrACS): Unifying tropical cyclone best "
            "track data, Bull. Amer. Meteor. Soc., 91, 363-376. Data: IBTrACS "
            "Project v04r01, NOAA NCEI, doi:10.25921/82ty-9e16.")
ROLE = ("static geographic context; not a model input, not an OceanEmbed output, "
        "and never used in inference, diagnostics or masks")


def read_csv(fetch: bool) -> tuple[bytes, str]:
    if fetch:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "OceanEmbed/events"})
        with urllib.request.urlopen(req, timeout=300) as response:
            raw = response.read()
        LOCAL_CSV.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_CSV.write_bytes(raw)
    else:
        if not LOCAL_CSV.is_file():
            raise SystemExit(f"{LOCAL_CSV} missing; run with --fetch once")
        raw = LOCAL_CSV.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest()


def storm_rows(raw: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="replace")))
    next(reader, None)  # IBTrACS repeats a units row beneath the header
    wanted = set(R.CANDIDATES)
    rows = defaultdict(list)
    for row in reader:
        key = (row.get("NAME", "").strip().upper(), row.get("SEASON", "").strip())
        if key in wanted:
            rows[key].append(row)
    return rows


def availability(start: str, end: str) -> dict:
    """Data availability only: presence and joint surface-input counts per day."""
    days, missing, counts = R.window_dates(start, end), [], {}
    stores: dict[int, xr.Dataset] = {}
    for day in days:
        year = int(day[:4])
        path = MODEL_READY / f"oceanembed_{year}.zarr"
        if year not in stores:
            if not path.exists():
                missing.append(day)
                continue
            stores[year] = xr.open_zarr(path, consolidated=True)
        ds = stores[year]
        times = pd.DatetimeIndex(ds.time.values).normalize()
        hit = np.flatnonzero(times == pd.Timestamp(day))
        if not len(hit):
            missing.append(day)
            continue
        counts[day] = int(ds["surface_input_valid"].isel(time=int(hit[0])).values.sum())
    values = list(counts.values())
    return {"days": len(days), "missing_dates": missing,
            "zero_input_dates": [d for d, n in counts.items() if n == 0],
            "valid_cells_min": min(values) if values else None,
            "valid_cells_median": int(np.median(values)) if values else None,
            "valid_cells_max": max(values) if values else None,
            "checked": "surface_input_valid counts in the frozen model-ready store; "
                       "no inference"}


def eligibility(chron: R.Chronology, fixes: list[dict], avail: dict) -> list[str]:
    reasons = []
    if pd.Timestamp(chron.window_start) < R.RECORD_START or \
            pd.Timestamp(chron.window_end) > R.RECORD_END:
        reasons.append("window outside the processed record 2015-01-01..2024-12-15")
    if avail["missing_dates"]:
        reasons.append(f"dates missing from the model-ready store: {avail['missing_dates']}")
    if avail["zero_input_dates"]:
        reasons.append(f"dates with no valid surface input: {avail['zero_input_dates']}")
    peak = R.peak_fix(fixes)
    if not R.inside_domain(peak["lat"], peak["lon"]):
        reasons.append("peak-intensity fix outside the reconstruction domain")
    if sum(R.inside_domain(p["lat"], p["lon"]) for p in fixes) < 2:
        reasons.append("fewer than two track fixes inside the domain")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()

    raw, sha = read_csv(args.fetch)
    frozen_track = json.loads(FROZEN_TRACK.read_text(encoding="utf-8"))
    if frozen_track["source_sha256"] != sha:
        print(f"NOTE: IBTrACS checksum {sha} differs from the frozen Mocha track "
              f"source {frozen_track['source_sha256']}; Mocha keeps its frozen asset.")
    from oceanembed.poc.app import EVENT as FROZEN_MOCHA

    grouped = storm_rows(raw)
    OUT.mkdir(parents=True, exist_ok=True)
    index = {"schema": 1,
             "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "rule": R.RULE_DOC,
             "source": {"dataset": "IBTrACS v04r01, North Indian basin",
                        "url": SOURCE_URL, "sha256": sha},
             "candidates": [], "events": []}

    for name, season in R.CANDIDATES:
        event_id = f"{name.lower()}-{season}"
        record = {"event_id": event_id, "name": name.title(), "season": int(season)}
        rows = grouped.get((name, season), [])
        if not rows:
            index["candidates"].append({**record, "enabled": False,
                                        "exclusion_reasons": ["storm not found in IBTrACS"]})
            continue
        fixes = R.fixes_from_rows(rows)
        try:
            chron = R.chronology(fixes)
        except R.RuleExclusion as exc:
            index["candidates"].append({**record, "enabled": False,
                                        "exclusion_reasons": [str(exc)]})
            continue

        frozen = name == "MOCHA" and season == "2023"
        if frozen:
            rule_view = {"window_start": chron.window_start, "window_end": chron.window_end,
                         "peak": chron.peak, "landfall": chron.landfall,
                         "segments": list(chron.segments)}
            frozen_view = {k: FROZEN_MOCHA[k] for k in rule_view}
            if rule_view != frozen_view:
                raise SystemExit(f"rule disagrees with frozen Mocha: {rule_view} vs {frozen_view}")

        avail = availability(chron.window_start, chron.window_end)
        reasons = eligibility(chron, fixes, avail)
        subbasins = sorted({r.get("SUBBASIN", "").strip() for r in rows} - {""})
        basin = " / ".join(R.SUBBASIN_NAMES.get(s, s) for s in subbasins) or "North Indian Ocean"
        split = R.split_for(chron.window_start, chron.window_end)
        peak = R.peak_fix(fixes)
        pressures = [p["imd_pressure_hpa"] for p in fixes if p["imd_pressure_hpa"] is not None]
        usa = [p["usa_wind_kt"] for p in fixes if p["usa_wind_kt"] is not None]

        if frozen:
            track = frozen_track
            segments = FROZEN_MOCHA["segments"]
            window = (FROZEN_MOCHA["window_start"], FROZEN_MOCHA["window_end"])
            peak_day, landfall_day = FROZEN_MOCHA["peak"], FROZEN_MOCHA["landfall"]
            basin = FROZEN_MOCHA["basin"]
        else:
            track = {
                "schema": 1,
                "event": f"Cyclone {name.title()} ({season})",
                "basin": f"North Indian ({basin})",
                "dataset": "IBTrACS v04r01, North Indian basin",
                "agency": "IMD / RSMC New Delhi, via IBTrACS",
                "provider": "NOAA National Centers for Environmental Information",
                "source_url": SOURCE_URL, "source_sha256": sha,
                "citation": CITATION,
                "licence": "US Government work, public domain; NOAA/NCEI attribution retained",
                "role": ROLE,
                "n_points": len(fixes),
                "first_time": fixes[0]["time"], "last_time": fixes[-1]["time"],
                "peak_imd_wind_kt": peak["imd_wind_kt"],
                "min_imd_pressure_hpa": min(pressures) if pressures else None,
                "points": [{k: p[k] for k in ("time", "lat", "lon", "imd_wind_kt",
                                              "imd_pressure_hpa", "usa_wind_kt", "nature",
                                              "dist2land_km")} for p in fixes],
            }
            segments = list(chron.segments)
            window = (chron.window_start, chron.window_end)
            peak_day, landfall_day = chron.peak, chron.landfall

        asset = {
            "schema": 1,
            "event_id": event_id,
            "display_name": f"Cyclone {name.title()} ({season})",
            "name": name.title(), "season": int(season),
            "sid": sorted({r["SID"] for r in rows}),
            "basin": basin, "subbasin_codes": subbasins,
            "replay_start": window[0], "replay_end": window[1],
            "formation": chron.formation, "peak": peak_day, "landfall": landfall_day,
            "peak_time": chron.peak_time, "landfall_time": chron.landfall_time,
            "segments": segments,
            "phase_rule": ("outputs/phase7/EVENT_SELECTION.md (frozen Phase 7D)"
                           if frozen else R.RULE_DOC),
            "frozen": frozen,
            "split": split, "in_sample": split == "train",
            "split_note": R.SPLIT_NOTES[split],
            "external_metadata": {
                "intensity_source": "IMD / RSMC New Delhi agency columns via IBTrACS "
                                    "(3-minute sustained wind)",
                "peak_imd_wind_kt": peak["imd_wind_kt"],
                "peak_imd_wind_time": peak["time"],
                "min_imd_pressure_hpa": min(pressures) if pressures else None,
                "jtwc_peak_wind_kt_1min": max(usa) if usa else None,
                "first_landfall_fix_time": chron.landfall_time,
            },
            "track_fixes_inside_domain": sum(R.inside_domain(p["lat"], p["lon"]) for p in fixes),
            "track_fixes_total": len(fixes),
            "availability": avail,
            "enabled": not reasons,
            "exclusion_reasons": reasons,
            "track": track,
        }
        (OUT / f"{event_id}.json").write_text(json.dumps(asset, indent=2), encoding="utf-8")
        index["candidates"].append({**record, "enabled": not reasons,
                                    "exclusion_reasons": reasons, "split": split,
                                    "basin": basin, "replay_start": window[0],
                                    "replay_end": window[1]})
        if not reasons:
            index["events"].append(event_id)
        print(f"{event_id:16s} {'ENABLED ' if not reasons else 'EXCLUDED'} "
              f"{window[0]}..{window[1]} {split:10s} {basin} {reasons or ''}")

    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        **index,
        "assets": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in sorted(OUT.glob("*.json"))},
        "frozen_mocha_track_sha256": hashlib.sha256(FROZEN_TRACK.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    print(f"wrote {len(index['events'])} enabled events to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
