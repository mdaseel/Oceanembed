"""Resume-safe download bookkeeping shared by the Phase 6A.5 fetchers.

The rules that matter scientifically:
  * a file is only skipped if it OPENS and carries the expected number of days;
  * a partial transfer can never masquerade as complete (write .part, then
    atomic rename);
  * a good raw file is never silently overwritten.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import xarray as xr


def get_logger(name: str, logfile: Path) -> logging.Logger:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%dT%H:%M:%S")
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(fh)
    lg.addHandler(sh)
    return lg


def expected_days(start: str, end: str) -> int:
    return len(pd.date_range(start, end, freq="D"))


def verify(path: Path, start: str, end: str, tolerance: int = 0) -> tuple[bool, str]:
    """Return (is_good, reason). A file is good only if it opens AND has the
    expected number of daily timesteps."""
    if not path.exists():
        return False, "missing"
    if path.stat().st_size == 0:
        return False, "zero bytes"
    try:
        with xr.open_dataset(path) as ds:
            if "time" not in ds.coords:
                return False, "no time coordinate"
            n = ds.sizes["time"]
    except Exception as exc:  # noqa: BLE001
        return False, f"unreadable ({type(exc).__name__})"
    want = expected_days(start, end)
    if abs(n - want) > tolerance:
        return False, f"incomplete: {n} timesteps, expected {want}"
    return True, f"ok ({n} timesteps)"


def cleanup_partials(directory: Path) -> list[Path]:
    """Remove leftover .part files from an interrupted run."""
    removed = []
    if directory.exists():
        # Also catches the copernicusmarine toolbox's own temp naming, which
        # appends a random suffix (e.g. foo.part.nc.95x9hs3m).
        pats = ("*.part.nc", "*.part", "*.part.nc.*")
        for p in {q for pat in pats for q in directory.rglob(pat)}:
            try:
                p.unlink()
                removed.append(p)
            except OSError:
                # On Windows a killed transfer can leave a handle behind for a
                # while. A stale partial only wastes disk - it can never be
                # mistaken for real data, because only a verified file is ever
                # promoted to the final name. Skip it rather than abort the run.
                pass
    return removed
