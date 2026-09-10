# Selected-depth probe

The terrain coastline/outer-edge glow was removed at the user's request. Terrain material and lighting are unchanged.

The retained probe samples the canonical selected cell in the existing selected-depth mesh, including its current exploded layout, water curvature and bathymetry support. It ends on that rendered sheet. Selecting the top sheet draws no downward guide; a below-seafloor selection withholds downward extent. The surface marker and selected latitude/longitude remain unchanged.

Implementation: `web/src/components/LocationProbe.ts` and `DepthRenderer.tsx`.
Tests: `web/src/test/locationProbe.test.ts` and `web/e2e/probeEndpoint.spec.ts`.

Existing probe width, opacity and glow settings in `web/src/field/visualConfig.ts` remain usable. No API, inference, exports, masks or scientific values were changed.
