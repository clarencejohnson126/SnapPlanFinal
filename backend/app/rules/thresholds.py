"""
VOB/C thresholds — every number that comes from a norm rather than from a plan.

WHY THIS FILE EXISTS SEPARATELY

An Übermessungsgrenze is not a magic constant. It is a legal value from a
specific Abschnitt of a specific ATV, it differs between trades, and it changes
when the VOB is revised. Scattering `2.5` across ruleset code makes it
impossible to answer "which norm version did we bill this under?" — which is
exactly what a Prüfer asks.

THE `verified` FLAG — READ THIS BEFORE SHIPPING

Every threshold carries `verified`. It means: has a human compared this value
against the current printed VOB/C. Values marked False are *plausible working
assumptions*, not confirmed law.

An unverified threshold does not silently produce a number. `Calculation.
apply_threshold()` attaches a warning to any position that used one, which
forces that position into needs_review and blocks its export until a human signs
off. That is deliberate: the system stays honest about what it does not know
rather than emitting a confident wrong invoice.

To ship a trade commercially: check its thresholds against VOB/C, correct the
values, flip `verified` to True, and record the edition in `source_note`.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from app.domain.trades import Trade


@dataclass(frozen=True)
class Threshold:
    """
    One norm-derived constant, with its provenance.

    Fields:
        key: stable identifier, used in warnings and audit output
        value: the number itself
        unit: what the number measures
        atv: which ATV DIN it comes from
        clause: which Abschnitt, as precisely as known
        description: what the rule does, in German, for the Rechenweg
        verified: whether a human checked this against the printed VOB/C
        source_note: which edition was checked, or what still needs checking
    """

    key: str
    value: float
    unit: str
    atv: str
    clause: str
    description: str
    verified: bool = False
    source_note: str = ""

    @property
    def citation(self) -> str:
        """Human-readable provenance for the Aufmaßprotokoll."""
        suffix = "" if self.verified else " [UNGEPRÜFT]"
        return f"{self.atv} {self.clause}{suffix}"


#: Openings at or below this area are übermessen (measured over, not deducted).
#: The single most consequential rule in Aufmaß — it is the difference between a
#: plausible number and a billable one.
OPENING_DEDUCTION_THRESHOLD: Dict[Trade, Threshold] = {
    Trade.TROCKENBAU: Threshold(
        key="opening_deduction_trockenbau",
        value=2.5,
        unit="m²",
        atv="DIN 18340",
        clause="Abschnitt 5 (Abrechnung)",
        description="Öffnungen bis 2,5 m² werden übermessen",
        verified=False,
        source_note="Arbeitsannahme. Gegen aktuelle VOB/C ATV DIN 18340 Abschnitt 5 prüfen.",
    ),
    Trade.MALER: Threshold(
        key="opening_deduction_maler",
        value=2.5,
        unit="m²",
        atv="DIN 18363",
        clause="Abschnitt 5 (Abrechnung)",
        description="Öffnungen bis 2,5 m² werden übermessen",
        verified=False,
        source_note="Arbeitsannahme. Gegen aktuelle VOB/C ATV DIN 18363 Abschnitt 5 prüfen.",
    ),
    Trade.PUTZ: Threshold(
        key="opening_deduction_putz",
        value=2.5,
        unit="m²",
        atv="DIN 18350",
        clause="Abschnitt 5 (Abrechnung)",
        description="Öffnungen bis 2,5 m² werden übermessen",
        verified=False,
        source_note="Arbeitsannahme. Gegen aktuelle VOB/C ATV DIN 18350 Abschnitt 5 prüfen.",
    ),
}

#: Recesses and built-ins at or below this area are not deducted from a floor.
RECESS_DEDUCTION_THRESHOLD: Dict[Trade, Threshold] = {
    Trade.BODENBELAG: Threshold(
        key="recess_deduction_bodenbelag",
        value=0.1,
        unit="m²",
        atv="DIN 18365",
        clause="Abschnitt 5 (Abrechnung)",
        description="Einbauten bis 0,1 m² werden übermessen",
        verified=False,
        source_note="Arbeitsannahme. Gegen aktuelle VOB/C ATV DIN 18365 Abschnitt 5 prüfen.",
    ),
    Trade.ESTRICH: Threshold(
        key="recess_deduction_estrich",
        value=0.1,
        unit="m²",
        atv="DIN 18353",
        clause="Abschnitt 5 (Abrechnung)",
        description="Einbauten bis 0,1 m² werden übermessen",
        verified=False,
        source_note="Arbeitsannahme. Gegen aktuelle VOB/C ATV DIN 18353 Abschnitt 5 prüfen.",
    ),
}


def opening_threshold(trade: Trade) -> Optional[Threshold]:
    """The Übermessungsgrenze for openings in this trade, if one applies."""
    return OPENING_DEDUCTION_THRESHOLD.get(trade)


def recess_threshold(trade: Trade) -> Optional[Threshold]:
    """The Übermessungsgrenze for floor recesses in this trade, if one applies."""
    return RECESS_DEDUCTION_THRESHOLD.get(trade)


def unverified_thresholds() -> Dict[str, Threshold]:
    """
    Every threshold still awaiting a check against the printed VOB/C.

    Surfaced on the health endpoint so an unverified norm value can never
    quietly reach production.
    """
    collected: Dict[str, Threshold] = {}
    for table in (OPENING_DEDUCTION_THRESHOLD, RECESS_DEDUCTION_THRESHOLD):
        for threshold in table.values():
            if not threshold.verified:
                collected[threshold.key] = threshold
    return collected
