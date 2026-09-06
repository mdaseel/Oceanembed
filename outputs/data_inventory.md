# OceanEmbed — Phase 6A Data Inventory (STEP 0)

Generated: 2026-09-04
Source archives (unmodified, in repo root):
- `Ocean embed datas.zip` (369.8 MB)
- `Agro data.zip` (21.9 MB)

Working copies extracted to: `data/raw/_extracted/` (originals untouched).

Inspection scripts: `scripts/inspect/inspect_all.py`

---

## 1. Summary table

| # | Dataset / product | File(s) | Format | Key variables | Dims | Lat coverage | Lon coverage | Date coverage | Spatial res | Temporal res | Depth | Units | Missing encoding | Phase 6A? | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **SST — NOAA/NCEI Daily OISST v2.1 (AVHRR-OI)** *(NOT OSTIA)* | `sst/2019123112…nc`, `sst/2020010112…nc` | NetCDF4 CF-1.6 | `analysed_sst`, `analysis_error`, `mask`, `sea_ice_fraction` | time,lat,lon (1,720,1440) | −89.875 → 89.875 (asc) | −179.875 → 179.875 | **2019-12-31, 2020-01-01** (2 days) | 0.25° | daily | surface | **kelvin** | `_FillValue` → NaN; land ~33% | **PARTIAL** | Usable as `sst`, but product is AVHRR-OI not the PDF-mandated OSTIA; only 2 days |
| 2 | **SSS — SMAP JPL L3 CAP v5.0, 8-DAY RUNNING MEAN** | `sss/SMAP_L3_SSS_2019122[8-31]_8DAYS…`, `…2020010[1-5]_8DAYS…` (9 files) | NetCDF4 | `smap_sss`, `smap_sss_uncertainty`, `anc_sss`, `anc_sst`, `land_fraction`, `ice_fraction` | latitude,longitude (720,1440) + scalar time | −89.875 → 89.875 (**desc**) | −179.875 → 179.875 | file-stamps **2019-12-28 → 2020-01-05** (each = trailing 8-day mean) | 0.25° | 8-day running mean (stamped daily) | surface | `1e-3` (≈ PSU) | `_FillValue` → NaN; ~48% global | **YES (with caveat)** | Only viable `sss` source; it is an 8-day smoothed field, not a true daily product |
| 3 | **SMOS CATDS L2Q SSS** *(folder misnamed `ssh/` — this is SALINITY, not sea level)* | `ssh/cmems_obs-mob_glo_phy-sss_mynrt_smos-asc_P1D_…3701.nc` (global), `…5266.nc` (domain subset) | NetCDF4 CF-1.11 | `Sea_Surface_Salinity`, `_QC`, `_Rain_Corrected`, `X_Swath` | time,lat,lon | file1 global −83.6→83.6; **file2 5.0→29.8N** | file1 global; **file2 45.2→105.0E** | file1 time stamp **2026-09-02 (bogus/placeholder)**; **file2: 2020-01-01, 2020-01-02** | ~0.2° | daily (ascending pass) | surface | `0.001` (≈ PSU) | NaN; **86–98% missing** in domain | **NO (backup only)** | Extremely sparse; redundant with SMAP; file1 time stamp is corrupt |
| 4 | **Currents — OSCAR L4_OC_FINAL v2.0** | `OSCAR/oscar_currents_final_202001[01-08].nc` (8 files) + `OSCAR/oscar_all_data.csv` (global dump, 1,035,360 rows) | NetCDF4 CF-1.8; cftime **Julian** calendar | `u`, `v` (total), `ug`, `vg` (geostrophic) | time,longitude,latitude (1,1440,719) | −89.75 → 89.75 (asc) | **0.0 → 359.75 (0–360)** | **2020-01-01 → 2020-01-08** (8 days) | 0.25° | daily | ~top 30 m avg | m s⁻¹ | NaN; ~44% (land+ice) | **YES** | Usable as `current_u`/`current_v` from `u`/`v`; needs lon 0–360 → −180–180 and Julian→proleptic time |
| 5 | **Winds — CCMP v3.1 L4** | `ccmp/CCMP_Wind_Analysis_2020010[1-2]_V03.1_L4.nc` (2 files) | NetCDF4 CF-1.7 | `uwnd`, `vwnd`, `ws`, `nobs` | time,latitude,longitude (4,720,1440) | −78.375 → 78.375 | **0.125 → 359.875 (0–360)** | **2020-01-01, 2020-01-02** (4 × 6-hourly each) | 0.25° | **6-hourly** | 10 m | m s⁻¹ | multiple `_FillValue` (1e30) → NaN | **YES** | Usable as `wind_u`/`wind_v`; aggregate 6-hourly → daily mean of U and V independently |
| 6 | **Winds — MetOp-C ASCAT-L2-Coastal** | `ascat/ascat_20200101_*_metopc_*.l2.nc` (7 swaths) | NetCDF4 CF-1.6 | `wind_speed`, `wind_dir`, `model_speed`, `model_dir`, `wvc_quality_flag` | NUMROWS,NUMCELLS (3168,82) | swath, global track | swath (0–360) | **2020-01-01 only** | L2 swath (~12.5 km WVC) | per-overpass | 10 m | speed m s⁻¹ / dir deg | NaN; ~51% | **NO (not for smoke test)** | Raw swath L2, not gridded/daily-complete; kept in docs per instructions; CCMP is the smoke-test wind source |
| 7 | **Target — GLORYS12V1 `thetao`** | `Glorys.nc` | NetCDF4 CF-1.11 | `thetao` | time,depth,latitude,longitude (31,**1**,301,720) | **5.0 → 30.0N (domain-subset)** | **45.0 → 104.92E (domain-subset)** | **2020-01-01 → 2020-01-31** (31 days, daily) | **1/12° (0.0833°)** | daily | ⚠️ **depth = 1 level only: 0.494 m** | °C | NaN; ~50% (land) | **PARTIAL — BLOCKER** | Only the surface level supplied → `temp_0m` possible; **temp_50m/100m/500m/1000m CANNOT be built** (STEP 9 blocked) |
| 8 | **Validation — INCOIS gridded ARGO** | `Argo gridded.nc` | NetCDF4 COARDS | `TEMP` | time,ZAX,latitude,longitude (2,19,25,61) | 5.5 → 29.5N | 45.5 → 105.5E | **monthly: 2020-01-15, 2020-02-15** | 1° | monthly | 19 levels: 5,10,20,30,50,75,100,125,150,200,250,300,400,500,600,700,800,900,1000 m | `degs` (°C) | NaN; ~58% | **INVENTORY ONLY** (STEP 14) | Monthly 1° field; validation deferred to later phase |
| 9 | **Raw Argo profiles (GDAC)** | `Agro_data/2020010[1-31]_prof.nc` (31 daily files) | NetCDF Argo-3.1 | `PRES`, `TEMP`, `PSAL` (+ `_ADJUSTED`, `_QC`), `LATITUDE`, `LONGITUDE`, `JULD`, `PLATFORM_NUMBER` | N_PROF,N_LEVELS (~79,1014) | **global floats** (day 1: −64 → +17) | global | **2020-01-01 → 2020-01-31** (daily) | point profiles | per-cycle | native pressure levels to ~5700 dbar | °C / dbar / PSU | `_FillValue` + QC flags | **INVENTORY ONLY** (STEP 14) | Raw QC'd profiles; must be filtered to 5–30N/45–105E; validation deferred |

---

## 2. Canonical variable-name mapping (supplied → OceanEmbed)

| OceanEmbed channel | Source product | Source var | Native units | Target units | Conversion |
|---|---|---|---|---|---|
| `sst` | OISST v2.1 (AVHRR-OI) | `analysed_sst` | K | °C | −273.15 |
| `sss` | SMAP L3 8-day | `smap_sss` | 1e-3 (PSU) | PSU | none |
| `sla` | **— MISSING —** | — | — | — | **no DUACS product supplied** |
| `current_u` | OSCAR FINAL v2.0 | `u` | m s⁻¹ | m s⁻¹ | none |
| `current_v` | OSCAR FINAL v2.0 | `v` | m s⁻¹ | m s⁻¹ | none |
| `wind_u` | CCMP v3.1 | `uwnd` | m s⁻¹ | m s⁻¹ | 6-hourly → daily mean |
| `wind_v` | CCMP v3.1 | `vwnd` | m s⁻¹ | m s⁻¹ | 6-hourly → daily mean |
| `temp_0m` | GLORYS12V1 | `thetao` @ 0.494 m | °C | °C | none (nearest surface level) |
| `temp_50m/100m/500m/1000m` | **— MISSING —** | — | — | — | **GLORYS supplied with 1 depth level only** |

---

## 3. Conflicts vs. the Phase 6A instructions / official PDF

| # | Instruction | Supplied reality | Severity |
|---|---|---|---|
| C1 | Smoke-test window 2019-04-25 → 2019-05-10 (Cyclone Fani) | All supplied data is **January 2020**. Fani absent. | **High** — period must change |
| C2 | GLORYS target → vertical interpolation to 0/50/100/500/1000 m (STEP 9) | `Glorys.nc` has **1 depth level (0.494 m)** | **Blocker** — no subsurface target |
| C3 | SLA/SSH from DUACS (DOI 10.48670/moi-00145) — mandated channel | No sea-level product in archive; `ssh/` folder actually holds SMOS **salinity** | **Blocker** — mandated input missing |
| C4 | SST from OSTIA (DOI 10.48670/moi-00168) | Supplied SST is **AVHRR-OI / OISST v2.1** | Medium — defensible substitute, needs sign-off |
| C5 | CCMP daily coverage for the window | CCMP present for **2 days only** (2020-01-01/02) | Medium — limits usable window to 2 days |
| C6 | SSS ideally daily | SMAP supplied is **8-day running mean**; SMOS is 86–98% empty | Medium — smoothed proxy only |

### Actual cross-product overlap (supplied data)
`sst` ∩ `sss` ∩ `currents` ∩ `winds` ∩ `GLORYS` = **2020-01-01 and 2020-01-02** (2 days).
Constrained by SST (2 days) and CCMP (2 days). OSCAR has 8 days, GLORYS 31 days, SMAP 9 file-days.

---

## 4. What can be built from supplied data alone
- Canonical 0.25° grid + config (STEPS 3–4)
- 5 of 7 surface channels regridded to 0.25°, daily, for 2020-01-01/02: `sst`, `sss`, `current_u`, `current_v`, `wind_u`, `wind_v` (6 fields; `sla` absent)
- `temp_0m` target only (GLORYS surface)
- Sanity checks, overlap check, partial merge, single-cell proof (surface), diagnostic figures
- Argo inventory (gridded + raw profiles filtered to domain)
- Automated preprocessing tests

## 5. What is blocked pending download + authentication
| Need | Product | DOI / ID | Provider | Auth |
|---|---|---|---|---|
| Subsurface target (C2) | GLORYS12V1 multi-depth `thetao`, 50 levels, 5–30N/45–105E | 10.48670/moi-00021 (`cmems_mod_glo_phy_my_0.083deg_P1D-m` / `cmems_mod_glo_phy_myint_*`) | Copernicus Marine | **free account + `copernicusmarine login`** |
| SLA channel (C3) | DUACS L4 SLA, 5–30N/45–105E | 10.48670/moi-00145 (`cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.25deg_P1D`) | Copernicus Marine | same account |
| Optional OSTIA (C4) | OSTIA L4 SST | 10.48670/moi-00168 (`METOFFICE-GLO-SST-L4-REP-OBS-SST`) | Copernicus Marine | same account |
