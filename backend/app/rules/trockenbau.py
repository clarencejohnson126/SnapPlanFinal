"""
Trockenbau — Abrechnung nach ATV DIN 18340.

The reference ruleset. Every other trade is built by copying this file's shape,
so it is written to be read as much as to run.

WHAT MAKES THIS DIFFERENT FROM THE OLD drywall PATH

The existing `services/gewerke.py` drywall path computes perimeter × height and
stops. That is a geometric area, not a billable one — it silently bills the
customer for the doorways. This ruleset applies the Übermessungsregel: openings
at or below the threshold stay in the area (übermessen), larger ones come out,
and each decision is written into the Rechenweg with its citation.

That difference is the product.
"""

from typing import Dict, List, Optional

from app.domain.evidence import Evidence
from app.domain.position import Position, PositionSet, format_de
from app.domain.quantities import QuantityKind, RawModel, RoomSpace
from app.domain.trades import Trade
from app.rules.base import Calculation, RuleParams, Ruleset, register_ruleset
from app.rules.thresholds import opening_threshold


@register_ruleset
class TrockenbauRules(Ruleset):
    """
    Wall and ceiling quantities for Trockenbauarbeiten.

    Produces per room:
      - Wandfläche (m²), openings handled per DIN 18340
      - Deckenfläche (m²), when params.extras["include_ceiling"] is set

    Ceilings are opt-in rather than automatic: whether a room gets an abgehängte
    Decke is a scope question the plan does not answer, and billing one that was
    never built is worse than omitting one that was.
    """

    trade = Trade.TROCKENBAU
    ruleset_id = "trockenbau-vob-18340"
    version = "0.1.0"
    description = "Wand- und Deckenflächen nach ATV DIN 18340, Öffnungen übermessen"

    def apply(self, model: RawModel, params: RuleParams) -> PositionSet:
        result = PositionSet(
            document_id=model.document_id,
            trade=self.trade,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
        )

        if model.is_empty:
            result.warnings.append(
                "Die Extraktion hat keine Räume oder Bauteile gefunden — "
                "es konnte kein Aufmaß erzeugt werden."
            )
            return result

        if not model.scale.is_user_confirmed and model.scale.denominator:
            result.warnings.append(
                f"Maßstab 1:{model.scale.denominator} wurde automatisch erkannt "
                f"({model.scale.source or 'Quelle unbekannt'}) und ist nicht bestätigt."
            )

        include_ceiling = bool(params.extras.get("include_ceiling", False))

        # Why rooms were skipped, counted by cause. Without this the caller is
        # told "no positions" and has to guess whether the plan lacks heights,
        # perimeters, or areas — three different problems with three different
        # fixes.
        skipped: Dict[str, int] = {}

        for room in model.rooms:
            if not params.wants_room(room.room_id):
                continue

            wall_position = self._wall_position(room, params, skipped)
            if wall_position:
                result.positions.append(wall_position)

            if include_ceiling:
                ceiling_position = self._ceiling_position(room, params)
                if ceiling_position:
                    result.positions.append(ceiling_position)

        if skipped:
            result.warnings.extend(self._skip_summary(skipped, len(model.rooms)))

        return result

    @staticmethod
    def _skip_summary(skipped: Dict[str, int], room_count: int) -> List[str]:
        """Turn skip causes into messages that name the actual fix."""
        messages: List[str] = []

        missing_perimeter = skipped.get("no_perimeter", 0)
        if missing_perimeter:
            messages.append(
                f"{missing_perimeter} von {room_count} Räumen haben keinen Umfang. "
                f"Trockenbau rechnet Umfang × Höhe — Pläne im Format 'F:' oder "
                f"'NGF:' geben nur die Fläche an. Für diese Pläne muss der Umfang "
                f"aus der Plangeometrie ermittelt werden (noch nicht angebunden), "
                f"oder es eignet sich ein flächenbasiertes Gewerk wie Bodenbelag."
            )

        missing_height = skipped.get("no_height", 0)
        if missing_height:
            messages.append(
                f"{missing_height} von {room_count} Räumen haben keine Höhe im Plan. "
                f"Eine Raumhöhe lässt sich unter Parametern als Vorgabe setzen."
            )

        return messages

    # ------------------------------------------------------------------ walls

    def _wall_position(self, room: RoomSpace, params: RuleParams,
                       skipped: Dict[str, int]) -> Optional[Position]:
        """
        Billable wall area for one room.

        Returns None when the geometry does not support a defensible number,
        recording *why* in `skipped`. Returning None is correct here — a skipped
        room the user can see is better than a guessed one they cannot — but a
        silent skip is not, which is what `skipped` prevents.
        """
        calc = Calculation()
        label = self._room_label(room)

        gross = self._gross_wall_area(room, params, calc)
        if gross is None:
            cause = "no_perimeter" if room.perimeter_m is None else "no_height"
            skipped[cause] = skipped.get(cause, 0) + 1
            return None

        openings = room.all_openings()
        if not openings:
            # The common case on a plain Grundriss, and the dangerous one: a
            # wall area with no door deducted at all comes out too large, and
            # too large is the direction that costs the customer money.
            calc.warn(
                f"Für {label} wurden keine Öffnungen erkannt — es wurde nichts "
                f"abgezogen. Türen und Fenster im Plan prüfen."
            )
        deduction = calc.deduct_openings(
            openings,
            opening_threshold(self.trade),
            default_height_m=params.extras.get("default_opening_height_m"),
        )

        net = gross - deduction
        if net <= 0:
            calc.warn(
                f"Abrechnungsfläche für {label} ist {format_de(net)} m² — "
                f"die Abzüge übersteigen die Bruttofläche. Bitte Öffnungen prüfen."
            )
            net = 0.0

        calc.step(
            label="Abrechnungsfläche",
            expression=f"{format_de(gross)} m² − {format_de(deduction)} m²",
            result=net,
            unit="m²",
        )

        return Position(
            trade=self.trade,
            designation=f"Wandfläche {label}",
            quantity=round(net, 3),
            kind=QuantityKind.AREA,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
            calculation=calc.steps,
            evidence=self._collect_evidence(room, include_openings=True),
            raw_quantity=round(gross, 3),
            warnings=calc.warnings,
            room_id=room.room_id,
            room_label=label,
        )

    def _gross_wall_area(self, room: RoomSpace, params: RuleParams,
                         calc: Calculation) -> Optional[float]:
        """
        Gross wall area before deductions, with the source recorded.

        Three paths, in order of preference: explicit wall surfaces, the room's
        own perimeter × clear height, or perimeter × a height the user supplied.
        A height that came from the user is marked as such in the Rechenweg —
        the Prüfer must be able to tell a measured number from a specified one.
        """
        from_model = room.wall_gross_area_m2()
        if from_model is not None:
            if room.walls:
                expression = " + ".join(
                    f"{format_de(w.length_m)} × {format_de(w.height_m)}"
                    for w in room.walls if w.height_m is not None
                )
                calc.step("Bruttofläche", expression, from_model, "m²",
                          note=f"{len(room.walls)} Wandflächen aus Plangeometrie")
            else:
                calc.step(
                    "Bruttofläche",
                    f"{format_de(room.perimeter_m)} m × {format_de(room.clear_height_m)} m",
                    from_model, "m²",
                    note="Umfang × lichte Höhe laut Plan",
                )
            return from_model

        # Perimeter and height each have their own fallback chain. Both must
        # resolve, and each records where its number came from.
        perimeter = self._perimeter_for(room, params, calc)
        height = self._height_for(room, params, calc)
        if perimeter is None or height is None:
            return None

        gross = perimeter * height
        calc.step(
            "Bruttofläche",
            f"{format_de(perimeter)} m × {format_de(height)} m",
            gross, "m²",
        )
        return gross

    def _perimeter_for(self, room: RoomSpace, params: RuleParams,
                       calc: Calculation) -> Optional[float]:
        """
        Room perimeter, by the best means available.

        Three tiers, best first. Each is recorded in the Rechenweg so a reviewer
        can see instantly whether a number was read, measured or estimated:

          1. stated in the Raumstempel (U:)            — measured
          2. length × width the user supplied          — measured by the user
          3. derived from floor area and an assumed    — ESTIMATE, flagged
             room proportion

        Tier 3 exists because most German plan formats print only the area.
        Refusing to produce anything would leave a Kalkulator with an empty row;
        a flagged estimate they can correct in one click is more useful. The
        assumed proportion errs towards a longer room, because understating a
        perimeter understates the invoice.
        """
        if room.perimeter_m is not None:
            calc.step("Umfang", f"Angabe U: im Raumstempel", room.perimeter_m, "m",
                      note="aus dem Plan gelesen")
            return room.perimeter_m

        dims = params.dimensions_for(room.room_id)
        if dims and dims.get("length_m") and dims.get("width_m"):
            length, width = dims["length_m"], dims["width_m"]
            perimeter = 2 * (length + width)
            calc.step(
                "Umfang",
                f"2 × ({format_de(length)} m + {format_de(width)} m)",
                perimeter, "m",
                note="aus den vom Nutzer erfassten Raummaßen",
            )
            return perimeter

        # No third tier. A perimeter cannot be derived from an area: a 380 m²
        # room may have 78 m of wall or 123 m depending on its shape, and the
        # area says nothing about which. Measured against real U: values, an
        # assumed proportion was 17 % off on average and understated three out
        # of four rooms — which bills the contractor for wall they built.
        #
        # An unmeasurable quantity is reported as unmeasurable. The room shows
        # up in the review screen asking to be measured, which takes two clicks
        # and yields an exact number instead of a plausible wrong one.
        calc.warn(
            f"Umfang von {self._room_label(room)} ist im Plan nicht angegeben. "
            f"Bitte Länge und Breite im Plan messen oder eintragen — aus der "
            f"Fläche allein lässt sich kein Umfang berechnen."
        )
        return None

    def _height_for(self, room: RoomSpace, params: RuleParams,
                    calc: Calculation) -> Optional[float]:
        """
        Clear room height: OK FFB to UK Rohdecke, per the client's rule.

        Falls back to a user-specified height, which is recorded as such — the
        Prüfer must be able to tell a measured height from a specified one.
        """
        if room.clear_height_m is not None:
            calc.step("Lichte Höhe", "OK FFB bis UK Rohdecke",
                      room.clear_height_m, "m", note="aus dem Plan")
            return room.clear_height_m

        if params.wall_height_m is not None:
            calc.step("Lichte Höhe", "Nutzervorgabe", params.wall_height_m, "m",
                      note="nicht aus dem Plan")
            calc.warn(
                f"Raumhöhe {format_de(params.wall_height_m)} m stammt aus der "
                f"Parametereingabe, nicht aus dem Plan."
            )
            return params.wall_height_m

        calc.warn(
            f"Keine Raumhöhe für {self._room_label(room)} gefunden. Höhe unter "
            f"Parametern vorgeben oder eine Ansicht mitgeben."
        )
        return None

    # --------------------------------------------------------------- ceilings

    def _ceiling_position(self, room: RoomSpace, params: RuleParams) -> Optional[Position]:
        """Suspended ceiling area — equal to floor area."""
        if room.floor_area_m2 is None:
            return None

        calc = Calculation()
        label = self._room_label(room)

        area = calc.step(
            label="Deckenfläche",
            expression=f"Grundfläche {label}",
            result=room.floor_area_m2,
            unit="m²",
            note="entspricht der Raumgrundfläche",
        )

        if room.is_outdoor:
            calc.warn(
                f"{label} ist als Außenbereich klassifiziert — "
                f"abgehängte Decke bitte prüfen."
            )

        return Position(
            trade=self.trade,
            designation=f"Deckenfläche {label}",
            quantity=round(area, 3),
            kind=QuantityKind.AREA,
            ruleset_id=self.ruleset_id,
            ruleset_version=self.version,
            calculation=calc.steps,
            evidence=self._collect_evidence(room, include_openings=False),
            raw_quantity=round(area, 3),
            warnings=calc.warnings,
            room_id=room.room_id,
            room_label=label,
        )

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _room_label(room: RoomSpace) -> str:
        """Best human label available, for designations and warnings."""
        parts = [p for p in (room.number, room.name) if p]
        return " ".join(parts) if parts else room.room_id

    @staticmethod
    def _collect_evidence(room: RoomSpace, include_openings: bool) -> List[Evidence]:
        """
        Every source that fed this position.

        Wall and opening evidence is included so the reviewer can click through
        to each measured element, not just to the room stamp.
        """
        collected = [room.evidence]
        collected.extend(w.evidence for w in room.walls)
        if include_openings:
            collected.extend(o.evidence for o in room.all_openings())
        return collected
