"""Operational input-assembly contract for the FROZEN L2 model.

This package never modifies a model and never modifies the legacy
preprocessing. Its only job is to decide whether a declared input situation is
experimentally supported and, when it is, to assemble a COMPLETE seven-channel
field that is then handed to the unmodified frozen ``day_field``.
"""
from .policy import (POLICY_REGISTRY, PolicyState, UnsupportedInputMode,  # noqa: F401
                     lookup_policy)
from .availability import ChannelAvailability, InputDeclaration  # noqa: F401
from .provenance import ChannelProvenance, ReconstructionManifest, PersistenceStore  # noqa: F401
from .assemble import assemble_field, reference_complete_field  # noqa: F401
