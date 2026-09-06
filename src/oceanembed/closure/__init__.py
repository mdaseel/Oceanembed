"""Architecture-closure study support code (Experiments B, C and D).

Everything here is ADDITIVE. No frozen artefact is written, moved or refitted
by any module in this package; the frozen L0 climatology, the L1 and L2
checkpoints and the two frozen scalers are opened read-only and hash-checked.
"""
from .ablation import ABLATION_GROUPS, ablate_field, group_channel_indices
from .residual import ResidualTargets, residual_scaler_path
from .sampling import CachedDaySampler

__all__ = ["ABLATION_GROUPS", "ablate_field", "group_channel_indices",
           "ResidualTargets", "residual_scaler_path", "CachedDaySampler"]
