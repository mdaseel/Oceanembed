# OceanEmbed — SIH 2026 Demo Video Pitch

**Project:** SIH26066 — INCOIS / Ministry of Earth Sciences  
**Recommended runtime:** 5 minutes 20 seconds  
**Format:** Presenter-led story with frequent website demonstrations  
**Presenters:** Written for three people; roles can be combined  
**Core promise:** From surface observations to defensible subsurface ocean intelligence

## Production rhythm

Change the visual every 7–12 seconds. Presenter shots establish the story and credibility; the website proves each claim. Avoid showing a presenter speaking for more than 25 seconds without a cutaway.

The delivery should feel like the team is showing someone something they built—not reciting a report. Keep the small conversational phrases: “Here is the problem,” “Let me show you,” and “This part matters.”

---

## Scene 1 — The hook: the ocean we cannot see

**Time:** 0:00–0:32  
**Shot:** Presenter 1 on camera. Begin close, with no background music for the first sentence. Cut to a satellite ocean map, then to the OceanEmbed 3D layers.

**Presenter 1:**

“A satellite can see the ocean surface. But a cyclone does not interact with a two-dimensional ocean.

Under every surface pixel is a column of water—sometimes warm for a few metres, sometimes warm hundreds of metres deep. That hidden heat can matter, but direct ocean profiles are too sparse to give us a complete daily picture.

So we asked a simple question: can the surface tell us what is happening underneath?”

**On screen:**  
`The surface is visible. The subsurface is sparse.`

---

## Scene 2 — The answer

**Time:** 0:32–0:55  
**Shot:** Presenter 2 beside a monitor. Reveal the website as the product name is spoken.

**Presenter 2:**

“We built OceanEmbed.

It combines seven daily surface variables and reconstructs temperature at 15 depths—from the surface down to 1,000 metres—across the North Indian Ocean.

The result is not just another heat map. It is one explorable, depth-resolved ocean field, with the evidence and limitations visible beside it.”

**On screen:**  
`7 surface variables → 15 depths → one shared field`

---

## Scene 3 — The innovation, without the lecture

**Time:** 0:55–1:28  
**Shot:** Use the illustrated technical-approach graphic. Animate or zoom through the pipeline while Presenter 2 continues as voice-over.

**Presenter 2 — voice-over:**

“The model sees sea-surface temperature, salinity, sea-level anomaly, currents and winds. But it does not treat one location as an isolated dot.

For every prediction, it studies a 33-by-33 neighbourhood. A spatial CNN compresses that surrounding ocean structure into a 32-dimensional embedding, then combines it with location and season to reconstruct all 15 depths together.

That spatial context is where the useful improvement came from—especially around the thermocline.”

**On screen:**

`33×33 context` → `32-D embedding` → `15-depth temperature field`

**Editing note:** Keep this visually driven. Do not read architecture layer names or parameter counts aloud.

---

## Scene 4 — Website reveal: one field, three ways to understand it

**Time:** 1:28–2:13  
**Shot:** Full-screen website recording.

**Website actions:**

1. Open Historical Replay.
2. Choose a date with complete data.
3. Show the 2D temperature map.
4. Change from 0 m to 100 m.
5. Open the 3D Depth View and rotate it gently.
6. Select 300 m and 1,000 m.
7. Click one ocean point and open its vertical profile.

**Presenter 1 — voice-over:**

“Let me show you what that means in practice.

We choose a historical date, and OceanEmbed reconstructs the complete field once. This map shows the selected depth. Now we move from the surface to 100 metres and the thermal structure changes immediately.

The same field powers our 3D Depth View. We can inspect the layers, rotate the ocean and select any of the 15 mandated depths. Choosing a new layer does not rerun the model—it explores the reconstruction already produced.

And when we click a location, the map, 3D marker and temperature profile stay synchronized.”

**On-screen callouts:**

- `One inference • shared map, 3D and profile`
- `15 depths • 0–1000 m`

---

## Scene 5 — A scientific detail that changes the picture

**Time:** 2:13–2:35  
**Shot:** Stay on 3D view. Switch between shallow and deep layers so coastal shelf regions disappear. Briefly show the profile’s unavailable depths.

**Presenter 3 — voice-over:**

“This detail is important. A neural network can output all 15 numbers even where the real ocean is shallow. We do not display those values as if water exists below the seabed.

OceanEmbed uses real ETOPO bathymetry to mask each layer by local water depth. The raw prediction remains preserved, while the visualization stays physically honest.”

**On screen:**  
`Real bathymetry • no ocean rendered below the seafloor`

---

## Scene 6 — The proof: we tested information, not model fashion

**Time:** 2:35–3:12  
**Shot:** Presenter 3 on camera, then validation graphics and an Argo-float visual.

**Presenter 3:**

“Here is what makes our research different.

We did not begin with the biggest model we could name. We built an evidence ladder: climatology first, then a pointwise model, then spatial context, then temporal memory and other controlled alternatives.

Spatial context survived. Temporal memory looked better during validation, but failed to generalize on the frozen benchmark—so we rejected it. A climatology-residual model also failed its pre-declared gate, so we rejected that too.

Then we checked the frozen model against 5,176 real Argo profiles from 92 floats. At 100 metres, it improved RMSE by about 28 percent over climatology and about 9 percent over the pointwise model.”

**On screen:**

- `5,176 Argo profiles • 92 floats`
- `At 100 m: 28.1% better than climatology`
- `At 100 m: 8.8% better than the pointwise model`

**Presenter 3:**

“We kept the negative results because they tell us why the final model deserves to exist.”

---

## Scene 7 — The disaster-management moment: Cyclone Mocha

**Time:** 3:12–4:02  
**Shot:** Website screen recording. Open the Cyclone Mocha historical replay. Show the external track, thermal-support map, a before/passage/wake/recovery sequence and the report or along-track analysis.

**Presenter 2 — voice-over:**

“Now let us use the reconstruction for a real disaster-management question.

This is Cyclone Mocha in May 2023. The cyclone track is external context—it is not predicted by OceanEmbed and it never enters the neural network.

We place that track over the reconstructed thermal field. Now an analyst can inspect the heat available along the path, the subsurface anomaly, Tropical Cyclone Heat Potential and the strongest thermal segment encountered.

As Mocha passed, OceanEmbed reconstructed a coherent cold-wake response: surface cooling, a shallower 26-degree isotherm and a reduction in upper-ocean heat, followed by partial recovery.”

**Cut briefly to Presenter 2:**

“We are not predicting cyclone intensity. We are showing the hidden ocean conditions the cyclone encountered—and how the ocean changed after it passed.”

**On-screen permanent note:**  
`Ocean thermal support ≠ cyclone forecast`

---

## Scene 8 — Latest state: honesty is a feature

**Time:** 4:02–4:31  
**Shot:** Website screen recording. Open Latest Qualified Ocean State. Highlight the valid date, retrieval time, lag/source status and unavailable/withheld diagnostics if shown.

**Presenter 1 — voice-over:**

“OceanEmbed also has a Latest Qualified Ocean State. But we do not call a field ‘live’ just because it is the newest one on the screen.

The model requires all seven qualified inputs for the same date. We show the actual valid date, provider lag and source status. If the stack is incomplete, inference is blocked rather than filled with invented data.

Temperature is qualified with limitations. TCHP passed its operational gate. Standalone latest D26 did not—so the product withholds it.”

**On screen:**  
`Complete stack or no inference`  
`Actual valid date and lag shown`

---

## Scene 9 — The decision that proves the discipline

**Time:** 4:31–4:55  
**Shot:** Presenter 3 on camera. Use a simple two-column insert: “Fresher date” versus “Argo thermocline skill.”

**Presenter 3:**

“We even found a newer official current product that could make the dashboard date look three days fresher.

The frozen model barely changed—but real Argo observations showed a measurable degradation between 100 and 150 metres. So we rejected the substitution.

We chose a scientifically defensible older field over a cosmetically newer one. That is how every OceanEmbed output is promoted.”

**On screen:**  
`Fresher current source tested → Argo gate failed → substitution rejected`

---

## Scene 10 — Who uses it and why it scales

**Time:** 4:55–5:15  
**Shot:** Presenter 1 on camera, with quick inserts of the map, 3D layers, cyclone analysis and export.

**Presenter 1:**

“For an ocean researcher, OceanEmbed brings maps, vertical profiles, anomalies, provenance and exports into one workflow.

For a disaster-management analyst, it adds the depth-resolved thermal state beneath an authoritative storm track—information a surface map alone cannot provide.

And because the backend, validation rules and interface all use one frozen field contract, the same platform can support historical replay and qualified recent reconstruction without hiding a second model behind the screen.”

---

## Scene 11 — Closing

**Time:** 5:15–5:32  
**Shot:** Entire team on camera. Each person takes one short line. Finish on the OceanEmbed logo and rotating 3D ocean.

**Presenter 1:**  
“We reconstruct the ocean we cannot continuously observe.”

**Presenter 2:**  
“We validate what works—and preserve the evidence when something does not.”

**Presenter 3:**  
“And we turn that science into intelligence a researcher or disaster-management analyst can actually explore.”

**All / Presenter 1:**

“We are Team OceanEmbed. From surface observations to subsurface ocean intelligence.”

**Final frame:**

`OceanEmbed`  
`SIH 2026 • SIH26066`  
`INCOIS / Ministry of Earth Sciences`

---

## Website recording checklist

Record these clips separately, then edit them under the dialogue:

1. Dashboard opening and Historical Replay selection.
2. Date selection and loading state.
3. 2D map at 0 m and 100 m.
4. 3D rotation and depth selection at 0, 100, 300 and 1,000 m.
5. A point click with synchronized profile and marker.
6. Bathymetry-supported layer footprint changing with depth.
7. TCHP and historical D26 diagnostics.
8. Cyclone Mocha track × thermal-field replay.
9. Pre-event, passage, cold-wake and recovery views.
10. Latest Qualified Ocean State with visible valid date, lag and source status.
11. Validation/Argo evidence and export screen.

## Delivery notes for a natural pitch

- Learn the idea in each paragraph rather than memorising every word.
- Speak to one person behind the camera, not to an auditorium.
- Let the cursor action finish before explaining the next feature.
- Pause after the lines “so we rejected it” and “inference is blocked.” They are credibility moments.
- Keep technical terms only where the screen makes them understandable.
- Do not use “revolutionary,” “perfect accuracy,” “real-time” or “cyclone prediction.”
- Record presenter audio in short scene-sized takes. Natural breathing and slight variation will sound better than one uninterrupted performance.

## If the video must be under four minutes

Remove Scene 3’s second paragraph, shorten Scene 6 to the Argo result and one rejected-model sentence, and combine Scenes 8 and 9. Keep the Mocha demonstration and final three-person closing intact.
