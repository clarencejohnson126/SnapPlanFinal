"""
Trade Material Projections Package

This package contains rule-based projection engines for different construction trades.
Each module implements a `project_*` function that takes extraction results and
trade parameters, returning a MaterialProjectionResult.

Available projections:
- scaffolding: Gerüstbau (facade scaffolding, mobile scaffolds)
- drywall: Trockenbau (gypsum boards, profiles, fasteners)
- screed: Estrich (cement/anhydrite screed, edge strips)
- floor_finish: Oberbelag (laminate, tile, carpet)
- waterproofing: Abdichtung (liquid membrane, sealing tape)
"""

from app.services.projections.screed import project_screed
from app.services.projections.drywall import project_drywall
from app.services.projections.scaffolding import project_scaffolding
from app.services.projections.floor_finish import project_floor_finish
from app.services.projections.waterproofing import project_waterproofing

__all__ = [
    "project_screed",
    "project_drywall",
    "project_scaffolding",
    "project_floor_finish",
    "project_waterproofing",
]
