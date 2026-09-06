"""NRT product compatibility research infrastructure.

Data access, latency measurement, product-shift measurement and frozen-model
substitution sensitivity. No model is trained here and no production scheduler
is built.
"""
from .registry import PRODUCTS, PAIRS, write_registry  # noqa: F401
from .latency import append_poll, load_log, summarise  # noqa: F401
