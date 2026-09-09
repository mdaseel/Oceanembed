# Phase 7B 3D visual tuning

Edit `web/src/field/visualConfig.ts`, object `OCEAN_VISUAL_CONFIG`, then run `npm run build` from `web` and refresh the application.

| Setting | Current | Suggested range | Effect |
| --- | --- | --- | --- |
| emissiveIntensity | 0.08 | 0–0.15 | Higher lifts ocean RGB brightness after the existing surface finish; lower looks more matte. Values, palette and normalization are unchanged. Stronger settings can saturate bright reds. |
| outlineOpacity | 0.38 | 0.15–0.6 | Visibility of non-selected white layer perimeters. |
| selectedOutlineIntensity | 1 | 0.55–1 | Cyan selected frame emphasis (opacity); 1 is maximum. |
| selectedOutlineRadius | 0.035 | 0.015–0.06 | Thin selected edge radius in scene units; independent of scientific geometry. |
| cornerOpacity | 0.25 | 0.1–0.45 | Visibility of four vertical corners and lower closing perimeter. |
| legendSeparatorOpacity | 0.45 | 0.15–0.65 | Tick-aligned separator visibility on all prism faces. |
| normalOutlineColor | 0xd5e6f2 | CSS-style hex RGB | Neutral cool-white frame color. |
| selectedOutlineColor | 0x16bbff | CSS-style hex RGB | Selected cyan frame color. |
| legendViewportFraction | 0.20 | 0.18–0.24 | Right foreground space reserved for the 3D legend; picking and camera sizing use the same helper. |

There is no bloom postprocessing pass. `bloomStrength`, `bloomRadius`, and `bloomThreshold` are deliberately not inactive knobs: they are not implemented. In a future bloom implementation, strength controls spread intensity, radius controls width/softness, and a lower threshold admits more scene brightness. This refinement uses the existing self-lit ocean shader and small edge geometry to avoid a new render-target/postprocessing cost.

The ocean uses MeshBasicMaterial already, so emissiveIntensity is an explicit shader brightness multiplier, not an ineffective MeshStandardMaterial emissive property. No new colormap is generated. No field values are read or mutated by frame creation.

The foreground prism is real box geometry rendered in a dedicated scene using the same WebGL renderer/canvas. It has a fixed camera and fixed dimensions; it is not anchored to a geographic coordinate. Its ticks, gradient and separators derive from the active temperature/anomaly range. Depth selection, orbit and separation do not reposition or highlight it. The scientific camera and raycast use the ocean viewport width consistently. The geographic probe stays in the ocean scene.

Frames reuse the existing selected depth index and visibleLevels()/layerLayout() output. The matching layer alone is cyan, including intermediate required depths. No new controls, scientific inference, terrain or export changes are introduced.
