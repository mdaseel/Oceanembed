# OceanEmbed — SIH 2026 Demo Video Pitch

**Recommended duration:** 4 minutes 45 seconds to 5 minutes 15 seconds  
**Format:** Hybrid presenter + website demo  
**Tone:** Confident, conversational and evidence-led  
**Project:** OceanEmbed — SIH26066

## Filming approach

- Use presenter shots for the problem, innovation, impact and closing.
- Use clean screen recordings for the actual workflow. Let the website remain visible long enough for the jury to understand each interaction.
- Keep presenters beside a monitor or in a simple lab/college setting. Avoid reading while looking down; speak in short thoughts and pause naturally.
- Record the website at full resolution. Use gentle cursor movement, one action at a time and short zooms around the feature being discussed.
- Use three speakers if available. The script also works with one or two presenters by combining the roles.

---

## Scene 1 — The problem

**Time:** 0:00–0:28  
**Visual:** Presenter 1 on camera. Start with a clean medium shot. After the first sentence, briefly cut to satellite imagery of the Indian Ocean.

**Presenter 1:**

“We can observe the ocean surface from space every day. But many of the conditions that influence marine heat, cyclone interaction and ocean response are hidden below that surface.

Direct subsurface measurements are valuable, but they are sparse. So when a researcher needs to understand what the ocean looked like at 50, 300 or even 1,000 metres, there is a major information gap.

That is the gap we built OceanEmbed to address.”

**On-screen text:**  
`The surface is visible. The subsurface is not.`

---

## Scene 2 — The solution in one sentence

**Time:** 0:28–0:48  
**Visual:** Presenter 2 on camera, standing beside a monitor showing the OceanEmbed landing page or overview screen.

**Presenter 2:**

“OceanEmbed learns the spatial state of the ocean surface and reconstructs one consistent temperature field across 15 depths, from the surface down to 1,000 metres.

It turns scattered surface information into an explorable view of the ocean’s vertical thermal structure.”

**On-screen graphic:**  
`7 surface channels → spatial embedding → 15-depth temperature field`

---

## Scene 3 — What enters the model

**Time:** 0:48–1:14  
**Visual:** Website screen recording. Show the input/data overview or use a brief animated crop of the technical-approach graphic. Highlight each input family as it is named.

**Voice-over — Presenter 2:**

“The system combines seven surface channels: sea-surface temperature, salinity, sea-level anomaly, current velocity in two directions and wind velocity in two directions.

We quality-check them, align them by date, place them on the same quarter-degree grid and preserve a separate validity mask. Historical and qualified recent inputs follow the same frozen seven-channel contract.”

**Editing note:** Do not show Argo or GLORYS as operational inputs. GLORYS is training supervision; Argo is observational validation.

---

## Scene 4 — The innovation

**Time:** 1:14–1:45  
**Visual:** Presenter 3 on camera for the first sentence, then switch to a close crop of the architecture graphic: 33×33 map patch → CNN plates → coloured embedding → decoder → depth stack.

**Presenter 3 / voice-over:**

“The core innovation is spatial context. A single ocean location does not exist in isolation, so OceanEmbed studies a 33-by-33 neighbourhood around it.

A dilated convolutional encoder compresses that neighbourhood into a compact 32-dimensional embedding. A decoder combines it with geographic and seasonal context to reconstruct all 15 depths together.

Because the depths come from one shared field, the map, the profile and the 3D view all describe the same reconstruction.”

**On-screen text:**  
`Spatial context • compact embedding • one shared field`

---

## Scene 5 — Live website demonstration: 2D to 3D

**Time:** 1:45–2:32  
**Visual:** Full-screen website recording.

**Actions:**

1. Open the OceanEmbed dashboard.
2. Select an available historical date.
3. Show the 2D surface-temperature map.
4. Switch to the 3D Depth View.
5. Rotate the model slowly.
6. Select 0 m, 100 m, 300 m and 1,000 m.
7. Click one valid ocean point and show the synchronized marker/profile.

**Voice-over — Presenter 1:**

“Let us see that in the product.

We choose a date and first receive the reconstructed surface field. Now we move into the 3D Depth View. Each layer is a real model depth, and selecting a depth only changes the view—it does not rerun the neural network.

Notice how the visible footprint changes as we go deeper. OceanEmbed uses ETOPO 2022 bathymetry to hide values below the local seafloor, so a 1,000-metre layer is not drawn across shallow coastal water.

When we select a point, the map, 3D marker and vertical profile remain geographically synchronized.”

**On-screen callouts:**

- `15 depths • 0–1000 m`
- `Physical depth support`
- `One cached field • multiple views`

---

## Scene 6 — Thermal diagnostics

**Time:** 2:32–2:58  
**Visual:** Continue website recording. Open the temperature profile and thermal-diagnostics view. Show TCHP and D26 where the selected dataset supports them.

**Voice-over — Presenter 1:**

“The reconstruction becomes more useful when we derive ocean indicators from it. OceanEmbed calculates Tropical Cyclone Heat Potential and the depth of the 26-degree isotherm for supported historical analysis.

Researchers can inspect the complete temperature profile instead of relying on surface temperature alone.”

**Editing note:** If D26 is withheld in the qualified recent mode, show that state honestly. Do not describe the thermal indicators as cyclone forecasts.

---

## Scene 7 — Disaster-management workflow

**Time:** 2:58–3:35  
**Visual:** Show a historical cyclone replay in the website. Display an external track over the OceanEmbed thermal field, then show along-track information, before/passage/after frames or the cold-wake view.

**Voice-over — Presenter 2:**

“For disaster-management analysis, we keep the responsibilities clear. OceanEmbed reconstructs the ocean thermal state. The cyclone track comes from an external, attributed source.

We overlay that track on the reconstructed field to study the thermal conditions encountered along its path: TCHP, subsurface anomalies, the strongest thermal segment and high or elevated thermal-support intersections.

For historical cyclones, we can also examine the ocean before passage, during the event, through the cold wake and into recovery.”

**On-screen permanent note:**  
`Thermal support ≠ cyclone forecast`

**Presenter 2, briefly on camera at the end:**

“We are not claiming to predict a cyclone’s track or intensity. We are giving analysts a clearer picture of the ocean conditions beneath that track.”

---

## Scene 8 — Scientific trust

**Time:** 3:35–4:02  
**Visual:** Presenter 3 on camera, followed by validation charts, an Argo-float illustration and a short shot of the validation section in the website or technical graphic.

**Presenter 3:**

“For us, a strong visual is not enough. The reconstruction must be traceable and testable.

The frozen model is evaluated against held-out GLORYS data and checked against 5,176 real Argo profiles from 92 floats. We report errors by depth, preserve model and data hashes, and keep the raw 15-depth prediction separate from display masks and derived diagnostics.

That gives every map a clear scientific provenance.”

**On-screen text:**  
`5,176 Argo profiles • 92 floats • depth-wise evaluation`

---

## Scene 9 — Why this matters

**Time:** 4:02–4:31  
**Visual:** Presenter 1 on camera. Use two or three short website inserts while speaking: 3D stack, cyclone replay and export/report.

**Presenter 1:**

“Today, these workflows often require specialists to assemble large datasets, run separate tools and interpret disconnected outputs.

OceanEmbed brings reconstruction, depth exploration, thermal diagnostics, historical replay and analyst-ready exports into one system.

For research institutions and disaster-management teams, that means faster investigation, consistent evidence and a much clearer path from ocean data to a decision-support brief.”

---

## Scene 10 — Feasibility and closing pitch

**Time:** 4:31–5:02  
**Visual:** Begin with a three-person team shot. Cut once to the architecture slide and finish on the OceanEmbed logo and website.

**Presenter 2:**

“The system already has the complete path: harmonised inputs, a frozen spatial model, a FastAPI service, an interactive React and Three.js interface, physical depth support, validation and export.”

**Presenter 3:**

“Our next step is to operationalise the qualified input adapters and storage layer with partner infrastructure, while keeping the same verified model contract.”

**Presenter 1:**

“OceanEmbed makes the invisible ocean easier to explore, validate and act on.

We are Team OceanEmbed, and this is our approach to turning surface observations into subsurface ocean intelligence. Thank you.”

**Final frame:**

`OceanEmbed`  
`From surface observations to subsurface ocean intelligence`  
`SIH 2026 • SIH26066`

---

## Natural delivery notes

- Treat each paragraph as an idea, not a block to memorise word for word.
- Look into the camera for the first and last sentence of every presenter segment.
- Use small pauses after “OceanEmbed,” “one shared field,” and “beneath that track.”
- Keep the demo voice-over slightly faster than the presenter sections, but pause after every click.
- Avoid exaggerated words such as “revolutionary,” “perfect” or “100% accurate.” The evidence is more persuasive than hype.
- Let each presenter use their normal speaking rhythm. A slight change of wording during recording will sound more human.

## Optional opening alternative

If you want a more cinematic opening, replace Scene 1’s first paragraph with:

“A satellite can show us the temperature of the ocean surface. But a cyclone does not interact with a two-dimensional ocean. Beneath every pixel is a changing column of water—and most of that structure is difficult to observe continuously. OceanEmbed was built to make that hidden structure explorable.”
