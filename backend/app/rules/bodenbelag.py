"""
Bodenbelag — Abrechnung nach ATV DIN 18365.

WHY THIS RULESET MATTERS MORE THAN IT LOOKS

Trockenbau needs a perimeter, and a perimeter only exists in plans that print
one. A run across 33 real plans from three projects found:

    LeiQ (NRF:)       perimeter on some rooms
    Haardtring (F:)   perimeter on none
    Omniturm (NGF:)   perimeter on none

Area, by contrast, is on all 351 rooms — it is the one number every German plan
format states. So this is the ruleset that works on the whole corpus today,
while wall-based trades wait for perimeters to be derived from plan geometry.

Floor area is also the honest place to start commercially: a floor covering
quantity is a floor area minus what is not covered, and both parts are readable.
"""

from typing import Optional

from app.domain.position import Position, PositionSet, format_de
from app.domain.quantities import QuantityKind, RawModel, RoomSpace
from app.domain.trades import Trade
from app.rules.base import Calculation, RuleParams, Ruleset, register_ruleset
from app.rules.thresholds import recess_threshold


@register_ruleset
class BodenbelagRules(Ruleset):
    """
    Floor covering quantities for Bodenbelagarbeiten.

    Produces per room:
      - Bodenfläche (m²) from the room's stated area
      - Sockelleiste (m) from the perimeter, when the plan states one

    Outdoor areas are reported, never silently factored. The 50 % rule that
    plans often print next to a Dachterrasse comes from the
    Wohnflächenverordnung — it governs how living space is *counted*, not how a
    floor covering is *billed*. Applying it here would quietly halve a real
    quantity, so the room is flagged for the reviewer instead.
    """

    trade = Trade.BODENBELAG
    ruleset_id = "bodenbelag-vob-18365"
    version = "0.1.0"
    description = "Bodenflächen und Sockelleisten nach ATV DIN 18365"

    def apply(self, model: RawModel, params: RuleParams) -> PositionSet:
        result = PositionSet(
            document_id=model.document_id,
            trade=self.trade,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
        )

        if model.is_empty:
            result.warnings.append(
                "Die Extraktion hat keine Räume gefunden — es konnte kein Aufmaß "
                "erzeugt werden."
            )
            return result

        include_skirting = bool(params.extras.get("include_skirting", False))
        skipped_area = 0

        for room in model.rooms:
            if not params.wants_room(room.room_id):
                continue

            floor = self._floor_position(room)
            if floor:
                result.positions.append(floor)
            else:
                skipped_area += 1

            if include_skirting:
                skirting = self._skirting_position(room)
                if skirting:
                    result.positions.append(skirting)

        if skipped_area:
            result.warnings.append(
                f"{skipped_area} von {len(model.rooms)} Räumen ohne Flächenangabe — "
                f"diese konnten nicht abgerechnet werden."
            )

        if include_skirting:
            without_perimeter = sum(1 for r in model.rooms if r.perimeter_m is None)
            if without_perimeter:
                result.warnings.append(
                    f"Sockelleisten: {without_perimeter} Räume ohne Umfangsangabe im "
                    f"Plan — für diese wurde keine Länge ermittelt."
                )

        return result

    # ------------------------------------------------------------------- floor

    def _floor_position(self, room: RoomSpace) -> Optional[Position]:
        """
        Billable floor area for one room.

        The plan's area is the starting point. Deductions for built-ins would
        come next, but nothing in Schicht 1 currently detects them — so rather
        than presenting the number as final, the ruleset states what it could
        not check.
        """
        if room.floor_area_m2 is None:
            return None

        calc = Calculation()
        label = self._room_label(room)

        area = calc.step(
            label="Bodenfläche",
            expression=f"Grundfläche {label}",
            result=room.floor_area_m2,
            unit="m²",
            note="Flächenangabe aus dem Raumstempel",
        )

        threshold = recess_threshold(self.trade)
        if threshold:
            if not threshold.verified:
                calc.warn(
                    f"Übermessungsgrenze für Einbauten "
                    f"({format_de(threshold.value)} {threshold.unit}, {threshold.atv}) "
                    f"ist nicht gegen die VOB/C geprüft. {threshold.source_note}"
                )
            calc.warn(
                f"Einbauten und Aussparungen wurden nicht erkannt — nach "
                f"{threshold.citation} wären Flächen über "
                f"{format_de(threshold.value)} {threshold.unit} abzuziehen. "
                f"Bitte im Plan prüfen."
            )

        if room.is_outdoor:
            calc.warn(
                f"{label} ist als Außenbereich klassifiziert. Die volle Fläche wurde "
                f"angesetzt — ein etwaiger Flächenfaktor im Plan stammt aus der "
                f"Wohnflächenverordnung und gilt nicht für die Bodenbelagsabrechnung."
            )

        if room.is_wet_room:
            calc.warn(
                f"{label} ist ein Nassraum — Belagsart und Abdichtung gesondert prüfen."
            )

        return Position(
            trade=self.trade,
            designation=f"Bodenfläche {label}",
            quantity=round(area, 3),
            kind=QuantityKind.AREA,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
            calculation=calc.steps,
            evidence=[room.evidence],
            raw_quantity=round(area, 3),
            warnings=calc.warnings,
            room_id=room.room_id,
            room_label=label,
        )

    # ---------------------------------------------------------------- skirting

    def _skirting_position(self, room: RoomSpace) -> Optional[Position]:
        """
        Skirting board length — the room perimeter.

        Door openings shorten the actual run, but a floor plan without located
        doors cannot say by how much. The full perimeter is reported and the
        omission stated, rather than deducting a guessed number of doorways.
        """
        if room.perimeter_m is None:
            return None

        calc = Calculation()
        label = self._room_label(room)

        length = calc.step(
            label="Sockelleiste",
            expression=f"Umfang {label}",
            result=room.perimeter_m,
            unit="m",
            note="Umfangsangabe aus dem Raumstempel",
        )

        calc.warn(
            "Türöffnungen wurden nicht abgezogen — der volle Raumumfang ist "
            "angesetzt. Bitte Türdurchgänge prüfen."
        )

        return Position(
            trade=self.trade,
            designation=f"Sockelleiste {label}",
            quantity=round(length, 3),
            kind=QuantityKind.LENGTH,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
            calculation=calc.steps,
            evidence=[room.evidence],
            raw_quantity=round(length, 3),
            warnings=calc.warnings,
            room_id=room.room_id,
            room_label=label,
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _room_label(room: RoomSpace) -> str:
        """Best human label available, for designations and warnings."""
        parts = [p for p in (room.number, room.name) if p]
        return " ".join(parts) if parts else room.room_id
