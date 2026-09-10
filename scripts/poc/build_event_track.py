"""Bundle one cyclone best track offline, from IBTrACS (NOAA NCEI).

Build-time only, exactly like the ETOPO terrain and bathymetry: fetch once,
subset to the single pre-registered storm, record the source checksum, and write
a small local asset. The running application performs no network access.

The track is STATIC GEOGRAPHIC CONTEXT. It is never a model input, never an
OceanEmbed output, and it never enters inference, the diagnostics or any mask.
Intensity columns are the IMD/RSMC New Delhi agency values carried by IBTrACS,
not a re-analysis by this project.

Source and event are fixed by outputs/phase7/EVENT_SELECTION.md.

    python scripts/poc/build_event_track.py
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "assets" / "event"

SOURCE_URL = ("https://www.ncei.noaa.gov/data/"
              "international-best-track-archive-for-climate-stewardship-ibtracs/"
              "v04r01/access/csv/ibtracs.NI.list.v04r01.csv")

# Fixed by the pre-registered event selection. Not chosen here.
EVENT_NAME = "MOCHA"
EVENT_SEASON = "2023"

CITATION = ("Knapp, K. R., M. C. Kruk, D. H. Levinson, H. J. Diamond and "
            "C. J. Neumann (2010), The International Best Track Archive for "
            "Climate Stewardship (IBTrACS): Unifying tropical cyclone best "
            "track data, Bull. Amer. Meteor. Soc., 91, 363-376. Data: IBTrACS "
            "Project v04r01, NOAA NCEI, doi:10.25921/82ty-9e16.")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OceanEmbed/7D"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read()


def extract(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    next(reader, None)  # IBTrACS repeats a units row beneath the header
    points: list[dict] = []
    for row in reader:
        if (row.get("NAME", "").strip().upper() != EVENT_NAME
                or row.get("SEASON", "").strip() != EVENT_SEASON):
            continue
        try:
            lat, lon = float(row["LAT"]), float(row["LON"])
        except (KeyError, ValueError):
            continue

        def number(field: str):
            value = (row.get(field) or "").strip()
            try:
                return float(value)
            except ValueError:
                return None

        points.append({
            "time": row["ISO_TIME"].strip(),
            "lat": lat,
            "lon": lon,
            # IMD is the WMO agency of record for this basin; USA columns are
            # kept only as a labelled secondary reference.
            "imd_wind_kt": number("NEWDELHI_WIND"),
            "imd_pressure_hpa": number("NEWDELHI_PRES"),
            "usa_wind_kt": number("USA_WIND"),
            "nature": (row.get("NATURE") or "").strip(),
        })
    points.sort(key=lambda p: p["time"])
    return points


def main() -> int:
    print(f"fetching {SOURCE_URL}")
    raw = fetch(SOURCE_URL)
    source_sha = hashlib.sha256(raw).hexdigest()
    print(f"  {len(raw):,} bytes · sha256 {source_sha}")

    points = extract(raw)
    if not points:
        raise SystemExit(f"no {EVENT_NAME} {EVENT_SEASON} points found in IBTrACS")

    winds = [p["imd_wind_kt"] for p in points if p["imd_wind_kt"] is not None]
    pressures = [p["imd_pressure_hpa"] for p in points
                 if p["imd_pressure_hpa"] is not None]
    payload = {
        "schema": 1,
        "event": f"Cyclone {EVENT_NAME.title()} ({EVENT_SEASON})",
        "basin": "North Indian (Bay of Bengal)",
        "dataset": "IBTrACS v04r01, North Indian basin",
        "agency": "IMD / RSMC New Delhi, via IBTrACS",
        "provider": "NOAA National Centers for Environmental Information",
        "source_url": SOURCE_URL,
        "source_sha256": source_sha,
        "citation": CITATION,
        "licence": "US Government work, public domain; NOAA/NCEI attribution retained",
        "role": "static geographic context; not a model input, not an OceanEmbed "
                "output, and never used in inference, diagnostics or masks",
        "n_points": len(points),
        "first_time": points[0]["time"],
        "last_time": points[-1]["time"],
        "peak_imd_wind_kt": max(winds) if winds else None,
        "min_imd_pressure_hpa": min(pressures) if pressures else None,
        "points": points,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    (OUT / "track.json").write_text(text, encoding="utf-8")
    print(f"  {len(points)} track points {points[0]['time']} .. {points[-1]['time']}")
    print(f"  peak IMD wind {payload['peak_imd_wind_kt']} kt · "
          f"min pressure {payload['min_imd_pressure_hpa']} hPa")
    print(f"wrote {(OUT / 'track.json').relative_to(ROOT)} "
          f"({len(text):,} bytes, sha256 {hashlib.sha256(text.encode()).hexdigest()[:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
