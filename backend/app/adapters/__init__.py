"""
Adapters between the existing services and the layered contracts.

Nothing in app/domain/ or app/rules/ may import from app/services/. This package
is the only place allowed to know both sides, which is what keeps the extraction
code replaceable without touching the rules.
"""

from app.adapters.layer1 import build_raw_model

__all__ = ["build_raw_model"]
