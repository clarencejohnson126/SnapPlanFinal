"""
Domain contracts shared by all three layers.

Import from here rather than the submodules — it keeps the layer boundary
visible at the call site:

    from app.domain import RawModel, Position, Trade
"""

from app.domain.evidence import (
    CoordinateSpace,
    Evidence,
    ExtractionMethod,
    Geometry,
    INTERPRETIVE_METHODS,
    manual_evidence,
    method_rank,
)
from app.domain.position import (
    CalculationStep,
    Position,
    PositionSet,
    PositionStatus,
    SIGNED_OFF_STATUSES,
    format_de,
)
from app.domain.quantities import (
    Opening,
    OpeningKind,
    QuantityKind,
    RawModel,
    RoomSpace,
    ScaleInfo,
    UNIT_BY_KIND,
    WallSurface,
)
from app.domain.trades import (
    ATV_BY_TRADE,
    LABEL_BY_TRADE,
    Trade,
    atv_for,
    is_implemented,
    label_for,
    parse_trade,
)

__all__ = [
    # evidence
    "CoordinateSpace", "Evidence", "ExtractionMethod", "Geometry",
    "INTERPRETIVE_METHODS", "manual_evidence", "method_rank",
    # quantities
    "Opening", "OpeningKind", "QuantityKind", "RawModel", "RoomSpace",
    "ScaleInfo", "UNIT_BY_KIND", "WallSurface",
    # position
    "CalculationStep", "Position", "PositionSet", "PositionStatus",
    "SIGNED_OFF_STATUSES", "format_de",
    # trades
    "ATV_BY_TRADE", "LABEL_BY_TRADE", "Trade", "atv_for", "is_implemented",
    "label_for", "parse_trade",
]
