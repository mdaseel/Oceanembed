# Phase 7B visual polish tuning

All settings live in `web/src/field/visualConfig.ts`, object `OCEAN_VISUAL_CONFIG`. Edit, run `npm run build` from `web`, then refresh. These are presentation settings; bathymetry, raw values, palette normalization, geographic positions and depth selection remain unchanged.

| Constant | Current | Suggested range / meaning |
| --- | --- | --- |
| backgroundCenter | #07131e | Dark navy central color |
| backgroundEdge | #02060b | Near-black navy edge color |
| vignetteStrength | 0.12 | 0–0.25; higher darkens the edges |
| haloIntensity | 0.18 | 0–0.3; higher strengthens the broad diffuse blue backdrop |
| emissiveIntensity | 0.175 | 0–0.25; raises self-lit ocean brightness. Previous setting 0.15; this is a 16.7% increase in emission strength, not a 16.7% change to every final pixel. |
| oceanGlowStrength | 1.08 | 0.8–1.2; scales existing optical sheen, without a bloom pass |
| outlineOpacity | 0.40 | 0.25–0.40; neutral perimeter visibility |
| cornerOpacity | 0.35 | 0.25–0.40; vertical corner and bottom-frame visibility |
| selectedOutlineIntensity | 1 | 0.8–1; selected cyan frame opacity |
| selectedOutlineRadius | 0.035 | 0.02–0.05 world units; selected edge thickness |
| selectedFrameGlow | 0.12 | 0–0.2; selected edge's wider translucent accent |
| terrainKeyIntensity | 2.8 | 2–3.2; upper-left/front directional light |
| terrainRimIntensity | 0.9 | 0.4–1.1; opposite cool fill/rim |
| terrainAmbientIntensity | 0.8 | 0.5–0.9; soft ambient fill |
| probeLineWidth | 0.10 | 0.05–0.16 world units; full diameter of vertical guide |
| probeLineOpacity | 0.42 | 0.25–0.6; guide visibility |
| probeGlowIntensity | 0.14 | 0–0.25; wider translucent guide accent opacity |
| probeColor | 0x21ddff | Guide, stem and ring cyan |
| labelOffsetDistance | 5.3 | 4.8–7; distance west of the frame; smaller moves labels closer |
| legendSeparatorOpacity | 0.45 | 0.15–0.65; existing prism separators |

The bead size and terrain shape remain unchanged. Probe width uses real cylinder geometry because WebGL line width is not reliably supported. The guide remains in the geographic scene, using the existing canonical selected cell and rendered surface height. Glow uses thin translucent accent geometry with depth testing, without postprocessing, animated pulses, or extra lights.

The backdrop is a static 256 × 256 texture with a broad elliptical halo and subtle vignette. It is generated once and disposed with the renderer. No per-frame texture generation is added.

The legend remains a model in the SAME geographic scene, preserving its current placement and orbit/pan/zoom behavior. It is not a UI overlay. No depth selector was added.

Changed implementation files:
- `web/src/field/visualConfig.ts`: centralized settings
- `web/src/field/sceneBackdrop.ts`: gradient, vignette and atmospheric halo
- `web/src/field/surfaceMaterials.ts`: configurable ocean emission and optical sheen
- `web/src/components/DepthRenderer.tsx`: backdrop, lighting and label offset
- `web/src/components/StackFrame.ts`: restrained selected-edge glow
- `web/src/components/LocationProbe.ts`: adjustable guide diameter, opacity and glow

Screenshot: `outputs/phase7b/navy-scene-polish.png` (actual application, real replay, 1000 m selected). Snapshot performance approximately 141 FPS in Edge headless; hardware-dependent.
