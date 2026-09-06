#!/usr/bin/env bash
# Build each Phase 6A.5 year as soon as its GLORYS download lands, so that
# processing overlaps the remaining ~4 hours of downloading instead of
# starting only after it finishes.
#
# Safe to re-run: build_phase6a5.py rebuilds a year from scratch and merges
# its QC rows into the canonical tables rather than overwriting them.
set -u
cd "$(dirname "$0")/../.." || exit 1

for year in "$@"; do
  src="data/raw/glorys/${year}/glorys_${year}.nc"
  echo "[orchestrator] waiting for ${src}"
  while [ ! -f "$src" ]; do sleep 60; done
  # the file appears only after verification + atomic rename, so it is complete
  echo "[orchestrator] building ${year}"
  PYTHONPATH=src python scripts/preprocess/build_phase6a5.py --years "$year" \
    >> outputs/logs/build_as_available.out 2>&1
  echo "[orchestrator] ${year} exit=$?"
done
echo "[orchestrator] all requested years processed"
