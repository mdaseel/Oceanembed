# Phase 7B implementation plan

Scope: historical offline PoC only. Starting commit: `5bbe96b`.

1. Preserve the frozen core, Phase 7A primitives, scientific data and evidence.
2. Add a local application wrapper over the existing replay API, with a single
   complete-field transport, surface-input transport, read-only evidence, and
   actual field NetCDF export. Serialize access to the shared scientific engine.
3. Build React/TypeScript/Vite, Tailwind and shadcn-style Radix components;
   lazy Plotly charts; separate replay, 3D, validation, exports and settings routes.
4. Adapt replay responses to a validated, transport-independent field contract.
   Canvas maps and a bundled three.js discrete-depth slice renderer share values,
   masks, colors and selected profiles. No interpolation of scientific arrays.
5. Default to the existing Phase 7A test date/location: 2021-06-15,
   15.25 N, 87.75 E. This is a central Bay of Bengal coordinate selected by
   geography, not prediction error. Explicit force-recompute on normal launch.
6. Verify regressions, exact data equality, offline browser operation, interactions,
   fallback and responsive layouts. Record measured performance and screenshots.
7. Write PHASE7B_HISTORICAL_POC_REPORT.md and stop for review.

Inspection notes: no AGENTS.md or frontend existed. The two handoff references
`docs/CODEX_CONTEXT.md` and
`docs/OceanEmbed_Research_Validation_Competition_Pointers_VERSION_3.md` are absent.
The repository master prompt, Phase 7A code/manifest and executed reports supply
the authoritative requirements. No attached dashboard image was available.
The existing 437-test result is historical evidence; it must be rerun locally.
