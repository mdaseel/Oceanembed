# OceanEmbed — Experiment A: Literature and Architecture Audit

**Question.** Are there architecture families relevant to SIH26066 that would
materially change OceanEmbed's model choice, or is the current compact CNN
scientifically defensible?

**Method.** Literature search prioritising 2022–2026, restricted to peer-reviewed
publisher pages, DOI records and institutional sources; arXiv preprints are
included only where noted and are labelled as preprints. No blog or vendor
material is used for a scientific claim. **No model was trained for this
section.** Searches were run 2026-09-05.

**Scope limits, stated up front.** This is a targeted audit, not a systematic
review: no PRISMA protocol, no exhaustive database sweep, and the search engine
is US-region. Publisher paywalls blocked full-text retrieval for several entries
(marked ✗ below), so those rows are populated from abstracts and publisher
metadata only. Where a field could not be verified it is recorded as `?`, never
guessed.

---

## 1. What the literature is actually doing

### 1.1 The problem is well-posed and actively worked
Surface-to-subsurface reconstruction from SST/SSS/SSH/wind is an established
task with a decade of method development, from support-vector and clustered
neural-network approaches (Su et al. 2015; Lu et al. 2019) through LSTM
thermohaline retrieval (Su et al. 2021) to attention CNNs, Vision Transformers,
U-Nets, graph networks and diffusion models in 2023–2026. OceanEmbed is not
attempting something unusual, and the comparison set is real.

### 1.2 The nearest neighbours to OceanEmbed
Two entries are close enough to be direct comparators.

**Qi et al. (2023), CBAM-CNN, tropical Indian Ocean** — the closest published
analogue by domain and inputs (35–120 °E, 30 °S–30 °N; SST, SSS, SSHA, wind U/V,
lon, lat → 58 levels to 1975 m). It uses 3×3 kernels over three convolutional
layers, i.e. a *very local* spatial context, on **monthly** data, and validates
against the Roemmich–Gilson gridded Argo **climatology product** rather than
individual profiles. Reported OSTS RMSE ≈ 0.54–0.57 °C.

That comparison matters in both directions. Their headline RMSE looks better
than OceanEmbed's thermocline numbers, but it is not the same quantity:
monthly-mean targets and a gridded, already-smoothed Argo climatology remove
most of the day-to-day and mesoscale variance that OceanEmbed is scored against.
OceanEmbed's daily, 0.25°, per-profile QC'd Argo validation (Phase 6C-A) is the
harder test, and the two numbers should never be placed side by side without
that caveat.

**Feng et al. (2025), DSVIT, tropical Indian Ocean** — a Vision Transformer with
a geographic positional prior and a thermocline-weighted physics-aware loss,
using SST, ADT and wind-stress curl **plus explicit climatological information**
as input. Reported RMSE 0.29 °C, R² 0.9962, beating their CNN and RNN baselines.
This is the strongest published argument that an attention architecture could
beat a plain CNN *in our own basin*.

### 1.3 The two structural ideas that recur
Across the strongest recent work, two design choices appear repeatedly and are
directly relevant to Experiments B and C.

**A climatological prior that the network adjusts.** Chae et al. (2026),
*TS-Cast*, conditions a U-Net on monthly climatological thermohaline profiles and
learns dynamic adjustments from satellite observations, validated against 23,631
Argo/CTD profiles plus KEO/EC1 moorings and PIES arrays, reaching <1 °C RMSE in
the upper 500 m at the Kuroshio Extension. Feng et al. (2025) likewise feed
climatology in as prior knowledge. Anomaly-relative formulations are also the
classical framing in the interpolation literature (subtract climatology,
reconstruct the anomaly, add climatology back). **This is exactly the hypothesis
Experiment C tests.**

**Low-rank vertical structure.** EOF decomposition of the vertical is a standard
compression step, and DERN-EOF (Deep-Sea Research I, 2023) combines an EOF
profile basis with a deep evidential regression network, reporting ~20 %
accuracy improvement plus calibrated uncertainty. **This is exactly the
hypothesis Experiment B diagnoses.**

### 1.4 A finding that constrains what any of us can claim
Garcia-Espriu et al. (2025, *Ocean Science*) ran a controlled feasibility study
on global surface-only reconstruction (0.25°, daily, T and S to 1000 m over 75
levels, Random Forest vs LSTM). Their conclusions are worth quoting in effect:
salinity reconstructs better than temperature; **temperature reconstruction
degrades significantly below 200 m**; performance deteriorates when the mixed
layer is shallow; and both models **underestimate the variability range in the
upper layers**.

Independently, the DERN-EOF work states that the high reconstruction uncertainty
originates from the ocean subsurface field being in weak relation with the sea
surface field.

Both findings match OceanEmbed's own results: 1000 m has stayed
climatology-dominant in every phase from 6B-A to 6C-C, and L2's advantage over
L0 is concentrated in the thermocline. That is not a defect specific to our
model; it is the physics of the problem showing up in someone else's experiment
too.

### 1.5 Where the literature is weaker than OceanEmbed
Three gaps recur, and they are the places where this project is genuinely ahead:

- **Observational validation.** Many studies validate against gridded Argo
  climatologies or reanalysis rather than individual QC'd profiles. TS-Cast is
  the notable exception. OceanEmbed's Phase 6C-A used 5,176 individual
  profiles with DATA_MODE-aware QC, TEOS-10 potential-temperature conversion,
  ocean-aware collocation and float-clustered bootstrap confidence intervals.
- **Operational input realism.** Almost nothing in this literature asks whether
  the products used for training are available in near-real time. Phase 6C-D
  measured it: the reference products lag 158–501 days, the NRT counterparts
  0.4–2.5 days, and raw substitution of the SSS channel fails.
- **Missing-input behaviour.** Handling is usually "exclude incomplete points"
  (Qi et al. 2023) or "train with artificial clouds". Phase 6C-B/6C-C built an
  evidence-gated fallback contract with provenance and age semantics.

### 1.6 Where the literature is ahead of OceanEmbed
Honestly stated:

- **Uncertainty.** TS-Cast predicts depth-dependent error variances; DERN-EOF
  gives evidential uncertainty; diffusion approaches give ensembles. OceanEmbed
  currently emits a point estimate with no per-prediction uncertainty. This is
  the single clearest capability gap.
- **Vertical resolution.** TS-Cast uses 128 levels, Qi et al. 58, Garcia-Espriu
  et al. 75. OceanEmbed uses 15, chosen for the disaster-management use case.
  That is a scope decision, not a deficiency, but it should be stated as one.
- **Attention mechanisms** have beaten plain CNNs in at least two studies in our
  own basin (Qi et al. 2023 CBAM vs CNN; Feng et al. 2025 DSVIT vs CNN/RNN).

---

## 2. Paper record

`?` = not verifiable from the accessible material. `✗ full text` = publisher
page returned 403 or was paywalled; row built from abstract and metadata only.

### Qi et al. (2023) — CBAM-CNN
- **Citation:** Qi, J., Xie, B., Li, D., Chi, J., Yin, B., Sun, G. (2023).
  Estimating thermohaline structures in the tropical Indian Ocean from surface
  parameters using an improved CNN model. *Frontiers in Marine Science*, 10,
  1181182. doi:10.3389/fmars.2023.1181182
- **Domain:** tropical Indian Ocean, 35–120 °E, 30 °S–30 °N
- **Inputs:** SST, SSS, SSHA, wind U/V, lon, lat · **Target:** T and S, 2.5–1975 m, 58 levels
- **Family:** CNN + Convolutional Block Attention Module · **Spatial context:** 3×3 kernels, 3 layers · **Temporal:** none (monthly)
- **Climatology prior:** no · **Missing inputs:** points with any missing parameter excluded · **Uncertainty:** no
- **Validation:** Roemmich–Gilson gridded Argo climatology, 2010–2020; OSTS RMSE ≈0.54–0.57 °C
- **Relevance:** closest published analogue; shows attention helped over plain CNN in our basin; but monthly + gridded-climatology validation is a much easier target than daily per-profile Argo

### Feng et al. (2025) — DSVIT
- **Citation:** Feng, Z., Qi, J., Xie, B., Cao, Y., Li, D., Liu, C., Yin, B. (2025).
  A prior-knowledge-integrated downscaling approach for subsurface thermal
  structure reconstruction in the tropical Indian Ocean. *Deep-Sea Research
  Part II*, 225, 105589. doi:10.1016/j.dsr2.2025.105589 (✗ full text)
- **Domain:** tropical Indian Ocean · **Inputs:** SST, ADT, wind-stress curl, temporal/geographic/**climatological** information
- **Family:** Vision Transformer + geographic positional prior + thermocline-weighted physics-aware loss
- **Uncertainty:** ? · **Validation:** independent test set; RMSE 0.29 °C, R² 0.9962, beating CNN and RNN baselines
- **Relevance:** strongest published case that attention plus a climatological prior beats a CNN in our own basin

### Chae, Donohue & Park (2026) — TS-Cast
- **Citation:** Chae, J.-Y., Donohue, K. A., Park, J.-H. (2026). TS-Cast: deep
  learning for subsurface ocean reconstruction from satellite observations in
  the northwestern Pacific. *Ocean Science*, 22, 2161–2177. doi:10.5194/os-22-2161-2026
- **Domain:** NW Pacific 20–50 °N · **Inputs:** SST, SSS, ADT + their error fields, coordinates
- **Target:** T and S, 10–700 dbar, 128 levels · **Family:** U-Net + FiLM conditioning, 512-d latent
- **Spatial context:** ~2°×2° (15×15 at 1/8°) sized to mesoscale eddies · **Temporal:** 31-day sequence (±15 d)
- **Climatology prior:** **yes** — monthly climatological profiles adjusted by the network
- **Missing inputs:** gapped profiles excluded from training, masked at test · **Uncertainty:** **yes**, depth-dependent predicted variances with an uncertainty-aware loss
- **Validation:** 23,631 Argo/CTD profiles (2021–2023), KEO and EC1 moorings, two PIES arrays; benchmarked against GLORYS12v1, ARMOR3D, HYCOM; <1 °C RMSE upper 500 m at Kuroshio Extension
- **Relevance:** the methodological gold standard in this set — climatology prior, spatial context sized to the physics, uncertainty, and mooring/PIES validation. Directly motivates Experiment C.

### Garcia-Espriu, González-Haro & Aguilar-Gómez (2025)
- **Citation:** Garcia-Espriu, A., González-Haro, C., Aguilar-Gómez, F. (2025).
  On the global reconstruction of ocean interior variables: a feasibility
  data-driven study with simulated surface and water column observations.
  *Ocean Science*, 21, 2579–2603. doi:10.5194/os-21-2579-2025
- **Domain:** global 60 °S–60 °N, detailed validation Gulf Stream · **Inputs:** SST, SSS, SSH, MLD, surface U/V, lat, lon, day-of-year
- **Target:** T and S to 1000 m, 75 levels · **Family:** Random Forest vs LSTM · **Climatology prior:** no
- **Key findings:** salinity reconstructs better than temperature; **temperature degrades significantly below 200 m**; degraded when the mixed layer is shallow; **upper-layer variability underestimated**
- **Relevance:** an independent controlled study reaching the same limits OceanEmbed hit — deep skill is climatology-dominated, and variance is under-dispersed

### DERN-EOF (2023)
- **Citation:** *Reconstructing subsurface temperature profiles with sea surface
  data worldwide through deep evidential regression methods.* Deep-Sea Research
  Part I (2023), ScienceDirect PII S0967063723000936. (✗ full text; author list
  not retrievable — publisher page returned 403. Cited by title and PII rather
  than with a guessed author list.)
- **Family:** deep evidential regression network on an **EOF profile basis** · **Uncertainty:** yes, evidential
- **Reported:** ≈20 % accuracy improvement; explicitly attributes high reconstruction uncertainty to the weak surface–subsurface relationship
- **Relevance:** the direct precedent for an EOF decoder — the hypothesis Experiment B diagnoses

### Su, Wu, Yan and colleagues — the earlier lineage
- Su, H., Wu, X., Yan, X.-H., Kidwell, A. (2015). Estimation of subsurface
  temperature anomaly in the Indian Ocean during recent global surface warming
  hiatus from satellite measurements: A support vector machine approach.
  *Remote Sensing of Environment*, 160, 63–71. doi:10.1016/j.rse.2015.01.001 (✗ full text)
- Lu, W., Su, H., Yang, X., Yan, X.-H. (2019). Subsurface temperature estimation
  from remote sensing data using a clustering-neural network method. *Remote
  Sensing of Environment*, 229, 213–222. doi:10.1016/j.rse.2019.04.009 (✗ full text)
- Su, H. et al. (2021). Predicting subsurface thermohaline structure from remote
  sensing data based on long short-term memory neural networks. *Remote Sensing
  of Environment*, 260, 112465. doi:10.1016/j.rse.2021.112465 (✗ full text)
- **Relevance:** establishes the Indian Ocean surface→subsurface anomaly
  formulation and the pointwise/clustered-MLP family that OceanEmbed's L1 sits in

### Graph and clustering approaches (2026)
- *Multi-Granularity Graph Neural Network for Satellite-Assisted Marine
  Environmental Field Reconstruction over Sparse Observation Grids.* Remote
  Sensing 18(17), 3003. (✗ full text) — motivated by irregular sampling,
  vertical non-stationarity and bathymetric barriers
- *An Adaptive Spatiotemporal Clustering Framework for 3D Ocean Subsurface
  Temperature Reconstruction.* arXiv:2605.00860 — **preprint, not peer
  reviewed**; ViT + dual-path CNN + Attention U-Net with vertical-dependency and
  temporal-dynamics clustering
- **Relevance:** graph methods target *irregular in-situ* observation geometry.
  OceanEmbed's inputs are already gridded L4 products on a fixed 101×241 grid, so
  the problem GNNs solve is one we do not have.

---

## 3. Decision matrix

| Model family | Potential advantage | Cost / risk | Already tested in OceanEmbed? | Extra experiment justified before SIH? | Decision |
|---|---|---|---|---|---|
| **MLP (pointwise)** | Establishes that the local surface state carries subsurface information at all; cheapest possible baseline | Spatially and temporally blind; cannot see fronts or eddies | **Yes — L1**, Phase 6B-A, and re-validated against Argo in 6C-A (L1 beats L2 at 20–30 m against Argo) | No | **TESTED-ADOPTED** (as the interpretability baseline, not the core) |
| **CNN (compact, dilated, spatial)** | Mesoscale context; the 33×33 receptive field is ≈8° ≈ the eddy scale TS-Cast also sized for | Fixed receptive field; no explicit long-range interaction | **Yes — L2**, Phase 6B-B; +33.5 % over L0 at 100 m on the grid benchmark, +28.1 % against Argo | No | **TESTED-ADOPTED — current core** |
| **CNN + temporal (GRU/LSTM/ConvLSTM)** | Eddy propagation, memory of recent forcing; TS-Cast uses a 31-day window | Multiplies cost by window length; risk of fitting validation-only structure | **Yes — L3**, Phase 6B-C. Validation gain +1.57 % reversed to −0.43 % out of sample; reversing history cost only 0.215 % | **No — explicitly not repeated** | **TESTED-REJECTED** |
| **ViT / Transformer / attention** | Beat CNN baselines in two studies in our own basin (Qi 2023 CBAM; Feng 2025 DSVIT) | Data-hungry; ~10³–10⁴× the parameters; both wins are confounded with other changes (climatology prior, physics loss, downscaling target), so the attention mechanism is not isolated in either | No | **No** — the published gains are not attributable to attention alone, and our 6-year daily training set is small for a ViT. The unresolved question it would address (is 33×33 enough context?) is a *receptive-field* question, testable far more cheaply | **DEFER** |
| **GNN** | Handles irregular, unstructured observation geometry | Substantial machinery | No | **No** — OceanEmbed's inputs are already gridded L4 on a fixed grid; the irregularity GNNs solve does not exist here. It would matter only if we ingested raw Argo/swath directly | **DEFER** |
| **Autoencoder / self-supervised encoder** | Pretraining on unlabelled surface fields; latent compression | Extra pipeline with no identified failure it fixes | Partially — L2's encoder already produces a 32-d latent, and Phase 6B-B found **12 of 32 latent dimensions dead** and ~7 PCs explaining 90 % of embedding variance | **No** — the existing latent is already over-provisioned; adding self-supervised pretraining addresses no measured deficit | **DEFER** |
| **EOF / low-rank vertical decoder** | Fewer decoder outputs, physically interpretable modes, and the direct precedent (DERN-EOF) pairs it with uncertainty | Injects representation error; a low-*k* basis can flatten thermocline structure | **Diagnosed here — Experiment B** | **Diagnostic only**, as pre-registered. No EOF decoder is trained in this study whatever B shows | **DIAGNOSTIC-ONLY** |
| **Climatology-residual formulation** | Used by the two strongest entries in this review (TS-Cast, DSVIT) and the classical interpolation framing; targets the exact weakness the literature reports — deep skill collapse and under-dispersed anomalies | Cannot beat L0 where L0 is already near-optimal; may trade upper-ocean skill for deep gains | **Tested here — Experiment C** | **Yes — this is the one new formulation this study trains** | **TESTED — see the closure report for the verdict** |
| **Uncertainty head (evidential / predicted variance)** | The clearest gap versus TS-Cast and DERN-EOF; a disaster-management product arguably needs it more than a research one | New loss, new calibration protocol, new validation design | No | **No — out of scope for this study by the brief**, and it is a capability addition rather than an architecture question | **DEFER — highest-value single follow-up** |

---

## 4. Answer to Experiment A's question

**The compact CNN choice is scientifically defensible, and no reviewed
architecture family justifies a new training experiment beyond the two this
study already runs.**

The reasoning, in short:

1. **The CNN is not an assumption here.** It was adopted after L0 and L1
   established the baseline and the pointwise ceiling, and it was checked
   against Argo, not only against a reanalysis.
2. **The temporal family was tested and rejected on evidence**, not skipped.
   TS-Cast's 31-day window is the strongest published counter-argument, but our
   own controlled ablation found history ordering nearly irrelevant and the
   validation gain non-reproducible out of sample.
3. **Attention's published wins in our basin are confounded.** In both Indian
   Ocean papers the attention model also changed the loss, the prior, or the
   target resolution. Nothing in the literature isolates attention as the cause,
   and training a ViT on six years of daily 101×241 fields to find out is a poor
   use of the remaining budget. Deferring it is a judgement about attribution,
   not a claim that CNNs are optimal.
4. **Graph methods solve a problem we do not have** — our inputs are gridded.
5. **The two ideas the strongest literature agrees on** — a climatology prior and
   a low-rank vertical basis — are precisely the two this study tests
   (Experiment C) and diagnoses (Experiment B). That is where the evidence
   pointed, and that is where the compute went.
6. **The real gap is uncertainty, not architecture.** TS-Cast and DERN-EOF both
   emit calibrated uncertainty; OceanEmbed emits a point estimate. If one thing
   is added after this study, it should be that.

**What this review does not establish:** that a CNN is optimal; that 33×33 is the
right receptive field; that attention would not help if isolated properly; or
that 15 depths are sufficient for every downstream use. Those remain open, and
saying so is part of the answer.

---

*Machine-readable version: `outputs/tables/architecture_closure/architecture_review_matrix.csv`*
