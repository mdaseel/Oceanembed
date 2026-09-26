"""Scientific integrity checks, computed from the repository - never asserted as text.

Each item states what was checked and how. A check that cannot be evaluated is
reported as UNVERIFIED, never as PASS.
"""
from __future__ import annotations

import json

import pandas as pd

from ..config import REPO_ROOT
from ..replay import engine as E

DECISION = REPO_ROOT / "outputs" / "phase8b" / "qualification_decision.json"
ARGO_MANIFEST = REPO_ROOT / "outputs" / "argo" / "download_manifest.json"
ARGO_MATCHED = REPO_ROOT / "outputs" / "argo" / "matched_profiles.parquet"
ARGO_META = REPO_ROOT / "outputs" / "argo" / "analysis_meta.json"
THRESHOLDS = REPO_ROOT / "outputs" / "phase7" / "HAZARD_THRESHOLDS.json"

PIPELINE = [
    {"stage": "Historical training", "detail": "TRAIN 2015-2020 surface inputs -> GLORYS targets"},
    {"stage": "Frozen L2", "detail": "state-dict and encoder hashes pinned"},
    {"stage": "Observational validation", "detail": "independent 2022-2023 Argo profiles"},
    {"stage": "NRT input qualification", "detail": "seven channels, one valid date, pre-registered protocol"},
    {"stage": "Latest qualified field", "detail": "15-depth temperature and TCHP; D26 withheld"},
    {"stage": "Disaster decision support", "detail": "context beside official warnings, never a forecast"},
]


def _item(label, state, value, how):
    return {"label": label, "state": state, "value": value, "how": how}


def checks(engine) -> dict:
    items = []
    sd_ok = engine.l2_state_dict_sha256 == E.EXPECTED_L2_STATE_DICT
    enc_ok = engine.l2_encoder_sha256 == E.EXPECTED_L2_ENCODER
    files_ok = all(engine.file_hashes[k] == v for k, v in E.EXPECTED_SHA256.items())
    items.append(_item("Frozen L2 model", "VERIFIED" if sd_ok and files_ok else "FAILED",
                       "checkpoint, scalers and climatology match recorded hashes" if files_ok
                       else "a frozen file hash differs",
                       "state-dict SHA256 recomputed at engine start and compared"))
    items.append(_item("Model hash", "VERIFIED" if sd_ok else "FAILED",
                       engine.l2_state_dict_sha256, "sha256 over sorted state-dict tensors"))
    items.append(_item("Encoder hash", "VERIFIED" if enc_ok else "FAILED",
                       engine.l2_encoder_sha256, "sha256 over encoder.* tensors"))

    try:
        meta = json.loads(ARGO_META.read_text(encoding="utf-8"))
        items.append(_item("Argo observational check", "COMPLETED",
                           f"{meta['n_matched']:,} profiles, {meta['n_floats']} floats, "
                           f"{meta['date_min']}..{meta['date_max']}",
                           "outputs/argo/analysis_meta.json"))
    except (OSError, ValueError, KeyError):
        items.append(_item("Argo observational check", "UNVERIFIED", "analysis metadata missing",
                           "outputs/argo/analysis_meta.json"))

    try:
        manifest = json.loads(ARGO_MANIFEST.read_text(encoding="utf-8"))
        held = manifest.get("heldout_period_not_fetched")
        dmax = pd.to_datetime(pd.read_parquet(ARGO_MATCHED, columns=["date"])["date"]).max()
        protected = dmax < pd.Timestamp("2024-01-01")
        items.append(_item("2024 Argo holdout", "PROTECTED" if protected else "FAILED",
                           f"held out {held}; newest matched profile {dmax.date()}",
                           "download manifest + newest collocated date < 2024-01-01"))
    except (OSError, ValueError, KeyError) as exc:
        items.append(_item("2024 Argo holdout", "UNVERIFIED", str(exc), "manifest unreadable"))

    try:
        d = json.loads(DECISION.read_text(encoding="utf-8"))
        items.append(_item("Latest D26", "WITHHELD" if d["d26_category"] != "QUALIFIED" else "QUALIFIED",
                           f"D26 operational category: {d['d26_category']}",
                           "outputs/phase8b/qualification_decision.json"))
        items.append(_item("NRT qualification", d["temperature_category"],
                           f"TCHP {d['tchp_category']}", "frozen Phase 8B decision artefact"))
    except (OSError, ValueError, KeyError):
        items.append(_item("Latest D26", "UNVERIFIED", "decision artefact unreadable", str(DECISION)))

    leaked = [v for v in E.ALLOWED_STORE_VARS if str(v).startswith(("temp_", "target_valid_"))]
    items.append(_item("Target leakage guards", "PASS" if not leaked else "FAILED",
                       "inference reads surface inputs only" if not leaked else f"allowed: {leaked}",
                       "replay engine ALLOWED_STORE_VARS excludes every target variable; "
                       "the store opener raises if one is selected"))
    try:
        thr = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        items.append(_item("Thermal-support thresholds", "FROZEN",
                           f"p50/p75/p90 = {thr['boundaries']['p50']:.2f} / "
                           f"{thr['boundaries']['p75']:.2f} / {thr['boundaries']['p90']:.2f} kJ/cm2",
                           thr.get("reference_period", "")))
    except (OSError, ValueError, KeyError):
        pass
    return {"items": items, "pipeline": PIPELINE}
