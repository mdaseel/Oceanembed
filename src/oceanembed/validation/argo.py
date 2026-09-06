"""Argo profile QC, TEOS-10 conversion and vertical interpolation.

Three things here decide whether the observational audit is meaningful:

1. QC AND DATA_MODE. Argo distributes real-time (R), adjusted (A) and
   delayed-mode (D) data. For A/D profiles the *_ADJUSTED fields carry the
   calibrated values and *_ADJUSTED_QC the corresponding flags; for R profiles
   only the raw fields exist. Using raw values on a delayed-mode profile throws
   away the calibration, and using ADJUSTED where it was never filled yields
   NaN. The rule is applied per profile, not globally.

2. TEMPERATURE QUANTITY. OceanEmbed's target is GLORYS ``thetao``, whose
   standard_name is sea_water_potential_temperature. Argo TEMP is IN-SITU
   temperature. Comparing them directly would introduce a depth-dependent bias
   of order 0.08 degC at 1000 dbar - comparable to the model differences being
   measured. Observations are therefore converted to potential temperature
   referenced to 0 dbar via TEOS-10 (gsw), which requires salinity; profiles
   without usable salinity cannot be converted and are rejected rather than
   having salinity invented.

3. NO EXTRAPOLATION. A target depth is only produced when it is genuinely
   bracketed by two accepted observations. Nothing is extended above the
   shallowest or below the deepest accepted sample, and nothing is invented
   below the profile.
"""
from __future__ import annotations

import numpy as np

# Argo reference table 2: 1 good, 2 probably good, 3 probably bad, 4 bad,
# 5 changed, 8 interpolated, 9 missing.
GOOD_QC = {b"1", b"2"}
# Position flag 8 means an interpolated location, which is not good enough for
# collocating against a 0.25 deg grid, so it is excluded.
GOOD_POSITION_QC = {b"1", b"2"}
GOOD_JULD_QC = {b"1", b"2"}

MIN_PRES_DBAR = 0.0
MAX_PRES_DBAR = 2100.0        # audit only needs the top 1000 m
PLAUSIBLE_TEMP = (-2.5, 40.0)
PLAUSIBLE_PSAL = (2.0, 42.0)


def _qc_bytes(arr) -> np.ndarray:
    """Normalise an Argo QC array to one byte flag per level.

    Real GDAC files deliver these as numpy OBJECT arrays of single bytes
    (b"1", b"4", b" "), but some readers hand back a fixed-width string, one
    packed string covering every level, or a numeric array. All four shapes are
    normalised here; anything unrecognised becomes b"9" (missing) so that it
    fails the good-QC test rather than silently passing.
    """
    a = np.asarray(arr).reshape(-1)
    out: list[bytes] = []
    for x in a:
        if isinstance(x, bytes):
            s = x.decode("utf-8", "ignore")
        elif isinstance(x, str):
            s = x
        elif x is None:
            s = "9"
        else:
            try:
                s = "9" if not np.isfinite(float(x)) else str(int(x))
            except (TypeError, ValueError):
                s = "9"
        s = s.strip()
        if len(s) > 1:                 # one packed string covering all levels
            out.extend(c.encode() if c.strip() else b"9" for c in s)
        else:
            out.append(s.encode() if s else b"9")
    return np.array(out)


def _s(x) -> str:
    if isinstance(x, bytes):
        return x.decode("utf-8", "ignore").strip()
    return str(x).strip()


def select_fields(ds, i: int) -> dict:
    """Choose raw vs adjusted fields for profile ``i`` according to DATA_MODE.

    Returns the chosen arrays plus a record of which convention was used, so
    the choice is auditable rather than implicit.
    """
    mode = _s(ds["DATA_MODE"].values[i])
    use_adjusted = mode in ("A", "D")
    out = {"data_mode": mode, "used_adjusted": use_adjusted}
    for var in ("PRES", "TEMP", "PSAL"):
        adj = f"{var}_ADJUSTED"
        if use_adjusted and adj in ds:
            val = np.asarray(ds[adj].values[i], dtype="float64")
            qc = _qc_bytes(ds[f"{adj}_QC"].values[i]) if f"{adj}_QC" in ds else None
            # A profile flagged A/D whose ADJUSTED field was never populated is
            # rejected downstream rather than silently falling back to raw.
            out[var] = val
            out[f"{var}_qc"] = qc
            out[f"{var}_source"] = adj
        elif var in ds:
            out[var] = np.asarray(ds[var].values[i], dtype="float64")
            out[f"{var}_qc"] = _qc_bytes(ds[f"{var}_QC"].values[i]) if f"{var}_QC" in ds else None
            out[f"{var}_source"] = var
        else:
            out[var] = None
            out[f"{var}_qc"] = None
            out[f"{var}_source"] = None
    return out


def profile_is_acceptable(ds, i: int) -> tuple[bool, str]:
    """Profile-level gates applied before any level is considered."""
    pq = _qc_bytes(ds["POSITION_QC"].values[i])
    if pq.size and pq[0] not in GOOD_POSITION_QC:
        return False, f"position_qc={pq[0].decode()}"
    jq = _qc_bytes(ds["JULD_QC"].values[i])
    if jq.size and jq[0] not in GOOD_JULD_QC:
        return False, f"juld_qc={jq[0].decode()}"
    lat = float(ds["LATITUDE"].values[i])
    lon = float(ds["LONGITUDE"].values[i])
    if not (np.isfinite(lat) and np.isfinite(lon)):
        return False, "position_missing"
    return True, "ok"


def accepted_levels(f: dict) -> np.ndarray:
    """Boolean mask of levels passing QC and plausibility for P, T and S."""
    pres, temp, psal = f["PRES"], f["TEMP"], f["PSAL"]
    if pres is None or temp is None or psal is None:
        return np.zeros(0, dtype=bool)
    n = min(len(pres), len(temp), len(psal))
    ok = np.ones(n, dtype=bool)
    for var, lo, hi in (("PRES", MIN_PRES_DBAR, MAX_PRES_DBAR),
                        ("TEMP", *PLAUSIBLE_TEMP),
                        ("PSAL", *PLAUSIBLE_PSAL)):
        v = np.asarray(f[var][:n], dtype="float64")
        ok &= np.isfinite(v) & (v >= lo) & (v <= hi)
        qc = f[f"{var}_qc"]
        if qc is not None and len(qc) >= n:
            ok &= np.isin(qc[:n], list(GOOD_QC))
    return ok


def to_potential_temperature(pres, temp, psal, lon, lat):
    """In-situ TEMP -> potential temperature at 0 dbar, and depth in metres.

    Uses TEOS-10 (gsw): practical salinity -> Absolute Salinity, then
    pt0_from_t. Depth comes from gsw.z_from_p, which accounts for latitude,
    rather than the 1 dbar ~ 1 m approximation.
    """
    import gsw
    pres = np.asarray(pres, dtype="float64")
    temp = np.asarray(temp, dtype="float64")
    psal = np.asarray(psal, dtype="float64")
    lon_a = np.full(pres.shape, float(lon))
    lat_a = np.full(pres.shape, float(lat))
    SA = gsw.SA_from_SP(psal, pres, lon_a, lat_a)
    pt0 = gsw.pt0_from_t(SA, temp, pres)
    depth = -gsw.z_from_p(pres, lat_a)
    return pt0, depth


def interp_to_depths(depth: np.ndarray, value: np.ndarray, targets,
                     max_gap_m: float = 100.0):
    """Linear interpolation onto target depths with NO extrapolation.

    A target is returned only when it lies strictly between two accepted
    samples whose separation is at most ``max_gap_m``. Targets shallower than
    the first sample or deeper than the last are NaN - in particular the
    nominal 0 m level, which Argo essentially never observes.

    Returns (values, supported_mask, gap_used).
    """
    targets = np.asarray(targets, dtype="float64")
    out = np.full(targets.shape, np.nan)
    sup = np.zeros(targets.shape, dtype=bool)
    gap = np.full(targets.shape, np.nan)

    order = np.argsort(depth)
    d, v = depth[order], value[order]
    keep = np.isfinite(d) & np.isfinite(v)
    d, v = d[keep], v[keep]
    if d.size < 2:
        return out, sup, gap
    # collapse duplicate depths
    uniq, idx = np.unique(d, return_index=True)
    d, v = uniq, v[idx]

    for k, td in enumerate(targets):
        if td < d[0] or td > d[-1]:
            continue                       # no extrapolation, ever
        j = int(np.searchsorted(d, td))
        if d[j] == td:
            out[k], sup[k], gap[k] = v[j], True, 0.0
            continue
        lo, hi = j - 1, j
        if lo < 0 or hi >= d.size:
            continue
        g = d[hi] - d[lo]
        if g > max_gap_m:
            continue                       # vertical support too sparse
        w = (td - d[lo]) / g
        out[k] = v[lo] * (1.0 - w) + v[hi] * w
        sup[k] = True
        gap[k] = g
    return out, sup, gap
