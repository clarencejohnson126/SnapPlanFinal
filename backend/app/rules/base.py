"""
The Schicht 2 engine: rulesets, their registry, and the Rechenweg recorder.

A ruleset turns trade-neutral RawModel geometry into billable Positions under
one ATV. It is the only place in SnapPlan allowed to apply an Übermessungsregel,
an Abzug, a Zulage, or a factor.

THE CONTRACT A RULESET MUST HONOUR

  1. Read only from RawModel. Never open a PDF, never call an extraction
     service. If you need data that is not on the model, extend Schicht 1.
  2. Never invent a number. If clear height is unknown and the user supplied no
     fallback, emit a warning and skip the position — do not assume 2.50 m.
  3. Record every step. A Position without a Rechenweg is a Position a Prüfer
     will reject.
  4. Be deterministic. Same model plus same params yields the same output,
     always. No randomness, no wall clock, no LLM.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Type

from app.domain.position import CalculationStep, PositionSet, format_de
from app.domain.quantities import Opening, RawModel
from app.domain.trades import Trade
from app.rules.thresholds import Threshold


def _join_notes(*parts: Optional[str]) -> str:
    """Join the non-empty note fragments of a Rechenweg step."""
    return "; ".join(p for p in parts if p)


@dataclass
class RuleParams:
    """
    What the user contributes that the plan does not contain.

    Deliberately small. Every field here is a place where the answer depends on
    something outside the document, and each one is a question the UI must ask
    rather than guess.
    """

    #: Fallback wall height when the plan carries no LH:/clear height.
    #: None means "unknown" — rules must skip rather than assume.
    wall_height_m: Optional[float] = None

    #: Restrict calculation to these room ids. None means all rooms.
    include_rooms: Optional[List[str]] = None

    #: Skip these room ids.
    exclude_rooms: List[str] = field(default_factory=list)

    #: Per-room dimensions the user supplied, keyed by room id:
    #: {"room_x": {"length_m": 5.20, "width_m": 4.10}}
    #: Measured or typed in the review screen. Beats every derived value.
    room_dimensions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    #: Trade-specific knobs a ruleset documents for itself.
    extras: Dict[str, Any] = field(default_factory=dict)

    def dimensions_for(self, room_id: str) -> Optional[Dict[str, float]]:
        """User-supplied length/width for this room, if any."""
        return self.room_dimensions.get(room_id)

    def wants_room(self, room_id: str) -> bool:
        """Whether this room passes the caller's include/exclude filter."""
        if room_id in self.exclude_rooms:
            return False
        if self.include_rooms is not None:
            return room_id in self.include_rooms
        return True


class Calculation:
    """
    Records the Rechenweg while a rule computes.

    Rules do not append to a list by hand — they call `step()` and get the value
    back, so the recorded expression and the value carried forward cannot drift
    apart:

        gross = calc.step("Bruttofläche", f"{l} m × {h} m", l * h, "m²")

    Warnings collected here land on the Position and force it into review.
    """

    def __init__(self) -> None:
        self.steps: List[CalculationStep] = []
        self.warnings: List[str] = []

    def step(self, label: str, expression: str, result: float,
             unit: str, note: Optional[str] = None) -> float:
        """Record one line of the Rechenweg and return its result."""
        self.steps.append(CalculationStep(
            label=label, expression=expression, result=result, unit=unit, note=note,
        ))
        return result

    def warn(self, message: str) -> None:
        """Flag something the reviewer must know. Blocks export until signed off."""
        if message not in self.warnings:
            self.warnings.append(message)

    def deduct_openings(self, openings: List[Opening],
                        threshold: Optional[Threshold],
                        default_height_m: Optional[float] = None) -> float:
        """
        Apply the Übermessungsregel to a set of openings.

        Openings at or below the threshold are übermessen — they stay in the
        billable area. Larger ones are deducted. Each decision is recorded
        individually, because "why is this door not deducted?" is the single
        most common question a Prüfer asks.

        Returns the total area to deduct. Openings with unknown dimensions are
        not silently ignored: they raise a warning, because an undetected window
        is the difference between a correct and an incorrect invoice.
        """
        if threshold is None:
            self.warn(
                "Für dieses Gewerk ist keine Übermessungsgrenze hinterlegt — "
                "Öffnungen wurden nicht abgezogen."
            )
            return 0.0

        if not threshold.verified:
            self.warn(
                f"Übermessungsgrenze {format_de(threshold.value)} {threshold.unit} "
                f"({threshold.atv}) ist nicht gegen die VOB/C geprüft. "
                f"{threshold.source_note}"
            )

        total_deduction = 0.0
        for opening in openings:
            area = opening.area_m2
            label = opening.label or opening.kind.value
            height_note: Optional[str] = None

            # Geometric detection yields a width but no height — a floor plan
            # simply does not contain one. Rather than guess, we use a height
            # the user specified, and say in the Rechenweg that we did.
            if area is None and default_height_m and opening.width_m:
                area = opening.width_m * default_height_m
                height_note = (
                    f"Höhe {format_de(default_height_m)} m als Nutzervorgabe"
                )
                self.warn(
                    f"Öffnung '{label}': Höhe stammt aus der Parametereingabe "
                    f"({format_de(default_height_m)} m), nicht aus dem Plan."
                )

            if area is None:
                self.warn(
                    f"Öffnung '{label}' ohne Maße — konnte nicht bewertet werden. "
                    f"Bitte im Plan prüfen."
                )
                continue

            if area <= threshold.value:
                self.step(
                    label=f"Öffnung {label}",
                    expression=f"{format_de(area)} m² ≤ {format_de(threshold.value)} m²",
                    result=0.0,
                    unit="m²",
                    note=_join_notes(f"übermessen nach {threshold.citation}", height_note),
                )
            else:
                total_deduction += area
                self.step(
                    label=f"Abzug Öffnung {label}",
                    expression=f"{format_de(area)} m² > {format_de(threshold.value)} m²",
                    result=-area,
                    unit="m²",
                    note=_join_notes(f"abgezogen nach {threshold.citation}", height_note),
                )

        return total_deduction


class Ruleset(ABC):
    """
    Base class for a trade's Abrechnung rules.

    Subclasses declare their identity as class attributes so the registry and
    the audit trail can name them without instantiating anything:

        @register_ruleset
        class TrockenbauRules(Ruleset):
            trade = Trade.TROCKENBAU
            ruleset_id = "trockenbau-vob-18340"
            version = "0.1.0"

    Bump `version` whenever a rule changes the numbers it produces. Positions
    carry it, so a recalculation after a norm revision stays auditable.
    """

    trade: ClassVar[Trade]
    ruleset_id: ClassVar[str]
    version: ClassVar[str]

    #: One-line German description shown in the trade picker.
    description: ClassVar[str] = ""

    @abstractmethod
    def apply(self, model: RawModel, params: RuleParams) -> PositionSet:
        """
        Turn raw geometry into billable positions.

        Must not raise on incomplete input. A model missing heights yields a
        PositionSet with warnings and fewer positions — never an exception, and
        never a guessed number.
        """
        raise NotImplementedError


#: Registered rulesets, keyed by trade. One ruleset per trade.
_REGISTRY: Dict[Trade, Ruleset] = {}


def register_ruleset(cls: Type[Ruleset]) -> Type[Ruleset]:
    """
    Class decorator that registers a ruleset for its trade.

    Refuses to overwrite an existing registration — two rulesets claiming the
    same trade is a bug that would otherwise surface as silently wrong numbers
    depending on import order.
    """
    for attr in ("trade", "ruleset_id", "version"):
        if not hasattr(cls, attr):
            raise TypeError(f"{cls.__name__} is missing required attribute '{attr}'")

    existing = _REGISTRY.get(cls.trade)
    if existing is not None and type(existing) is not cls:
        raise ValueError(
            f"Trade {cls.trade.value} already has ruleset "
            f"'{existing.ruleset_id}'; {cls.__name__} cannot also claim it."
        )

    _REGISTRY[cls.trade] = cls()
    return cls


def get_ruleset(trade: Trade) -> Optional[Ruleset]:
    """The registered ruleset for this trade, or None if unimplemented."""
    return _REGISTRY.get(trade)


def registered_trades() -> List[Trade]:
    """Trades that have a ruleset. The UI must not offer anything else."""
    return list(_REGISTRY.keys())


def run_ruleset(model: RawModel, trade: Trade,
                params: Optional[RuleParams] = None) -> PositionSet:
    """
    Apply a trade's ruleset to a model, carrying extraction problems forward.

    Rulesets see geometry, not provenance. A missing Maßstab, or openings that
    Schicht 1 could not place in a room, are invisible to them — but they affect
    every number produced. Left alone, that surfaces as a wall area which is
    quietly too large, in the customer's favour, which is the expensive
    direction to be wrong in.

    So extraction warnings are copied onto every position, forcing them into
    needs_review and blocking export until a human has looked. Conservative on
    purpose: a document-level extraction problem taints the whole document.
    """
    ruleset = get_ruleset(trade)
    if ruleset is None:
        result = PositionSet(document_id=model.document_id, trade=trade)
        result.warnings.append(
            f"Für {trade.value} ist kein Regelwerk hinterlegt — "
            f"es kann kein Aufmaß erzeugt werden."
        )
        return result

    result = ruleset.apply(model, params or RuleParams())

    if model.warnings:
        result.warnings.extend(model.warnings)
        for position in result.positions:
            for warning in model.warnings:
                if warning not in position.warnings:
                    position.warnings.append(warning)

    return result


def ruleset_catalog() -> List[Dict[str, str]]:
    """Registry contents for the trade picker and the health endpoint."""
    from app.domain.trades import atv_for, label_for
    return [
        {
            "trade": trade.value,
            "label": label_for(trade),
            "atv": atv_for(trade),
            "ruleset_id": ruleset.ruleset_id,
            "version": ruleset.version,
            "description": ruleset.description,
        }
        for trade, ruleset in sorted(_REGISTRY.items(), key=lambda kv: kv[0].value)
    ]
