# Phase 7B physical depth display validity

## Source and build

Reuses the unchanged local NOAA NCEI **ETOPO 2022 v1 ice-surface, 60 arc-second product**, same underlying source as the terrain mesh. No additional download or runtime remote request.

- Source: `outputs/phase7b/terrain/etopo2022-60s-stride3.nc`
- Source SHA-256: `1c998d5c0c800580e10511fef42ed93bb79605d29c1319a9bfa63741da662dad`
- Original product resolution: 60 arc seconds. Existing local subset samples every third point: **0.05° / 3 arc minutes**. This is not a full-resolution 60-second subset.
- Attribution: NOAA NCEI, ETOPO 2022, DOI 10.25921/fd45-gt74; EGM2008 vertical datum.
- Recorded source URL: https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.nc?z[(4.95):3:(30.05)][(44.95):3:(105.05)]
- Build: `.venv\Scripts\python.exe scripts/poc/build_bathymetry.py`
- Output: `web/public/assets/bathymetry/depth.bin` and `metadata.json` (copied by the normal frontend build into `web/dist/assets/bathymetry`). Binary is little-endian float64 metres, latitude-major then longitude, 101 × 241.

The builder checks the source hash against existing terrain metadata. Source variable `z` explicitly states `positive=up`, `units=meters`. It reuses `oceanembed.preprocessing.regrid.regrid_horizontal`: xarray linear interpolation to ascending canonical latitude 5–30°N and longitude 45–105°E, inclusive, every 0.25°. No extrapolation; missing values propagate. Elevation is interpolated first, then water depth is `max(0, -elevation)`. No visual terrain exaggeration or smoothing participates.

## Rule and affected displays

`display_depth_valid = ocean_cell AND finite(local_water_depth) AND local_water_depth >= requested_depth`.

Existing surface-input support and finite selected-field-value requirements also remain necessary for a rendered triangle. Both temperature and anomaly surfaces and their side walls use the same predicate. No triangles/picking targets are emitted below seafloor. Ocean shader support follows that filtered footprint. The rectangular depth frames remain geographic guides, not claims that every point inside them is wet.

The standalone frontend bathymetry loader verifies checksum, dimensions, coordinate order and depth sign. Missing/corrupt bathymetry hides all unverified 3D ocean layers with an explicit notice. It never falls back to L0 availability, distance to coast or fabricated depth. Terrain and frame controls remain available.

The profile chart omits below-seafloor L2 and L0 points. Its raw 15-row table remains intact with an added physical-depth-support column. The selected local depth and raw-table semantics are stated above the plot. Invalid ocean selections remain invalid. No nearest-ocean relocation is introduced.

**API, FieldView contract, raw temperature/anomaly/climatology arrays, raw scientific exports and inference: unchanged.** `climatology_defined` is not bathymetry and is not used in physical depth support. The display does not construct a replacement prediction field; it filters geometry and chart points using a separate context array.

## Real replay evidence (2021-06-15)

| Depth | Supported display cells |
| --- | ---: |
| 0 m | 11136 |
| 30 m | 10816 |
| 100 m | 9785 |
| 300 m | 9520 |
| 1000 m | 9111 |

At 20°N, 70°E the sampled local water depth is 73.23 m: levels through 50 m are permitted, 75–1000 m are not. The internal raw model profile is not changed.

Screenshots: `outputs/phase7b/bathymetry-0m.png`, `bathymetry-30m.png`, `bathymetry-100m.png`, `bathymetry-300m.png`, `bathymetry-1000m.png`. Counts are recorded in `outputs/phase7b/bathymetry-validity.json`.

## Preservation and caveat

Frozen checkpoint, encoder, state dictionary, L0 and scaler guard tests verify the recorded hashes. The L2 checkpoint remains `81979a6541927ff5c6b0a13c5ce7cdbcd486040d16a304dcdc10b2962a586e35`. No Argo data is an ingestion input; no 2024 Argo data is opened for this task. There is no retraining or evaluation change.

This is cell-centre bilinear sampling, not a minimum-depth guarantee over an entire 0.25° cell. Fine shelves/canyons, coastline disagreement between the model ocean mask and ETOPO, datum differences and unsampled relief remain resolution limitations. A model ocean cell whose interpolated elevation is positive gets water depth zero: it can retain the nominal 0 m surface under the explicit model-ocean rule, but no positive-depth water. This mask establishes physical depth existence at the sampled grid point; it does not validate the accuracy of L2 temperatures. The 2D map and scientific exports retain their existing raw contracts.

Validation: production build passed; 62 Vitest tests passed; 12 Playwright tests passed. Python bathymetry/frozen/holdout checks: 14 passed (26 unrelated tests deselected); one non-functional pytest cache permission warning. Explicit L0-mask test and screenshot checks rerun after their final test-only edits.
