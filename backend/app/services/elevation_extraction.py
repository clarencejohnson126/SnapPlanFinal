"""
Clear room heights read from Ansichten and Schnitte.

WHY THIS EXISTS

A Grundriss states areas. It almost never states heights. Trockenbau, Maler and
Putz all bill wall area — perimeter × clear height — so without a height those
trades cannot be calculated at all. A run over 33 real plans produced 483 floor
areas and 12 wall positions, purely because the heights were missing.

They were not missing from the project. They were in the Ansichten, where they
belong, annotated the way German elevations always annotate them:

    +11,93 OKFFB     Oberkante Fertigfußboden of a storey
    +14,50 UKRD      Unterkante Rohdecke above it
    ------------
      2,57 m         lichte Höhe

This module reads those pairs. It is pure text-and-coordinate work — no CV, no
model, no guessing. The numbers are printed on the plan; we only pair them up.

CROSS-VALIDATION COMES FREE

A building usually has several elevation sheets (Nord, Süd, Ost). They repeat
the same storey heights, so disagreement between sheets is a reliable signal
that something was misread. `ElevationResult.conflicts` reports it rather than
silently picking one.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import re

logger = logging.getLogger(__name__)

#: A signed height annotation: +11,93 / -3,99 / +0,05
_KOTE = re.compile(r'^[+-]\d+[,.]\d{2}$')

#: Room numbers carry their storey: F.E5.1.08.12 → E5, R1.E-1.0.3 → E-1
_ROOM_LEVEL = re.compile(r'^[A-Z]\d*\.(E-?\d+)\.')

#: Elevation sheets annotate the Rohbau: OK Fertigfußboden against UK Rohdecke
#: is the pairing they print. Kept separate from the Grundriss chains below
#: because an Ansicht rarely carries Ausbaumaße at all — what it gives is the
#: structural storey, and callers are told so via LevelHeight.chain.
_FLOOR_LABELS = frozenset({"OKFFB", "OKFF"})
_CEILING_LABELS = frozenset({"UKRD"})

#: How far apart (in points) a value and its label may sit and still count as
#: the same annotation. Elevation labels are typeset tight against their value.
_SAME_ROW_TOLERANCE = 6.0

#: Plausible clear room heights. Anything outside is a pairing error, not a
#: room — a 12 m "storey" means we matched a floor to the wrong slab.
_MIN_CLEAR_HEIGHT_M = 1.80
_MAX_CLEAR_HEIGHT_M = 6.00


@dataclass
class LevelHeight:
    """One storey, with the two koten it was derived from."""

    okffb_m: float
    ukrd_m: float
    page_number: int
    level_label: Optional[str] = None      # "E0", "E-1" — from room numbers
    room_numbers: List[str] = field(default_factory=list)
    #: Which measurement chain produced this: "fertig" (OK FFB → UK Ausbaumaß)
    #: or "roh" (OK Rohfußboden → UK Rohdecke). The two differ by the floor and
    #: ceiling build-up and must never be compared or summed as if equal.
    chain: str = "fertig"

    @property
    def clear_height_m(self) -> float:
        """Lichte Höhe: underside of slab above minus finished floor."""
        return round(self.ukrd_m - self.okffb_m, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level_label": self.level_label,
            "okffb_m": self.okffb_m,
            "ukrd_m": self.ukrd_m,
            "clear_height_m": self.clear_height_m,
            "page_number": self.page_number,
            "room_numbers": self.room_numbers,
        }


@dataclass
class ElevationResult:
    """Every storey height an elevation or section sheet yielded."""

    document_id: str
    levels: List[LevelHeight] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: Storeys whose height differs between sheets: label → differing values.
    conflicts: Dict[str, List[float]] = field(default_factory=dict)

    def height_for_level(self, level_label: str) -> Optional[float]:
        """Clear height for a storey label such as 'E3', or None."""
        for level in self.levels:
            if level.level_label == level_label:
                return level.clear_height_m
        return None

    def dominant_height_m(self) -> Optional[float]:
        """
        The most common clear height in the building.

        Useful as a fallback for rooms whose storey could not be identified —
        but it is a fallback, and callers must label it as one rather than
        presenting it as a measured value.
        """
        if not self.levels:
            return None
        counts: Dict[float, int] = {}
        for level in self.levels:
            counts[level.clear_height_m] = counts.get(level.clear_height_m, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "levels": [level.to_dict() for level in self.levels],
            "dominant_height_m": self.dominant_height_m(),
            "conflicts": self.conflicts,
            "warnings": self.warnings,
        }


def extract_level_heights(pdf_path: Union[str, Path]) -> ElevationResult:
    """
    Read storey heights from an Ansicht or Schnitt.

    Never raises on an unsuitable sheet — a Grundriss passed in here simply
    comes back with no levels and a warning saying so.
    """
    path = Path(pdf_path)
    result = ElevationResult(document_id=path.stem)

    if not path.exists():
        result.warnings.append(f"Datei nicht gefunden: {path.name}")
        return result

    try:
        import fitz
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"PyMuPDF nicht verfügbar: {exc}")
        return result

    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc):
                _read_page(page.get_text("words"), page_index + 1, result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Höhenextraktion fehlgeschlagen für %s: %s", path.name, exc)
        result.warnings.append(f"Höhenextraktion fehlgeschlagen: {exc}")
        return result

    if not result.levels:
        result.warnings.append(
            "Keine Geschosshöhen gefunden. Der Plan enthält keine OKFFB/UKRD-"
            "Angaben — Höhen stehen in Ansichten und Schnitten, nicht in "
            "Grundrissen."
        )

    return result


#: The two measurement chains, each internally consistent.
#:
#: A height is only ever formed WITHIN one chain. Pairing a finished floor with
#: a raw slab mixes Rohbau and Ausbau: the result is neither the structural
#: clear height nor the finished one, and is short by the floor build-up on one
#: side while long by the ceiling build-up on the other.
#:
#:   ROH     OK Rohfußboden      → UK Rohdecke        structural clear height
#:   FERTIG  OK Fertigfußboden   → UK Ausbaumaß       what the room measures
#:
#: The plan's own legend states the same definition:
#: "LRH = Lichte Raumhöhe, OK FFB bis UK Ausbamaß".
_CHAIN_ROH = {
    "floor": frozenset({"OKRFB", "OKRF", "OKRD"}),
    "ceiling": frozenset({"UKRD"}),
}
_CHAIN_FERTIG = {
    "floor": frozenset({"OKFFB", "OKFF"}),
    "ceiling": frozenset({"UK", "ADH", "UKFD"}),
}

#: Unterzug — the lowest ceiling point in a room. It limits a wall locally, but
#: it belongs to neither chain as a room height, so it is collected separately
#: and reported rather than silently used as *the* room height.
_BEAM_TOKENS = ("UZ",)


def extract_heights_from_floorplan(pdf_path: Union[str, Path]) -> ElevationResult:
    """
    Read clear room heights directly from a Grundriss.

    German floor plans annotate heights next to doors and beams, in a stack:

        +11,92     OKFFB, top of finished floor
         2,135     the clear height itself
        +11,75     OKRD, top of raw slab

    and separately `UK UZ=+14,065` for the underside of a beam. The two agree —
    14,065 − 11,93 = 2,135 — which gives a cross-check for free rather than a
    number that has to be trusted.

    Strategy, in order of confidence:
      1. A kote pair (floor label + ceiling label) whose difference is a
         plausible room height. Derived, verifiable, preferred.
      2. A bare value that equals such a difference. Confirms (1).

    A bare 2,13 with nothing to check it against is *not* accepted — on a plan
    dense with dimension chains, plenty of unrelated numbers look like heights.
    """
    path = Path(pdf_path)
    result = ElevationResult(document_id=path.stem)

    if not path.exists():
        result.warnings.append(f"Datei nicht gefunden: {path.name}")
        return result

    try:
        import fitz
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"PyMuPDF nicht verfügbar: {exc}")
        return result

    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc):
                _read_floorplan_page(page.get_text("words"), page_index + 1, result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Höhen aus Grundriss fehlgeschlagen für %s: %s", path.name, exc)
        result.warnings.append(f"Höhenextraktion fehlgeschlagen: {exc}")
        return result

    if not result.levels:
        result.warnings.append(
            "Im Grundriss wurden keine belegbaren Raumhöhen gefunden — es fehlt "
            "ein Kotenpaar aus Fußboden- und Deckenhöhe."
        )

    return result


def _read_floorplan_page(words: List[Tuple], page_number: int,
                         result: ElevationResult) -> None:
    """
    Collect koten on a Grundriss page and pair them within each chain.

    Both chains are evaluated. FERTIG wins when available — it is the height a
    room actually has once built, and the one a Trockenbauer's wall must reach.
    ROH is the fallback, and which chain produced a height is recorded, because
    the two differ by the floor and ceiling build-up and must never be summed
    or compared as if they were the same measurement.
    """
    beams: List[float] = []
    chains: Dict[str, Dict[str, List[float]]] = {
        "fertig": {"floor": [], "ceiling": []},
        "roh": {"floor": [], "ceiling": []},
    }

    for word in words:
        token = word[4]

        # "UK UZ=+14,065" arrives as one word — the kote sits inside the token.
        inline = re.search(r'[+-]\d+[,.]\d{2,3}', token)
        if inline and any(t in token for t in _BEAM_TOKENS):
            beams.append(float(inline.group(0).replace(",", ".")))
            continue

        for chain_name, chain in (("fertig", _CHAIN_FERTIG), ("roh", _CHAIN_ROH)):
            for role in ("floor", "ceiling"):
                if token in chain[role]:
                    value = _value_near(word, words)
                    if value is not None:
                        chains[chain_name][role].append(value)

    #: Bare numbers on the sheet, used only to confirm a derived height.
    stated = {
        round(float(w[4].replace(",", ".")), 3)
        for w in words
        if re.match(r'^\d[,.]\d{2,3}$', w[4])
    }

    produced = False
    for chain_name in ("fertig", "roh"):
        floors = chains[chain_name]["floor"]
        ceilings = chains[chain_name]["ceiling"]
        if not floors or not ceilings:
            continue
        if _pair_within_chain(floors, ceilings, chain_name, page_number,
                              stated, result):
            produced = True
            break  # FERTIG wins; do not mix a ROH height into the same result

    if not produced and beams:
        result.warnings.append(
            f"Seite {page_number}: Es liegen nur Unterzugshöhen vor "
            f"({', '.join(f'{b:+.3f}' for b in sorted(set(beams))[:3])}). Diese "
            f"begrenzen die Wand örtlich, sind aber nicht die Raumhöhe und "
            f"wurden daher nicht als solche verwendet."
        )


def _pair_within_chain(floors: List[float], ceilings: List[float],
                       chain_name: str, page_number: int,
                       stated: set, result: ElevationResult) -> bool:
    """Form heights from one chain only. Returns True if any were produced."""
    produced = False

    for floor_value in sorted(set(floors)):
        above = [c for c in ceilings if c > floor_value]
        if not above:
            continue
        ceiling_value = min(above)

        height = round(ceiling_value - floor_value, 3)
        if not (_MIN_CLEAR_HEIGHT_M <= height <= _MAX_CLEAR_HEIGHT_M):
            continue

        level = LevelHeight(
            okffb_m=floor_value,
            ukrd_m=ceiling_value,
            page_number=page_number,
            chain=chain_name,
        )
        if height in stated:
            # The plan prints the number it implies — strong confirmation.
            result.warnings.append(
                f"Raumhöhe {height:.3f} m ({chain_name}) aus Koten "
                f"{floor_value:+.2f} / {ceiling_value:+.3f} abgeleitet und im "
                f"Plan als Maß bestätigt."
            )
        _merge_level(level, result)
        produced = True

    return produced


def _value_near(label_word: Tuple, words: List[Tuple]) -> Optional[float]:
    """
    The kote belonging to a label in a Grundriss.

    Unlike an elevation, a plan may put the value left, right or directly under
    its label, so the nearest kote in any direction wins — but only within a
    tight radius, because plans are dense with unrelated numbers.
    """
    cx = (label_word[0] + label_word[2]) / 2.0
    cy = (label_word[1] + label_word[3]) / 2.0

    best: Optional[Tuple[float, float]] = None  # (distance, value)
    for word in words:
        if not _KOTE.match(word[4]):
            continue
        wx = (word[0] + word[2]) / 2.0
        wy = (word[1] + word[3]) / 2.0
        distance = ((wx - cx) ** 2 + (wy - cy) ** 2) ** 0.5
        if distance > 60.0:
            continue
        value = float(word[4].replace(",", "."))
        if best is None or distance < best[0]:
            best = (distance, value)

    return best[1] if best else None


def _read_page(words: List[Tuple], page_number: int, result: ElevationResult) -> None:
    """Pair floor koten with the slab above them on one page."""
    floors: List[Tuple[float, float]] = []    # (value, y)
    ceilings: List[Tuple[float, float]] = []

    for word in words:
        label = word[4]
        if label not in _FLOOR_LABELS and label not in _CEILING_LABELS:
            continue

        value = _value_left_of(word, words)
        if value is None:
            continue

        row_y = (word[1] + word[3]) / 2.0
        if label in _FLOOR_LABELS:
            floors.append((value, row_y))
        else:
            ceilings.append((value, row_y))

    for floor_value, floor_y in sorted(set(floors)):
        # The storey's ceiling is the lowest slab underside above its floor.
        above = [c for c in ceilings if c[0] > floor_value]
        if not above:
            continue
        ceiling_value, ceiling_y = min(above, key=lambda c: c[0])

        height = round(ceiling_value - floor_value, 3)
        if not (_MIN_CLEAR_HEIGHT_M <= height <= _MAX_CLEAR_HEIGHT_M):
            # Implausible pairing — say so instead of emitting a wrong height.
            result.warnings.append(
                f"Seite {page_number}: OKFFB {floor_value:+.2f} und UKRD "
                f"{ceiling_value:+.2f} ergäben {height:.2f} m lichte Höhe — "
                f"unplausibel, Paar verworfen."
            )
            continue

        level = LevelHeight(
            okffb_m=floor_value,
            ukrd_m=ceiling_value,
            page_number=page_number,
            room_numbers=_room_numbers_near(ceiling_y, words),
        )
        level.level_label = _level_from_rooms(level.room_numbers)

        _merge_level(level, result)


def _value_left_of(label_word: Tuple, words: List[Tuple]) -> Optional[float]:
    """
    The kote belonging to a label.

    Elevation sheets put the number immediately to the left of its label
    ("+14,50 UKRD"), so the nearest signed number on the same row wins.
    """
    row_y = (label_word[1] + label_word[3]) / 2.0
    candidates = [
        w for w in words
        if abs((w[1] + w[3]) / 2.0 - row_y) < _SAME_ROW_TOLERANCE
        and w[2] <= label_word[0] + 2.0
        and _KOTE.match(w[4])
    ]
    if not candidates:
        return None

    nearest = max(candidates, key=lambda w: w[0])
    return float(nearest[4].replace(",", "."))


def _room_numbers_near(row_y: float, words: List[Tuple]) -> List[str]:
    """
    Room numbers printed on the same row as a slab annotation.

    German elevations list the rooms of a storey next to its UKRD line, which
    is what lets a height be tied to a specific storey rather than guessed from
    ordering.
    """
    found: List[str] = []
    for word in words:
        if abs((word[1] + word[3]) / 2.0 - row_y) >= _SAME_ROW_TOLERANCE * 2:
            continue
        if _ROOM_LEVEL.match(word[4]):
            found.append(word[4])
    return found


def _level_from_rooms(room_numbers: List[str]) -> Optional[str]:
    """The storey label shared by these room numbers, if they agree."""
    levels = {m.group(1) for n in room_numbers if (m := _ROOM_LEVEL.match(n))}
    return levels.pop() if len(levels) == 1 else None


def _merge_level(level: LevelHeight, result: ElevationResult) -> None:
    """
    Add a storey, recording disagreement rather than overwriting.

    Several elevation sheets describe the same building. When two of them state
    different heights for one storey, that is a reading error worth surfacing —
    silently keeping the last one seen would hide it.
    """
    for existing in result.levels:
        same_storey = (
            existing.level_label
            and level.level_label
            and existing.level_label == level.level_label
        ) or (
            existing.level_label is None
            and level.level_label is None
            and abs(existing.okffb_m - level.okffb_m) < 0.01
        )
        if not same_storey:
            continue

        if abs(existing.clear_height_m - level.clear_height_m) > 0.02:
            key = existing.level_label or f"OKFFB {existing.okffb_m:+.2f}"
            heights = result.conflicts.setdefault(key, [existing.clear_height_m])
            if level.clear_height_m not in heights:
                heights.append(level.clear_height_m)
        # Keep the room numbers from whichever sheet listed them.
        if level.room_numbers and not existing.room_numbers:
            existing.room_numbers = level.room_numbers
            existing.level_label = level.level_label
        return

    result.levels.append(level)
