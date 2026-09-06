"""Input-availability and latency stress harness for the FROZEN L2 model.

Nothing here trains, fine-tunes or modifies a model. It only builds degraded
input fields and runs the existing frozen inference path.

The central architectural fact this harness exists to expose: ``day_field``
computes ONE joint validity mask, ``isfinite(all seven channels)``. There is no
per-channel mask. So if a single channel is unavailable everywhere, the joint
mask is False everywhere, every channel is zeroed, and the CNN receives a blank
field. Two mask policies are therefore provided:

  ``joint``      - the literal current behaviour, retained so the failure can be
                   quantified rather than assumed.
  ``available``  - validity computed from the channels that ARE present, which
                   is what an operator would do. This is the only setting under
                   which different imputation policies can be compared at all,
                   and it is still outside what L2 was trained to see.

TIME SEMANTICS. A channel with age k reads index t-k and nothing else. There is
no nearest-time search, so a future value can never be selected; this is
asserted in the tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

import numpy as np
import xarray as xr

from .features import SURFACE
from .patches import N_CHANNELS, N_DATA_CHANNELS

CH = {name: i for i, name in enumerate(SURFACE)}
CURRENT_CHANNELS = ("current_u", "current_v")
WIND_CHANNELS = ("wind_u", "wind_v")


@dataclass(frozen=True)
class Mode:
    """One pre-registered failure mode."""
    name: str
    age: dict = dc_field(default_factory=dict)              # channel -> days old
    missing: tuple = ()                                     # wholly unavailable
    policy: str = "zero_standardised"                       # imputation policy
    mask_policy: str = "available"                          # 'available' | 'joint'
    description: str = ""

    @property
    def max_age(self) -> int:
        return max([0, *self.age.values()])


# ------------------------------------------------------------- pre-registered
MODES = [
    Mode("A_COMPLETE", description="all seven inputs, same day"),
    Mode("B_SSS_MISSING", missing=("sss",),
         description="entire SSS channel unavailable"),
    Mode("C_SSS_SPATIAL_GAPS", missing=(),
         description="coherent SSS gaps (mask applied separately)"),
    Mode("D_CURRENT_STALE_1D", age={"current_u": 1, "current_v": 1},
         description="surface currents from t-1"),
    Mode("E_CURRENT_STALE_2D", age={"current_u": 2, "current_v": 2},
         description="surface currents from t-2"),
    Mode("F_CURRENT_STALE_3D", age={"current_u": 3, "current_v": 3},
         description="surface currents from t-3"),
    Mode("G_WIND_STALE_1D", age={"wind_u": 1, "wind_v": 1},
         description="10 m winds from t-1"),
    Mode("H_SLA_STALE_1D", age={"sla": 1}, description="sea level anomaly from t-1"),
    Mode("I_SSS_MISSING_CURRENT_STALE_2D", missing=("sss",),
         age={"current_u": 2, "current_v": 2},
         description="combined SSS outage and 2-day-old currents"),
    Mode("J_SSS_MISSING_JOINT_MASK", missing=("sss",), mask_policy="joint",
         description="SSS outage handled by the UNMODIFIED joint-mask path"),
]
MODES_BY_NAME = {m.name: m for m in MODES}

POLICIES = ("zero_standardised", "persistence", "channel_climatology")


def coherent_sss_gap_mask(nlat: int, nlon: int, day: int, frac: float = 0.35,
                          seed: int = 20260905) -> np.ndarray:
    """Coherent (not per-pixel) synthetic SSS gaps.

    Explicitly labelled synthetic: no historical SMAP swath-gap masks are held
    locally for the evaluation period. Independent random pixels would be far
    easier for a 33x33 convolution to interpolate around than real coverage
    holes, so gaps are built as a few large blobs whose position rotates with
    the day, giving spatially coherent outages of roughly ``frac`` of the grid.
    """
    rng = np.random.default_rng(seed + day)
    yy, xx = np.mgrid[0:nlat, 0:nlon]
    keep = np.ones((nlat, nlon), dtype=bool)
    target = frac * nlat * nlon
    covered = 0.0
    while covered < target:
        cy, cx = rng.uniform(0, nlat), rng.uniform(0, nlon)
        ry = rng.uniform(nlat * 0.12, nlat * 0.30)
        rx = rng.uniform(nlon * 0.10, nlon * 0.26)
        blob = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
        new = blob & keep
        covered += new.sum()
        keep &= ~blob
    return keep          # True where SSS is still observed


def build_field(ds: xr.Dataset, t: int, scaler, patch: int, mode: Mode,
                policy: str | None = None,
                surface_clim=None, sss_keep: np.ndarray | None = None) -> np.ndarray:
    """Degraded analogue of ``patches.day_field`` for one target day.

    Returns the same (8, nlat+2h, nlon+2h) array the frozen encoder expects.
    """
    policy = policy or mode.policy
    half = patch // 2
    nlat, nlon = ds.sizes["lat"], ds.sizes["lon"]

    raw = np.empty((N_DATA_CHANNELS, nlat, nlon), dtype="float64")
    for k, v in enumerate(SURFACE):
        age = int(mode.age.get(v, 0))
        src = t - age
        # A channel of age k reads exactly index t-k. No nearest-time search,
        # so t+1 can never be reached.
        assert 0 <= src <= t, f"channel {v} would read index {src} for target {t}"
        raw[k] = ds[v].isel(time=src).values

    present = np.ones((N_DATA_CHANNELS, nlat, nlon), dtype=bool)
    for k, v in enumerate(SURFACE):
        present[k] = np.isfinite(raw[k])

    # ---- whole-channel outage
    for v in mode.missing:
        k = CH[v]
        present[k] = False

    # ---- coherent spatial gaps (mode C)
    if sss_keep is not None:
        k = CH["sss"]
        present[k] &= sss_keep

    # ---- imputation of unavailable values, all train-only information
    filled = raw.copy()
    for k, v in enumerate(SURFACE):
        bad = ~present[k]
        if not bad.any():
            continue
        if policy == "zero_standardised":
            filled[k][bad] = scaler.mean[k]           # 0 in standardised space
        elif policy == "persistence":
            got = np.full((nlat, nlon), np.nan)
            for back in range(1, 8):                  # carry forward, never forward in time
                src = t - int(mode.age.get(v, 0)) - back
                if src < 0:
                    break
                cand = ds[v].isel(time=src).values
                take = bad & np.isnan(got) & np.isfinite(cand)
                got[take] = cand[take]
                if not (bad & np.isnan(got)).any():
                    break
            still = bad & ~np.isfinite(got)
            filled[k][bad & np.isfinite(got)] = got[bad & np.isfinite(got)]
            filled[k][still] = scaler.mean[k]         # fall back to the train mean
        elif policy == "channel_climatology":
            if surface_clim is None:
                raise ValueError("channel_climatology needs a fitted surface climatology")
            cl = surface_clim.predict_channel(v, ds.time.values[t])
            ok = bad & np.isfinite(cl)
            filled[k][ok] = cl[ok]
            filled[k][bad & ~np.isfinite(cl)] = scaler.mean[k]
        else:
            raise ValueError(policy)

    # ---- validity mask
    if mode.mask_policy == "joint":
        # literal frozen behaviour: one mask over all seven channels
        valid = present.all(axis=0)
        filled = np.where(valid[None, :, :], filled, np.nan)
    elif mode.mask_policy == "available":
        # validity from the channels that are actually present
        avail = [k for k, v in enumerate(SURFACE)
                 if v not in mode.missing and not (sss_keep is not None and v == "sss")]
        if not avail:
            valid = np.zeros((nlat, nlon), dtype=bool)
        else:
            valid = present[avail].all(axis=0)
    else:
        raise ValueError(mode.mask_policy)

    z = (filled.reshape(N_DATA_CHANNELS, -1).T - scaler.mean[:N_DATA_CHANNELS]) \
        / scaler.std[:N_DATA_CHANNELS]
    z = z.T.reshape(N_DATA_CHANNELS, nlat, nlon)
    z = np.where(np.isfinite(z), z, 0.0)
    z = np.where(valid[None, :, :], z, 0.0).astype("float32")

    out = np.zeros((N_CHANNELS, nlat + 2 * half, nlon + 2 * half), dtype="float32")
    out[:N_DATA_CHANNELS, half:half + nlat, half:half + nlon] = z
    out[N_DATA_CHANNELS, half:half + nlat, half:half + nlon] = valid.astype("float32")
    assert np.isfinite(out).all(), "no NaN may reach the CNN"
    return out
