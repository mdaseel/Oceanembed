# Offline terrain context — Phase 7B

## Current geometry and theme update

Exploded ocean sheets now have actual shallow **display-only curvature**, not
just optical shading. CPU mesh deformation changes only rendered Y positions:
the surface amplitude is bounded by 0.36 scene units, deeper sheets by 0.22.
Curvature tapers to zero beside land/missing-data cells, while open-ocean crop
edges may curve. Side faces receive the identical offset, keeping thickness
constant at 0.8 scene units. The existing horizontal footprint and six-unit
layer spacing remain unchanged. Side opacity is 62% of face opacity.

The same curved mesh is used for raycast picking, retaining two triangles per
scientific cell. Curvature is disabled when layer separation is zero, restoring
planar true-depth sheet positions. This styling is explicitly disclosed as
illustrative, not measured waves or depth variation. Temperature, anomaly,
scientific masks and exported numerical values are untouched.

Land lighting now uses cool ambient `#c4dce5` at 0.75, key `#e4f2f5` at 2.35
from (-30,34,18), and rim `#8ebcc9` at 0.65 from (30,16,-24). The real ETOPO
terrain and charcoal material remain. The 2D map now shares the 3D thermal
palette and uses a cool charcoal land fill (`#182a30`); both its legends and
rendered PNG use that matching palette. Coordinate selection is unchanged.

Screenshots: `outputs/phase7b/terrain/curved-water.png`,
`curved-water-side.png`, and `matching-map.png`. Build and 53 frontend tests
passed, including constant side thickness, coordinate preservation,
true-depth restoration and curved-mesh raycast-to-cell identity.

## Latest reference finish

The current 3D view uses a richer red-ended thermal palette defined in
`web/src/field/depthColors.ts`. The water faces, thin side faces and 3D legend
share the same ramp and unchanged numerical range. The 2D palette, anomaly
palette, viridis and cividis remain unchanged. Larger-scale hot/cold patterns
are still determined by the real field, not copied from the reference image.

Terrain stays charcoal with real ETOPO relief, now with two light adjacency
smoothing passes and **60× default exaggeration**. Each pass retains 75% of
the previous height and adds 25% of the local triangle-neighbor mean. All
sea-level coastline vertices, horizontal positions and connectivity remain
fixed; the source DEM is unchanged.

The striped ocean shading has been replaced by irregular multiscale optical
surface detail. It adds no geometric wave height. Supported-cell edge coverage
is linearly filtered and feathered only inside existing ocean triangles; no
new water or values are drawn across the scientific mask. Renderer pixel ratio
is bounded to 1.5–2 for smoother edges. Ocean side thickness is 0.45 display
units with 38% of face opacity, preserving a thin-layer appearance and the
existing 6-unit separation. No rectangular cage is added.

Final screenshot: `outputs/phase7b/terrain/reference-finish.png`. Earlier
settings and measurements below are retained as implementation history.

## Current finish: charcoal terrain and optical ocean ripples

The latest requested finish supersedes the earthy material described in the
historical notes below. Land again uses matte charcoal linear RGB
`(0.17, 0.18, 0.19)`, roughness 0.95 and metalness 0, with no color texture,
elevation palette, or procedural grain.

Terrain display heights receive one gentle adjacency smoothing pass: 75% of
the original height plus 25% of the adjacent triangle-vertex mean. Zero-height
coastline vertices remain fixed. Horizontal coordinates and connectivity never
change, so smoothing cannot bridge water gaps. The original ETOPO binary,
checksum and elevations remain untouched; only the displayed relief is
smoothed before the independent terrain exaggeration is applied.

Ocean faces now use stationary, irregular wave-like optical normals and
highlights. This decorative shading does not displace geometry, simulate
measured waves, modify scalar arrays, or change point picking. The surface
finish is strongest on the uppermost sheet and reduced to 22% strength on
deeper sheets. Base shading changes by up to 11.5%, with pale highlights capped
at a 12% mix; numerical values remain available in the profile and exports.

Current screenshot: `outputs/phase7b/terrain/charcoal-ripples.png`.
Build, 49 frontend tests and 6 browser tests passed. A final shader screenshot
check recorded no shader errors and approximately 141.3 fps locally.

The 3D renderer now uses an independent, real-elevation terrain surface. The previous flat land rendering path has been replaced; there is no flat land fallback, constant-height extrusion, backing, hull, bottom face, or vertical rectangular perimeter wall.

## Dataset and provenance

- Dataset: NOAA NCEI **ETOPO 2022 v1**, ice-surface global relief, **60 arc-second product**. The parent ETOPO model is available at 15 arc-seconds; this implementation does **not** claim to use that finer product.
- Attribution: NOAA National Centers for Environmental Information (NCEI), 2022, [doi:10.25921/fd45-gt74](https://doi.org/10.25921/fd45-gt74).
- Official product description: [NOAA ETOPO Global Relief Model](https://www.ncei.noaa.gov/products/etopo-global-relief-model).
- Subset service: [NOAA Pacific Islands OceanWatch ETOPO dataset](https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.html).
- Elevations: metres above EGM2008, positive upward. No bathymetry is rendered.
- Downloaded subset: every third native sample, approximately 4.95833–30.00833 N and 44.95833–105.00833 E; **180 arc-second / 0.05-degree effective spacing**.
- Local source: `outputs/phase7b/terrain/etopo2022-60s-stride3.nc` (2,433,384 bytes).
- Source SHA-256: `1c998d5c0c800580e10511fef42ed93bb79605d29c1319a9bfa63741da662dad`.

The source NetCDF metadata includes the redistribution notice. It is preserved in the bundled metadata. All downloads are build-time only; the application uses local files exclusively.

## Processing and rendering

`scripts/poc/build_terrain.py` reads only the local DEM. It bilinearly resamples onto a 501 × 1201 display grid at 0.05 degrees within **5–30 N, 45–105 E**. Each grid triangle is clipped to its positive-elevation portion. Crossings of the zero-elevation contour become coastline vertices at exactly zero; submerged portions and missing data remain holes. Islands are not connected by hulls or polygon filling.

The resulting indexed surface contains **317,826 vertices and 620,447 triangles**. Maximum sampled elevation is **6,987.073 m**. No random noise, invented peaks, or constant-height land is generated. Resampling is a display approximation: islands smaller than the display resolution may be unresolved, and fine coastline details differ from the 0.25-degree scientific mask. The latter is never changed to match the DEM.

Bundle:

- `web/public/assets/terrain/land.bin`: little-endian float32 longitude, latitude, elevation triples followed by uint32 indices.
- `web/public/assets/terrain/metadata.json`: provenance, processing, resolution, counts, bounds, and source/mesh checksums.
- Vite copies these files into `web/dist/assets/terrain/` for the existing local static server.
- The loader verifies the mesh checksum, shape, coordinates, and indices before rendering.

The terrain uses the existing horizontal `position()` mapping. Its separate vertical mapping is `elevation_m / 111000 * terrain_exaggeration`, positioned above the uppermost displayed ocean sheet. Default terrain exaggeration is **75×**, independently adjustable from **20× to 150×**. Maximum default rendered height is approximately 4.72 scene units. The existing ocean gap remains 6 units. The UI explicitly labels this as vertically exaggerated static geographic context.

Material (updated surface finish): `MeshStandardMaterial`, elevation-based olive/earth/stone/pale-highland vertex tints, roughness **0.94**, metalness **0**, opaque, double-sided, shared-vertex slope normals. Fine stationary shader grain varies the material by at most 12%. This is illustrative coloring, not satellite imagery, measured land cover, or elevation displacement. There is no emissive terrain or coastline outline.

Lighting: existing neutral ambient **0.65**, white angled key **2.1** at `(-24, 40, 26)`, soft cool fill **0.8** at `(35, 8, 30)`. Ocean faces remain unlit MeshBasic materials with a separate subtle optical finish. The camera and exploded layer positions were preserved.

## Rebuild from the bundled local source

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/poc/build_terrain.py `
  outputs/phase7b/terrain/etopo2022-60s-stride3.nc `
  --dataset 'NOAA ETOPO 2022' `
  --version 'v1, ice surface, 60 arc-second product' `
  --attribution 'NOAA National Centers for Environmental Information (NCEI), ETOPO 2022, doi:10.25921/fd45-gt74' `
  --source-url 'https://oceanwatch.pifsc.noaa.gov/erddap/griddap/ETOPO_2022_v1_60s.nc?z[(4.95):3:(30.05)][(44.95):3:(105.05)]' `
  --native-arcseconds 60
```

Then run `npm.cmd run build` from `web/`. Launch the usual local application. No internet is required to rebuild from that file or to run the application.

For a replacement GEBCO/ETOPO file, supply a local NetCDF with a geographic latitude/longitude grid covering the full domain, a 2D elevation variable explicitly in metres, positive upward, and appropriate attribution. Flags `--variable`, `--lat`, and `--lon` select different variable names; `--step` controls display resolution. The script rejects insufficient coverage or incompatible units. It does not automatically download data. Unsupported projected rasters must be converted to a geographic NetCDF beforehand, with datum/provenance retained.

If the local bundle is absent, corrupt, or cannot load, the app states that terrain is unavailable and keeps the ocean and scientific controls usable. It never substitutes fake terrain or the old flat land mesh.

## Scientific separation and evidence

Terrain code does not call inference, read L2/L0, modify FieldView or scientific masks, alter depths/temperature/anomaly, change exports, or hide below-seafloor cells. Picking still raycasts only the selected ocean mesh. No Phase 7C work is included.

- Before: `outputs/phase7b/land-cutouts.png`.
- Actual application after: `outputs/phase7b/terrain/default.png` and `application.png`.
- Browser measurements: `outputs/phase7b/terrain/performance.json`.
- Python regression tests include zero-contour clipping, disconnected islands and water holes, and absent/ocean-only DEM cases.
- Frontend tests verify bundle provenance/checksum, real elevation variation, horizontal mapping, and separation of terrain exaggeration from source values.
- Browser tests verify local-only requests, terrain controls without repeated field requests, selected coordinates, FPS, and graceful missing-DEM handling, alongside existing scientific replay/export/picking tests.

## Verified results

Production TypeScript/Vite build passed. **456 Python tests, 47 Vitest tests, and 6 Playwright tests passed**. Python reported seven pre-existing deprecation warnings. Existing export and calibrated ocean-picking checks passed without tolerance changes.

The real historical replay for **2021-06-15**, default five sheets and 75× terrain relief, measured **141.3 fps median** in Microsoft Edge headless at 1440 × 1050 (734 × 560 3D canvas). Samples were 140, 141.3, 141.3, 140, 141.3 fps. Browser verification recorded one field request and zero external requests. This is a local hardware measurement, not a cross-device guarantee.

The default screenshot was inspected in the actual app: the uniform land top has been replaced by DEM-derived slopes, ridges, low coastal land, and higher inland relief, with the existing luminous ocean stack beneath it. The mesh is a surface only; its only zero-height boundary follows the sampled DEM's sea-level contour. Geographic agreement is at DEM display resolution, not an assertion of sub-grid shoreline precision.

## Subsequent ocean and land surface finish

The requested softer ocean presentation removes rectangular frame lines and reduces only visual skirt thickness from 0.75 to 0.22 scene units. Side opacity is now 25% of the face opacity. Layer separation, actual depth-face positions, supported geometry and triangle-to-cell picking order are unchanged.

Water corner RGB is averaged only where all four adjacent scientific cells are supported. Any missing/land neighbor prevents that corner averaging. This smooths displayed color transitions without changing masks or underlying scalar values. A stationary optical sheen mixes at most 5.5% into the surface face color and 1.8% into deeper faces; it does not displace water or claim measured wave heights. Exact numerical readings remain in the profile and exports. Ocean scalar colors are consequently display-smoothed, not a promise of pixel-for-pixel equality with the legend.

The real terrain positions, elevation source, and exaggeration remain unchanged. New land material grain is decorative only. The final appearance is captured in `outputs/phase7b/terrain/textured-ocean.png`. Build and 48 frontend tests passed, including a test for water smoothing that leaves source colors intact and cannot interpolate across unsupported cells. Browser results are recorded in `outputs/phase7b/browser-tests.json`.
