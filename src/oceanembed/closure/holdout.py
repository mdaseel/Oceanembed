"""Hard guard for the protected 2024 Argo observational holdout.

The 2024 Argo year was never downloaded (`outputs/argo/download_manifest.json`
records `heldout_period_not_fetched: [2024-01-01, 2024-12-15]`). A test asserts
that, but a test only fires when someone runs it. This module refuses at call
time, so a closure experiment cannot quietly widen an Argo window.

The guard is about the ARGO holdout specifically. Gridded 2024 GLORYS inputs
belong to the locked grid test split, which is governed separately by
``oceanembed.ml.splits`` and is likewise not used for any decision in this study.
"""
from __future__ import annotations

import pandas as pd

HOLDOUT_START = pd.Timestamp("2024-01-01")
HOLDOUT_END = pd.Timestamp("2024-12-15")
DEV_ARGO_START = pd.Timestamp("2022-01-01")
DEV_ARGO_END = pd.Timestamp("2023-12-31")


class HoldoutViolation(PermissionError):
    """Raised when something tries to reach into the protected 2024 Argo year."""


def assert_no_2024_argo(times, what: str = "argo") -> None:
    """Refuse any timestamp inside the protected window."""
    t = pd.DatetimeIndex(pd.Series(times).dropna()) if not isinstance(
        times, pd.DatetimeIndex) else times
    if len(t) == 0:
        return
    hit = (t >= HOLDOUT_START) & (t <= HOLDOUT_END)
    if hit.any():
        raise HoldoutViolation(
            f"{what}: {int(hit.sum())} timestamp(s) fall inside the protected "
            f"2024 Argo holdout {HOLDOUT_START.date()}..{HOLDOUT_END.date()}; "
            f"first offender {t[hit][0]}. This study must not open it.")


def assert_argo_is_development_window(frame, column: str = "date") -> None:
    """The Argo confirmation set must be exactly the already-inspected years."""
    t = pd.DatetimeIndex(frame[column])
    assert_no_2024_argo(t, what="argo confirmation set")
    if t.min() < DEV_ARGO_START or t.max() > DEV_ARGO_END:
        raise HoldoutViolation(
            f"argo confirmation set spans {t.min().date()}..{t.max().date()}, "
            f"outside the declared development window "
            f"{DEV_ARGO_START.date()}..{DEV_ARGO_END.date()}")
