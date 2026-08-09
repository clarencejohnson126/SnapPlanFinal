"""
Gewerke (trades) and the ATV that governs each one.

The ATV reference is the point of this module. A trade is not just a label for
grouping positions — it decides *which rules apply* when turning a raw geometric
quantity into a billable one. Trockenbau and Maler measure the same wall and
legitimately arrive at different numbers.

Relationship to services/trade_projection.py:TradeType
-----------------------------------------------------
That enum models *material projection* — estimating how much gypsum board to
order, explicitly allowing LLM_ASSISTED guesses. This one models *Abrechnung*
under VOB/C, which is deterministic and legally defined. They are different
concepts and deliberately stay separate; PROJECTION_TRADE_MAP bridges them.
"""

from enum import Enum
from typing import Dict, List, Optional


class Trade(str, Enum):
    """Gewerke SnapPlan can produce a VOB-conformant Aufmaß for."""

    TROCKENBAU = "trockenbau"
    MALER = "maler"
    BODENBELAG = "bodenbelag"
    ESTRICH = "estrich"
    PUTZ = "putz"
    FLIESEN = "fliesen"
    TUEREN = "tueren"
    ABBRUCH = "abbruch"


#: ATV DIN standard governing each trade under VOB/C. Abschnitt 5 ("Abrechnung")
#: of each ATV is what the corresponding ruleset in app/rules/ encodes.
ATV_BY_TRADE: Dict[Trade, str] = {
    Trade.TROCKENBAU: "DIN 18340",   # Trockenbauarbeiten
    Trade.MALER: "DIN 18363",        # Maler- und Lackierarbeiten
    Trade.BODENBELAG: "DIN 18365",   # Bodenbelagarbeiten
    Trade.ESTRICH: "DIN 18353",      # Estricharbeiten
    Trade.PUTZ: "DIN 18350",         # Putz- und Stuckarbeiten
    Trade.FLIESEN: "DIN 18352",      # Fliesen- und Plattenarbeiten
    Trade.TUEREN: "DIN 18355",       # Tischlerarbeiten
    Trade.ABBRUCH: "DIN 18459",      # Abbruch- und Rückbauarbeiten
}

#: Human-facing labels. The UI shows these; the enum value never reaches a user.
LABEL_BY_TRADE: Dict[Trade, str] = {
    Trade.TROCKENBAU: "Trockenbau",
    Trade.MALER: "Maler- und Lackierarbeiten",
    Trade.BODENBELAG: "Bodenbelag",
    Trade.ESTRICH: "Estrich",
    Trade.PUTZ: "Putz",
    Trade.FLIESEN: "Fliesen und Platten",
    Trade.TUEREN: "Türen",
    Trade.ABBRUCH: "Abbruch",
}

#: Bridge to the material-projection enum. Only trades that exist on both sides
#: appear here; SCAFFOLDING and WATERPROOFING have no ATV counterpart in this
#: enum and are intentionally absent.
PROJECTION_TRADE_MAP: Dict[Trade, str] = {
    Trade.TROCKENBAU: "drywall",
    Trade.ESTRICH: "screed",
    Trade.BODENBELAG: "floor_finish",
}


def atv_for(trade: Trade) -> str:
    """The ATV DIN standard governing this trade."""
    return ATV_BY_TRADE[trade]


def label_for(trade: Trade) -> str:
    """German display label for this trade."""
    return LABEL_BY_TRADE[trade]


def implemented_trades() -> List[Trade]:
    """
    Trades that actually have a ruleset registered.

    Imported lazily so this module stays free of a dependency on app.rules —
    the rulesets themselves import from here.
    """
    from app.rules.base import registered_trades
    return registered_trades()


def is_implemented(trade: Trade) -> bool:
    """True when a ruleset exists. The UI must not offer a trade without one."""
    return trade in implemented_trades()


def parse_trade(value: Optional[str]) -> Optional[Trade]:
    """Tolerant parsing for API input. Accepts enum value or German label."""
    if not value:
        return None
    normalized = value.strip().lower()
    for trade in Trade:
        if trade.value == normalized:
            return trade
    for trade, label in LABEL_BY_TRADE.items():
        if label.lower() == normalized:
            return trade
    return None
