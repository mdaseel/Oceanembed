"""Phase 8B decision rules, transcribed from the frozen protocol.

``outputs/phase8b/NRT_SUBSURFACE_QUALIFICATION_PROTOCOL.md`` (commit 5b69dda)
fixes every rule here before any Phase 8B result existed. The stack verdict is
the Phase 6C-D section 4.4 rule, the skill gates are Phase 6C-A gates A and C,
the basin gate is Phase 6C-C criterion 4, and the D26/TCHP rule is the 6C-C
non-inferiority logic. Nothing in this module may be edited to suit a result.
"""
from __future__ import annotations

from .compatibility import SENS_BANDS

#: The categories the protocol allows (section 7). QUALIFIED is listed so that
#: it is visibly unreachable, not silently absent.
QUALIFIED = "QUALIFIED"
QUALIFIED_WITH_LIMITATIONS = "QUALIFIED WITH LIMITATIONS"
NOT_QUALIFIED = "NOT QUALIFIED"
BLOCKED = "BLOCKED — INSUFFICIENT EVIDENCE"

QUALIFIED_REACHABLE = False
QUALIFIED_UNREACHABLE_REASON = (
    "QUALIFIED requires an independent observational hindcast of the operational "
    "stack. The NRT products exist only from 2024, 2022-2023 Argo predates them, "
    "and 2024 Argo is protected, so no permitted data supports one.")

#: Section 4.1: at least half of the 56 pre-registered dates must assemble.
PREREGISTERED_DATES = 56
MIN_DATES = 28

SKILL_DEPTHS_0_200 = (0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200)
THERMOCLINE_DEPTHS = (75, 100, 125)
G3_MAJORITY = 6

STACK_VIABLE_RAW = "NRT_STACK_VIABLE_RAW"
STACK_VIABLE_WITH_MONITORING = "NRT_STACK_VIABLE_WITH_MONITORING"
STACK_NOT_VIABLE_RAW = "NRT_STACK_NOT_VIABLE_RAW"

CHANNEL_QUALIFYING = ("SUBSTITUTE_APPROVED", "SUBSTITUTE_WITH_MONITORING")


def _le(a: str, b: str) -> bool:
    return SENS_BANDS.index(a) <= SENS_BANDS.index(b)


def stack_verdict(band_100m: str, worst_band: str, coverage_loss: float) -> str:
    """Phase 6C-D section 4.4, exactly as executed in 6C-D."""
    if (band_100m in ("NEGLIGIBLE", "MINOR") and _le(worst_band, "MATERIAL")
            and coverage_loss < 0.05):
        return STACK_VIABLE_RAW
    if _le(band_100m, "MATERIAL") and worst_band != "SEVERE":
        return STACK_VIABLE_WITH_MONITORING
    return STACK_NOT_VIABLE_RAW


def gate_g1(sss_channel_decision: str) -> bool:
    return sss_channel_decision in CHANNEL_QUALIFYING


def gate_g2(verdict: str) -> bool:
    return verdict in (STACK_VIABLE_RAW, STACK_VIABLE_WITH_MONITORING)


def gate_g3(rmse_n: dict, rmse_l0: dict) -> tuple[bool, int]:
    """6C-A gate A: N beats L0 at a majority (>= 6) of the 11 depths 0-200 m."""
    wins = sum(1 for d in SKILL_DEPTHS_0_200 if rmse_n[d] < rmse_l0[d])
    return wins >= G3_MAJORITY, wins


def gate_g4(rmse_n: dict, rmse_l0: dict, ci_hi: dict) -> tuple[bool, dict]:
    """6C-A gate C: at 75/100/125 m N beats L0 and the 95 % CI of
    (RMSE_N - RMSE_L0) lies entirely below zero."""
    per = {d: bool(rmse_n[d] < rmse_l0[d] and ci_hi[d] < 0)
           for d in THERMOCLINE_DEPTHS}
    return all(per.values()), per


def gate_g5(rmse_n_as: float, rmse_l0_as: float,
            rmse_n_bob: float, rmse_l0_bob: float) -> bool:
    """6C-C criterion 4: at 100 m N beats L0 in BOTH basins."""
    return bool(rmse_n_as < rmse_l0_as and rmse_n_bob < rmse_l0_bob)


def temperature_category(n_dates: int, gates: dict[str, bool] | None) -> str:
    """Section 7. ``gates`` maps G1..G5 to pass/fail; None means not run."""
    if n_dates < MIN_DATES or gates is None:
        return BLOCKED
    if all(gates[g] for g in ("G1", "G2", "G3", "G4", "G5")):
        return QUALIFIED_WITH_LIMITATIONS
    return NOT_QUALIFIED


def is_qualified(category: str) -> bool:
    return category in (QUALIFIED, QUALIFIED_WITH_LIMITATIONS)


def non_inferior(ci_lo: float, ci_hi: float) -> bool:
    """Section 8: MAE(N) - MAE(R) interval contains zero or lies below it.

    Equivalently: the operational mode is not detectably WORSE than the
    reference-input historical replay. Only the upper bound matters.
    """
    return bool(ci_hi <= 0 or ci_lo <= 0 <= ci_hi)
