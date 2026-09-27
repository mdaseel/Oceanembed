# OceanEmbed UI refinement — 27 September 2026

## Changes

- Restrained navy surfaces, clearer hierarchy, consistent controls, keyboard focus states, and short entrance/hover transitions. Reduced-motion preferences are respected.
- Column structure and anomaly panels now respond to their actual available width. Metric cards wrap, tables can scroll locally, and scientific tooltips are rendered outside clipping containers.
- Added a direct **Preview archived cyclone** action in the latest-state inspector. It opens the analysis tray and loads the existing historical test endpoint; historical/test labels remain explicit.
- Added source-by-source dates and a common-date bottleneck label. Qualification details remain available in an expandable banner.
- Manual provider refresh bypasses persisted discovery as well as memory. The UI waits for date discovery before loading the newest field, exposes provider errors, and bounds waiting times. Existing unavailable-state information remains visible during retries.
- Frozen inference, input qualification gates, bathymetry rules, field values, exports, and model artifacts were not changed.

## Live source check

Direct configured-provider discovery completed successfully on 27 September, with no source errors:

| Qualified source | Newest date |
| --- | --- |
| SST | 2026-09-26 |
| Salinity | 2026-09-21 |
| Sea level | 2026-09-27 |
| OSCAR currents | **2026-09-03** |
| Wind | 2026-09-25 |

September 3 is therefore a genuine input availability limit, not a hardcoded UI date. The renderer must not advance it without a complete newer seven-channel stack. A first verification server with restricted provider access timed out; direct provider verification subsequently succeeded with network access.

## Verification

- Frontend production build: passed.
- Frontend unit suite: **135 passed**. Focused refresh/workspace rerun after timeout changes: **5 passed**.
- `tests/test_phase8b_latest.py`: **62 passed**, including new manual-refresh regressions and existing frozen-hash/field-contract checks. Existing dependency deprecation warnings remain.
- Browser checks: **10 scenarios passed**, with one unavailable-state regression fixed and rerun after the initial nine passes. Covers latest-state semantics, shared renderer, date selection, archived cyclone preview, and widths 1440 / 1024 / 390.
- Git whitespace check: passed.

Browser regression fixtures isolate provider availability for deterministic testing; the archived cyclone endpoint and reconstruction fields are real local application outputs. Source dates were also checked directly against the configured providers.

Screenshots in this directory include the main workspace, responsive column panels, source-date cards, and the archived cyclone preview.

The updated preview runs at http://127.0.0.1:8001. The user's pre-existing server on port 8000 was left running; restarting the normal launcher loads the backend changes there too.
