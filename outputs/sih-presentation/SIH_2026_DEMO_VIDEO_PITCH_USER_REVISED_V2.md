# OceanEmbed — SIH 2026 Demo Video Pitch

**Target runtime:** ~5 minutes 50 seconds
**Style:** Story first → product proof → scientific proof → real-world use → operational discipline
**Key principle:** Do not sound like you are reading a research paper. Show the evidence while speaking simply.

---

## SCENE 1 — THE HOOK

**Time:** 0:00–0:28
**Visual:** Presenter on camera. First sentence with no music. Then cut immediately to satellite surface imagery and OceanEmbed 3D depth layers.

### Presenter 1

“A satellite can see the ocean surface.

But a cyclone does not interact with a two-dimensional ocean.

Under every surface pixel is an entire column of water. Sometimes that warmth extends only a few metres. Sometimes it extends hundreds of metres deep.

That hidden structure matters.

But direct ocean profiles are too sparse to give us a complete daily picture.

So we asked one question:

**Can the surface tell us what is happening underneath?**”

**On screen:**
`The surface is visible.`
`The subsurface is sparse.`

---

## SCENE 2 — SHOW THE ANSWER IMMEDIATELY

**Time:** 0:28–0:58
**Visual:** Go directly into the working website. Change depth from 0 m → 100 m → 300 m. Briefly rotate the 3D visualization.

### Presenter 2 — voice-over

“This is OceanEmbed.

Using seven daily surface variables, OceanEmbed reconstructs ocean temperature at 15 depths, from the surface down to 1,000 metres, across the North Indian Ocean.

Here is the surface.

Now 100 metres.

And deeper.

This is not fifteen independently generated maps. One model inference produces the full depth-resolved field, which drives the map, 3D view and vertical profiles together.”

**On screen:**
`7 surface variables → 15 depths → one ocean field`

---

## SCENE 3 — WHAT ACTUALLY MAKES IT DIFFERENT

**Time:** 0:58–1:18
**Visual:** Presenter beside display. Show a simple pipeline graphic, not detailed neural-network layers.

### Presenter 2

“But our main innovation is not simply that we used a neural network.

**OceanEmbed is evidence-gated.**

A model, input substitution or ocean diagnostic reaches the final system only after that exact approach survives validation.

We did not choose the model because it looked more advanced.

We chose the simplest model that survived the evidence.”

**On screen:**
`Build → Test → Validate → Accept / Reject`

---

## SCENE 4 — TECHNICAL APPROACH, QUICKLY

**Time:** 1:18–1:43
**Visual:** Technical approach animation.

### Presenter 2 — voice-over

“The model receives sea-surface temperature, salinity, sea-level anomaly, currents and winds.

Instead of treating every location as an isolated point, it studies a 33-by-33 surrounding region.

A spatial CNN compresses that ocean structure into a 32-dimensional satellite embedding and reconstructs all 15 depths together.

That surrounding spatial information produced its strongest useful improvement around the thermocline.”

**On screen:**
`33×33 spatial context → 32-D embedding → 15 depths`

---

## SCENE 5 — EXPLORE THE OCEAN

**Time:** 1:43–2:13
**Visual:** Historical Replay. Select a date, click a location, change depth, open profile, synchronize map/3D marker.

### Presenter 1 — voice-over

“Now let me show you what an analyst can actually do with it.

We choose a historical date and reconstruct the ocean once.

Changing the depth does not rerun the model. We are exploring the same reconstructed water column.

Click any ocean location and the 2D map, 3D marker and complete vertical temperature profile remain synchronized.

The user can compare the reconstruction with climatology and inspect the anomaly instead of seeing only a temperature number.”

**On screen:**
`One inference • Map • 3D • Profile • Anomaly`

---

## SCENE 6 — PHYSICAL HONESTY

**Time:** 2:13–2:31
**Visual:** Switch from shallow to deep layers. Coastal regions disappear with increasing depth.

### Presenter 3 — voice-over

“There is another detail we deliberately handle.

A neural network can output fifteen temperatures even where the real ocean is shallower than those depths.

We do not display that as real water.

OceanEmbed uses actual ETOPO bathymetry to prevent the visualization from rendering ocean beneath the local seafloor.”

**On screen:**
`Real bathymetry`
`No ocean rendered below the seafloor`

---

## SCENE 7 — THE RESEARCH PROOF

**Time:** 2:31–3:12
**Visual:** Presenter → evidence ladder → Argo float graphic → simple 100 m comparison chart.

### Presenter 3

“This is where our research became important.

We started with climatology.

Then a pointwise neural network.

Then spatial context.

Then we tested temporal memory.

Temporal memory looked better during validation.

But on our frozen benchmark, that improvement did not generalize.

**So we rejected it.**

We also tested a climatology-residual formulation.

It failed its pre-declared gate.

**So we rejected that too.**

Then we tested the frozen spatial model against **5,176 real Argo ocean profiles from 92 floats.**

At 100 metres, OceanEmbed reduced RMSE by approximately **28 percent compared with climatology**, and by about **9 percent compared with the pointwise model**.

That is why the spatial model became our final scientific core.”

**On screen:**
`5,176 Argo profiles • 92 floats`

`100 m RMSE improvement:`
`28.1% vs climatology`
`8.8% vs pointwise model`

Small disclosure:

`Strongest skill: upper ocean / thermocline`
`Deep anomaly skill is weaker`

---

## SCENE 8 — WE VALIDATED THE APPLICATION, NOT JUST THE MODEL

**Time:** 3:12–3:29
**Visual:** D26 and TCHP screen.

### Presenter 3 — voice-over

“And we did not assume that good temperature RMSE automatically meant every derived ocean indicator was reliable.

Before using cyclone-relevant quantities such as the 26-degree isotherm depth and Tropical Cyclone Heat Potential, we validated those diagnostics separately.

Only the diagnostics that passed their gates were promoted into the application.”

**On screen:**
`Temperature validation ≠ automatic diagnostic validation`

---

## SCENE 9 — CYCLONE MOCHA

**Time:** 3:29–4:05
**Visual:** Mocha replay: track overlay → before → passage → wake → recovery.

### Presenter 2 — voice-over

“Now let us apply this to a real event.

This is Cyclone Mocha in May 2023.

The cyclone track comes from an external authoritative source. It is not predicted by OceanEmbed and never enters the neural network.

We selected the event using a pre-declared rule rather than choosing a cyclone after seeing which result looked best.

Overlaying the track on the reconstructed ocean lets us inspect the thermal environment beneath the storm.

During Mocha, OceanEmbed reconstructed a coherent cold-wake response: surface cooling, changes in the 26-degree isotherm depth, reduced upper-ocean heat and subsequent recovery.”

### Presenter 2 — briefly on camera

“We are not predicting the cyclone.

We are reconstructing the hidden ocean conditions the cyclone encountered.”

**Permanent on-screen label:**
`Ocean thermal intelligence ≠ cyclone forecast`

---

## SCENE 10 — LATEST OCEAN + ACTIVE CYCLONE WATCH

**Time:** 4:05–4:52
**Visual:** Latest Qualified Ocean State → source status → Ocean Thermal Watch. Click **Check source**. Show thermal monitoring hotspots. If a current North Indian Ocean cyclone is available, show its external GDACS track over the latest qualified field. If no cyclone is active during recording, keep the honest “NO ACTIVE” state visible, then use the clearly labelled archived test event only to demonstrate the workflow.

### Presenter 1 — voice-over

“Historical reconstruction is only one part of the system.

OceanEmbed also supports a Latest Qualified Ocean State. It shows the real valid date, retrieval time, product age and source status. If the seven-channel stack is incomplete, the system blocks inference instead of filling the gap with invented data.

From here, the Ocean Thermal Watch checks the connected GDACS source for current North Indian Ocean cyclones.

When a cyclone is active, its external track is placed over the latest qualified OceanEmbed field. The system checks which HIGH or ELEVATED thermal hotspots the track intersects and measures the ocean heat encountered along it: the highest thermal-support category, peak TCHP, the largest 100-metre anomaly and the strongest thermal segment.

It also generates an along-track vertical section and a printable analyst brief.

The cyclone track remains external context. OceanEmbed supplies the thermal intelligence underneath it.”

**On screen:**

`Current cyclone source → External track`

`Latest qualified ocean field → Thermal hotspots`

`Track × hotspots → Peak TCHP • 100 m anomaly • strongest segment`

Small permanent label:

`OceanEmbed does not forecast cyclone track or intensity`

---

## SCENE 11 — SCENARIO MODE

**Time:** 4:52–5:18
**Visual:** Open **Scenario**. Select either a historical field or Latest Qualified Field. Click **Draw on map**, add a short path through a visible hotspot, then click **Analyse path**. Show track analysis and the along-track depth section.

### Presenter 2 — voice-over

“We also built Scenario Mode for planning and exploration.

An analyst can draw a possible path across either a historical field or the latest qualified ocean state.

OceanEmbed then samples the thermal conditions along that route: where it intersects HIGH or ELEVATED water, how TCHP changes, where the subsurface anomaly is strongest, and how temperature varies with depth along the path.

The route is always labelled as user-drawn. It is not an observed track and not an official forecast. It is a transparent what-if tool for understanding the ocean conditions along a path.”

**On screen:**

`USER-DRAWN SCENARIO • NOT AN OFFICIAL FORECAST`

`Draw path → Analyse heat → Inspect vertical section`

---

## SCENE 12 — THE DECISION I WANT THE JURY TO REMEMBER

**Time:** 5:18–5:39
**Visual:** Split screen.

LEFT: `Newer current product`
RIGHT: `Argo observational validation`

### Presenter 3

“One experiment captures the philosophy of the entire project.

We found a newer official ocean-current product that could make our displayed ocean state approximately **three days fresher**.

The frozen model output barely changed.

So visually, everything looked fine.

But when we tested that substitution against real Argo observations, performance degraded around the thermocline.

**We rejected it.**

We chose a scientifically defensible older field over a cosmetically newer dashboard date.”

**On screen:**
`Fresher ≠ Better`

`New product → Argo gate failed → Rejected`

---
## SCENE 13 — CLOSE

**Time:** 5:39–5:52
**Visual:** Team on camera, then final 3D OceanEmbed shot.

### Presenter 1

“OceanEmbed reconstructs the ocean we cannot continuously observe.”

### Presenter 2

“We validate what works—”

### Presenter 3

“—and reject what does not.”

### Presenter 1

“From surface observations to defensible subsurface ocean intelligence.”

**Final frame:**

`OceanEmbed`

`SIH 2026 • SIH26066`

`INCOIS • Ministry of Earth Sciences`

`Surface observations → Subsurface intelligence`


