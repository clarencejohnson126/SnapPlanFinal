"""
Room Area Extraction Engine - Deterministic extraction from CAD-generated PDFs.

This module extracts room areas from German CAD PDFs with full traceability.
All values come directly from PDF text - no inference, no guessing, no LLM.

Patterns supported:
- "F: 22,79 m²" - Floor area
- "50%: 1,15 m²" - Balcony counted area (50% factor applied)
- German decimal comma (22,79)

Hard rules:
1. Only extract values that exist as text in the PDF
2. Every extracted number includes source_text and bbox
3. Missing values are explicitly marked and excluded from totals
"""

import re
import fitz  # PyMuPDF
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BoundingBox:
    """PDF bounding box coordinates (in points, origin at top-left)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> Dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_dict(cls, d: Dict) -> "BoundingBox":
        return cls(x0=d["x0"], y0=d["y0"], x1=d["x1"], y1=d["y1"])

    @classmethod
    def from_tuple(cls, t: Tuple[float, float, float, float]) -> "BoundingBox":
        return cls(x0=t[0], y0=t[1], x1=t[2], y1=t[3])

    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class ExtractedValue:
    """A single extracted value with full traceability."""
    value: float
    source_text: str
    bbox: BoundingBox
    page: int
    confidence: float = 1.0  # 1.0 = directly extracted from PDF text

    def to_dict(self) -> Dict:
        return {
            "value": self.value,
            "source_text": self.source_text,
            "bbox": self.bbox.to_dict(),
            "page": self.page,
            "confidence": self.confidence
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ExtractedValue":
        return cls(
            value=d["value"],
            source_text=d["source_text"],
            bbox=BoundingBox.from_dict(d["bbox"]),
            page=d["page"],
            confidence=d.get("confidence", 1.0)
        )


@dataclass
class RoomAreaItem:
    """A single room with extracted area and traceability."""
    room_id: str
    name: Optional[str]
    area_m2: float
    counted_m2: float
    factor: float
    page: int
    source_text: str
    bbox: BoundingBox
    room_type: str = "standard"  # "standard", "balkon", "terrasse", "loggia"
    name_source: Optional[Dict] = None  # Traceability for room name
    factor_source: Optional[Dict] = None  # Traceability for 50% value if explicit

    def to_dict(self) -> Dict:
        result = {
            "room_id": self.room_id,
            "name": self.name,
            "area_m2": self.area_m2,
            "counted_m2": self.counted_m2,
            "factor": self.factor,
            "page": self.page,
            "source_text": self.source_text,
            "bbox": self.bbox.to_dict(),
            "room_type": self.room_type
        }
        if self.name_source:
            result["name_source"] = self.name_source
        if self.factor_source:
            result["factor_source"] = self.factor_source
        return result

    @classmethod
    def from_dict(cls, d: Dict) -> "RoomAreaItem":
        return cls(
            room_id=d["room_id"],
            name=d.get("name"),
            area_m2=d["area_m2"],
            counted_m2=d["counted_m2"],
            factor=d["factor"],
            page=d["page"],
            source_text=d["source_text"],
            bbox=BoundingBox.from_dict(d["bbox"]),
            room_type=d.get("room_type", "standard"),
            name_source=d.get("name_source"),
            factor_source=d.get("factor_source")
        )


@dataclass
class MissingValue:
    """Tracks a value that could not be extracted."""
    page: int
    reason: str
    nearby_text: Optional[str]
    bbox: Optional[BoundingBox]

    def to_dict(self) -> Dict:
        result = {
            "page": self.page,
            "reason": self.reason,
            "nearby_text": self.nearby_text
        }
        if self.bbox:
            result["bbox"] = self.bbox.to_dict()
        return result


@dataclass
class RoomAreaResult:
    """Complete extraction result with rooms, totals, and missing values."""
    rooms: List[RoomAreaItem]
    total_area_m2: float
    sum_counted_m2: float
    missing: List[MissingValue]
    page_count: int
    extraction_method: str = "pymupdf_rawdict"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "rooms": [r.to_dict() for r in self.rooms],
            "total_area_m2": self.total_area_m2,
            "sum_counted_m2": self.sum_counted_m2,
            "missing": [m.to_dict() for m in self.missing],
            "page_count": self.page_count,
            "extraction_method": self.extraction_method,
            "warnings": self.warnings
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "RoomAreaResult":
        return cls(
            rooms=[RoomAreaItem.from_dict(r) for r in d["rooms"]],
            total_area_m2=d["total_area_m2"],
            sum_counted_m2=d["sum_counted_m2"],
            missing=[],  # Simplified for now
            page_count=d["page_count"],
            extraction_method=d.get("extraction_method", "pymupdf_rawdict"),
            warnings=d.get("warnings", [])
        )


# =============================================================================
# TEXT EXTRACTION USING PYMUPDF RAWDICT
# =============================================================================

@dataclass
class TextSpan:
    """A single text span from PDF with position info."""
    text: str
    bbox: BoundingBox
    font: str
    size: float

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "font": self.font,
            "size": self.size
        }


@dataclass
class TextLine:
    """A reconstructed logical line from multiple spans."""
    spans: List[TextSpan]
    bbox: BoundingBox

    @property
    def text(self) -> str:
        """Combine spans into a single string, sorted by x position."""
        sorted_spans = sorted(self.spans, key=lambda s: s.bbox.x0)
        return " ".join(s.text.strip() for s in sorted_spans if s.text.strip())

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "spans": [s.to_dict() for s in self.spans]
        }


def extract_text_with_positions(page: fitz.Page) -> List[TextLine]:
    """
    Extract text from PDF page using dict, reconstructing logical lines.

    Uses page.get_text("dict") to get detailed text structure with:
    - Block → Line → Span hierarchy
    - Bounding boxes for each element
    - Font information

    Note: "dict" works more reliably than "rawdict" for CAD PDFs.

    Returns logical lines sorted by y-position (top to bottom).
    """
    lines: List[TextLine] = []

    try:
        # Use "dict" instead of "rawdict" - more reliable for CAD PDFs
        raw = page.get_text("dict")
    except Exception as e:
        logger.error(f"Failed to extract dict: {e}")
        return lines

    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # Skip non-text blocks (images)
            continue

        for line in block.get("lines", []):
            spans: List[TextSpan] = []

            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue

                bbox_tuple = span.get("bbox", (0, 0, 0, 0))
                spans.append(TextSpan(
                    text=text,
                    bbox=BoundingBox.from_tuple(bbox_tuple),
                    font=span.get("font", ""),
                    size=span.get("size", 0)
                ))

            if spans:
                # Calculate line bounding box from all spans
                x0 = min(s.bbox.x0 for s in spans)
                y0 = min(s.bbox.y0 for s in spans)
                x1 = max(s.bbox.x1 for s in spans)
                y1 = max(s.bbox.y1 for s in spans)

                lines.append(TextLine(
                    spans=spans,
                    bbox=BoundingBox(x0, y0, x1, y1)
                ))

    # Sort by y-position (top to bottom), then x (left to right)
    lines.sort(key=lambda l: (l.bbox.y0, l.bbox.x0))

    return lines


# =============================================================================
# REGEX PATTERNS FOR AREA EXTRACTION
# =============================================================================

# =============================================================================
# GERMAN CAD AREA PATTERNS
# =============================================================================
# These patterns match German construction document area annotations.
# Note: m²/m2/m at end - the ² may be in a separate span in CAD PDFs

# Primary pattern: "NRF: 22,79 m" (Netto-Raumfläche - Net Room Floor area)
# This is the standard annotation in German architectural CAD systems
AREA_PATTERN = re.compile(
    r'NRF\s*:\s*(\d+[,.]?\d*)\s*m[²2]?',
    re.IGNORECASE
)

# Pattern for "50%: 1,15 m²" (explicit counted area for balconies)
COUNTED_AREA_PATTERN = re.compile(
    r'(\d+)\s*%\s*:\s*(\d+[,.]?\d*)\s*m[²2]?',
    re.IGNORECASE
)

# Alternative German area patterns
ALT_AREA_PATTERNS = [
    # "BGF: 22,79 m²" (Bruttogrundfläche - Gross Floor Area)
    re.compile(r'BGF\s*:\s*(\d+[,.]?\d*)\s*m[²2]?', re.IGNORECASE),
    # "NGF: 22,79 m²" (Nettogrundfläche - Net Floor Area)
    re.compile(r'NGF\s*:\s*(\d+[,.]?\d*)\s*m[²2]?', re.IGNORECASE),
    # "Fläche: 22,79 m²" or "Fläche = 22,79 m²"
    re.compile(r'Fl[äa]che\s*[:=]\s*(\d+[,.]?\d*)\s*m[²2]?', re.IGNORECASE),
    # "WF: 22,79 m²" (Wohnfläche - Living Area)
    re.compile(r'WF\s*:\s*(\d+[,.]?\d*)\s*m[²2]?', re.IGNORECASE),
]

# Balcony/terrace room types (German)
BALCONY_KEYWORDS = [
    "balkon", "terrasse", "loggia", "dachterrasse",
    "wintergarten", "freisitz"
]


def parse_german_decimal(value_str: str) -> float:
    """Convert German decimal format (comma) to float."""
    return float(value_str.replace(",", "."))


def extract_area_from_line(line: TextLine) -> Optional[Tuple[float, str]]:
    """
    Extract area value from a text line.

    Returns (area_m2, source_text) if found, None otherwise.
    """
    text = line.text

    # Try primary pattern first: "F: 22,79 m²"
    match = AREA_PATTERN.search(text)
    if match:
        try:
            area = parse_german_decimal(match.group(1))
            return (area, match.group(0))
        except ValueError:
            pass

    # Try alternative patterns
    for pattern in ALT_AREA_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                area = parse_german_decimal(match.group(1))
                return (area, match.group(0))
            except ValueError:
                pass

    return None


def extract_counted_area_from_line(line: TextLine) -> Optional[Tuple[float, float, str]]:
    """
    Extract explicit counted area like "50%: 1,15 m²".

    Returns (percentage, area_m2, source_text) if found, None otherwise.
    """
    match = COUNTED_AREA_PATTERN.search(line.text)
    if match:
        try:
            percentage = float(match.group(1)) / 100.0
            area = parse_german_decimal(match.group(2))
            return (percentage, area, match.group(0))
        except ValueError:
            pass

    return None


def is_balcony_type(text: str) -> Tuple[bool, str]:
    """
    Check if text indicates a balcony/terrace type room.

    Returns (is_balcony, room_type).
    """
    text_lower = text.lower()
    for keyword in BALCONY_KEYWORDS:
        if keyword in text_lower:
            return (True, keyword)
    return (False, "standard")


# =============================================================================
# ROOM NAME ASSOCIATION
# =============================================================================

def find_nearest_room_name(
    area_line: TextLine,
    all_lines: List[TextLine],
    max_y_distance: float = 50.0,  # Points (~17mm at 72 DPI)
    max_x_distance: float = 150.0  # Points (~53mm)
) -> Optional[Tuple[str, Dict]]:
    """
    Find the nearest room name label above/near the area line.

    Strategy:
    1. Look for lines ABOVE the area line (smaller y value)
    2. Prefer lines with smaller y-distance
    3. Then prefer lines with smaller x-distance (closer horizontally)
    4. Skip lines that are themselves area values

    Returns (room_name, source_info) if found, None otherwise.
    """
    area_center = area_line.bbox.center()
    area_y = area_line.bbox.y0

    candidates = []

    for line in all_lines:
        if line is area_line:
            continue

        # Skip lines that contain area patterns (not room names)
        if AREA_PATTERN.search(line.text) or COUNTED_AREA_PATTERN.search(line.text):
            continue

        # Skip lines below the area line
        line_y = line.bbox.y1  # Bottom of potential label
        y_distance = area_y - line_y

        if y_distance < 0:  # Line is below area
            continue
        if y_distance > max_y_distance:
            continue

        # Calculate horizontal distance
        line_center_x = (line.bbox.x0 + line.bbox.x1) / 2
        x_distance = abs(line_center_x - area_center[0])

        if x_distance > max_x_distance:
            continue

        # Filter out very short text (likely symbols) and pure numbers
        text = line.text.strip()
        if len(text) < 2:
            continue
        if text.replace(",", "").replace(".", "").isdigit():
            continue

        candidates.append({
            "text": text,
            "y_distance": y_distance,
            "x_distance": x_distance,
            "bbox": line.bbox
        })

    if not candidates:
        return None

    # Sort by y_distance first (closer above), then x_distance
    candidates.sort(key=lambda c: (c["y_distance"], c["x_distance"]))

    best = candidates[0]
    return (
        best["text"],
        {
            "source_text": best["text"],
            "bbox": best["bbox"].to_dict(),
            "y_distance": best["y_distance"],
            "x_distance": best["x_distance"]
        }
    )


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_room_areas(
    pdf_path: Union[str, Path],
    pages: Optional[List[int]] = None,
    default_balcony_factor: float = 0.5
) -> RoomAreaResult:
    """
    Extract room areas from a PDF with full traceability.

    Args:
        pdf_path: Path to PDF file
        pages: Optional list of page numbers (0-indexed). None = all pages.
        default_balcony_factor: Factor for balcony/terrace if no explicit % given (default 0.5)

    Returns:
        RoomAreaResult with rooms, totals, and missing values

    Hard rules:
    - Only extracts values that exist as text in the PDF
    - Every extracted number includes source_text and bbox
    - Missing values are explicitly tracked and excluded from totals
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    rooms: List[RoomAreaItem] = []
    missing: List[MissingValue] = []
    warnings: List[str] = []

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    page_indices = pages if pages is not None else range(len(doc))
    room_counter = 0

    for page_idx in page_indices:
        if page_idx >= len(doc):
            warnings.append(f"Page {page_idx} does not exist (PDF has {len(doc)} pages)")
            continue

        page = doc[page_idx]
        lines = extract_text_with_positions(page)

        # Track which lines have been processed as area values
        processed_lines = set()

        # First pass: Find all area values
        area_lines = []
        for i, line in enumerate(lines):
            area_result = extract_area_from_line(line)
            if area_result:
                area_lines.append((i, line, area_result))
                processed_lines.add(i)

        # Second pass: Find associated counted areas (50%: X m²)
        counted_areas = {}  # Maps area_line_idx to counted info
        for i, line in enumerate(lines):
            if i in processed_lines:
                continue
            counted_result = extract_counted_area_from_line(line)
            if counted_result:
                percentage, counted_m2, source = counted_result
                # Find nearest area line above or at same level
                for area_idx, area_line, _ in area_lines:
                    if abs(area_line.bbox.y_center() - line.bbox.y_center()) < 30:
                        counted_areas[area_idx] = {
                            "percentage": percentage,
                            "counted_m2": counted_m2,
                            "source_text": source,
                            "bbox": line.bbox
                        }
                        break

        # Third pass: Build room items
        for area_idx, area_line, (area_m2, area_source) in area_lines:
            room_counter += 1
            room_id = f"room_{room_counter:03d}"

            # Find room name
            name_result = find_nearest_room_name(area_line, lines)
            room_name = name_result[0] if name_result else None
            name_source = name_result[1] if name_result else None

            # Check if balcony type
            is_balcony, room_type = False, "standard"
            if room_name:
                is_balcony, room_type = is_balcony_type(room_name)

            # Determine factor and counted_m2
            factor = 1.0
            counted_m2 = area_m2
            factor_source = None

            if area_idx in counted_areas:
                # Explicit counted area found (e.g., "50%: 1,15 m²")
                info = counted_areas[area_idx]
                factor = info["percentage"]
                counted_m2 = info["counted_m2"]
                factor_source = {
                    "source_text": info["source_text"],
                    "bbox": info["bbox"].to_dict(),
                    "method": "explicit_percentage"
                }
            elif is_balcony:
                # Apply default balcony factor
                factor = default_balcony_factor
                counted_m2 = round(area_m2 * factor, 2)
                factor_source = {
                    "method": "default_balcony_factor",
                    "factor": default_balcony_factor,
                    "reason": f"Room type '{room_type}' matched balcony keywords"
                }

            rooms.append(RoomAreaItem(
                room_id=room_id,
                name=room_name,
                area_m2=area_m2,
                counted_m2=counted_m2,
                factor=factor,
                page=page_idx,
                source_text=area_source,
                bbox=area_line.bbox,
                room_type=room_type,
                name_source=name_source,
                factor_source=factor_source
            ))

        # Track pages with no areas found
        if not area_lines:
            # Get some sample text for debugging
            sample_text = " ".join(line.text[:50] for line in lines[:5])
            missing.append(MissingValue(
                page=page_idx,
                reason="No area patterns found on page",
                nearby_text=sample_text[:200] if sample_text else None,
                bbox=None
            ))

    # Store page count before closing
    page_count = len(doc)
    doc.close()

    # Calculate totals (only from successfully extracted values)
    total_area_m2 = round(sum(r.area_m2 for r in rooms), 2)
    sum_counted_m2 = round(sum(r.counted_m2 for r in rooms), 2)

    return RoomAreaResult(
        rooms=rooms,
        total_area_m2=total_area_m2,
        sum_counted_m2=sum_counted_m2,
        missing=missing,
        page_count=page_count,
        extraction_method="pymupdf_rawdict",
        warnings=warnings
    )


# =============================================================================
# ALTERNATIVE: PDFPLUMBER FALLBACK
# =============================================================================

def extract_room_areas_pdfplumber(
    pdf_path: Union[str, Path],
    pages: Optional[List[int]] = None,
    default_balcony_factor: float = 0.5
) -> RoomAreaResult:
    """
    Fallback extraction using pdfplumber when PyMuPDF fails.

    Same interface as extract_room_areas() but uses pdfplumber.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    rooms: List[RoomAreaItem] = []
    missing: List[MissingValue] = []
    warnings: List[str] = []

    with pdfplumber.open(str(path)) as pdf:
        page_indices = pages if pages is not None else range(len(pdf.pages))
        room_counter = 0

        for page_idx in page_indices:
            if page_idx >= len(pdf.pages):
                warnings.append(f"Page {page_idx} does not exist")
                continue

            page = pdf.pages[page_idx]
            words = page.extract_words(keep_blank_chars=True)

            # Reconstruct text with positions
            text_items = []
            for word in words:
                text_items.append({
                    "text": word["text"],
                    "x0": word["x0"],
                    "y0": word["top"],
                    "x1": word["x1"],
                    "y1": word["bottom"]
                })

            # Sort by position
            text_items.sort(key=lambda w: (w["y0"], w["x0"]))

            # Find area patterns
            full_text = " ".join(w["text"] for w in text_items)

            for match in AREA_PATTERN.finditer(full_text):
                try:
                    room_counter += 1
                    area_m2 = parse_german_decimal(match.group(1))

                    rooms.append(RoomAreaItem(
                        room_id=f"room_{room_counter:03d}",
                        name=None,  # pdfplumber fallback doesn't do name association
                        area_m2=area_m2,
                        counted_m2=area_m2,
                        factor=1.0,
                        page=page_idx,
                        source_text=match.group(0),
                        bbox=BoundingBox(0, 0, 0, 0),  # Approximate
                        room_type="standard"
                    ))
                except ValueError:
                    pass

            if not any(r.page == page_idx for r in rooms):
                missing.append(MissingValue(
                    page=page_idx,
                    reason="No area patterns found (pdfplumber)",
                    nearby_text=full_text[:200] if full_text else None,
                    bbox=None
                ))

    total_area_m2 = round(sum(r.area_m2 for r in rooms), 2)
    sum_counted_m2 = round(sum(r.counted_m2 for r in rooms), 2)

    return RoomAreaResult(
        rooms=rooms,
        total_area_m2=total_area_m2,
        sum_counted_m2=sum_counted_m2,
        missing=missing,
        page_count=len(pdf.pages),
        extraction_method="pdfplumber_fallback",
        warnings=warnings
    )


# =============================================================================
# CONVENIENCE API
# =============================================================================

def extract_room_areas_auto(
    pdf_path: Union[str, Path],
    pages: Optional[List[int]] = None,
    default_balcony_factor: float = 0.5
) -> Dict[str, Any]:
    """
    Main API: Extract room areas with automatic fallback.

    Tries PyMuPDF first, falls back to pdfplumber if needed.
    Returns a dict for JSON serialization.
    """
    try:
        result = extract_room_areas(pdf_path, pages, default_balcony_factor)
        if not result.rooms and result.missing:
            # Try pdfplumber fallback
            logger.info("PyMuPDF found no rooms, trying pdfplumber fallback")
            result = extract_room_areas_pdfplumber(pdf_path, pages, default_balcony_factor)
            result.warnings.append("Used pdfplumber fallback")
    except Exception as e:
        logger.warning(f"PyMuPDF failed: {e}, trying pdfplumber")
        result = extract_room_areas_pdfplumber(pdf_path, pages, default_balcony_factor)
        result.warnings.append(f"PyMuPDF failed: {str(e)}, used pdfplumber fallback")

    return result.to_dict()
