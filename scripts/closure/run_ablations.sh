#!/usr/bin/env bash
# Experiment D queue: the full-input control first, then the five
# leave-one-group-out variants. Same protocol and seed for every run.
set -u
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=8
python -u scripts/closure/train_closure.py --name D_CONTROL_ALL      --seed 20260905
python -u scripts/closure/train_closure.py --name D_MINUS_SST        --seed 20260905 --ablate SST
python -u scripts/closure/train_closure.py --name D_MINUS_SSS        --seed 20260905 --ablate SSS
python -u scripts/closure/train_closure.py --name D_MINUS_SLA        --seed 20260905 --ablate SLA
python -u scripts/closure/train_closure.py --name D_MINUS_CURRENTS   --seed 20260905 --ablate CURRENTS
python -u scripts/closure/train_closure.py --name D_MINUS_WINDS      --seed 20260905 --ablate WINDS
echo "ABLATION QUEUE COMPLETE"
