# OceanEmbed — Evaluation Scope

## Governing principle

> OceanEmbed is a general subsurface-temperature reconstruction framework.
> Cyclones are the first high-impact stress test, not the system's sole use case.
> Subsequent evaluation will include marine heatwaves and may include other
> scientifically justified regimes such as strong eddies, monsoon transitions and
> abnormal stratification. Hazards without a meaningful relationship to subsurface
> thermal structure will not be artificially attached to the project.

## What the system is

Multi-source satellite surface observations → learned ocean representation →
subsurface temperature reconstruction at 15 depth levels across the North Indian
Ocean (5–30 °N, 45–105 °E), 0.25°, daily.

The reconstruction is **general purpose**. It is not a cyclone product, and the
training dataset is deliberately **condition-neutral**: it is not restricted to
cyclone dates or cyclone regions, and it carries no event labels.

## Stress-test hierarchy (evaluation only — none implemented in Phase 6A.5)

| # | Regime | Status | Why it qualifies |
|---|---|---|---|
| 1 | Normal / background ocean | baseline | The reference against which every other regime is measured |
| 2 | Tropical cyclones | first stress test | Tracks are independently observed; upper-ocean thermal structure is directly and physically implicated |
| 3 | Marine heatwaves | second stress test | A temperature extreme by definition; ~1/3 of subsurface events have no continuous SST signature, making them a genuine test of a surface-only method |
| 4 | Strong mesoscale eddies | candidate | Displace isotherms; already visible in the GLORYS 100 m field |
| 5 | Monsoon-transition conditions | candidate | Rapid changes in stratification and forcing |
| 6 | Abnormal stratification / barrier layers | candidate | Region-specific; a Bay of Bengal winter inversion was observed in the very first Phase 6A proof cell |

## Explicitly out of scope

**Tsunamis.** Subsurface temperature is not a primary tsunami detection or
prediction variable. Attaching tsunami work to this project would be a
presentational choice, not a scientific one, and is therefore excluded.

Also out of scope for the reconstruction system itself: cyclone track or intensity
forecasting, alerting, and evacuation functionality. These sit outside the
mandated problem statement.

## Dataset neutrality guarantee

The Phase 6A.5 model-ready dataset contains **no** event masks, cyclone labels,
heatwave labels, eddy labels or monsoon-stage labels. Regime definitions belong
to the evaluation layer and will be applied to a frozen, condition-neutral
dataset so that no regime can influence what the model was trained on.
