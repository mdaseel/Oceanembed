"""Per-channel provenance, age semantics, and the reconstruction manifest.

The age rule that matters: AGE FOLLOWS THE ORIGINAL OBSERVATION. If day t-1's
stored SSS was itself persisted from t-3, then using it at day t gives an age of
THREE days, not one. A store that reset the age each day would make an
arbitrarily stale field look fresh, so ``PersistenceStore`` carries the original
observation time forward untouched.

A climatological replacement is not an observation at all, so it carries a null
source_valid_time and a null age, plus the training period it came from.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

REPLAY_RETROSPECTIVE = "RETROSPECTIVE"
REPLAY_AS_ISSUED = "AS_ISSUED"


@dataclass
class ChannelProvenance:
    channel: str
    requested_valid_time: str
    source_valid_time: str | None            # null for climatology
    original_observation_time: str | None    # follows persistence chains
    age_days: float | None                   # null for climatology
    fallback_policy: str | None
    source_product: str | None = None
    source_available_time: str | None = None
    source_revision: str | None = None
    training_period: str | None = None       # only for climatology
    note: str = ""

    @staticmethod
    def observed(channel, requested, source_product=None, available_time=None,
                 revision=None) -> "ChannelProvenance":
        ts = pd.Timestamp(requested)
        return ChannelProvenance(
            channel=channel, requested_valid_time=str(ts),
            source_valid_time=str(ts), original_observation_time=str(ts),
            age_days=0.0, fallback_policy=None, source_product=source_product,
            source_available_time=(None if available_time is None
                                   else str(pd.Timestamp(available_time))),
            source_revision=revision,
            note="observed at the requested valid time")

    @staticmethod
    def persisted(channel, requested, source_valid, original_obs, policy,
                  source_product=None, available_time=None,
                  revision=None) -> "ChannelProvenance":
        req = pd.Timestamp(requested)
        orig = pd.Timestamp(original_obs)
        return ChannelProvenance(
            channel=channel, requested_valid_time=str(req),
            source_valid_time=str(pd.Timestamp(source_valid)),
            original_observation_time=str(orig),
            age_days=float((req - orig).total_seconds() / 86400.0),
            fallback_policy=policy, source_product=source_product,
            source_available_time=(None if available_time is None
                                   else str(pd.Timestamp(available_time))),
            source_revision=revision,
            note="age measured from the ORIGINAL observation, not the store date")

    @staticmethod
    def climatology(channel, requested, policy, training_period) -> "ChannelProvenance":
        return ChannelProvenance(
            channel=channel, requested_valid_time=str(pd.Timestamp(requested)),
            source_valid_time=None, original_observation_time=None,
            age_days=None, fallback_policy=policy,
            source_product="train-only channel climatology",
            training_period=training_period,
            note="climatology is not an observation; it has no valid time or age")


@dataclass
class ReconstructionManifest:
    reconstruction_issue_time: str
    requested_valid_time: str
    replay_mode: str
    policy_name: str
    policy_state: str
    policy_evidence: str
    channels: list = field(default_factory=list)
    model: dict = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["channels"] = [c if isinstance(c, dict) else asdict(c) for c in self.channels]
        return d

    def to_json(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        json.dump(self.as_dict(), open(p, "w"), indent=2)

    @property
    def max_age_days(self) -> float:
        ages = [(c["age_days"] if isinstance(c, dict) else c.age_days)
                for c in self.channels]
        ages = [a for a in ages if a is not None]
        return max(ages) if ages else 0.0


class PersistenceStore:
    """Last-known-good field per channel, carrying its ORIGINAL observation time.

    ``push`` records a genuine observation. ``carry_forward`` copies a field to a
    new store date WITHOUT touching its original observation time, so repeated
    persistence accumulates age rather than resetting it.
    """

    def __init__(self, max_age_days: int = 7):
        self._store: dict[str, tuple] = {}
        self.max_age_days = int(max_age_days)

    def push(self, channel, valid_time, array, source_product=None, revision=None) -> None:
        ts = pd.Timestamp(valid_time)
        self._store[channel] = (array, ts, ts, source_product, revision)

    def carry_forward(self, channel, new_store_time) -> None:
        if channel not in self._store:
            return
        arr, _store_t, orig, prod, rev = self._store[channel]
        self._store[channel] = (arr, pd.Timestamp(new_store_time), orig, prod, rev)

    def get(self, channel, requested):
        if channel not in self._store:
            return None
        arr, store_t, orig, prod, rev = self._store[channel]
        age = (pd.Timestamp(requested) - orig).total_seconds() / 86400.0
        if age < 0:
            return None                      # never serve a future field
        if age > self.max_age_days:
            return None                      # beyond the configured range
        return {"array": arr, "source_valid_time": store_t,
                "original_observation_time": orig, "age_days": float(age),
                "source_product": prod, "source_revision": rev}

    def has(self, channel: str) -> bool:
        return channel in self._store
