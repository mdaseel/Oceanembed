# Phase 6A.5 — Storage & Download Plan

Written **before** acquisition, as required. All per-day sizes below are **measured**, not guessed:
Copernicus figures come from the actual Phase 6A downloads; PO.DAAC figures come from live CMR
granule metadata queried on 2026-09-04.

---

## 1. Free disk

| | |
|---|---|
| Volume | `C:` |
| Total | 476 GB |
| Used | 292 GB |
| **Free** | **185 GB** |

## 2. Window

`DATASET_START = 2015-01-01`, `DATASET_END = 2024-12-15` → **3,637 days**.

`DATASET_END` is **not** a choice — it is the hard end of the official multi-year SSS reanalysis
(`cmems_obs-mob_glo_phy-sss_my_multi_P1D`, DOI 10.48670/moi-00051), which stops at 2024-12-15.
Every other product extends well beyond it (see §4 of the main report). The prompt's target end
date and the binding product limit coincide exactly.

## 3. Measured per-day volume (domain-subset, 1° padded box: lat 4–31 N, lon 44–106 E)

| Product | Access | Subsetting | Measured MB/day | × 3,637 days |
|---|---|---|---|---|
| GLORYS12V1 `thetao`, 36 levels 0–1200 m | Copernicus | server-side | 17.45 | **63.5 GB** |
| OSTIA `analysed_sst` 0.05° | Copernicus | server-side | 1.35 | **4.9 GB** |
| MULTIOBS SSS `sos` 0.125° | Copernicus | server-side | ~0.40 | **1.5 GB** |
| DUACS `sla` 0.25° | Copernicus | server-side | 0.10 | **0.4 GB** |
| | | | **Copernicus subtotal** | **≈ 70 GB** |
| CCMP v3.1 winds | PO.DAAC | **none on direct download** | 32.0 (global) | 116 GB ⚠ |
| OSCAR FINAL v2.0 currents | PO.DAAC | **none on direct download** | 31.7 (global) | 115 GB ⚠ |
| | | | **PO.DAAC subtotal (naive)** | **≈ 231 GB** |
| | | | **NAIVE TOTAL** | **≈ 301 GB** |

### The PO.DAAC problem, and the fix
CCMP and OSCAR are distributed only as **global** daily files. Our domain is 2.6 % of the globe, so a
naive download transfers ~231 GB to keep ~6 GB — and 301 GB total exceeds comfortable headroom
against 185 GB free.

Both collections **do** expose OPeNDAP endpoints (confirmed in CMR granule metadata):
- CCMP → `https://opendap.earthdata.nasa.gov/collections/C2916514952-POCLOUD/granules/...`
- OSCAR → `https://opendap.earthdata.nasa.gov/collections/C2098858642-POCLOUD/granules/...`

Requesting only the `lat`/`lon` index range (and only `uwnd`,`vwnd` / `u`,`v`) via a DAP4 constraint
expression moves the subsetting server-side and reduces transfer by ~40×.

| Product | Naive | Via OPeNDAP subset | Saving |
|---|---|---|---|
| CCMP | 116 GB | ~3.0 GB | 113 GB |
| OSCAR | 115 GB | ~2.9 GB | 112 GB |

## 4. Planned footprint (with OPeNDAP subsetting)

| Stage | Size |
|---|---|
| Raw — Copernicus | ~70 GB |
| Raw — PO.DAAC (subset) | ~6 GB |
| **Raw total** | **≈ 76 GB** |
| Processed model-ready Zarr (see §5) | ~5–8 GB |
| **Peak total** | **≈ 84 GB** |
| Free afterwards | ~100 GB |

**Verdict: fits comfortably in 185 GB free.** No disk problem, *provided* OPeNDAP subsetting is used
for the two PO.DAAC products. Without it the job is ~301 GB and would leave <30 GB headroom —
not acceptable.

## 5. Processed-volume arithmetic

Canonical grid 101 × 241 = 24,341 cells · 3,637 days · float32.
- 7 surface channels: 24,341 × 3,637 × 7 × 4 B ≈ **2.5 GB**
- 15 target depths: 24,341 × 3,637 × 15 × 4 B ≈ **5.3 GB**
- validity masks (bool/int8): ≈ 0.4 GB
- **≈ 8.2 GB uncompressed**; Zarr with compression on a ~50 % NaN field → **~4–6 GB actual**.

## 6. Chunking

Per-year Zarr stores under `data/processed/model_ready/oceanembed_<year>.zarr`.

Chosen chunks: **time = 32, lat = 101, lon = 241** (whole spatial field per chunk).
Rationale: every planned downstream access pattern — temporal windows, spatial patches, regime
masks, per-depth loss masking — reads whole maps over a short time span. Keeping lat/lon whole
avoids cross-chunk stitching for spatial patches, and time = 32 gives ~3 MB float32 chunks
(24,341 × 32 × 4 B), comfortably inside the 1–10 MB range Zarr performs best at. One year =
~11 time-chunks, so no single read pulls a whole year into RAM.

## 7. Download policy
- annual chunks per product (not one enormous request)
- **resume-safe**: an existing file is opened and its time-axis length verified before being skipped
- partial/corrupt files are detected (open fails or day-count mismatch) and re-fetched
- writes to `.part` then atomic rename, so an interrupted download can never masquerade as complete
- good raw files are never silently overwritten
- every request logs dataset ID, variables, bounding box, and date range to
  `outputs/logs/download_phase6a5.log`

## 8. Blocker identified at plan time

**NASA Earthdata Login credentials are absent** (`~/.netrc`, `~/_netrc`, `~/.edl_token` all missing).
OSCAR and CCMP cannot be fetched — by direct download *or* OPeNDAP — without them. The Copernicus
half (~70 GB: GLORYS, OSTIA, SSS, DUACS) is unblocked and proceeds immediately.
