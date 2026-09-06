"""Central configuration loader for OceanEmbed.

Single source of truth is ``config/phase6a.yaml``. Nothing else in the codebase
should hard-code the domain, grid resolution, test period, or depth lists.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Repo root = two levels above this file's package dir (src/oceanembed/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "phase6a.yaml"


def load(path: Path | str | None = None) -> dict[str, Any]:
    """Load and return the Phase 6A configuration as a plain dict."""
    p = Path(path) if path is not None else CONFIG_PATH
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


CFG: dict[str, Any] = load()

# Convenience accessors ------------------------------------------------------
DOMAIN = CFG["domain"]
SOUTH, NORTH = float(DOMAIN["south"]), float(DOMAIN["north"])
WEST, EAST = float(DOMAIN["west"]), float(DOMAIN["east"])
RESOLUTION = float(CFG["grid"]["resolution"])

TEST_START = CFG["test_period"]["start"]
TEST_END = CFG["test_period"]["end"]

DEBUG_DEPTHS = list(CFG["debug_target_depths_m"])
FINAL_DEPTHS = list(CFG["final_target_depths_m"])
SURFACE_CHANNELS = list(CFG["surface_channels"])

PRODUCTS = CFG["products"]
PIPELINE_VERSION = CFG["pipeline_version"]

__all__ = [
    "CFG", "REPO_ROOT", "CONFIG_PATH", "load", "path",
    "DOMAIN", "SOUTH", "NORTH", "WEST", "EAST", "RESOLUTION",
    "TEST_START", "TEST_END", "DEBUG_DEPTHS", "FINAL_DEPTHS",
    "SURFACE_CHANNELS", "PRODUCTS", "PIPELINE_VERSION",
]


def path(key: str) -> Path:
    """Resolve a configured relative path against the repo root."""
    return REPO_ROOT / CFG["paths"][key]
