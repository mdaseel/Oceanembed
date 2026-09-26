# Live / NRT Cyclone Context — Source Decision

**Status:** FROZEN 2026-09-14, before any live-cyclone adapter code was written.
Evidence was gathered by direct requests to the providers on 2026-09-13/14.

External cyclone information is **context only**. It never becomes an L2 input,
never influences a reconstruction, and is always displayed as external.

---

## 1. Candidates examined

### IMD / RSMC New Delhi — the authoritative North Indian Ocean agency

| Question | Finding |
|---|---|
| Accessible? | Yes — `https://rsmcnewdelhi.imd.gov.in/` |
| Machine-readable track? | **No.** "Observed & Forecast Track", national/RSMC/TCAC/quadrant-wind bulletins and storm-surge guidance are **PDF**; fishermen warnings and probability-of-exceedance charts are **PNG**. |
| `track-forecast.php` | Forecast-**verification** statistics (images), not advisories. |
| "Interactive Track" (`dss.imd.gov.in/dwr_img/GIS/cyclone.html`) | A Leaflet page drawing PNG overlays over ArcGIS boundary services; no documented track data service was found. |
| Active system on check | Homepage products read "No Cyclone". |
| Parsing reliability | Parsing PDFs or scraping an undocumented page is not a reliable operational path. |

**Decision: not integrated in this build.** The UI states:
*"IMD / RSMC New Delhi official track: not connected in this build — official
advisories are published as PDF bulletins."*

### GDACS — Global Disaster Alert and Coordination System (EC JRC / UN OCHA)

| Question | Finding |
|---|---|
| Accessible? | Yes, public, no authentication. |
| Machine-readable? | Yes — JSON / GeoJSON. |
| Discovery | `gdacsapi/api/events/geteventlist/EVENTS4APP` lists current events with `eventtype`, `iscurrent`, `fromdate`, `todate`, `source`, `episodeid`. `…/SEARCH?eventlist=TC&fromDate=…&toDate=…` returns archived events. |
| Track geometry | `gdacsapi/api/polygons/getgeometry?eventtype=TC&eventid=…&episodeid=…` |
| Point times | One `Point_Polygon_Point_N` (`featuretype: PointRadii`) per track position; `key` = `MMDDHHMM`, `polygonlabel` = `"DD/MM HH:MM UTC"` (**no year** — taken from the episode's `polygondate`). The position is the centre of the radii polygon; it coincides with the `Line_Line_N` segment vertices. |
| Observed vs forecast | `Line_Line_N` segments carry a boolean **`forecast`**; `polygondate` is the episode (advisory) time. Verified on archived episodes: Mocha ep 6 (5 of 10 segments forecast, advisory 2023-05-12 06:00), Mocha ep 15 (2 of 16, advisory 2023-05-14 12:00), Biparjoy ep 12 (7 of 18, 2023-06-09 00:00). |
| Segment order | Not ordered and not continuous in the response; the track must be rebuilt from the timed positions. |
| Intensity | Segment `polygonlabel` gives a class (TD/TS/HU); no numeric wind or pressure per position → **not invented**. |
| Uncertainty | `Poly_Cones` "Uncertainty Cones" polygon is provided by GDACS. |
| Provenance for the North Indian Ocean | Event `source` = **JTWC** for Mocha-23 and Biparjoy-23 — **not IMD**. |
| Active North Indian Ocean system on check | **None.** The only current tropical cyclone was NORBERT-26 (East Pacific, source NOAA). |

**Decision: GDACS is adopted for live discovery and track geometry, with exact
provenance.**

## 2. Provenance semantics (binding on the UI and API)

- Label: **"External track · GDACS (EC JRC / UN OCHA) · track source: <GDACS
  `source` field, e.g. JTWC>"**.
- Never labelled "IMD", "official" or "RSMC" unless the GDACS `source` field
  itself says so.
- Observed position = at or before the episode advisory time; forecast position
  = after it. The segment `forecast` flags are cross-checked and any disagreement
  is reported, not silently resolved.
- Missing wind/pressure are left missing.
- A cached advisory is shown only as **"CACHED — NOT CURRENT"** with its
  retrieval time.
- An archived GDACS event used to exercise the parser and UI is always labelled
  **"HISTORICAL / TEST EVENT"** and never presented as live.
- No commercial weather API is used.

## 3. North Indian Ocean scope rule

A GDACS tropical-cyclone event is treated as North Indian Ocean when at least one
of its track positions lies inside **0–32 °N, 40–100 °E**. This is a documented
display rule for discovery, not a forecast corridor. Track × thermal analysis
samples only positions inside the OceanEmbed domain (5–30 °N, 45–105 °E).

## 4. Track × OceanEmbed

Track positions are sampled on the latest **qualified** OceanEmbed field (or a
historical replay date). Distances use great-circle (haversine) steps along the
position sequence; category intersections are the lengths of steps whose sample
cell carries the backend thermal-support category. No corridor width is invented
for live tracks: sampling is along the line, and GDACS's own uncertainty cone is
displayed only as GDACS geometry.
