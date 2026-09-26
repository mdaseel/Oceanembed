# OceanEmbed Operational Current Candidate Research

**Session type:** research and experiment design only. Nothing was integrated, retrained,
downloaded in bulk, or configured. No production current source was changed. The protected
2024 Argo holdout was not opened. The Phase 8C GlobCurrent rejection stands unmodified.

**Repository state at start:** branch `main`, HEAD `7572a21`, clean tree.
**Live verification performed:** 2026-09-12, 15:20–18:20 UTC.

Throughout, four dates are kept separate, as required:
**source-file date** (the label in the filename), **model initialisation date**,
**field valid date**, and **retrieval date**. Several findings below exist only because
those four were not assumed equal.

---

## 1. Executive Decision

```
1. ISRO/SAC MOSDAC Global Ocean Surface Current  — RESEARCH MORE BEFORE TEST
                                                   (provider-access step required first)
2. NOAA Global RTOFS                             — TEST IF NEEDED (operational test only)
3. HYCOM ESPC-D-V02                              — TEST IF NEEDED (operational test only)
4. ECCC GIOPS                                    — TEST IF NEEDED (operational test only)
5. INCOIS RSMC HYCOM                             — NOT RECOMMENDED as an L2 input channel
```

Two results dominate everything else in this report, and both were measured, not assumed.

**First: the prize is at most three days.** Re-verified live at 2026-09-12 18:18 UTC:

| channel | newest valid date |
|---|---|
| `sla_nrt` | 2026-09-12 |
| `sst_nrt` | 2026-09-11 |
| `wind_nrt` | 2026-09-11 |
| **`sss_nrt_multiobs`** | **2026-09-06** |
| **`currents_nrt` (OSCAR NRT)** | **2026-09-03** |
| **common qualified date** | **2026-09-03** |

Replacing currents with a product valid *today* moves the common date only to
**2026-09-06**, because salinity becomes the binding channel. That is the same
**+3 days** Phase 8C measured. No candidate in this report can do better than +3 days,
and none of them can deliver "genuinely near-real-time" on its own. A project goal of a
same-day latest qualified reconstruction requires the **SSS** channel to be addressed too;
currents alone cannot reach it.

**Second: four of the five candidates cannot be scientifically qualified at all under the
present rules.** OceanEmbed's only observational gate (C8) uses authorized 2022–2023 Argo.
INCOIS, RTOFS-as-NetCDF, ESPC-D-V02 and GIOPS all fail to provide same-version historical
currents for that window — verified individually in §11. For them, the strongest available
evidence is an *operational* comparison, which is materially weaker than the gate the
rejected GlobCurrent candidate had to clear. Promoting a product on weaker evidence than
the one that was rejected would be incoherent.

MOSDAC is ranked first not because it is fresher — **its freshness could not be verified at
all** — but because it is the only candidate that is scientifically the *same kind of object*
as OSCAR: the same Bonjean & Lagerloef (2002) formulation, the same 0–30 m layer, the same
0.25° daily global grid, derived from altimetry + scatterometer wind + SST, with no
subsurface assimilation. If its archive exists, it is the only candidate that could clear the
real gate. If its archive does not exist, there is currently **no** candidate that can.

**Recommended action before SIH: none of these substitutions.** See §19.

---

## 2. Current OceanEmbed Bottleneck

OSCAR NRT stopped being produced. Re-verified against NASA CMR at 2026-09-12 15:22 UTC:

| collection | newest granule | valid | ingested |
|---|---|---|---|
| `OSCAR_L4_OC_NRT_V2.0` | `oscar_currents_nrt_20260903` | 2026-09-03 | 2026-09-05 06:12 UTC |
| `OSCAR_L4_OC_INTERIM_V2.0` | `oscar_currents_interim_20260831` | 2026-08-31 | 2026-09-05 08:12 UTC |
| `OSCAR_L4_OC_FINAL_V2.0` | `oscar_currents_final_20260116` | 2026-01-16 | 2026-08-19 |

Every OSCAR ingest timestamp still stops on 2026-09-05. The outage is now **7 days old** and
affects the whole OSCAR family, which is consistent with a production-side stoppage rather
than a per-collection delay. This confirms the Phase 8B addendum and adds a week of evidence.

Two facts follow:

- The lag is **not** an OceanEmbed defect. Discovery, intersection semantics and caching were
  already fixed in `ff96e27` / `8bc5d39`.
- The outage may end on its own. Nothing in this report should be read as evidence that
  OSCAR is permanently gone.

---

## 3. Frozen Scientific Constraints

| constraint | value |
|---|---|
| L2 state-dict SHA-256 | `b715bb2bff32d5e4a1e696b5350e29c3971fbd1cfd5d4b3f5c68bebe51ae728d` |
| L2 encoder SHA-256 | `30cfd2db9e8b6b96473c1e205280c0099a422a1ec4a3cc6d0dd6dee554db4808` |
| channels | `[sst, sss, sla, current_u, current_v, wind_u, wind_v]` |
| grid | 101 × 241 @ 0.25°, 5–30 °N, 45–105 °E |
| training currents | OSCAR v2.0 Final (`currents_reference`) |
| operational currents | OSCAR v2.0 NRT (`currents_nrt`) |
| alignment | `COMMON_VALID_DATE`, persistence envelope 0 days |
| validity mask | `isfinite(all 7).all(axis=0)` — a single joint mask |
| inference | `ReplayEngine._infer`, the only implementation |

Only `current_u` and `current_v` may vary in any experiment designed here. No retraining, no
output calibration, no scaler change, no threshold change, no second model.

**The precedent that binds this work:** Phase 8C rejected Copernicus GlobCurrent NRT
(`cmems_obs-mob_glo_phy-cur_nrt_0.25deg_P1D-m`) even though it passed every model-side and
reanalysis-side gate, because against authorized 2022–2023 Argo it degraded RMSE by
+1.42 / +1.67 / +1.64 % at 100 / 125 / 150 m, against a pre-registered allowance of +0.68 %.
That allowance is not arbitrary — it is the weakest policy 6C-C ever promoted
(`CURRENT_STALE_3D`). Any new candidate must clear the same bar.

**Directly relevant to this report:** GlobCurrent was a *multi-observation geostrophic +
Ekman* product — of all five candidates it was the one *closest* to OSCAR, and it still
failed on observations. Four of the five candidates here are 3-D assimilative ocean models,
which are *further* from OSCAR, not closer. That is a prior worth stating before any of them
is tested.

---

## 4. Candidate 1 — ISRO / SAC MOSDAC Global Ocean Surface Current

**Classification: B — multi-observation derived surface current product.**
**Semantic distance from OSCAR: VERY LOW.**

### What the product is

From the official MOSDAC product page: the product is "the average current for the top
0 to 30 m layer", derived from "the synergistic use of three different satellite derived
parameters" — altimeter-derived Maps of Absolute Dynamic Topography (JASON-2, SARAL/AltiKa,
CryoSat), gridded ocean surface vector winds from ASCAT, and gridded AVHRR SST. The page
states that "The methodology presented by Bonjean and Lagerloef, (2002) is used to derive
ocean surface currents."

That is *the OSCAR paper*. This is not a similar product; it is an independent
implementation of the same physics on the same class of inputs.

| property | value | source |
|---|---|---|
| resolution | 0.25° (~25 km) | product page |
| coverage | global, −90 to 90 °N, 0–360 °E | product page |
| temporal | daily | product page |
| depth semantics | **0–30 m layer average** | product page |
| variables | zonal and meridional components of ocean surface current | product page |
| units | m/s | product page |
| format / naming | NetCDF-4, `ISRO_CURRENT_TOT_YYYYMMDD.nc` (TOT = geostrophic + ageostrophic) | product page |
| version | **"Version 1.0 (beta)"**, metadata dated 2015-09-15 | product page |
| components | geostrophic + Ekman/wind-driven + thermal-wind, per Bonjean & Lagerloef | methodology |
| tides | not included (not part of the B&L formulation) | inferred from methodology — **to be confirmed from file metadata** |
| Stokes drift | not included | same |

NIO coverage: global, so 5–30 °N / 45–105 °E is fully covered with no edge handling needed,
**and the 0.25° grid is already the canonical OceanEmbed grid** — the only candidate for
which harmonisation is close to a no-op.

### Access — verified, and this is the blocker

The product page's "Click Here to access the Science Products" link resolves to:

```
https://www.mosdac.gov.in/opendata/ocean_surface_current/
```

Verified live:

- `https://www.mosdac.gov.in/opendata/` → **HTTP 401 Unauthorized**
- Navigating to `/opendata/ocean_surface_current/` in a browser → redirected to
  **"Sign in to MOSDAC Single Sign ON"**
- MOSDAC's catalog SPA calls `/catalog/Search/getAllProductData.php`,
  `getSatelliteData.php`, `getSensorData.php`, `getVersion.php`. These respond (400/403/500
  depending on headers) but their parameter schema is not publicly documented. **I did not
  guess at it and did not invent a schema.**
- The public MOSDAC *Satellite Catalog* UI lists only mission-level products (EOS-06,
  SARAL, SCATSAT-1, OCEANSAT-2, INSAT…). The derived Global Ocean Surface Current is a
  science product and does not appear there, so its Start/End dates are not publicly listed.

> **AUTHENTICATION BLOCKED — ACTUAL LATEST GRANULE NOT VERIFIED**
>
> I could not confirm that any granule exists for any date, recent or historical. No
> credentials were used, requested, or entered.

**Exact manual step needed** (one person, a few minutes):

1. Register a MOSDAC Single Sign On account at `https://www.mosdac.gov.in/`.
2. Sign in, then open `https://www.mosdac.gov.in/opendata/ocean_surface_current/`.
3. Record: (a) the newest `ISRO_CURRENT_TOT_YYYYMMDD.nc` present; (b) whether files exist for
   each of the last 10 days; (c) the **earliest** file present, and specifically whether
   2022-05-01 → 2023-12-31 is covered; (d) whether the listing is a plain directory that
   `curl` / `wget` can walk with a session cookie or token.
4. Open one file and record: exact U/V variable names, units, `_FillValue`, whether the time
   coordinate is a daily mean or an instant, and whether any attribute mentions tides or
   Stokes drift.

Until step 3 is done, every freshness and archive claim about MOSDAC is unverified.

### Honest risk flags

- **"Version 1.0 (beta)" with 2015 metadata.** An eleven-year-old beta label is not evidence
  that production stopped, but it is not evidence that it continues either. Item (a) above
  settles it.
- **Input continuity.** The documented altimeter inputs include JASON-2 (decommissioned 2019)
  and SARAL/AltiKa. If the processing chain was not re-pointed at the current altimeter
  constellation, recent files may exist but be degraded. The file metadata in step 4 should
  be checked for the actual contributing missions.
- **No documented programmatic API.** Automation would depend on an SSO session, which is
  operationally more fragile than the token-based `copernicusmarine` / `earthaccess` clients
  OceanEmbed already uses.

### Why it still ranks first

If — and only if — the archive exists, MOSDAC is the one candidate that could pass the real
gate: same formulation, same depth layer, same resolution, same daily cadence,
observation-derived, and with **no subsurface assimilation**, so it introduces no circularity.
For a problem statement about reconstructing subsurface temperature *from surface satellite
observations*, an ISRO satellite-derived current product is also the most defensible input
OceanEmbed could name at SIH.

---

## 5. Candidate 2 — INCOIS RSMC HYCOM

**Classification: C/D — data-assimilating 3-D ocean analysis, published as forecast.**
**Semantic distance from OSCAR: VERY HIGH.**

INCOIS turned out to have a **publicly readable THREDDS server** at
`https://incois.gov.in/thredds/` — no login. Two relevant catalogs were inspected live.

### 5.1 `osf/currents` — the Ocean State Forecast currents

Files `CURRENTS_IO_YYYYMMDD.nc` and `CURRENTS_NIO_YYYYMMDD.nc`, 597 MB each, present for
2026-09-05 … 2026-09-11 only (**7-day rolling window**). `CURRENTS_NIO_20260911.nc` was
published 2026-09-12 00:50 UTC.

OPeNDAP structure: `U`, `V`, `CURRENT` on `[TAXIS=32][DEPTH1_1=1][LAT=720][LON=1080]`,
`long_name "Surface Currents (m/s)"`, `standard_name eastward_current`, source
`.../OGCM/NIO_HOOFS/nioout_20260911.nc`.

**The decisive finding.** The time axis reads:

```
TAXIS units = "hours since 2026-09-09 01:30"
TAXIS       = 72, 75, 78, ... , 162, 165        (3-hourly, 32 steps)
```

which converts to valid times **2026-09-12 01:30 → 2026-09-15 22:30**.

A file *labelled* 2026-09-11 contains no field valid on 2026-09-11. It is initialised on
2026-09-09 and contains **only forecast leads +72 h to +165 h** — its earliest valid time is
already three days in the future. This is precisely the filename trap flagged in the brief.
Using this product as a "latest" current channel would feed pure forecast into the frozen
model while labelling the result an analysis of the past. That is disqualifying on its own.

Two further defects:

- `DEPTH1_1 = 0.0 m` — a single surface model level, **not** a 0–30 m average.
- Domain LON 30.0–119.88 °E, LAT −30.0 to **29.8927 °N** at 1/12°. OceanEmbed's grid runs to
  **30.0 °N**, so the northernmost row of the canonical grid falls **outside** the product
  domain and could only be filled by extrapolation. That would either break the joint validity
  mask or silently invent data.

### 5.2 `osf/currents2` — `RSMC_hycom_YYYYMMDD.nc`

10.58 GB/day, present 2026-09-06 … 2026-09-12 (**7-day rolling**). `RSMC_hycom_20260912.nc`
published 2026-09-12 00:16 UTC.

Structure: `UVEL`, `VVEL` (m/s, `eastward_current`), plus `TEMP`, `SALN`, `SSH`, `TCHP`, `MLD`
on `[TIME=28][DEPTH=6][LAT=1384][LON=1665]`; `DEPTH = 0, 10, 50, 100, 250, 500 m`;
LON 20.0–119.84 °E, LAT −44.93 to 30.95 °N at ~1/16°. **This one does cover the full
OceanEmbed box.**

Time axis (`days since 1900-12-31`): 45910.25 … 45917.0 →
**2026-09-11 06:00 → 2026-09-18 00:00**, 6-hourly.

So the file published at 00:16 UTC on 09-12 contains four steps at or before its publication
time (09-11 06/12/18 Z and 09-12 00 Z) and 24 steps in the future. A daily mean for 09-11
could in principle be assembled from consecutive files using only non-future steps, giving a
~1-day lag. **But** the 7-day span beginning 06:00 on the day *before* publication strongly
suggests the run is initialised at ~09-11 00 Z and that even the "past" steps are short-lead
forecast, not the DA analysis itself. I could not confirm which from the file metadata; this
would have to be confirmed with INCOIS directly before the product could be called a nowcast.

### 5.3 Circularity — the reason this is NOT RECOMMENDED

INCOIS HYCOM uses the T-SIS (Tendral Statistical Interpolation System) assimilation scheme,
which ingests altimetry, SST **and in-situ temperature/salinity profiles**, i.e. Argo. The
`RSMC_hycom` file makes this concrete: **it ships `TEMP` on six depth levels and `TCHP` in the
same file as the currents.** Those are the very quantities OceanEmbed reconstructs and the
quantities Phase 7C/7D derive.

Feeding `UVEL`/`VVEL` from that system into the frozen L2 means the "surface" input channel
carries information from an analysis that already contains the subsurface temperature field.
The project's claim — surface observations → embedding → subsurface temperature — would no
longer be cleanly true, and at SIH the obvious question ("your current field already knows the
subsurface; how much of your skill is that?") would have no clean answer.

### 5.4 Qualification

Archive is 7 days. There is no 2022–2023 INCOIS current archive on this server, so gate C8
cannot be run at all. **QUALIFICATION BLOCKED.**

---

## 6. Candidate 3 — NOAA Global RTOFS

**Classification: C — data-assimilating 3-D ocean analysis/nowcast (with forecast).**
**Semantic distance from OSCAR: HIGH.**

### Operational version and freshness — verified

Current operational version is **RTOFS v2.5**, implemented 2025-07-29. v2.5 added
climatological constraints on SSH assimilation, changed the DA-increment conversion, and
**added assimilation of velocity observations from drifting buoys and HF radar**. The version
operational during 2022–2023 was v2.3.

Live directory check, `https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod/`:

- Present: `rtofs.20260911/`, `rtofs.20260912/` — **a 2-day rolling window only.**
- `rtofs_glo_2ds_n000_prog.nc` published **12-Sep-2026 03:14 UTC**, 148 MB
- `rtofs_glo_2ds_n024_prog.nc` published **12-Sep-2026 03:24 UTC**, 148 MB
- `rtofs_glo_3dz_n024_daily_3zuio.nc` published **12-Sep-2026 03:19 UTC**, 861 MB

So the 00 Z cycle lands by ~03:20 UTC the same day. **RTOFS is the freshest usable
observation-independent option after GIOPS: same-day, ~3.5 h latency.**

Nowcast (`n000`–`n024`) and forecast (`f000`–`f192`) files are cleanly separated, so using
analysis/nowcast only is straightforward — no forecast-leakage risk, unlike INCOIS.

### Variable and depth semantics — verified from the file header

A 16 KB range read of `rtofs_glo_2ds_n024_prog.nc` shows an HDF5/netCDF-4 file with
`title = "HYCOM ATLb2.00"`, `source = "HYCOM archive file"`, `history = archv2ncdf2d`,
`experiment 93.1`, and the variable **`u_velocity`** (with `v_velocity` by symmetry).

Critically, the file carries a **`Layer`** dimension with `units = "layer"`, `positive = down`.
The "surface" current is the **top HYCOM hybrid layer**, whose thickness varies in space and
time, *not* a fixed depth and *not* a 0–30 m average. That is a genuine semantic mismatch
with OSCAR that no regridding fixes.

Recommendation on representation (answers Q10): if RTOFS were ever used, the defensible
choice is **not** the 2ds top-layer current but the daily
`rtofs_glo_3dz_n024_daily_3zuio` / `3zvio` z-level fields averaged over 0–30 m, because that
reconstructs OSCAR's documented layer rather than an arbitrary model layer. The cost is
861 MB per component per day.

### Historical archive — verified, and it is worse than it looks

The AWS Open Data bucket `noaa-nws-rtofs-pds` holds **960 day-prefixes, 2024-01-27 →
2026-09-12** — continuous, but starting only in 2024. That alone blocks 2022–2023.

Worse, a full enumeration of `rtofs.20260910/` (894 keys) shows the mirror carries:

- `rtofs_glo_2ds_*_diag.nc` (138) and `_ice.nc` (138) — SSH/SST/SSS/MLD and ice
- `rtofs_glo_3dz_*_6hrly_hvr_US_east / US_west / alaska.nc` — **regional only**
- native HYCOM `archv` / `archs` `.a.tgz` / `.b` binaries

and **no `rtofs_glo_2ds_*_prog.nc` and no global `3zuio` / `3zvio` at all**. The archive that
goes back does not contain the current fields; the place that contains them keeps two days.
Historical RTOFS currents would have to be reconstructed from the native `archv` binaries on
the tripolar curvilinear grid with HYCOM-specific tooling — and only back to 2024-01-27.

NCEI was checked as an alternative archive; `www.ncei.noaa.gov/data/oceans/ncep/rtofs/`
returned HTTP 503 and the THREDDS catalogs timed out at the time of checking.
**NOT VERIFIED** — worth one retry before any RTOFS work, but it cannot change the
version-continuity problem.

### Circularity

RTOFS assimilates in-situ T/S profiles (Argo) through NCODA, and from v2.5 also assimilates
observed velocities. Subsurface-assimilation concern: **HIGH**.

**QUALIFICATION BLOCKED** for 2022–2023: no same-version data, and no NetCDF current archive.

---

## 7. Candidate 4 — HYCOM ESPC-D-V02

**Classification: C — data-assimilating 3-D ocean analysis with 8-day forecast.**
**Semantic distance from OSCAR: HIGH.**

Verified directly from the `tds.hycom.org` root catalog, which states:

> **ESPC-D-V02: Global 1/12° Analysis (Aug-10-2024 to Present with 8-day forecast)**

with these dataset families:

| dataset | contents |
|---|---|
| `ESPC-D-V02 ice` | 1-hourly `sic, sih, siu, siv, sss, sst, `**`ssu, ssv`**`, surtx, surty` |
| `ESPC-D-V02 u3z` / `v3z` | 3-hourly `water_u` / `water_v` on z-levels |
| `ESPC-D-V02 uv3z` | 3-hourly combined `water_u`, `water_v` |
| `ESPC-D-V02 ssh` / `Sssh` | 1-hourly `surf_el`, `steric_ssh` |
| `ESPC-D-V02 t3z` / `s3z` | 3-hourly `water_temp`, `salinity` |

**Q11 answered definitively: no. The current operational version begins 2024-08-10.** There is
no same-version data before August 2024, and therefore none for 2022–2023. Its predecessor,
GOFS 3.1 `GLBy0.08/expt_93.0`, covers Dec-04-2018 → Sep-04-2024 and *does* span 2022–2023 —
but it is a different system version, and historical data from an older version must not be
treated as validation of the current operational one.

**Q12 answered: yes.** Under the protected-2024-Argo rule, gate C8 needs 2022–2023
collocations, and ESPC-D-V02 simply does not exist then. The observational gate is
unreachable for this product. The alternative allowed evidence — GLORYS reanalysis comparison
over 2024-07-01 → 2024-12-15, and direct-vs-OSCAR overlap — is exactly the evidence
GlobCurrent **passed** before failing on Argo, so it is demonstrably not sufficient to promote
a product. I am not proposing 2024 Argo be opened.

Freshness, verified: the FMRC runs catalog holds **9 rolling runs**, latest
**2026-09-11T12:00:00Z** — about one day old. Archive depth on the THREDDS FMRC path is
therefore ~9 days, though the per-year aggregations extend back to 2024-08-10.

On representation: `ssu` / `ssv` (1-hourly surface) versus `water_u` / `water_v` (3-hourly
z-levels) — the more defensible choice is `water_u` / `water_v` averaged over 0–30 m to
reconstruct OSCAR's layer, for the same reason as RTOFS.

Access is the best of the model candidates: THREDDS with OPeNDAP and NCSS server-side
subsetting, so a 5–30 °N / 45–105 °E box can be pulled without moving global files.

Data assimilation: NCODA, ingesting altimetry, SST, and in-situ T/S profiles including Argo.
Subsurface-assimilation concern: **HIGH**.

---

## 8. Candidate 5 — ECCC GIOPS

**Classification: C — data-assimilating 3-D ocean analysis with forecast.**
**Semantic distance from OSCAR: HIGH.**

Current operational version **GIOPS 3.6.0, implemented 2026-04-14**. Version history:
3.5.0 (2024-06-11), 3.4.1 (2023-11-28), 3.4.0 (2022-06-28) — so 2022–2023 ran 3.4.x, two
minor versions and an HPC migration behind the current system. NEMO at 1/4°, with the SAM2
(Système d'Assimilation Mercator v2) reduced-order Kalman filter.

### Freshness — the best of all five, verified daily

MSC Datamart path (found by walking the tree; the legacy `/model_giops/` path is 404):

```
https://dd.weather.gc.ca/YYYYMMDD/WXO-DD/model_giops/netcdf/lat_lon/3d/00/000/
  CMC_giops_vozocrtx_depth_all_latlon0.2x0.2_YYYYMMDD00_Anal000.nc   (149 MB)
  CMC_giops_vomecrty_depth_all_latlon0.2x0.2_YYYYMMDD00_Anal000.nc   (152 MB)
  CMC_giops_votemper_...                                              (87 MB)
  CMC_giops_vosaline_...                                              (91 MB)
```

Today's analysis files were **published 2026-09-12 02:08 UTC** — roughly **2 hours** after the
00 Z analysis time. An 8-day HEAD sweep of the `Anal000` `vozocrtx` file returned HTTP 200 for
2026-09-05 … 2026-09-12, with one transient failure on 09-10 consistent with a request timeout
rather than a missing file.

`Anal000` is genuinely the analysis: the MSC documentation states that "Fields provided at 00Z
and at forecast hour 0 represent the GIOPS analysis, which is nominally valid at 00Z. At all
other forecast hours the fields represent the model forecast and are averaged in time."
Note the asymmetry — the analysis is **instantaneous at 00 Z** while the forecast steps are
**time-averaged**. Those two are not interchangeable, and only `Anal000` should ever be used.

### Semantics

- Variables `vozocrtx` (zonal) / `vomecrty` (meridional), 50 depth levels, shallowest
  **0.494025 m**. A 0.49 m instantaneous current is a very different object from OSCAR's
  0–30 m daily average; a 0–30 m average could be formed from the 50 levels instead.
- Grid 0.2° regular lat-lon — regrids cleanly to the 0.25° canonical grid. Global coverage.
- Instantaneous at 00 Z, not a daily mean.

### Archive — the disqualifier

Datamart retains roughly 30 dated directories (2026-08-14 onward), and the 3-D subdirectory
for the oldest of those was already empty when checked, so 3-D retention is shorter still.
`hpfx.collab.science.gc.ca` holds ~50 days (2026-07-23 onward). **No 2022–2023 archive was
found**, and the operational version then was 3.4.x in any case. **QUALIFICATION BLOCKED.**

### Circularity

SAM2 assimilates satellite SLA, satellite SST **and in-situ temperature and salinity
profiles** (Argo, XBT, CTD, moored buoys). The very same directory publishes `votemper` —
GIOPS's own subsurface temperature field — alongside the currents. Concern: **HIGH**.

**Q14 answered:** GIOPS's advantage over RTOFS/INCOIS is real but narrow — ~2 h latency, a
clean regular 0.2° grid, an explicitly labelled analysis step, per-variable files under
predictable names, and no authentication. It is the *easiest to automate* of all five. Its
disadvantages are identical to theirs: model-derived, Argo-assimilating, and no qualifiable
archive. It is a better *contingency*, not a better *candidate*.

---

## 9. Live Recency Audit (2026-09-12, 15:20–18:20 UTC)

Cells describe the **field valid date**, not the filename date.

| valid date | MOSDAC | INCOIS OSF currents | INCOIS RSMC HYCOM | NOAA RTOFS | ESPC-D-V02 | ECCC GIOPS |
|---|---|---|---|---|---|---|
| 2026-09-12 | UNKNOWN / AUTH | FORECAST ONLY | ANALYSIS/NOWCAST (unconfirmed) | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-11 | UNKNOWN / AUTH | FORECAST ONLY | ANALYSIS/NOWCAST (unconfirmed) | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-10 | UNKNOWN / AUTH | NOT AVAILABLE (aged out) | NOT AVAILABLE (aged out) | NOT AVAILABLE (aged out) | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-09 | UNKNOWN / AUTH | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-08 | UNKNOWN / AUTH | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-07 | UNKNOWN / AUTH | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-06 | UNKNOWN / AUTH | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |
| 2026-09-05 | UNKNOWN / AUTH | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | ANALYSIS AVAILABLE | ANALYSIS AVAILABLE |

"NOT AVAILABLE (aged out)" means the provider's rolling retention has already dropped the
file, not that it was never produced. This matters operationally: RTOFS and INCOIS must be
harvested daily or the data is gone.

| candidate | publication latency (measured) | current-channel lag | **resulting OceanEmbed common-date lag** |
|---|---|---|---|
| MOSDAC | not verified | not verified | not verified |
| INCOIS OSF currents | ~1 day after label, but **valid times are +3 to +7 days ahead** | unusable | unusable |
| INCOIS RSMC HYCOM | 00:16 UTC same day | ~1 day | **6 days** (SSS-bound) |
| NOAA RTOFS | 03:14–03:24 UTC same day | 0–1 day | **6 days** (SSS-bound) |
| ESPC-D-V02 | ~1 day | ~1 day | **6 days** (SSS-bound) |
| ECCC GIOPS | 02:08 UTC same day (~2 h) | 0 days | **6 days** (SSS-bound) |

Today's OceanEmbed lag is 9 days (valid 2026-09-03). Every viable candidate lands on the same
**6-day** lag, because `sss_nrt_multiobs` stops at 2026-09-06. The differences in current
latency between GIOPS (2 h), RTOFS (3.5 h) and ESPC (1 day) are **entirely absorbed** by the
salinity channel and produce no difference in the delivered product.

---

## 10. OSCAR Semantic Compatibility

OSCAR reference semantics: diagnostic, derived from SSH gradients + ocean vector winds + SST
via geostrophy, Ekman and thermal-wind dynamics; **0.25°**; **daily**; representing the
**upper ~30 m average**; gap-free over ocean; no tides; no Stokes drift; no subsurface
assimilation.

| dimension | MOSDAC | INCOIS OSF | INCOIS RSMC | RTOFS | ESPC-D-V02 | GIOPS |
|---|---|---|---|---|---|---|
| represented depth | **0–30 m avg** | 0 m level | 0 m level (6 levels avail.) | top hybrid **layer** | z-levels (0 m up) | 0.494 m (50 levels) |
| daily mean vs instantaneous | daily | 3-hourly instant. | 6-hourly instant. | hourly / daily instant. | 3-hourly instant. | instant. at 00 Z |
| geostrophic component | yes (B&L) | implicit in model | implicit | implicit | implicit | implicit |
| Ekman / wind-driven | yes (B&L) | implicit | implicit | implicit | implicit | implicit |
| buoyancy / thermal wind | yes (B&L) | implicit | implicit | implicit | implicit | implicit |
| tidal component | no | model-dependent (unconfirmed) | unconfirmed | no explicit tides | no explicit tides | no explicit tides |
| Stokes drift | no | no | no | no | no | no |
| observational derivation | **yes** | no | no | no | no | no |
| numerical-model derivation | no | yes | yes | yes | yes | yes |
| data assimilation | **none** | T-SIS | T-SIS | NCODA (+velocities v2.5) | NCODA | SAM2 |
| resolution | **0.25°** | 1/12° | 1/16° | 1/12° tripolar | 1/12° | 0.2° |
| coastal treatment | altimetry degrades near coast | model bathymetry | model bathymetry | model bathymetry | model bathymetry | model bathymetry |
| equatorial treatment | B&L equatorial formulation | model dynamics | model dynamics | model dynamics | model dynamics | model dynamics |
| units | m/s | m/s | m/s | m/s | m/s | m/s |
| **semantic distance from OSCAR** | **VERY LOW** | **VERY HIGH** | **VERY HIGH** | **HIGH** | **HIGH** | **HIGH** |

Justification of the two extremes:

**MOSDAC — VERY LOW.** Same published formulation (Bonjean & Lagerloef 2002), same 0–30 m
layer definition, same 0.25° grid, same daily cadence, same input classes (altimetric ADT,
scatterometer wind, satellite SST), same absence of tides, Stokes drift and assimilation. The
remaining differences are the specific altimeter constellation, the SST source (AVHRR vs
OSCAR's choice) and implementation details — differences of *inputs*, not of *physics*.

**INCOIS OSF — VERY HIGH.** Different physics (primitive-equation model, not a diagnostic
balance), different depth (a 0 m level, not a 30 m average), different time semantics
(3-hourly instantaneous), assimilates subsurface observations, **and its published fields are
forecast rather than analysis**. On every axis that matters it is a different object.

The three model analyses sit at HIGH rather than VERY HIGH because, unlike INCOIS OSF, they do
expose a genuine analysis/nowcast step and z-level fields from which a 0–30 m average can be
constructed — so the depth mismatch is at least *repairable*. The assimilation mismatch is not.

---

## 11. Historical Archive / Qualification Feasibility

The fair experiment needs candidate currents on dates where OceanEmbed already holds OSCAR
reference currents, the other six inputs, GLORYS targets, and authorized 2022–2023 Argo. Two
date sets exist: **D1** = the 56 pre-registered 6C-D dates (2024-07-01 → 2024-12-15, GLORYS
targets), and **D2** = 2022-05-01 → 2023-12-31 (4,347 Argo profiles, 86 floats, 610 dates).

| candidate | D1 (2024 H2, GLORYS) | D2 (2022–23, Argo) | same-version? | classification |
|---|---|---|---|---|
| MOSDAC | unknown | unknown | unknown (v1.0 beta throughout) | **RESEARCH BLOCKED** — could become FULL |
| INCOIS OSF / RSMC | no (7-day window) | no | n/a | **QUALIFICATION BLOCKED** |
| NOAA RTOFS | partial — native `archv` only, from 2024-01-27; no global NetCDF currents in archive | no | no (v2.3 then, v2.5 now) | **OPERATIONAL TEST ONLY** |
| ESPC-D-V02 | yes (starts 2024-08-10; covers 2024-08-10 → 12-15, ~70 % of D1) | **no — product did not exist** | n/a | **PARTIAL QUALIFICATION POSSIBLE** (model-side only) |
| ECCC GIOPS | no (~30–50 day retention) | no | no (v3.4.x then, v3.6.0 now) | **QUALIFICATION BLOCKED** |

Two points deserve emphasis.

**Version continuity is not a technicality here.** RTOFS v2.5 changed the SSH assimilation
constraint and began assimilating observed velocities — a change that acts *directly* on the
variable we would be substituting. GIOPS 3.5.0 changed the MDT and activated new altimetry
datasets, which likewise acts on the geostrophic part of the current. Validating 2022–2023
fields from v2.3 / v3.4.x would not be evidence about the fields we would actually ingest.

**ESPC-D-V02 is the only model candidate that could be partially qualified**, and only on the
model-side gates (C1–C7 on the D1 subset from 2024-08-10). Those are exactly the gates
GlobCurrent passed before failing C8. Passing them would therefore establish nothing that has
not already been shown to be insufficient.

---

## 12. Scientific Circularity Assessment

OceanEmbed's claim is: **seven surface fields → 32-D satellite embedding → 15-depth subsurface
temperature.** The registry already records honestly that these are not seven raw
measurements — SST and wind are blended L4 analyses, SLA is a multi-mission altimetry
analysis, and OSCAR currents are *diagnostically derived* from SSH + wind + SST. What OSCAR is
**not** is a product that has seen subsurface temperature observations.

| candidate | assimilates in-situ T/S (Argo)? | ships a subsurface temperature field alongside? | concern |
|---|---|---|---|
| MOSDAC | **no** | no | **NONE** |
| INCOIS OSF / RSMC | yes (T-SIS) | **yes — `TEMP` at 6 depths and `TCHP` in the same file** | **SEVERE** |
| NOAA RTOFS | yes (NCODA); v2.5 also assimilates observed velocities | yes (`t3z` family) | **HIGH** |
| ESPC-D-V02 | yes (NCODA) | yes (`t3z`: `water_temp`) | **HIGH** |
| ECCC GIOPS | yes (SAM2: SLA + SST + in-situ T/S) | **yes — `votemper` in the same directory** | **HIGH** |

The failure mode is specific, not vague. Argo profiles constrain the model's subsurface
density field; through geostrophic adjustment that density field *is* what sets the model's
current. So the candidate current channel is a compressed, model-mediated function of
subsurface temperature. The frozen L2 would then be partly reading back a transformed version
of its own target. Skill measured against GLORYS — itself an Argo-assimilating reanalysis —
would not detect this; it would reward it.

This is also the reason the 2022–2023 Argo gate matters more, not less, for these candidates:
it is the only evidence source in the project that is independent of the assimilation chain.
And it is precisely the evidence none of them can supply.

Two further honesty points:

- INCOIS RSMC HYCOM publishes `TCHP` directly. If OceanEmbed ingested its currents and then
  reported a TCHP-derived hazard indicator, the provenance story would become very hard to
  state cleanly.
- The 2024 Argo holdout would *not* rescue these products even if it were opened. The
  circularity is structural, not a matter of which validation window is used.

---

## 13. Automation / API Feasibility

| candidate | mechanism | auth | server-side subset | daily volume for the NIO box | practicality |
|---|---|---|---|---|---|
| MOSDAC | HTTPS directory behind SSO | **MOSDAC SSO** | no | small (0.25° global ≈ few MB) | **unproven** — session-based, no documented API |
| INCOIS OSF | THREDDS + OPeNDAP, open | none | yes (OPeNDAP) | small after subset | easy, but the data is forecast |
| INCOIS RSMC | THREDDS + OPeNDAP, open | none | yes | small after subset (file is 10.58 GB) | easy |
| NOAA RTOFS | flat HTTPS directory (NOMADS) | none | **no** | **148 MB/day** (2ds) or **1.7 GB/day** (3dz u+v) | heavy; must harvest daily before 2-day expiry |
| ESPC-D-V02 | THREDDS + OPeNDAP + NCSS | none | **yes** | small after subset | **best of the model candidates** |
| GIOPS | flat HTTPS, predictable filenames | none | no | **~300 MB/day** (u+v, global, all depths) | simple but bulky |

OceanEmbed already delegates authentication to `copernicusmarine` and `earthaccess`, neither
of which exposes credential values to project code. MOSDAC would be the first source requiring
a different auth mechanism, and a browser-session-based one at that. That is a real
engineering and security cost that should be weighed alongside the science.

---

## 14. Scored Comparison Table

Each criterion scored 0–5; maximum 75.

| # | criterion | MOSDAC | INCOIS HYCOM | RTOFS | ESPC-D-V02 | GIOPS |
|---|---|---|---|---|---|---|
| 1 | actual operational freshness | 2 \* | 4 | 5 | 4 | 5 |
| 2 | reliability / availability | 2 \* | 4 | 4 | 3 | 5 |
| 3 | North Indian Ocean coverage | 5 | 3 † | 5 | 5 | 5 |
| 4 | grid compatibility | 5 | 3 | 2 | 3 | 4 |
| 5 | temporal compatibility | 5 | 2 | 3 | 3 | 2 |
| 6 | physical-semantic similarity to OSCAR | 5 | 1 | 1 | 1 | 1 |
| 7 | observation-derived provenance | 5 | 0 | 0 | 0 | 0 |
| 8 | independence from subsurface assimilation | 5 | 0 | 0 | 0 | 0 |
| 9 | historical archive availability | 2 \* | 0 | 1 | 1 | 0 |
| 10 | 2022–23 qualification feasibility | 2 \* | 0 | 0 | 0 | 0 |
| 11 | ease of automation | 2 | 4 | 3 | 4 | 5 |
| 12 | long-term provider stability | 3 | 3 | 5 | 4 | 4 |
| 13 | SIH scientific defensibility | 5 | 2 | 2 | 2 | 2 |
| 14 | P(passing frozen-L2 thermocline validation) | 4 | 1 | 1 | 1 | 1 |
| 15 | expected improvement in common-date lag | 3 | 3 | 3 | 3 | 3 |
| | **TOTAL / 75** | **55** | **30** | **35** | **34** | **37** |
| | **SCIENTIFIC RISK CLASS** | **MODERATE** | **VERY HIGH** | **HIGH** | **HIGH** | **HIGH** |

\* MOSDAC scores 2 (not 0) on criteria 1, 2, 9 and 10 because these are **unverified**, not
because they are known to be bad. If the SSO check in §4 shows a live daily product with a
2022–2023 archive, these become 5 / 4 / 5 / 5 and the total rises to ~68. If it shows a dead
product, they fall to 0 and MOSDAC drops below every model candidate. **The entire ranking
turns on one 10-minute check.**

† INCOIS OSF currents end at 29.89 °N, inside OceanEmbed's 30.0 °N boundary. INCOIS RSMC
HYCOM reaches 30.95 °N and would score 5 on this row.

MOSDAC's risk is classed MODERATE rather than LOW only because of the unverified availability.
Its *scientific* risk is the lowest of the five by a wide margin.

### Recommended status

| candidate | recommended status |
|---|---|
| ISRO/SAC MOSDAC | **RESEARCH MORE BEFORE TEST** — blocked on one provider-access step |
| NOAA Global RTOFS | **TEST IF NEEDED** — operational contingency only |
| HYCOM ESPC-D-V02 | **TEST IF NEEDED** — the only model candidate with a partial model-side path |
| ECCC GIOPS | **TEST IF NEEDED** — best automation, same scientific ceiling |
| INCOIS RSMC HYCOM | **NOT RECOMMENDED** as an L2 input channel (see §18 for its real use) |

---

## 15. Pre-Registered Qualification Plan Per Candidate

**Not executed.** This is the design that would be pre-registered and committed *before* any
result is computed, exactly as `c01c170` was for Phase 8C.

### 15.1 Invariant pipeline (all candidates)

```
same sst · same sss · same sla · same wind_u/wind_v
  + candidate current_u/current_v
  → SAME frozen L2 (b715bb2b…)   → same 15 depths
```

No retraining. No output calibration in the first pass. No post-hoc tuning. No threshold
change. `ReplayEngine._infer` remains the only inference implementation. The joint validity
mask stays `isfinite(all 7).all(axis=0)`. Any date where the candidate is missing is
**dropped**, never persisted forward, never zero- or mean-filled.

### 15.2 Stages

| stage | content | pass condition |
|---|---|---|
| **0 provider availability** | enumerate candidate files for D1 and D2; record valid vs init vs publication date for every file | ≥ 28 usable dates on D1 **and** the D2 window fully covered, else stop |
| **1 metadata / semantics** | variable names, units, depth definition, tide/Stokes treatment, instantaneous vs mean, fill values, assimilation inputs | declared in writing **before** any number is computed |
| **2 harmonisation** | `nrt.harmonize.to_canonical` — the training regrid function, not a copy; ascending lat; [-180,180); 1° pad; NaN propagated; no land fill; no extrapolation | canonical 101 × 241; coverage loss recorded |
| **3 candidate vs OSCAR overlap** | U/V bias, RMSD, correlation, speed bias, speed RMSD, variance ratio q, vector-direction error, coverage change, joint-mask change | **C1** band from 6C-D §4.1, unchanged |
| **4 frozen-L2 response** | s = RMSD / L2_test_RMSE at 100 m and worst depth | **C2** band; **C3** `channel_decision` ∈ {APPROVED, WITH_MONITORING} |
| **5 GLORYS frozen benchmark** | RMSE / bias / correlation at all 15 depths vs L0 climatology | **C5** beats L0 at ≥ 6 of 11 depths 0–200 m |
| **6 thermocline** | 75 / 100 / 125 m, paired date-bootstrap | **C6** beats L0 **and** 95 % CI of (RMSE_cand − RMSE_L0) entirely below zero |
| **7 basins** | 100 m, Arabian Sea and Bay of Bengal separately | **C7** beats L0 in both |
| **8 observational (2022–23 Argo)** | existing collocations, same QC, same float grouping, float-clustered paired bootstrap; control must reproduce the stored executed `L2_<d>m` **exactly** | **C8** CI spans zero at ≥ 4 of 6 key depths **and** worst degradation ≤ **+0.68 %** |
| **9 recency benefit** | newest complete seven-channel date with vs without the candidate | reported, never decisive |
| **10 decision** | all gates pass → APPROVED / WITH_MONITORING; anything else → REJECTED | C8 is **not** optional |

### 15.3 Metrics (fixed now)

- **Current-product level:** U bias, V bias, U RMSD, V RMSD, U correlation, V correlation,
  speed bias, speed RMSD, variance ratio, vector-direction error, coverage change,
  joint-mask change.
- **Model level:** temperature RMSE, bias and correlation at all 15 depths; anomaly
  correlation where defined; ΔRMSE vs the incumbent OSCAR-input L2; 75/100/125/150 m; Arabian
  Sea and Bay of Bengal separately.
- **Argo level:** same 2022–2023 collocations, same QC, same float grouping, float-clustered
  bootstrap; ΔRMSE, Δbias, Δcorrelation.

2024 Argo is not touched at any stage.

### 15.4 Per-candidate instantiation

**MOSDAC — the only plan that can reach stage 8.**
Stage 0 is the SSO check in §4 and is a hard gate: if the 2022–2023 archive is absent, the plan
stops there and reports, exactly as Phase 8B stopped rather than silently swapping a product.
Stage 1 must resolve whether the file is a daily mean and whether "TOT" includes any tidal
term. Stage 2 is nearly trivial (0.25° → 0.25°) — and that is itself a benefit worth recording,
since it removes regridding as a confounder. Stages 3–7 reuse `channel_decision` from
`scripts/nrt/substitution_run.py` unchanged. Stage 8 reuses `run_argo_current_check.py`
including its cross-check that the recomputed control reproduces the stored `L2_<d>m` bitwise.
If MOSDAC clears C8, it would be the first current candidate ever to do so, and the recency
claim in stage 9 would still be capped at +3 days.

**ESPC-D-V02 — partial, and pre-labelled as insufficient.**
Stages 0–7 on the D1 subset from 2024-08-10 (~70 % of the 56 dates; the reduced N must be
declared in stage 0 and the bootstrap re-sized accordingly). Stage 8 is **unreachable** and
must be recorded as `C8 = NOT_EVALUABLE`, **not** as a pass and **not** as a waiver. Under the
existing decision table, `C8 ≠ pass` ⇒ `SUBSTITUTE_REJECTED`. This plan therefore cannot
approve the product; it can only quantify how the frozen model responds. It should only be run
if that measurement is itself wanted.

**RTOFS / GIOPS / INCOIS — operational rehearsal only, outside the frozen path.**
Stages 0–2 only: prove the file can be fetched daily inside the operating window, harmonised to
the canonical grid, and that its valid date is what it claims. Stage 3 (direct comparison
against OSCAR) may be run on whatever overlap exists *for description only*. Stages 4–10 are
**not** run, because a product that cannot reach C8 cannot be approved, and running the frozen
model on it would produce numbers that invite exactly the misreading the project has avoided so
far. Nothing from this rehearsal may enter `PRODUCTS` or any operational code path.

---

## 16. Candidate Calibration Possibilities

The question is whether a current-domain transform `candidate U/V → OSCAR-like U/V` could ever
be defensible without retraining L2.

**General position: raw substitution must be evaluated first, always.** Phase 8C established
this and it should not be relaxed. A calibrated product that passes where the raw product
failed is a weaker result, not a stronger one, and must be reported as such.

**Leakage rules that would apply to any calibration:**

- Fit only on historical dates **disjoint** from both evaluation sets — never on the 56 6C-D
  dates and never on the 2022–2023 Argo window used for C8.
- Never fit against frozen test results, GLORYS-derived L2 error, or any Argo quantity.
- The fit target is **OSCAR U/V on overlap dates** — a current-domain-only transform, blind to
  temperature.
- Hold out a contiguous block (a full season, not random days) for independent validation, and
  report both raw and calibrated results side by side.

**Per candidate:**

| candidate | is calibration needed? | is there enough overlap to fit? | verdict |
|---|---|---|---|
| MOSDAC | **probably not** — same formulation, same layer, same grid | unknown until the SSO check; if 2022–2023 exists, ample | if raw passes, do nothing; calibration would only weaken the story |
| ESPC-D-V02 | yes (top-layer vs 0–30 m) | 2024-08-10 → 2026 overlap with OSCAR NRT exists | possible, but cannot reach C8 either way — pointless |
| RTOFS | yes | overlap exists only as native `archv` binaries | impractical |
| GIOPS | yes (0.494 m instantaneous vs 0–30 m daily) | ~50 days of overlap only | insufficient to fit a seasonal/basin correction |
| INCOIS | yes | 7 days | impossible |

**The deeper objection, which applies to all four model candidates.** The mismatch with OSCAR
is not a constant offset. It is a *structured* difference: the Ekman spiral means a 0.5 m
instantaneous current differs from a 0–30 m daily average in a way that varies with wind
stress, mixed-layer depth, latitude and season. A fixed bias or global affine correction cannot
represent that; a correction rich enough to represent it would be a small trained model — and
training a model to make product X impersonate OSCAR, in order to feed a model frozen on OSCAR,
is a fit with all the fragility of retraining and none of its honesty.

**And the operational-story cost is real.** "We transform product X so it resembles the product
we actually trained on" invites the immediate question "then why is X better than waiting for
OSCAR?" — a question with no good answer when the measured benefit is three days.

---

## 17. Recommended Sequential Experiment Order

1. **MOSDAC provider-access check** (§4, steps 1–4). Cost: ~10 minutes of a human's time and
   one account registration. Decides the entire ranking. **Do this before anything else.**
2. **If** MOSDAC shows a live daily product **and** a 2022–2023 archive → pre-register and run
   the full §15.4 MOSDAC plan, stages 0–10, reusing the Phase 8C scripts unchanged.
3. **If** MOSDAC is live but has **no** 2022–2023 archive → stop and report. Do not substitute
   on model-side evidence alone; that is exactly the evidence GlobCurrent passed.
4. **If** MOSDAC is dead or inaccessible → run **no** substitution experiment. Keep OSCAR, keep
   the honest 9-day lag and its stated cause, and put the effort into §19 instead.
5. **Only if** an operational contingency is explicitly wanted, and separately authorized: an
   ESPC-D-V02 or GIOPS **rehearsal** (stages 0–2 only), kept strictly outside the frozen path
   and outside `PRODUCTS`.

---

## 18. What NOT to Use

- **Do not use INCOIS `osf/currents` (`CURRENTS_IO/NIO_*.nc`) as an input channel.** Its files
  contain only forecast leads +72 h to +165 h; a file labelled with a date contains no field
  valid on that date. Using it would place forecast values into a channel presented as an
  analysis of the past.
- **Do not use any candidate's forecast steps** — RTOFS `f***`, ESPC forecast leads, GIOPS
  forecast hours (which are additionally time-averaged, unlike the instantaneous `Anal000`).
- **Do not describe RTOFS, ESPC-D-V02, GIOPS or INCOIS HYCOM output as "satellite
  observations."** They are data-assimilating ocean model analyses.
- **Do not substitute on model-side gates alone.** GlobCurrent passed C1–C7 and was still
  rejected. Approving a *further* candidate on *less* evidence would invalidate that decision
  retroactively.
- **Do not treat older-version historical data as validating the current operational version**
  (RTOFS v2.3 → v2.5; GIOPS v3.4.x → v3.6.0; GOFS 3.1 → ESPC-D-V02).
- **Do not open 2024 Argo** to work around the missing 2022–2023 overlap. It would not fix the
  circularity anyway.
- **Do not carry currents forward, interpolate across missing days, or introduce persistence**
  to hide a gap. The persistence envelope is 0 days and `CURRENT_STALE_3D` was the weakest
  policy ever promoted, at +0.68 %.
- **A useful, permitted role for these model products:** INCOIS RSMC HYCOM and GIOPS publish
  their own subsurface `TEMP` / `votemper` and TCHP. They would make a legitimate
  **independent comparison reference** for OceanEmbed's output — a separate, clearly-labelled
  evaluation, not an input channel, and not part of this phase.

---

## 19. Decisive Recommendation

The honest answer to "which product gets OceanEmbed closest to near-real-time without weakening
scientific validity" is: **on current evidence, none of them does enough to be worth the risk
before SIH** — and the reason is arithmetic, not caution.

The best achievable outcome from a perfect, instantly-available current product is a common
date of **2026-09-06 instead of 2026-09-03**. Six days old instead of nine. That is still not
near-real-time, it does not change what the jury sees, and it would be bought by replacing the
one input channel whose provenance is currently clean with one derived from an
Argo-assimilating ocean model.

Meanwhile OceanEmbed's present position is genuinely strong and fully defensible: the lag is
measured, its cause is proven to be a provider outage with PO.DAAC ingest timestamps, the
qualification is pre-registered, and a candidate substitution was already tested and rejected
on observational evidence rather than accepted for convenience. That last point is a better
story at SIH than three extra days would be.

**The one action worth taking now** is the MOSDAC access check. It is cheap, it is the only
path to a scientifically clean *and* fresher current channel, and an ISRO satellite-derived
product in an ISRO-adjacent problem statement is the strongest possible provenance. If it comes
back live with history, this report's plan is ready to execute. If it comes back dead, the
right answer is to keep OSCAR, state the lag honestly, and spend the remaining time on the
**salinity** channel — which is the binding constraint on every scenario in this report.

---

## Required Final Decision

```
BEST NEXT CANDIDATE:
  ISRO/SAC MOSDAC Global Ocean Surface Current — conditional on a provider-access check

WHY:
  1. It is an independent implementation of the SAME physics as OSCAR (Bonjean &
     Lagerloef 2002), documented on the official product page.
  2. Identical channel semantics: 0-30 m layer average, 0.25 deg, daily, global —
     the only candidate needing essentially no regridding onto the canonical grid.
  3. Observation-derived from altimetric ADT + ASCAT winds + AVHRR SST, with NO
     subsurface data assimilation — the only candidate with zero circularity risk.
  4. Consequently the only candidate with a realistic chance of passing gate C8,
     the 2022-23 Argo observational non-inferiority test that rejected GlobCurrent.
  5. Strongest SIH provenance: an ISRO satellite-derived input for an ISRO/MoES
     problem statement about reconstruction from surface satellite observations.
  6. Every alternative is a data-assimilating ocean model that ingests Argo T/S and
     publishes its own subsurface temperature field alongside the currents.

LATEST VERIFIED DATA:
  NOT VERIFIED — AUTHENTICATION BLOCKED.
  https://www.mosdac.gov.in/opendata/ocean_surface_current/ redirects to MOSDAC
  Single Sign On; /opendata/ returns HTTP 401. No credentials were used. The
  product page states "Version 1.0 (beta)" with metadata dated 2015-09-15, so
  continued production is ALSO unverified.
  (Verified for others: RTOFS 2026-09-12 published 03:24 UTC; GIOPS analysis
   2026-09-12 published 02:08 UTC; ESPC-D-V02 latest run 2026-09-11T12:00Z;
   INCOIS RSMC 2026-09-12 published 00:16 UTC; INCOIS OSF currents FORECAST ONLY.)

HISTORICAL QUALIFICATION:
  UNKNOWN — resolves to FULL or BLOCKED once the MOSDAC archive is inspected.
  All four other candidates: BLOCKED (verified individually in section 11).

SCIENTIFIC RISK:
  MODERATE — and only because availability is unverified. Its physical and
  provenance risk is LOW, the lowest of the five by a wide margin.

NEXT ACTION:
  Register a MOSDAC Single Sign On account, sign in, open
  https://www.mosdac.gov.in/opendata/ocean_surface_current/ and record:
    (a) newest ISRO_CURRENT_TOT_YYYYMMDD.nc present;
    (b) presence for each of the last 10 days;
    (c) whether 2022-05-01 to 2023-12-31 is covered;
    (d) whether the listing is scriptable with a session cookie or token;
    (e) from one file: exact U/V variable names, units, _FillValue, whether the
        time coordinate is a daily mean, and any tide or Stokes-drift attribute.
  Report (a)-(e) back before any experiment is authorized.

SECOND CHOICE:
  HYCOM ESPC-D-V02 — the only model candidate with any historical path at all
  (2024-08-10 onward covers ~70% of the D1 dates), the best machine access
  (THREDDS + OPeNDAP + NCSS server-side subsetting), and clean analysis/forecast
  separation. It can reach stages 0-7 only; gate C8 is permanently unreachable
  because the product did not exist in 2022-23, so it can never be APPROVED under
  the existing decision table.

THIRD CHOICE:
  ECCC GIOPS — the freshest and most automatable of all five (analysis published
  ~2 h after 00Z, verified daily for 8 consecutive days, plain HTTPS, predictable
  filenames, no authentication). Useful purely as an operational contingency:
  ~30-50 day retention and SAM2 Argo assimilation make scientific qualification
  impossible.

DO NOT TEST BEFORE SIH:
  - INCOIS RSMC HYCOM / OSF currents — forecast-only publication in the OSF product,
    domain ends at 29.89N inside the OceanEmbed box, 7-day retention, and TEMP +
    TCHP shipped in the same file as the currents (severe circularity).
  - NOAA Global RTOFS — no global NetCDF current archive exists (the AWS mirror
    carries no _prog files at all; NOMADS keeps 2 days), plus a v2.3 -> v2.5
    version break across the qualification window.
  - Any calibrated substitution of any candidate. Raw must be evaluated first.

MOST IMPORTANT BLOCKER:
  Salinity, not currents — sss_nrt_multiobs stops at 2026-09-06, so even a perfect
  same-day current product moves the latest qualified state only from 2026-09-03 to
  2026-09-06, capping the entire exercise at +3 days.
```

---

## Terminology used in this report

"Latest qualified reconstruction" and "latest qualified ocean state" for OceanEmbed's output;
"operational analysis/nowcast input" for a model field at or before its publication time;
"current-source substitution" for the experiment class; "frozen L2" for the unchanged
checkpoint; "candidate current product" for anything not yet qualified. OceanEmbed's output is
**not** a forecast and is not described as one. "Near-real-time" is used only where every
required input is actually available at the stated latency — which, today, it is not.

---

## Sources

Primary provider catalogs and data servers, queried live on 2026-09-12:

- [NASA CMR granule search](https://cmr.earthdata.nasa.gov/search/) — OSCAR NRT/Interim/Final newest granules and ingest timestamps
- [MOSDAC — Global Ocean Surface Current](https://www.mosdac.gov.in/global-ocean-surface-current) — product definition, methodology, filename convention
- [MOSDAC — Open Data](https://www.mosdac.gov.in/open-data) and `https://www.mosdac.gov.in/opendata/ocean_surface_current/` (SSO-gated)
- [INCOIS THREDDS](https://incois.gov.in/thredds/catalog.html) — `osf/currents`, `osf/currents2` catalogs and OPeNDAP DDS/DAS
- [INCOIS RSMC](https://incois.gov.in/oceanservices/osf_gc_rsmc.jsp) and [INCOIS HYCOM](https://incois.gov.in/site/datainfo/modelling/hycom.jsp) — model configuration
- [NOMADS RTOFS production directory](https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod/) — file inventory and publication timestamps
- [NCEP RTOFS product inventory](https://www.nco.ncep.noaa.gov/pmb/products/rtofs/) — nowcast/forecast file semantics
- [NWS service change notice — RTOFS v2.5](https://www.weather.gov/media/notification/pdf_2025/scn25-47_RTOFS_v.2.5.pdf) — implementation date and assimilation changes
- [Global RTOFS on AWS Open Data](https://registry.opendata.aws/noaa-rtofs/) and bucket `noaa-nws-rtofs-pds` — archive extent and file inventory
- [HYCOM THREDDS](https://tds.hycom.org/thredds/catalog.html) — ESPC-D-V02 temporal extent, variables, FMRC runs
- [MSC Datamart GIOPS readme](https://eccc-msc.github.io/open-data/msc-data/nwp_giops/readme_giops-datamart_en/) and [GIOPS changelog](https://eccc-msc.github.io/open-data/msc-data/nwp_giops/changelog_giops_en/) — grids, levels, analysis semantics, version history
- [MSC Datamart](https://dd.weather.gc.ca/) — GIOPS `Anal000` file availability and publication times
- [GIOPS system description, Science.gc.ca](https://science.gc.ca/site/science/en/concepts/prediction-systems/global-ice-ocean-prediction-system-giops) — NEMO/SAM2 assimilation inputs
- [OSCAR, Earth and Space Research](https://www.esr.org/data-products/oscar/) and [PO.DAAC OSCAR Final v2.0](https://podaac.jpl.nasa.gov/dataset/OSCAR_L4_OC_FINAL_V2.0) — reference semantics

Internal (source of truth over planning documents): `outputs/phase8b/qualification_decision.json`,
`outputs/phase8c/decision.json`, `outputs/phase8c/argo_result.json`,
`outputs/phase8c/recency_comparison.json`, `src/oceanembed/nrt/registry.py`,
`src/oceanembed/nrt/latest.py`, `src/oceanembed/nrt/harmonize.py`,
`PHASE8B_OPERATIONAL_ADDENDUM_2026-09-12.md`, `OPERATIONAL_CURRENT_SOURCE_QUALIFICATION_REPORT.md`.
