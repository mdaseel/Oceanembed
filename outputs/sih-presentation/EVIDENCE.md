# OceanEmbed SIH technical approach — evidence notes

Deliverables: TECHNICAL_APPROACH.png (3840 × 2160) and editable TECHNICAL_APPROACH.svg. Deterministic vector composition rendered in Chromium/Edge, not an AI-painted screenshot. Application/model files were not modified. Generator: render_architecture.py.

## Verified architecture

- Historical input products and channels: src/oceanembed/replay/engine.py (_PRODUCTS), ml/features.py; outputs/phase7/final_core_manifest.json. OSTIA, MULTIOBS SSS, DUACS SLA, OSCAR Final v2, CCMP v3.1. These are multisource surface products, not seven direct satellite instruments.
- Canonical grid and missing-data treatment: src/oceanembed/grid.py; preprocessing/regrid.py, masks.py; config/data_splits.yaml; ml/scaler.py.
- Spatial CNN / latent / decoder: src/oceanembed/ml/l2_model.py. Note the default-class example is patch 17; the frozen production checkpoint configuration is patch 33, latent 32, 136335 parameters (phase7 manifest). Dilations 1/2/4/8/1. Decoder includes latitude, longitude and seasonal context.
- Training branch: scripts/baselines/train_l2.py, ml/l2_dataset.py, configuration and saved checkpoint outputs/models/phase6b_l2_final.pt. GLORYS12V1 is a training reference, never an inference feature.
- Frozen inference and cache: replay/engine.py, replay/api.py, replay/cache.py. Shared whole-field inference and point sampling preserve map/profile consistency. Hash-verified artifacts, local cache; not a database/cloud service.
- Physical support and diagnostics: diagnostics/bathymetry.py, diagnostics/thermal.py, diagnostics/hazard.py, plus frontend field/bathymetry.ts. ETOPO support is separate from raw predictions. D26/TCHP are derived diagnostics, not separate ML models. Thermal-support categories are not cyclone probability or forecast.
- Validation: validation/argo.py and scripts/validate/argo_validate.py; PHASE6C_ARGO_VALIDATION_REPORT.md; outputs/tables/phase6c_argo_metrics_by_depth.csv; phase6b_l2_metrics_by_depth_test.csv. Argo audit: 5176 profiles, 92 floats. Float-cluster bootstrap; L0/L1 comparisons. No global headline accuracy percentage is invented.
- Split dates: config/data_splits.yaml. Train 2015–2020; validation 2021; test 2022–2024-12-15. 2024 Argo is a separate observational holdout, not the same as reanalysis testing.
- Serving and UI: src/oceanembed/poc/app.py, replay/api.py; web/package.json, web/src/App.tsx and components. Local FastAPI/Uvicorn; React/TypeScript/Vite/Three.js/Plotly; raw exports and provenance.
- Event/science features: events/library.py, track_analysis.py; science/attribution.py, occlusion.py, physical_qa.py; outputs/science/README.md and generated artifacts. IBTrACS retrospective event analysis is not a forecast.
- Recent-state qualifications: PHASE8B_NRT_SUBSURFACE_QUALIFICATION_REPORT.md, operational addendum and nrt/latest.py. Temperature qualified with limitations; TCHP qualified; D26 withheld. Actual valid dates and source limitations must accompany any demonstration.
- Phase8C source-substitution research: outputs/phase8c/decision.json explicitly rejects the candidate. Diagram does NOT claim the CMEMS alternative currents were deployed; production remains OSCAR NRT, historical remains OSCAR Final.

## Emphasis and exclusions

Jury-facing strengths shown: spatial-context embedding rather than SST-only lookup; one consistent 15-depth field; independent observational evidence; physically supported outputs and traceable replay. These are implementation distinctions, not claims of world-first novelty.

Excluded as production architecture: rejected L3 GRU/residual alternatives; rejected operational current substitution; invented cloud infrastructure, Docker deployment, relational databases, live sensors, cyclone forecast probabilities and claimed execution of the protected 2024 Argo holdout.

Source-code files, scripts, manifests, reports, configuration, package dependencies and generated evidence were reviewed. Large binary datasets/checkpoints were not rewritten, retrained or executed for this illustration. Figure intentionally abstracts the full application into six major stages rather than listing every route and experiment.
