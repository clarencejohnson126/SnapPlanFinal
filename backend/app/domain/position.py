"""
Position — the billable line item. The output of Schicht 2.

This is the object the customer actually buys. It carries three things that
distinguish SnapPlan from "a script that reads numbers out of a PDF":

  1. `calculation` — the Rechenweg, not just the result. A Prüfer wants to see
     "8,00 × 2,75 = 22,00, Tür 1,78 m² übermessen (< Schwelle)", not "22,00".
  2. `evidence` — every source that fed the number, each with a spot on a page
     the reviewer can click.
  3. `status` — whether a human has signed off. A machine-produced number is a
     proposal. Only a reviewed one is exportable.

Point 3 is a hard gate, not a UI convention: `is_exportable` stays False until a
human touches it, and the exporters honour that.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from app.domain.evidence import Evidence
from app.domain.quantities import QuantityKind, UNIT_BY_KIND
from app.domain.trades import Trade, atv_for, label_for


class PositionStatus(str, Enum):
    """Where a position stands in the review workflow."""

    AUTO = "auto"            # machine proposal, nobody has looked at it
    REVIEWED = "reviewed"    # human checked it, value unchanged
    CORRECTED = "corrected"  # human checked it and changed the value
    MANUAL = "manual"        # human created it from scratch


#: Statuses meaning a human has taken responsibility for the number.
SIGNED_OFF_STATUSES = frozenset({
    PositionStatus.REVIEWED,
    PositionStatus.CORRECTED,
    PositionStatus.MANUAL,
})


def format_de(value: float, decimals: int = 2) -> str:
    """
    German number formatting: decimal comma, thousands dot.

    Used in Rechenweg strings and exports. A Prüfer reading "22.00" where they
    expect "22,00" will assume the tool is foreign and stop trusting it.
    """
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@dataclass
class CalculationStep:
    """
    One line of the Rechenweg.

    `expression` is what a human reads; `result` is what the machine carries
    forward. They must agree — if you write the expression by hand, compute the
    result from the same numbers.
    """

    label: str            # "Bruttofläche", "Abzug Öffnungen"
    expression: str       # "8,00 m × 2,75 m"
    result: float
    unit: str
    note: Optional[str] = None   # why a rule fired, e.g. the threshold applied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "expression": self.expression,
            "result": self.result,
            "result_formatted": format_de(self.result),
            "unit": self.unit,
            "note": self.note,
        }

    def as_line(self) -> str:
        """Single-line rendering for the Aufmaßprotokoll."""
        line = f"{self.label}: {self.expression} = {format_de(self.result)} {self.unit}"
        return f"{line}  ({self.note})" if self.note else line


@dataclass
class Position:
    """
    One billable quantity, fully traced.

    Fields worth explaining:
        raw_quantity: the value before the ruleset touched it. Keeping it lets
                      the UI show "geometrisch 22,00 → abrechenbar 20,22" and
                      proves the rule actually did something.
        ruleset_id / ruleset_version: which rules produced this, so a recalc
                      after a rule change is auditable.
        lv_position: GAEB Ordnungszahl once assigned. Empty until then, but
                      present from day one so the export path never needs a
                      schema migration.
    """

    trade: Trade
    designation: str
    quantity: float
    kind: QuantityKind
    ruleset_id: str
    ruleset_version: str
    calculation: List[CalculationStep] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    raw_quantity: Optional[float] = None
    status: PositionStatus = PositionStatus.AUTO
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    lv_position: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    room_id: Optional[str] = None
    room_label: Optional[str] = None
    position_id: str = field(default_factory=lambda: f"pos_{uuid.uuid4().hex[:10]}")

    @property
    def unit(self) -> str:
        return UNIT_BY_KIND[self.kind]

    @property
    def atv(self) -> str:
        """The ATV this position was calculated under."""
        return atv_for(self.trade)

    @property
    def confidence(self) -> float:
        """Weakest link across all evidence. One OCR guess taints the position."""
        if not self.evidence:
            return 0.0
        return min(e.confidence for e in self.evidence)

    @property
    def needs_review(self) -> bool:
        """
        True when a human must look before this can be exported.

        Interpretive evidence (OCR/CV) always needs review — that is the honest
        answer to "AI-assisted, not hands-off". Warnings do too.
        """
        if self.status in SIGNED_OFF_STATUSES:
            return False
        if any(e.is_interpretive for e in self.evidence):
            return True
        return bool(self.warnings)

    @property
    def is_exportable(self) -> bool:
        """
        Only signed-off positions may leave the system.

        This is the gate that keeps an unreviewed machine guess out of a
        Rechnung. Exporters must check it; they do not get to opt out.
        """
        return self.status in SIGNED_OFF_STATUSES

    def mark_reviewed(self, user: str, corrected_quantity: Optional[float] = None) -> None:
        """
        Sign off on this position.

        Passing `corrected_quantity` records a correction rather than a plain
        approval, and preserves the original machine value in `raw_quantity`.
        """
        if corrected_quantity is not None and corrected_quantity != self.quantity:
            if self.raw_quantity is None:
                self.raw_quantity = self.quantity
            self.calculation.append(CalculationStep(
                label="Korrektur",
                expression=f"{format_de(self.quantity)} → {format_de(corrected_quantity)}",
                result=corrected_quantity,
                unit=self.unit,
                note=f"manuell korrigiert von {user}",
            ))
            self.quantity = corrected_quantity
            self.status = PositionStatus.CORRECTED
        else:
            self.status = PositionStatus.REVIEWED
        self.reviewed_by = user
        self.reviewed_at = datetime.now(timezone.utc)

    def protocol_lines(self) -> List[str]:
        """The Rechenweg as text, for the Aufmaßprotokoll."""
        return [step.as_line() for step in self.calculation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "trade": self.trade.value,
            "trade_label": label_for(self.trade),
            "atv": self.atv,
            "designation": self.designation,
            "quantity": self.quantity,
            "quantity_formatted": format_de(self.quantity),
            "unit": self.unit,
            "kind": self.kind.value,
            "raw_quantity": self.raw_quantity,
            "raw_quantity_formatted": (
                format_de(self.raw_quantity) if self.raw_quantity is not None else None
            ),
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "calculation": [c.to_dict() for c in self.calculation],
            "evidence": [e.to_dict() for e in self.evidence],
            "status": self.status.value,
            "needs_review": self.needs_review,
            "is_exportable": self.is_exportable,
            "confidence": self.confidence,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "lv_position": self.lv_position,
            "warnings": self.warnings,
            "room_id": self.room_id,
            "room_label": self.room_label,
        }


@dataclass
class PositionSet:
    """
    All positions produced for one document and one trade.

    The counts here drive the review screen's header ("47 Positionen · 39
    geprüft · 8 offen"), so they are computed in one place rather than in the
    frontend.
    """

    document_id: str
    trade: Trade
    positions: List[Position] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ruleset_id: Optional[str] = None
    ruleset_version: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_count(self) -> int:
        return len(self.positions)

    @property
    def review_pending_count(self) -> int:
        return sum(1 for p in self.positions if not p.is_exportable)

    @property
    def exportable_count(self) -> int:
        return sum(1 for p in self.positions if p.is_exportable)

    @property
    def is_release_ready(self) -> bool:
        """True only when every position has been signed off."""
        return bool(self.positions) and self.review_pending_count == 0

    def totals_by_unit(self) -> Dict[str, float]:
        """Summed quantities per unit. Counts only what is exportable."""
        totals: Dict[str, float] = {}
        for position in self.positions:
            if not position.is_exportable:
                continue
            totals[position.unit] = totals.get(position.unit, 0.0) + position.quantity
        return totals

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "trade": self.trade.value,
            "trade_label": label_for(self.trade),
            "atv": atv_for(self.trade),
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "positions": [p.to_dict() for p in self.positions],
            "total_count": self.total_count,
            "exportable_count": self.exportable_count,
            "review_pending_count": self.review_pending_count,
            "is_release_ready": self.is_release_ready,
            "totals_by_unit": self.totals_by_unit(),
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat(),
        }
