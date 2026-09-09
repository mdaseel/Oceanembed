# 2D cartographic display refinement

The 2D map now combines smooth temperature display rendering with a static
shaded-relief land overlay from the same local NOAA ETOPO 2022 source used by
the 3D terrain. No online tiles, satellite imagery, or invented terrain are used.

## Rendering

- The 1320 × 555 map raster replaces overlapping per-cell canvas rectangles.
  Bilinear interpolation is applied to displayed scalar colors only where all
  four adjacent samples are supported. Every pixel is gated by its original
  containing scientific cell; missing and land cells never receive invented
  temperature values. Support edges are feathered inward only.
- `scripts/poc/build_map_relief.py` generates the local transparent land overlay
  from `outputs/phase7b/terrain/etopo2022-60s-stride3.nc`. Positive DEM elevations
  supply the land mask. Northwest illumination and two-scale slope shading
  reveal mountains and plains; 12× slope exaggeration is used only for lighting.
- `web/public/assets/terrain/map-relief.png` and `map-relief.json` are bundled
  into the local app. Metadata records source checksum, processing, dimensions
  and extent. Missing/out-of-subset DEM remains transparent.
- The coordinate mapping is unchanged: map cell-edge bounds are
  44.875–105.125 E and 4.875–30.125 N, around the canonical cell centres.
- Grid lines are subdued. Labels identify India, Arabia and Myanmar.
- The legend uses the same color mapper as the field. PNG export waits for the
  local relief overlay and uses the same drawing function. CSV/NetCDF numerical
  exports, scientific arrays, masks, selection, and inference are unchanged.

The finer DEM coast can differ from the coarse scientific mask. Data gaps stay
dark instead of being filled to resemble the artistic reference. Smoothing
does not add scientific resolution or manufacture the reference's hot/cold
patterns. If the relief asset is unavailable, the map remains usable and its
caption reports unavailable/loading relief.

## Rebuild and evidence

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe scripts/poc/build_map_relief.py
```

Then run `npm.cmd run build` from `web/`. The generated overlay works offline.

Actual screenshot: `outputs/phase7b/terrain/relief-map.png`.
Tests cover scalar display interpolation without mutation, missing-data gating,
local relief loading, and the existing coordinate/profile/export browser flow.
