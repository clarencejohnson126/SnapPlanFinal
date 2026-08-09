"""
Evidence — where a number came from.

Every quantity SnapPlan reports must be traceable back to a concrete spot in a
concrete document. This module defines that trace. Without it there is no
Prüfpfad, and without a Prüfpfad the number is worthless for Abrechnung.

Rule: no quantity may be constructed without Evidence. Not "should" — may not.
The only method that produces a number with no document backing is MANUAL,
and that one carries the user who drew it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


class ExtractionMethod(str, Enum):
    """How a raw value was obtained."""

    VECTOR = "vector"      # PDF vector geometry — exact, no interpretation
    TEXT = "text"          # PDF text layer (Raumstempel, NRF:, F:, Türstempel)
    TABLE = "table"        # Structured table extraction (Türenliste, Raumbuch)
    DERIVED = "derived"    # Computed from other raw quantities, deterministic
    MANUAL = "manual"      # User measured or typed it — authoritative by fiat
    OCR = "ocr"            # Rasterized text — interpretation, needs review
    CV = "cv"              # Computer vision detection — interpretation, needs review


#: Methods that produce a value by *interpreting* pixels rather than reading
#: structured data. Positions built on these default to needs_review.
INTERPRETIVE_METHODS = frozenset({ExtractionMethod.OCR, ExtractionMethod.CV})

#: Trust ordering, most trusted first. When two methods disagree about the same
#: subject, the lower-ranked one wins. MANUAL outranks everything because a user
#: override is a decision, not a measurement.
_METHOD_ORDER: Tuple[ExtractionMethod, ...] = (
    ExtractionMethod.MANUAL,
    ExtractionMethod.TEXT,     # the planner wrote the number down themselves
    ExtractionMethod.TABLE,
    ExtractionMethod.VECTOR,
    ExtractionMethod.DERIVED,
    ExtractionMethod.OCR,
    ExtractionMethod.CV,
)


def method_rank(method: ExtractionMethod) -> int:
    """Lower is more trustworthy. Used to resolve conflicting extractions."""
    try:
        return _METHOD_ORDER.index(method)
    except ValueError:
        return len(_METHOD_ORDER)


class CoordinateSpace(str, Enum):
    """
    Which coordinate system a geometry is expressed in.

    This is not a detail. The frontend draws overlays on a PDF canvas; the CV
    pipeline works on images rendered at some DPI. Mixing the two silently
    produces overlays offset by a factor of dpi/72, and nobody notices until a
    customer says "the highlight is in the wrong place".

    PDF_POINTS is canonical. Everything normalizes to it before leaving the API.
    """

    PDF_POINTS = "pdf_points"   # PDF user space, 72 units per inch
    RENDER_PX = "render_px"     # Rasterized image pixels at a given dpi


@dataclass
class Geometry:
    """
    Where on the page something is.

    Carries a bounding box, a polygon, or both. Polygon wins when present — a
    highlighted room outline reads very differently from the box around it.
    """

    space: CoordinateSpace
    bbox: Optional[Tuple[float, float, float, float]] = None  # x, y, w, h
    polygon: Optional[List[Tuple[float, float]]] = None
    dpi: Optional[int] = None  # required when space is RENDER_PX

    def __post_init__(self) -> None:
        if self.space == CoordinateSpace.RENDER_PX and not self.dpi:
            raise ValueError("Geometry in RENDER_PX space requires dpi")
        if self.bbox is None and not self.polygon:
            raise ValueError("Geometry needs a bbox or a polygon")

    def to_pdf_points(self) -> "Geometry":
        """
        Normalize into PDF user space.

        Everything crossing the API boundary goes through here, so the frontend
        only ever deals with one coordinate system.
        """
        if self.space == CoordinateSpace.PDF_POINTS:
            return self

        factor = 72.0 / float(self.dpi)  # dpi guaranteed by __post_init__
        return Geometry(
            space=CoordinateSpace.PDF_POINTS,
            bbox=tuple(v * factor for v in self.bbox) if self.bbox else None,
            polygon=[(x * factor, y * factor) for x, y in self.polygon] if self.polygon else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "space": self.space.value,
            "bbox": list(self.bbox) if self.bbox else None,
            "polygon": [list(p) for p in self.polygon] if self.polygon else None,
            "dpi": self.dpi,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Geometry":
        return cls(
            space=CoordinateSpace(data.get("space", CoordinateSpace.PDF_POINTS.value)),
            bbox=tuple(data["bbox"]) if data.get("bbox") else None,
            polygon=[tuple(p) for p in data["polygon"]] if data.get("polygon") else None,
            dpi=data.get("dpi"),
        )


@dataclass
class Evidence:
    """
    The audit trail for exactly one number.

    Fields:
        method: how the value was obtained
        file_id / page_number: which document, which sheet
        geometry: where on the sheet — this is what the reviewer clicks
        raw_value: the literal string as it appeared ("NRF: 24,35 m²"), kept
                   verbatim including the German decimal comma, so a reviewer
                   can compare against the plan without trusting our parsing
        detector: which service produced it, for debugging regressions
        confidence: 0.0–1.0. Structured methods report 1.0; only interpretive
                    methods report anything lower.
        notes: assumptions made — anything the reviewer should know
    """

    method: ExtractionMethod
    file_id: str
    page_number: int
    geometry: Optional[Geometry] = None
    raw_value: Optional[str] = None
    detector: Optional[str] = None
    confidence: float = 1.0
    notes: List[str] = field(default_factory=list)
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:10]}")

    @property
    def is_interpretive(self) -> bool:
        """True when a model guessed rather than read. Drives review flagging."""
        return self.method in INTERPRETIVE_METHODS

    def to_dict(self) -> Dict[str, Any]:
        geom = self.geometry.to_pdf_points() if self.geometry else None
        return {
            "evidence_id": self.evidence_id,
            "method": self.method.value,
            "file_id": self.file_id,
            "page_number": self.page_number,
            "geometry": geom.to_dict() if geom else None,
            "raw_value": self.raw_value,
            "detector": self.detector,
            "confidence": self.confidence,
            "is_interpretive": self.is_interpretive,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        return cls(
            method=ExtractionMethod(data["method"]),
            file_id=data.get("file_id", ""),
            page_number=data.get("page_number", 1),
            geometry=Geometry.from_dict(data["geometry"]) if data.get("geometry") else None,
            raw_value=data.get("raw_value"),
            detector=data.get("detector"),
            confidence=data.get("confidence", 1.0),
            notes=data.get("notes", []),
            evidence_id=data.get("evidence_id") or f"ev_{uuid.uuid4().hex[:10]}",
        )


def manual_evidence(file_id: str, page_number: int, geometry: Geometry,
                    user: str, note: str = "") -> Evidence:
    """Evidence for a measurement the user drew themselves."""
    notes = [f"Manuell gemessen von {user}"]
    if note:
        notes.append(note)
    return Evidence(
        method=ExtractionMethod.MANUAL,
        file_id=file_id,
        page_number=page_number,
        geometry=geometry,
        detector="user",
        confidence=1.0,
        notes=notes,
    )
