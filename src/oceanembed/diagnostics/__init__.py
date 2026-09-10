"""Derived thermal diagnostics computed from an authoritative OceanEmbed field.

These are DIAGNOSTICS, not a second inference path. Everything here consumes a
temperature profile that some authoritative source already produced (a
``replay_field`` result, or a reference reanalysis profile) and derives a
scalar from it. No model runs here.
"""
from .bathymetry import (BathymetryUnavailable, DISPLAY_VALID_RULE,
                         PHYSICAL_SUPPORT_RULE, PhysicalSupport,
                         bathymetry_provenance, depth_physically_valid,
                         display_valid, local_water_depth, qualify)
from .thermal import (CP0, D26Status, RHO0, RHO_CP, TEMPERATURE_THRESHOLD_C,
                      ThermalResult, d26_tchp, verify_constants)

#: What the UI and the exports must state alongside any D26/TCHP number, so a
#: reader comparing against an operational product knows the offset between
#: published conventions is a convention difference and not a skill difference.
CONVENTION = {
    "d26": "Depth of the shallowest downward 26 degC crossing, linearly "
           "interpolated between bracketing depth levels. Never extrapolated.",
    "tchp": "rho0 * cp0 * integral from 0 to D26 of (T - 26 degC) dz, "
            "in kJ/cm2. Leipper & Volgenau (1972); operational form used by "
            "NOAA/AOML (Shay et al. 2000; Goni et al. 1996).",
    "threshold_degC": TEMPERATURE_THRESHOLD_C,
    "rho0_kg_m3": RHO0,
    "cp0_J_kg_K": CP0,
    "constants_source": "TEOS-10 (IOC/SCOR/IAPSO 2010) via gsw: cp0 is the "
                        "defined reference heat capacity, rho0 = rho(SA=SSO, "
                        "CT=26 degC, p=0). Published TCHP conventions span "
                        "about 8 percent around this pair.",
    "protocol": "outputs/phase7/D26_TCHP_EVALUATION_PROTOCOL.md",
    "computed_from": "the authoritative replay_field temperature; no separate "
                     "inference path and no client-side recomputation",
}


def field_diagnostics(view) -> ThermalResult:
    """D26 and TCHP for an authoritative field view.

    Deliberately duck-typed on ``.temperature`` / ``.depths`` so this module
    never imports the replay transport: the diagnostics are a function of a
    profile, not of where the profile came from.
    """
    return d26_tchp(view.temperature, view.depths)


__all__ = ["CP0", "RHO0", "RHO_CP", "TEMPERATURE_THRESHOLD_C", "CONVENTION",
           "D26Status", "ThermalResult", "d26_tchp", "field_diagnostics",
           "verify_constants", "PHYSICAL_SUPPORT_RULE", "DISPLAY_VALID_RULE",
           "PhysicalSupport", "BathymetryUnavailable", "bathymetry_provenance",
           "depth_physically_valid", "display_valid", "local_water_depth",
           "qualify"]
