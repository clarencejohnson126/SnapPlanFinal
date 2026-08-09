"""
Raw quantities — the output of Schicht 1, the input of Schicht 2.

THE CONTRACT: this module knows nothing about Gewerke.

Nothing here may apply an Übermessungsregel, an Abzug, a Zulage, or an outdoor
factor. Those are Abrechnung rules and they live in app/rules/. What this layer
reports is what is geometrically and textually *in the document*:

    "This room's floor area is 24.35 m², its perimeter is 20.08 m, it contains
     one 0.885 × 2.010 m door, and it is called Dachterrasse."

Whether that Dachterrasse counts at 100 % or 50 %, and whether the door gets
deducted or übermessen, is not this layer's business. Keeping that line clean is
what lets one extraction serve every trade.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from app.domain.evidence import Evidence


class QuantityKind(str, Enum):
    """Physical kind of a measured value, with its canonical unit."""

    LENGTH = "length"        # m
    AREA = "area"            # m²
    VOLUME = "volume"        # m³
    COUNT = "count"          # Stk
    HEIGHT = "height"        # m
    PERIMETER = "perimeter"  # m


UNIT_BY_KIND: Dict[QuantityKind, str] = {
    QuantityKind.LENGTH: "m",
    QuantityKind.AREA: "m²",
    QuantityKind.VOLUME: "m³",
    QuantityKind.COUNT: "Stk",
    QuantityKind.HEIGHT: "m",
    QuantityKind.PERIMETER: "m",
}


class OpeningKind(str, Enum):
    """What kind of hole this is. Trades treat them differently."""

    DOOR = "door"
    WINDOW = "window"
    PASSAGE = "passage"    # Durchgang without a door leaf
    NICHE = "niche"        # Nische
    UNKNOWN = "unknown"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class Opening:
    """
    A hole in a wall: door, window, passage.

    Both dimensions are optional because plans are inconsistent — a Türstempel
    may give 0.885/2.010 while a window exists only as vector geometry with no
    annotation. Rules must handle a missing area rather than assume one.
    """

    kind: OpeningKind
    evidence: Evidence
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    label: Optional[str] = None            # "T-101", "F3"
    wall_id: Optional[str] = None          # which WallSurface it sits in
    room_id: Optional[str] = None
    opening_id: str = field(default_factory=lambda: _new_id("op"))
    attributes: Dict[str, Any] = field(default_factory=dict)  # e.g. fire rating

    @property
    def area_m2(self) -> Optional[float]:
        """Opening area, or None when either dimension is unknown."""
        if self.width_m is None or self.height_m is None:
            return None
        return self.width_m * self.height_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opening_id": self.opening_id,
            "kind": self.kind.value,
            "label": self.label,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "area_m2": self.area_m2,
            "wall_id": self.wall_id,
            "room_id": self.room_id,
            "attributes": self.attributes,
            "evidence": self.evidence.to_dict(),
        }


@dataclass
class WallSurface:
    """
    One wall face, as measured. Gross — before any Abzug.

    Openings attach here rather than to the room so a ruleset can decide per
    surface.
    """

    length_m: float
    evidence: Evidence
    height_m: Optional[float] = None
    room_id: Optional[str] = None
    label: Optional[str] = None
    openings: List[Opening] = field(default_factory=list)
    is_exterior: bool = False
    wall_id: str = field(default_factory=lambda: _new_id("wall"))

    @property
    def gross_area_m2(self) -> Optional[float]:
        """Length × height, no deductions. None when height is unknown."""
        if self.height_m is None:
            return None
        return self.length_m * self.height_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wall_id": self.wall_id,
            "label": self.label,
            "room_id": self.room_id,
            "length_m": self.length_m,
            "height_m": self.height_m,
            "gross_area_m2": self.gross_area_m2,
            "is_exterior": self.is_exterior,
            "openings": [o.to_dict() for o in self.openings],
            "evidence": self.evidence.to_dict(),
        }


@dataclass
class RoomSpace:
    """
    A room as the document describes it.

    Two things to note:

    `is_outdoor` and `is_wet_room` are *classifications*, not factors. Schicht 1
    reports "this is called Dachterrasse". Whether that means ×0.5 is a rule and
    lives elsewhere. Resist the urge to pre-apply it here.

    Wall area can come from two sources: explicit `walls`, or `perimeter_m` ×
    `clear_height_m` when the plan only gives U: and LH: (the LeiQ case). Rules
    ask via `wall_gross_area_m2()` and get the better of the two.
    """

    evidence: Evidence
    number: Optional[str] = None          # "B.00.2.002", "R2.E5.3.5"
    name: Optional[str] = None            # "Büro", "Dachterrasse"
    floor_area_m2: Optional[float] = None
    perimeter_m: Optional[float] = None
    clear_height_m: Optional[float] = None
    is_outdoor: bool = False
    is_wet_room: bool = False
    walls: List[WallSurface] = field(default_factory=list)
    openings: List[Opening] = field(default_factory=list)
    room_id: str = field(default_factory=lambda: _new_id("room"))
    attributes: Dict[str, Any] = field(default_factory=dict)

    def wall_gross_area_m2(self) -> Optional[float]:
        """
        Gross wall area for this room.

        Prefers summed explicit walls; falls back to perimeter × clear height.
        Returns None when neither is available — rules must handle that rather
        than silently substituting a default height.
        """
        if self.walls:
            areas = [w.gross_area_m2 for w in self.walls]
            if all(a is not None for a in areas):
                return sum(areas)
        if self.perimeter_m is not None and self.clear_height_m is not None:
            return self.perimeter_m * self.clear_height_m
        return None

    def all_openings(self) -> List[Opening]:
        """Openings attached to the room plus those attached to its walls."""
        collected = list(self.openings)
        for wall in self.walls:
            collected.extend(wall.openings)
        return collected

    def volume_m3(self) -> Optional[float]:
        """Room volume. None when floor area or clear height is unknown."""
        if self.floor_area_m2 is None or self.clear_height_m is None:
            return None
        return self.floor_area_m2 * self.clear_height_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "number": self.number,
            "name": self.name,
            "floor_area_m2": self.floor_area_m2,
            "perimeter_m": self.perimeter_m,
            "clear_height_m": self.clear_height_m,
            "wall_gross_area_m2": self.wall_gross_area_m2(),
            "volume_m3": self.volume_m3(),
            "is_outdoor": self.is_outdoor,
            "is_wet_room": self.is_wet_room,
            "walls": [w.to_dict() for w in self.walls],
            "openings": [o.to_dict() for o in self.openings],
            "attributes": self.attributes,
            "evidence": self.evidence.to_dict(),
        }


@dataclass
class ScaleInfo:
    """Plan scale, and whether we trust it."""

    denominator: Optional[int] = None      # 100 for 1:100
    pixels_per_meter: Optional[float] = None
    source: Optional[str] = None           # "Plankopf", "Maßkette", "manuell"
    confidence: float = 0.0
    is_user_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "denominator": self.denominator,
            "scale_string": f"1:{self.denominator}" if self.denominator else None,
            "pixels_per_meter": self.pixels_per_meter,
            "source": self.source,
            "confidence": self.confidence,
            "is_user_confirmed": self.is_user_confirmed,
        }


@dataclass
class RawModel:
    """
    Everything Schicht 1 could determine about a document. Trade-neutral.

    This is the single object a ruleset receives. If a rule needs something not
    on here, the fix is to extend Schicht 1 — never to have the rule read a PDF
    itself.
    """

    document_id: str
    scale: ScaleInfo = field(default_factory=ScaleInfo)
    rooms: List[RoomSpace] = field(default_factory=list)
    openings: List[Opening] = field(default_factory=list)   # not assigned to a room
    walls: List[WallSurface] = field(default_factory=list)  # not assigned to a room
    warnings: List[str] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)

    def all_openings(self) -> List[Opening]:
        """Every opening in the document, room-attached or free-floating."""
        collected = list(self.openings)
        for room in self.rooms:
            collected.extend(room.all_openings())
        return collected

    def room_by_id(self, room_id: str) -> Optional[RoomSpace]:
        return next((r for r in self.rooms if r.room_id == room_id), None)

    @property
    def is_empty(self) -> bool:
        """True when extraction found nothing to bill. Callers should say so."""
        return not self.rooms and not self.openings and not self.walls

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "scale": self.scale.to_dict(),
            "rooms": [r.to_dict() for r in self.rooms],
            "openings": [o.to_dict() for o in self.openings],
            "walls": [w.to_dict() for w in self.walls],
            "warnings": self.warnings,
            "source_files": self.source_files,
            "is_empty": self.is_empty,
        }
