"""
CV Output Schema

Defines the JSON-friendly structures used by the geometry/symbol CV pipeline.
This schema is intentionally separate from the deterministic room text results
to avoid regressions in the existing m² extraction path.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


class CVElementType(str, Enum):
    """Semantic object types emitted by the CV pipeline."""

    DOOR = "door"
    WINDOW = "window"
    WALL = "wall"
    TOILET = "toilet"
    WASH_BASIN = "wash_basin"
    CONDUIT = "conduit"
    ROOM_BOUNDARY = "room_boundary"
    DIMENSION = "dimension"
    SCALE = "scale"
    UNKNOWN = "unknown"


@dataclass
class DerivedMeasure:
    """Measurement derived from geometry + scale."""

    name: str  # e.g., "length", "area", "count"
    value: Optional[float]  # None when unknown
    unit: str  # "m", "m2", "count", "deg"
    method: str  # "vector_geometry", "bbox_scaled", "text_dimension"
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "method": self.method,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass
class CVElement:
    """Single detection or measurement emitted by the CV pipeline."""

    element_id: str
    element_type: CVElementType
    page_number: int
    bbox: Tuple[float, float, float, float]  # x, y, w, h in rendered px
    confidence: float
    source: str  # "yolo", "wall_mask", "vector", "roboflow", etc.
    mask_path: Optional[str] = None
    polygon: Optional[List[Tuple[float, float]]] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    derived: List[DerivedMeasure] = field(default_factory=list)
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.element_id,
            "type": self.element_type.value,
            "page": self.page_number,
            "bbox": {
                "x": self.bbox[0],
                "y": self.bbox[1],
                "width": self.bbox[2],
                "height": self.bbox[3],
            },
            "confidence": self.confidence,
            "source": self.source,
            "mask_path": self.mask_path,
            "polygon": self.polygon,
            "attributes": self.attributes,
            "derived": [d.to_dict() for d in self.derived],
            "needs_review": self.needs_review,
        }


@dataclass
class CVPageResult:
    """Per-page CV extraction result."""

    document_id: str
    page_number: int
    dpi: int
    elements: List[CVElement] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    debug_images: Dict[str, str] = field(default_factory=dict)
    processing_time_ms: int = 0
    pipeline_version: str = "cv-symbol-v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "page_number": self.page_number,
            "dpi": self.dpi,
            "elements": [e.to_dict() for e in self.elements],
            "warnings": self.warnings,
            "debug_images": self.debug_images,
            "processing_time_ms": self.processing_time_ms,
            "pipeline_version": self.pipeline_version,
        }

    @property
    def needs_review(self) -> bool:
        """True if any element is flagged for manual review."""
        return any(e.needs_review for e in self.elements)


@dataclass
class CVExtractionResult:
    """Multi-page CV extraction result."""

    document_id: str
    pages: List[CVPageResult]
    scale_string: Optional[str] = None
    pixels_per_meter: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "scale": self.scale_string,
            "pixels_per_meter": self.pixels_per_meter,
            "pages": [p.to_dict() for p in self.pages],
            "warnings": self.warnings,
        }


def generate_element_id(prefix: str = "cv") -> str:
    """Stable short IDs for CV elements."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

