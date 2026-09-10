"""D26 and TCHP, exactly as pre-registered.

Convention and constants are frozen by
``outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md``, written before any value was
computed. Nothing here may be tuned to improve agreement between a
reconstruction and a reference.

    D26  = depth of the SHALLOWEST downward 26 degC crossing, by linear
           interpolation between two adjacent valid levels. Never extrapolated.
    TCHP = rho0 * cp0 * integral from 0 to D26 of (T(z) - 26) dz.

Both are vectorised over any leading shape, so one call handles a single
profile ``(15,)`` or a whole field ``(101, 241, 36)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

#: The isotherm that defines both diagnostics.
TEMPERATURE_THRESHOLD_C = 26.0

#: TEOS-10 (IOC/SCOR/IAPSO 2010) reference isobaric heat capacity, J/(kg K).
#: A *defined* constant of the standard, not a fitted or regional value:
#: TEOS-10 defines Conservative Temperature by h0 = CP0 * CT, so
#: ``gsw.enthalpy(SA, CT, 0) / CT`` returns it for every SA and CT.
#: ``verify_constants`` re-derives it; a unit test pins that.
CP0 = 3991.86795711963

#: Reference density, kg/m3 = gsw.rho(SA=SSO, CT=26 degC, p=0 dbar), where
#: SSO = 35.16504 g/kg is the TEOS-10 Standard Ocean Reference Salinity and
#: 26 degC is the threshold that defines the diagnostic itself. Both inputs are
#: fixed by the standard and by D26's own definition; neither is tuned.
RHO0 = 1023.035344728

#: Volumetric heat capacity, J/(m3 K). Published TCHP conventions span about
#: 8% around this value (see the protocol); the offset is a convention
#: difference, never a skill difference.
RHO_CP = RHO0 * CP0

#: J/m2 -> kJ/cm2. 1 J/m2 = 1e-3 kJ / 1e4 cm2 = 1e-7 kJ/cm2.
J_PER_M2_TO_KJ_PER_CM2 = 1e-7


class D26Status(IntEnum):
    """Why a cell has, or has not, a defined D26. Never inferred from a mask."""

    OK = 0
    #: Shallowest valid level is already below 26 degC. D26 does not exist, but
    #: TCHP is exactly 0: there is no water warmer than 26 degC.
    SURFACE_BELOW_26 = 1
    #: Still at or above 26 degC at the deepest valid level. Extrapolating a
    #: crossing into unmeasured water is forbidden, so both are undefined.
    NO_CROSSING_IN_SUPPORT = 2
    #: Top level invalid, or a gap ended usable support before any crossing.
    INSUFFICIENT_SUPPORT = 3
    #: No finite temperature anywhere in the column.
    NO_VALID_LEVELS = 4


@dataclass(frozen=True)
class ThermalResult:
    """D26 in metres, TCHP in kJ/cm2, and the status that explains each cell.

    ``d26`` and ``tchp`` are NaN wherever the corresponding status says the
    quantity does not exist. A NaN here always means "undefined", never zero.
    """

    d26: np.ndarray
    tchp: np.ndarray
    status: np.ndarray

    def counts(self) -> dict[str, int]:
        return {s.name: int((self.status == s).sum()) for s in D26Status}

    @property
    def d26_defined(self) -> np.ndarray:
        return self.status == D26Status.OK

    @property
    def tchp_defined(self) -> np.ndarray:
        """TCHP also exists where the whole column is below 26 degC (TCHP = 0)."""
        return (self.status == D26Status.OK) | \
               (self.status == D26Status.SURFACE_BELOW_26)


def d26_tchp(temperature, depths) -> ThermalResult:
    """Compute D26 and TCHP for profiles of shape ``(..., n_levels)``.

    ``depths`` must be strictly increasing. Levels are used only while they are
    valid from the top down: a NaN ends the usable support rather than being
    bridged, because bridging a gap to reach a deeper crossing would be
    extrapolation through unmeasured water.
    """
    t = np.asarray(temperature, dtype="float64")
    z = np.asarray(depths, dtype="float64")
    if z.ndim != 1:
        raise ValueError("depths must be one-dimensional")
    if t.shape[-1] != z.size:
        raise ValueError(
            f"profile length {t.shape[-1]} does not match {z.size} depth levels")
    if z.size < 2:
        raise ValueError("at least two depth levels are required")
    if not np.all(np.diff(z) > 0):
        raise ValueError("depths must be strictly increasing")

    flat = t.reshape(-1, z.size)
    n, levels = flat.shape

    valid = np.isfinite(flat)
    # Usable support is the contiguous run of valid levels from the top: a
    # cumulative AND. This is what makes a mid-column gap end the profile
    # instead of silently joining across it.
    usable = np.cumprod(valid, axis=1).astype(bool)

    excess = flat - TEMPERATURE_THRESHOLD_C

    d26 = np.full(n, np.nan)
    tchp = np.full(n, np.nan)
    status = np.full(n, D26Status.INSUFFICIENT_SUPPORT, dtype="int8")

    status[~valid.any(axis=1)] = D26Status.NO_VALID_LEVELS

    top_ok = usable[:, 0]
    # Strictly below: exactly 26.0 at the top is a crossing at z[0], not a
    # "surface below 26" cell.
    surface_below = top_ok & (excess[:, 0] < 0)
    status[surface_below] = D26Status.SURFACE_BELOW_26
    tchp[surface_below] = 0.0

    # A crossing needs two ADJACENT usable levels straddling the threshold.
    pair = usable[:, :-1] & usable[:, 1:]
    crossing = pair & (excess[:, :-1] >= 0) & (excess[:, 1:] < 0)
    has_crossing = crossing.any(axis=1)
    k = np.argmax(crossing, axis=1)  # first True; meaningless where none

    exact_at_top = top_ok & (excess[:, 0] == 0)

    ok = top_ok & ~surface_below & (has_crossing | exact_at_top)
    # A column with no crossing means two different things, and they must not
    # be merged: usable support that reached the deepest level really is warm
    # throughout, whereas support cut short by a gap (or by the seafloor) simply
    # never covered the water where a crossing could have been.
    no_crossing = top_ok & ~surface_below & ~has_crossing & ~exact_at_top
    status[no_crossing & usable[:, -1]] = D26Status.NO_CROSSING_IN_SUPPORT
    status[no_crossing & ~usable[:, -1]] = D26Status.INSUFFICIENT_SUPPORT
    status[ok] = D26Status.OK

    # The isotherm sits exactly at the shallowest level; the integral is empty.
    k = np.where(exact_at_top, 0, k)

    rows = np.flatnonzero(ok)
    if rows.size:
        kk = k[rows]
        e_lo = excess[rows, kk]
        e_hi = excess[rows, kk + 1]
        z_lo = z[kk]
        z_hi = z[kk + 1]
        # e_lo >= 0 > e_hi is guaranteed by the crossing test, so the
        # denominator is strictly positive and this cannot divide by zero.
        span = np.where(exact_at_top[rows], 0.0,
                        e_lo * (z_hi - z_lo) / (e_lo - e_hi))
        crossing_depth = z_lo + span
        d26[rows] = crossing_depth

        # Water above the shallowest level is treated as isothermal at that
        # level's value. Zero for the 15-depth stages, whose top level is the
        # nominal 0 m; it matters only for the native profile starting at
        # ~0.494 m, and it makes the two start identically.
        integral = excess[rows, 0] * z[0]
        # Whole level pairs entirely above the crossing.
        for j in range(levels - 1):
            take = j < kk
            if not take.any():
                continue
            seg = 0.5 * (excess[rows, j] + excess[rows, j + 1]) * (z[j + 1] - z[j])
            integral += np.where(take, seg, 0.0)
        # Final partial segment. Exact: the integrand falls linearly to zero at
        # D26 by construction of the interpolation above.
        integral += 0.5 * e_lo * (crossing_depth - z_lo)

        tchp[rows] = integral * RHO_CP * J_PER_M2_TO_KJ_PER_CM2

    shape = t.shape[:-1]
    return ThermalResult(d26.reshape(shape), tchp.reshape(shape),
                         status.reshape(shape))


def verify_constants(rtol: float = 1e-9) -> dict:
    """Re-derive CP0 and RHO0 from TEOS-10 and check the frozen values.

    CP0 is not read from a table: TEOS-10 defines Conservative Temperature by
    h0 = CP0 * CT, so ``enthalpy(SA, CT, p=0) / CT`` must return it for every
    SA and CT. Raises if the frozen constants have drifted from the standard.
    """
    import gsw

    sso = 35.16504  # TEOS-10 Standard Ocean Reference Salinity, g/kg
    derived = [gsw.enthalpy(sa, ct, 0.0) / ct
               for sa in (33.0, sso, 36.5) for ct in (5.0, 26.0, 30.0)]
    cp0 = float(np.mean(derived))
    if not np.allclose(derived, cp0, rtol=rtol):
        raise AssertionError("TEOS-10 cp0 identity is not invariant in SA/CT")
    if not np.isclose(cp0, CP0, rtol=rtol):
        raise AssertionError(f"CP0 {CP0} != TEOS-10 derived {cp0}")

    rho0 = float(gsw.rho(sso, TEMPERATURE_THRESHOLD_C, 0.0))
    if not np.isclose(rho0, RHO0, rtol=rtol):
        raise AssertionError(f"RHO0 {RHO0} != TEOS-10 derived {rho0}")

    return {"gsw_version": gsw.__version__, "cp0_derived": cp0,
            "rho0_derived": rho0, "rho_cp": rho0 * cp0,
            "standard": "TEOS-10 (IOC/SCOR/IAPSO 2010)"}
