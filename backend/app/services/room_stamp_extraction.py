"""
Raumstempel read by position, not by line order.

WHY THIS REPLACES THE LINE-BASED PATH

`unified_extraction` walks the page's text line by line: find a room number,
then scan the following lines for its values. On real plans that is wrong, and
wrong in the most damaging way — silently.

    [1312] 'F= 12.14 m²'      the values of B.02.1.105
    [1313] 'LRH= 3.17 m'
    [1314] 'B.02.1.105'       the number comes AFTER them
    ...
    [1326] 'F= 6.06 m²'       the values of the NEXT room
    [1329] 'B.02.1.108'

Scanning forward from the number picks up the next room's values. Every area is
shifted by one room, and nothing about the output looks broken: 47 rooms, 47
plausible areas, all belonging to the wrong rooms. Found on
SPA-ARC-5-GR-BS-02, where B.02.1.105 was reported as 6,06 m² instead of 12,14.

Text order in a PDF follows the drawing order of the CAD export. It carries no
meaning. Position does: a Raumstempel is a tight block of lines, and every
value in it sits within a few points of its room number.

THE RULE THAT MAKES IT SAFE

A value belongs to the *nearest* room number. Not the one above it, not the one
before it in the text — the nearest. Where two stamps sit close together, that
is the only assignment that cannot silently swap them.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import re

logger = logging.getLogger(__name__)

#: Room number formats seen across the three reference projects.
#:   B.02.1.105      LeiQ / SPA
#:   R1.E-1.0.3      Haardtring, incl. basement levels
#:   B.E-1.0.26      Haardtring, letter-only building prefix
#:   33_b6.12        Omniturm
#:   BT1.EG.001      Omniturm building parts
_ROOM_NUMBER = re.compile(
    r'^(?:'
    r'[A-Z]\d*\.E-?\d+(?:\.\d+){2,3}'      # R1.E-1.0.3 / B.E-1.0.26
    r'|[A-Z]\.\d{2}\.\d+\.[A-Z]?\d+'       # B.02.1.105
    r'|\d+_[a-z]\d+\.\d+'                  # 33_b6.12
    r'|BT\d+\.[A-Z0-9]+\.\d+'              # BT1.EG.001
    r')$'
)

#: Area, perimeter and height labels. Both ":" and "=" appear, and the decimal
#: separator is a comma on some sheets and a dot on others — the same project
#: uses both, so neither may be assumed.
_AREA = re.compile(r'^(?:NRF|NGF|BGF|F)\s*[:=]', re.IGNORECASE)
_PERIMETER = re.compile(r'^U\s*[:=]', re.IGNORECASE)
_HEIGHT = re.compile(r'^(?:LRH|LH)\s*[:=]', re.IGNORECASE)
_NUMBER = re.compile(r'([\d]+[.,][\d]+|[\d]+)')

#: How far from a room number its stamp lines may sit, in PDF points. A stamp is
#: typeset tightly; beyond this a word belongs to another room or to the drawing.
_STAMP_RADIUS_X = 90.0
_STAMP_RADIUS_Y = 55.0

#: Vertical spacing within which words count as the same visual line.
_LINE_TOLERANCE = 2.5

#: Horizontal spacing within which words count as the same column. Rotated
#: stamps put a label and its value on one x, offset by a couple of points
#: because the label is wider than the number.
_COLUMN_TOLERANCE = 4.0

#: How far a value may sit from its label, in points. Beyond this it belongs to
#: another line of the stamp or to the drawing.
_VALUE_MAX_DISTANCE = 22.0


@dataclass
class RoomStamp:
    """One room as its stamp states it."""

    number: str
    page_number: int
    bbox: Tuple[float, float, float, float]      # of the room number itself
    name: Optional[str] = None
    area_m2: Optional[float] = None
    perimeter_m: Optional[float] = None
    clear_height_m: Optional[float] = None
    #: The stamp's lines verbatim, so a reviewer can compare against the plan.
    raw_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "area_m2": self.area_m2,
            "perimeter_m": self.perimeter_m,
            "clear_height_m": self.clear_height_m,
            "page_number": self.page_number,
            "bbox": list(self.bbox),
            "raw_lines": self.raw_lines,
        }


@dataclass
class StampResult:
    document_id: str
    stamps: List[RoomStamp] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "stamps": [s.to_dict() for s in self.stamps],
            "count": len(self.stamps),
            "with_area": sum(1 for s in self.stamps if s.area_m2 is not None),
            "with_perimeter": sum(1 for s in self.stamps if s.perimeter_m is not None),
            "with_height": sum(1 for s in self.stamps if s.clear_height_m is not None),
            "warnings": self.warnings,
        }


def extract_room_stamps(pdf_path: Union[str, Path]) -> StampResult:
    """
    Read every Raumstempel on every page, by position.

    Never raises. A plan without stamps returns an empty result with a warning.
    """
    path = Path(pdf_path)
    result = StampResult(document_id=path.stem)

    if not path.exists():
        result.warnings.append(f"Datei nicht gefunden: {path.name}")
        return result

    try:
        import fitz

        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc):
                _read_page(page.get_text("words"), page_index + 1, result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Raumstempel-Extraktion fehlgeschlagen für %s: %s", path.name, exc)
        result.warnings.append(f"Raumstempel konnten nicht gelesen werden: {exc}")
        return result

    if not result.stamps:
        result.warnings.append(
            "Keine Raumstempel gefunden — der Plan hat womöglich keine Textebene "
            "oder ein unbekanntes Nummernformat."
        )

    return result


def _read_page(words: List[Tuple], page_number: int, result: StampResult) -> None:
    """Find the room numbers on a page and claim the lines around each."""
    numbers = [w for w in words if _ROOM_NUMBER.match(w[4])]
    if not numbers:
        return

    centres = [((w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0) for w in numbers]

    for index, number_word in enumerate(numbers):
        cx, cy = centres[index]

        # Words close enough to be part of this stamp — and closer to this room
        # number than to any other. The second condition is what prevents two
        # adjacent stamps from stealing each other's values.
        claimed = []
        for word in words:
            wx, wy = (word[0] + word[2]) / 2.0, (word[1] + word[3]) / 2.0
            if abs(wx - cx) > _STAMP_RADIUS_X or abs(wy - cy) > _STAMP_RADIUS_Y:
                continue
            if _nearest_number_index(wx, wy, centres) != index:
                continue
            claimed.append(word)

        result.stamps.append(_parse_stamp(number_word, claimed, page_number))


def _nearest_number_index(x: float, y: float,
                          centres: List[Tuple[float, float]]) -> int:
    """Index of the room number closest to a point."""
    best_index = 0
    best_distance = float("inf")
    for index, (cx, cy) in enumerate(centres):
        distance = (x - cx) ** 2 + (y - cy) ** 2
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _parse_stamp(number_word: Tuple, claimed: List[Tuple],
                 page_number: int) -> RoomStamp:
    """
    Turn the words of one stamp into a RoomStamp.

    Values are read per label word, not per line. Building lines first fails on
    real sheets, because unrelated annotations share the stamp's y coordinates:

        'U= 14.90 m Stütze 28 = +7.60 LRH= 3.17 m BT'

    Here "Stütze" and a level kote sit on the same line as two different room
    values, so a line-anchored pattern finds U= but never LRH=. Anchoring on the
    label word and taking the number immediately to its right is immune to that.
    """
    stamp = RoomStamp(
        number=number_word[4],
        page_number=page_number,
        bbox=(number_word[0], number_word[1], number_word[2], number_word[3]),
        raw_lines=_group_into_lines(claimed),
    )

    stamp.area_m2 = _value_after_label(claimed, _AREA)
    stamp.perimeter_m = _value_after_label(claimed, _PERIMETER)
    stamp.clear_height_m = _value_after_label(claimed, _HEIGHT)
    stamp.name = _room_name(number_word, claimed)

    return stamp


def _value_after_label(words: List[Tuple], label: re.Pattern) -> Optional[float]:
    """
    The number belonging to a label word.

    STAMPS COME IN TWO ORIENTATIONS AND BOTH OCCUR ON THE SAME SHEET

    Upright, the value sits to the right of its label on one baseline:

        F=  12.14  m²          same y, increasing x

    Rotated 90° — used for narrow rooms — the text runs vertically, so in page
    coordinates the value sits *below* its label on one x:

        U=    x=3319 y=1428.9
        34.17 x=3317 y=1441.5      same x, increasing y

    Reading only left-to-right found 21 of 54 rooms on SPA-ARC-5-GR-BS-02 and
    silently dropped every rotated stamp. Both directions are searched, nearest
    match wins, and a label may also arrive with its value fused ("F=12.14").
    """
    for word in words:
        if not label.match(word[4]):
            continue

        inline = _value_in(word[4])
        if inline is not None:
            return inline

        label_x = (word[0] + word[2]) / 2.0
        label_y = (word[1] + word[3]) / 2.0

        best: Optional[Tuple[float, float]] = None  # (distance, value)
        for other in words:
            if other is word:
                continue
            parsed = _parse_number(other[4])
            if parsed is None:
                continue

            other_x = (other[0] + other[2]) / 2.0
            other_y = (other[1] + other[3]) / 2.0

            # Upright: same baseline, to the right.
            if abs(other_y - label_y) <= _LINE_TOLERANCE and other[0] >= word[2] - 1.0:
                distance = other[0] - word[2]
            # Rotated: same column, below.
            elif abs(other_x - label_x) <= _COLUMN_TOLERANCE and other_y > label_y:
                distance = other_y - label_y
            else:
                continue

            if distance > _VALUE_MAX_DISTANCE:
                continue
            if best is None or distance < best[0]:
                best = (distance, parsed)

        if best is not None:
            return best[1]

    return None


def _room_name(number_word: Tuple, words: List[Tuple]) -> Optional[str]:
    """
    The room's name — the alphabetic words on the line just below its number.

    Restricted to that one line because the stamp's neighbourhood also contains
    structural labels ("Stütze", "HOB") that would otherwise be mistaken for it.
    """
    number_y = (number_word[1] + number_word[3]) / 2.0
    number_x = (number_word[0] + number_word[2]) / 2.0

    below = [
        word for word in words
        if 0 < (word[1] + word[3]) / 2.0 - number_y <= 9.0
        and abs((word[0] + word[2]) / 2.0 - number_x) <= 45.0
    ]
    if not below:
        return None

    line_y = min((word[1] + word[3]) / 2.0 for word in below)
    same_line = sorted(
        (w for w in below if abs((w[1] + w[3]) / 2.0 - line_y) <= _LINE_TOLERANCE),
        key=lambda w: w[0],
    )

    parts = [
        word[4] for word in same_line
        if any(character.isalpha() for character in word[4])
        and not re.match(r'^(?:F|U|NRF|NGF|BGF|LRH|LH|OK|UK|BT|HOB|XX)\b',
                         word[4], re.IGNORECASE)
    ]
    name = " ".join(parts).strip()
    return name if _looks_like_name(name) else None


def _parse_number(token: str) -> Optional[float]:
    """Parse a bare dimension token, tolerating either decimal separator."""
    cleaned = token.replace("m²", "").replace("m2", "").replace("m", "").strip()
    match = _NUMBER.search(cleaned)
    if not match:
        return None
    normalised = match.group(1).replace(",", ".")
    if normalised.count(".") > 1:
        return None
    try:
        return float(normalised)
    except ValueError:
        return None


def _group_into_lines(words: List[Tuple]) -> List[str]:
    """
    Reassemble words into visual lines.

    Necessary because "F= 12.14 m²" reaches us as three separate words, and a
    label without its value is useless.
    """
    if not words:
        return []

    ordered = sorted(words, key=lambda w: ((w[1] + w[3]) / 2.0, w[0]))
    lines: List[str] = []
    current: List[Tuple] = [ordered[0]]

    for word in ordered[1:]:
        previous_y = (current[-1][1] + current[-1][3]) / 2.0
        current_y = (word[1] + word[3]) / 2.0
        if abs(current_y - previous_y) <= _LINE_TOLERANCE:
            current.append(word)
        else:
            lines.append(" ".join(w[4] for w in current))
            current = [word]

    lines.append(" ".join(w[4] for w in current))
    return lines


def _value_in(text: str) -> Optional[float]:
    """
    The number following a label such as "F=" or "NRF:".

    Handles both decimal separators. German plans use the comma, but CAD exports
    frequently write the dot — the SPA sheets say "F= 12.14 m²" while other LeiQ
    sheets say "NRF: 24,35 m2", so both must parse.
    """
    tail = re.split(r'[:=]', text, maxsplit=1)
    if len(tail) < 2:
        return None

    match = _NUMBER.search(tail[1])
    if not match:
        return None

    normalised = match.group(1).replace(",", ".")
    if normalised.count(".") > 1:
        return None
    try:
        return float(normalised)
    except ValueError:
        return None


def _looks_like_name(text: str) -> bool:
    """Whether a stamp line is plausibly the room's name."""
    if not (3 <= len(text) <= 40):
        return False
    if not any(character.isalpha() for character in text):
        return False
    # Reject label lines and drawing annotations sharing the stamp's area.
    return not re.match(
        r'^(?:F|U|NRF|NGF|BGF|LRH|LH|OK|UK|BT|HOB|XX)\b', text, re.IGNORECASE
    )
