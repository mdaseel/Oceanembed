"""Physical plausibility QA of reconstructed water columns (PREREGISTRATION §4).

There is deliberately no "temperature must decrease with depth" rule: real
inversions occur (for example under a low-salinity barrier layer). Profiles are
described, then compared against a reference on the same support.
"""
from __future__ import annotations

import numpy as np

INVERSION_TOL_C = 0.1
STRONG_INVERSION_C = 0.5
BANDS = {"0-50 m": (0, 50), "50-150 m": (50, 150), "150-300 m": (150, 300),
         "300-1000 m": (300, 1000)}
RULE = (f"inversion = warming with depth by more than {INVERSION_TOL_C} degC between "
        f"adjacent supported levels (strong: > {STRONG_INVERSION_C} degC); levels are used "
        "contiguously from the top only while finite and within the local water column; "
        "no monotonic-decrease rule is applied")


def usable_levels(temps: np.ndarray, depths, water_depth=None) -> np.ndarray:
    """Contiguous-from-top usable mask (..., L): finite and inside the water column."""
    t = np.asarray(temps, dtype="float64")
    ok = np.isfinite(t)
    if water_depth is not None:
        w = np.asarray(water_depth, dtype="float64")[..., None]
        ok &= np.isfinite(w) & (w >= np.asarray(depths, dtype="float64"))
    return np.cumprod(ok, axis=-1).astype(bool)


def profile_diagnostics(temps: np.ndarray, depths, usable: np.ndarray) -> dict:
    """Per-profile vertical diagnostics for arrays shaped (..., L)."""
    t = np.asarray(temps, dtype="float64")
    z = np.asarray(depths, dtype="float64")
    pair = usable[..., :-1] & usable[..., 1:]
    dT = np.diff(t, axis=-1)
    dz = np.diff(z)
    grad = np.where(pair, dT / dz, np.nan)
    inv = pair & (dT > INVERSION_TOL_C)
    strong = pair & (dT > STRONG_INVERSION_C)
    n_pairs = pair.sum(-1)
    with np.errstate(invalid="ignore"):
        g_masked = np.where(pair, grad, np.inf)
        k = np.argmin(g_masked, axis=-1)
        strongest = np.take_along_axis(grad, k[..., None], axis=-1)[..., 0]
        strongest = np.where(n_pairs > 0, strongest, np.nan)
        mid = (z[:-1] + z[1:]) / 2
        strongest_depth = np.where(n_pairs > 0, mid[k], np.nan)
        max_inv = np.where(inv.any(-1), np.where(inv, dT, -np.inf).max(-1), 0.0)
    return {"n_pairs": n_pairs, "pair_valid": pair, "gradient": grad,
            "inversion": inv, "strong_inversion": strong,
            "inversion_count": inv.sum(-1), "strong_count": strong.sum(-1),
            "max_inversion_c": np.where(n_pairs > 0, max_inv, np.nan),
            "strongest_gradient": strongest, "strongest_gradient_depth": strongest_depth}


def band_of_pair(depths) -> list[str | None]:
    z = np.asarray(depths, dtype="float64")
    out = []
    for a, b in zip(z[:-1], z[1:]):
        name = None
        for band, (lo, hi) in BANDS.items():
            if lo <= a and b <= hi:
                name = band
                break
        out.append(name)
    return out


def percentile_of(value: float, quantiles: list[float]) -> float | None:
    """Percentile position of ``value`` within a 101-point quantile table (p0..p100)."""
    if value is None or not np.isfinite(value) or not quantiles:
        return None
    q = np.asarray(quantiles, dtype="float64")
    return float(np.interp(value, q, np.linspace(0, 100, q.size)))


def single_profile(temps, depths, water_depth) -> dict:
    """Diagnostics for one reconstructed column, JSON-ready."""
    t = np.asarray(temps, dtype="float64")[None]
    use = usable_levels(t, depths, None if water_depth is None else np.array([water_depth]))
    d = profile_diagnostics(t, depths, use)
    grads = d["gradient"][0]
    pairs = [{"from_m": int(a), "to_m": int(b),
              "gradient_c_per_m": None if not np.isfinite(g) else round(float(g), 5),
              "delta_c": None if not np.isfinite(g) else round(float(g * (b - a)), 3),
              "inversion": bool(i)}
             for a, b, g, i in zip(depths[:-1], depths[1:], grads, d["inversion"][0])]
    n = int(d["n_pairs"][0])
    return {"n_supported_levels": int(use[0].sum()), "n_pairs": n,
            "inversion_count": int(d["inversion_count"][0]),
            "strong_inversion_count": int(d["strong_count"][0]),
            "max_inversion_c": None if n == 0 else round(float(d["max_inversion_c"][0]), 3),
            "strongest_gradient_c_per_m": None if n == 0 else round(float(d["strongest_gradient"][0]), 5),
            "strongest_gradient_depth_m": None if n == 0 else float(d["strongest_gradient_depth"][0]),
            "pairs": pairs, "rule": RULE}
