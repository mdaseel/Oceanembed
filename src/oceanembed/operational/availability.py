"""Declaration of what an operator says is available for a target valid time."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .policy import VECTOR_PAIRS, UnsupportedInputMode


@dataclass(frozen=True)
class ChannelAvailability:
    channel: str
    absent: bool = False
    age_days: int = 0
    source_product: str | None = None
    source_available_time: str | None = None
    source_revision: str | None = None

    def __post_init__(self):
        if self.age_days < 0:
            raise UnsupportedInputMode(
                f"{self.channel}: a negative age would mean using a future source")


@dataclass
class InputDeclaration:
    """What is available, for which valid time, as of which issue time."""
    requested_valid_time: str
    channels: dict = field(default_factory=dict)
    reconstruction_issue_time: str | None = None
    replay_mode: str = "RETROSPECTIVE"

    def declare(self, channel: str, **kw) -> "InputDeclaration":
        self.channels[channel] = ChannelAvailability(channel=channel, **kw)
        return self

    @property
    def absent(self) -> set:
        return {c for c, a in self.channels.items() if a.absent}

    @property
    def stale(self) -> dict:
        return {c: a.age_days for c, a in self.channels.items()
                if a.age_days > 0 and not a.absent}

    def check_issue_time(self) -> None:
        """A source may not be used before it was actually available."""
        if self.reconstruction_issue_time is None:
            return
        issue = pd.Timestamp(self.reconstruction_issue_time)
        for c, a in self.channels.items():
            if a.source_available_time is None:
                continue
            if pd.Timestamp(a.source_available_time) > issue:
                raise UnsupportedInputMode(
                    f"{c}: source became available at {a.source_available_time}, "
                    f"after the declared issue time {self.reconstruction_issue_time}")

    def check_vector_pairs(self) -> None:
        for a, b in VECTOR_PAIRS:
            aa, bb = self.channels.get(a), self.channels.get(b)
            if aa is None and bb is None:
                continue
            ka = (aa.absent, aa.age_days) if aa else (False, 0)
            kb = (bb.absent, bb.age_days) if bb else (False, 0)
            if ka != kb:
                raise UnsupportedInputMode(
                    f"{a} and {b} form a vector pair and must share availability; "
                    f"got {ka} and {kb}")

    def validate(self) -> None:
        self.check_vector_pairs()
        self.check_issue_time()
