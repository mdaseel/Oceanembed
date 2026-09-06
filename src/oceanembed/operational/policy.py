"""Explicit allow-list of experimentally supported input situations.

There is deliberately NO generic fallback. A situation is supported only if it
was actually tested, and the registry records which phase produced that
evidence. Anything else raises ``UnsupportedInputMode`` and no inference runs -
the alternative would be extrapolating a fallback to a channel nobody has ever
measured the model's sensitivity to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class PolicyState(str, Enum):
    REFERENCE_COMPLETE = "REFERENCE_COMPLETE"
    DEV_SUPPORTED_FALLBACK = "DEV_SUPPORTED_FALLBACK"
    OBS_SUPPORTED_FALLBACK = "OBS_SUPPORTED_FALLBACK"
    UNSUPPORTED_INPUT_MODE = "UNSUPPORTED_INPUT_MODE"
    NO_USABLE_INPUT = "NO_USABLE_INPUT"


class UnsupportedInputMode(Exception):
    """Raised when a declared input situation is outside the tested allow-list."""


class NoUsableInput(Exception):
    """Raised when a supported policy cannot actually be satisfied."""


FILL_PERSIST = "PERSIST_LAST_OBSERVED"
FILL_TRAIN_CLIM = "TRAIN_CHANNEL_CLIMATOLOGY"

# Channels that move as a vector pair and must always share an age.
VECTOR_PAIRS = (("current_u", "current_v"), ("wind_u", "wind_v"))


@dataclass(frozen=True)
class Policy:
    name: str
    absent: frozenset = frozenset()
    stale: Mapping[str, int] = field(default_factory=dict)
    fill: str | None = None
    state: PolicyState = PolicyState.DEV_SUPPORTED_FALLBACK
    evidence: str = ""
    max_persist_days: int = 7

    def signature(self) -> tuple:
        return (tuple(sorted(self.absent)),
                tuple(sorted((k, int(v)) for k, v in self.stale.items() if v)))


_P = [
    Policy("REFERENCE_COMPLETE", state=PolicyState.REFERENCE_COMPLETE,
           evidence="original inputs through the unmodified legacy path"),

    Policy("SSS_ABSENT_PERSIST", absent=frozenset({"sss"}), fill=FILL_PERSIST,
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B: 1.2254 vs 1.2255 degC at 100 m on GLORYS/2021. "
                    "6C-C Argo: -0.0007 degC vs COMPLETE at 100 m, CI spans "
                    "zero at all six key depths, bias change <0.001 degC"),
    Policy("SSS_ABSENT_CLIM", absent=frozenset({"sss"}), fill=FILL_TRAIN_CLIM,
           evidence="6C-B: 1.2243 vs 1.2255 degC at 100 m on GLORYS/2021 - i.e. "
                    "marginally BETTER in development. NOT promoted: 6C-C Argo "
                    "shows +4.46% at 100 m, significant at 6/6 key depths, and "
                    "worsens the thermocline warm bias by +0.060 degC"),

    Policy("CURRENT_STALE_1D", stale={"current_u": 1, "current_v": 1},
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B -0.07%; 6C-C Argo +0.19% at 100 m, CI spans zero 6/6"),
    Policy("CURRENT_STALE_2D", stale={"current_u": 2, "current_v": 2},
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B +0.02%; 6C-C Argo +0.37% at 100 m, CI spans zero 6/6"),
    Policy("CURRENT_STALE_3D", stale={"current_u": 3, "current_v": 3},
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B +0.26%; 6C-C Argo +0.68% at 100 m, detectable at 2/6 depths - the weakest promoted policy"),

    Policy("WIND_STALE_1D", stale={"wind_u": 1, "wind_v": 1},
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B +0.02%; 6C-C Argo -0.04% at 100 m, CI spans zero 6/6"),
    Policy("SLA_STALE_1D", stale={"sla": 1},
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B -0.11%; 6C-C Argo -0.23% at 100 m, never worse than COMPLETE"),

    Policy("SSS_ABSENT_PERSIST_CURRENT_STALE_2D", absent=frozenset({"sss"}),
           stale={"current_u": 2, "current_v": 2}, fill=FILL_PERSIST,
           state=PolicyState.OBS_SUPPORTED_FALLBACK,
           evidence="6C-B mode I; 6C-C Argo +0.31% at 100 m, CI spans zero 6/6"),
]

POLICY_REGISTRY = {p.name: p for p in _P}
_BY_SIGNATURE: dict[tuple, list[Policy]] = {}
for _p in _P:
    _BY_SIGNATURE.setdefault(_p.signature(), []).append(_p)


def lookup_policy(absent, stale, prefer_fill: str | None = None) -> Policy:
    """Resolve a declared situation to a registered policy, or refuse.

    ``absent`` and ``stale`` describe what the operator says is wrong. Nothing
    is inferred: an unlisted channel outage, an unlisted staleness, or any
    combination that was never tested raises UnsupportedInputMode.
    """
    absent = frozenset(absent or ())
    stale = {k: int(v) for k, v in (stale or {}).items() if int(v) > 0}

    for a, b in VECTOR_PAIRS:
        if stale.get(a, 0) != stale.get(b, 0):
            raise UnsupportedInputMode(
                f"{a} and {b} form a vector pair and must share an age; "
                f"got {stale.get(a, 0)} and {stale.get(b, 0)}")
        if (a in absent) != (b in absent):
            raise UnsupportedInputMode(f"{a} and {b} must be absent together")

    sig = (tuple(sorted(absent)), tuple(sorted(stale.items())))
    cands = _BY_SIGNATURE.get(sig)
    if not cands:
        raise UnsupportedInputMode(
            f"UNSUPPORTED_INPUT_MODE: absent={sorted(absent)} stale={dict(sorted(stale.items()))} "
            "is not in the tested allow-list; no inference will be run")
    if prefer_fill is not None:
        for c in cands:
            if c.fill == prefer_fill:
                return c
        raise UnsupportedInputMode(
            f"fill={prefer_fill} is not registered for absent={sorted(absent)}")
    return cands[0]
