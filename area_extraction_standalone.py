"""
Deterministic Area Extraction Engine - Standalone Version

Extracts room areas from German CAD-generated PDFs with 100% traceability.
All extracted values come directly from PDF text - zero hallucination.

Supported Styles:
- Haardtring (Residential): F: pattern, R2.E5.3.5 room numbers
- LeiQ (Office): NRF: pattern, B.00.2.002 room numbers
- Omniturm (Highrise): NGF: pattern, 33_b6.12 room numbers

Requirements:
    pip install PyMuPDF pdfplumber

Usage:
    from area_extraction_standalone import extract_room_areas

    result = extract_room_areas("floorplan.pdf")
    print(f"Found {result.room_count} rooms, total {result.total_area_m2} m²")

    for room in result.rooms:
        print(f"  {room.room_number}: {room.area_m2} m² (source: {room.source_text})")

Author: SnapPlan Team
License: MIT
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Union
from pathlib import Path
from enum import Enum

# Try to import PyMuPDF
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    print("WARNING: PyMuPDF not installed. Run: pip install PyMuPDF")

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class BlueprintStyle(str, Enum):
    """Detected blueprint style."""
    HAARDTRING = "haardtring"  # Residential, F: pattern
    LEIQ = "leiq"              # Office, NRF: pattern
    OMNITURM = "omniturm"      # Highrise, NGF: pattern
    UNKNOWN = "unknown"


class RoomCategory(str, Enum):
    """Room category for grouping."""
    OFFICE = "office"
    RESIDENTIAL = "residential"
    CIRCULATION = "circulation"
    STAIRS = "stairs"
    ELEVATORS = "elevators"
    SHAFTS = "shafts"
    TECHNICAL = "technical"
    SANITARY = "sanitary"
    STORAGE = "storage"
    OUTDOOR = "outdoor"
    OTHER = "other"


# German room type keywords for categorization
ROOM_CATEGORIES = {
    RoomCategory.OFFICE: ["büro", "office", "nutzungseinheit", "back office"],
    RoomCategory.RESIDENTIAL: ["schlafen", "wohnen", "essen", "kochen", "zimmer", "küche"],
    RoomCategory.CIRCULATION: ["flur", "diele", "schleuse", "vorraum", "eingang", "lobby"],
    RoomCategory.STAIRS: ["treppe", "treppenhaus", "trh"],
    RoomCategory.ELEVATORS: ["aufzug", "lift", "aufzugsschacht", "aufzugsvorr"],
    RoomCategory.SHAFTS: ["schacht", "lüftung", "medien", "druckbelüftung"],
    RoomCategory.TECHNICAL: ["elektro", "technik", "hwr", "it verteiler", "elt", "glt", "fiz"],
    RoomCategory.SANITARY: ["wc", "bad", "dusche", "gästebad", "umkleide", "sanitär"],
    RoomCategory.STORAGE: ["lager", "abstellraum", "müll", "fahrrad"],
    RoomCategory.OUTDOOR: ["balkon", "terrasse", "loggia", "dachterrasse", "freisitz"],
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BoundingBox:
    """PDF bounding box coordinates."""
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> Dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_tuple(cls, t: Tuple[float, float, float, float]) -> "BoundingBox":
        return cls(x0=t[0], y0=t[1], x1=t[2], y1=t[3])

    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass
class ExtractedRoom:
    """A single extracted room with full traceability."""
    room_number: str
    room_name: str
    area_m2: float
    counted_m2: float  # After applying factors (e.g., 50% for balcony)
    factor: float
    page: int
    source_text: str
    bbox: Optional[BoundingBox] = None
    category: RoomCategory = RoomCategory.OTHER
    perimeter_m: Optional[float] = None  # U: value (LeiQ style)
    height_m: Optional[float] = None     # LH: value (LeiQ style)
    factor_source: Optional[str] = None  # How factor was determined
    extraction_pattern: str = ""         # Which pattern matched

    def to_dict(self) -> Dict:
        result = {
            "room_number": self.room_number,
            "room_name": self.room_name,
            "area_m2": self.area_m2,
            "counted_m2": self.counted_m2,
            "factor": self.factor,
            "page": self.page,
            "source_text": self.source_text,
            "category": self.category.value,
            "extraction_pattern": self.extraction_pattern,
        }
        if self.bbox:
            result["bbox"] = self.bbox.to_dict()
        if self.perimeter_m:
            result["perimeter_m"] = self.perimeter_m
        if self.height_m:
            result["height_m"] = self.height_m
        if self.factor_source:
            result["factor_source"] = self.factor_source
        return result


@dataclass
class ExtractionResult:
    """Complete extraction result."""
    rooms: List[ExtractedRoom]
    total_area_m2: float
    total_counted_m2: float
    room_count: int
    page_count: int
    blueprint_style: BlueprintStyle
    extraction_method: str = "unified_extraction"
    warnings: List[str] = field(default_factory=list)
    totals_by_category: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "rooms": [r.to_dict() for r in self.rooms],
            "total_area_m2": self.total_area_m2,
            "total_counted_m2": self.total_counted_m2,
            "room_count": self.room_count,
            "page_count": self.page_count,
            "blueprint_style": self.blueprint_style.value,
            "extraction_method": self.extraction_method,
            "warnings": self.warnings,
            "totals_by_category": self.totals_by_category,
        }


# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

PATTERNS = {
    "haardtring": {
        "area_labels": [
            re.compile(r'^F:\s*([\d,]+)\s*m[²2]?$', re.IGNORECASE),
            re.compile(r'^F:$'),  # Split across lines
        ],
        "room_numbers": [
            re.compile(r'^(R\d+\.E\d+\.\d+\.\d+)$'),
        ],
        "balcony_factor": re.compile(r'^50%:\s*([\d,]+)\s*m[²2]?$', re.IGNORECASE),
    },
    "leiq": {
        "area_labels": [
            re.compile(r'^NRF:\s*([\d,]+)\s*m[²2]?$', re.IGNORECASE),
            re.compile(r'^NRF:$'),  # Split across lines
        ],
        "room_numbers": [
            re.compile(r'^(B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+)$'),
        ],
        "perimeter": re.compile(r'^U:\s*([\d,]+)\s*m$', re.IGNORECASE),
        "height": re.compile(r'^LH:\s*([\d,]+)\s*m$', re.IGNORECASE),
    },
    "omniturm": {
        "area_labels": [
            re.compile(r'^NGF:\s*([\d.,]+)\s*m[²2]?$', re.IGNORECASE),
            re.compile(r'^NGF:$'),  # Split across lines
        ],
        "room_numbers": [
            re.compile(r'^(\d+_[a-z]\d+\.\d+)$'),
            re.compile(r'^(BT\d+\.[A-Z]+\.\d+)$'),
        ],
        "schacht_name": re.compile(r'^(Schacht \d+)$'),
    },
}

# Flexible area patterns for unknown formats
FLEXIBLE_AREA_PATTERNS = [
    re.compile(r'(?:NRF|NGF|BGF|Fläche|Fl|FL|GF|WF|NF)\s*[=:]\s*([\d.,]+)\s*m[²2]?', re.IGNORECASE),
    re.compile(r'^F\s*[=:]\s*([\d.,]+)\s*m[²2]?$', re.IGNORECASE),
    re.compile(r'(?:NRF|NGF|Fläche)\s*[=:]\s*([\d.,]+)\s*qm\b', re.IGNORECASE),
]

# Flexible room identifier patterns
FLEXIBLE_ROOM_PATTERNS = [
    re.compile(r'^([A-Z]+\d*[\._][A-Z0-9]+[\._][A-Z0-9]+[\._][A-Z0-9]+)$', re.IGNORECASE),
    re.compile(r'^(\d+_[a-z]\d+\.\d+)$'),
    re.compile(r'^([EOU]G\d*[\._]\d{3})$', re.IGNORECASE),
    re.compile(r'^([A-Z][\._]\d{3})$', re.IGNORECASE),
]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def parse_german_number(s: str) -> float:
    """
    Parse German number format to float.
    Handles: "22,79" -> 22.79, "1.070,55" -> 1070.55
    """
    s = s.strip()
    if '.' in s and ',' in s:
        # German thousands separator format: 1.070,55
        s = s.replace('.', '').replace(',', '.')
    else:
        # Simple comma decimal: 22,79
        s = s.replace(',', '.')
    return float(s)


def categorize_room(room_name: str) -> RoomCategory:
    """Determine room category from name."""
    name_lower = room_name.lower()
    for category, keywords in ROOM_CATEGORIES.items():
        for keyword in keywords:
            if keyword in name_lower:
                return category
    return RoomCategory.OTHER


def is_outdoor_room(room_name: str) -> bool:
    """Check if room is outdoor (balcony, terrace, etc.)."""
    return categorize_room(room_name) == RoomCategory.OUTDOOR


# =============================================================================
# STYLE DETECTION
# =============================================================================

def detect_blueprint_style(text: str) -> BlueprintStyle:
    """
    Auto-detect blueprint style from PDF text content.
    """
    has_f = bool(re.search(r'\bF:\s*\d', text))
    has_nrf = bool(re.search(r'\bNRF:\s*\d', text, re.IGNORECASE))
    has_ngf = bool(re.search(r'\bNGF:\s*\d', text, re.IGNORECASE))

    has_r_pattern = bool(re.search(r'\bR\d+\.E\d+\.\d+\.\d+\b', text))
    has_b_pattern = bool(re.search(r'\bB\.\d+\.\d+\.\d+\b', text))
    has_grid_pattern = bool(re.search(r'\b\d+_[a-z]\d+\.\d+\b', text))

    if has_f and has_r_pattern:
        return BlueprintStyle.HAARDTRING
    elif has_nrf and has_b_pattern:
        return BlueprintStyle.LEIQ
    elif has_ngf and (has_grid_pattern or has_b_pattern):
        return BlueprintStyle.OMNITURM
    elif has_ngf:
        return BlueprintStyle.OMNITURM
    elif has_nrf:
        return BlueprintStyle.LEIQ
    elif has_f:
        return BlueprintStyle.HAARDTRING
    else:
        return BlueprintStyle.UNKNOWN


# =============================================================================
# EXTRACTION FUNCTIONS BY STYLE
# =============================================================================

def extract_haardtring(lines: List[str], page_idx: int) -> List[ExtractedRoom]:
    """
    Extract rooms from Haardtring-style blueprints.
    Pattern: Room number (R2.E5.3.5) -> Room name -> F: XX,XX m2
    """
    rooms = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        room_match = re.match(r'^(R\d+\.E\d+\.\d+\.\d+)$', line)
        if room_match:
            room_num = room_match.group(1)
            room_name = None
            area = None
            balcony_area = None

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'^(F:|BA:|B:|W:|D:|[\d,]+)', next_line):
                    room_name = next_line

            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                f_match = re.match(r'^F:\s*([\d,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if f_match:
                    area = parse_german_number(f_match.group(1))
                    if j + 1 < len(lines):
                        b_match = re.match(r'^50%:\s*([\d,]+)\s*m[²2]?$', lines[j + 1].strip())
                        if b_match:
                            balcony_area = parse_german_number(b_match.group(1))
                    break

                if curr == 'F:' and j + 1 < len(lines):
                    area_match = re.match(r'^([\d,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match:
                        area = parse_german_number(area_match.group(1))
                        if j + 2 < len(lines):
                            b_match = re.match(r'^50%:\s*([\d,]+)\s*m[²2]?$', lines[j + 2].strip())
                            if b_match:
                                balcony_area = parse_german_number(b_match.group(1))
                        break

                if re.match(r'^R\d+\.E\d+\.\d+\.\d+$', curr):
                    break

            if area:
                if balcony_area:
                    factor = 0.5
                    counted = balcony_area
                    factor_source = "explicit_50%"
                elif room_name and is_outdoor_room(room_name):
                    factor = 0.5
                    counted = round(area * 0.5, 2)
                    factor_source = "default_outdoor"
                else:
                    factor = 1.0
                    counted = area
                    factor_source = None

                rooms.append(ExtractedRoom(
                    room_number=room_num,
                    room_name=room_name or "Unknown",
                    area_m2=area,
                    counted_m2=counted,
                    factor=factor,
                    page=page_idx,
                    source_text=f"F: {area}",
                    category=categorize_room(room_name or ""),
                    factor_source=factor_source,
                    extraction_pattern="F:",
                ))
        i += 1

    return rooms


def extract_leiq(lines: List[str], page_idx: int) -> List[ExtractedRoom]:
    """
    Extract rooms from LeiQ-style blueprints.
    Pattern: Room number (B.00.2.002) -> Room name -> NRF: XX,XX m2
    """
    rooms = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        room_match = re.match(r'^(B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+)$', line)
        if room_match:
            room_num = room_match.group(1)
            room_name = None
            area = None
            perimeter = None
            height = None

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'^(NRF|F[=:]|U[=:]|LH[=:]|LRH[=:]|B\.|[\d,]+)', next_line):
                    room_name = next_line

            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                nrf_match = re.match(r'^NRF[=:]\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if nrf_match and area is None:
                    area = parse_german_number(nrf_match.group(1))
                    continue

                f_match = re.match(r'^F[=:]\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if f_match and area is None:
                    area = parse_german_number(f_match.group(1))
                    continue

                if curr in ('NRF:', 'NRF=') and j + 1 < len(lines):
                    area_match = re.match(r'^([\d.,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match and area is None:
                        area = parse_german_number(area_match.group(1))
                        continue

                u_match = re.match(r'^U[=:]\s*([\d.,]+)\s*m$', curr, re.IGNORECASE)
                if u_match:
                    perimeter = parse_german_number(u_match.group(1))
                    continue

                lh_match = re.match(r'^L(?:R)?H[=:]\s*([\d.,]+)\s*m$', curr, re.IGNORECASE)
                if lh_match:
                    height = parse_german_number(lh_match.group(1))
                    continue

                if re.match(r'^B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+$', curr):
                    break

            if area:
                rooms.append(ExtractedRoom(
                    room_number=room_num,
                    room_name=room_name or "Unknown",
                    area_m2=area,
                    counted_m2=area,
                    factor=1.0,
                    page=page_idx,
                    source_text=f"NRF: {area}",
                    category=categorize_room(room_name or ""),
                    perimeter_m=perimeter,
                    height_m=height,
                    extraction_pattern="NRF:",
                ))
        i += 1

    return rooms


def extract_omniturm(lines: List[str], page_idx: int) -> List[ExtractedRoom]:
    """
    Extract rooms from Omniturm-style blueprints.
    Pattern: Room number (33_b6.12) -> Room name -> NGF: XX,XX m2
    """
    rooms = []
    processed = set()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        room_match = re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', line)
        if room_match and line not in processed:
            room_num = line
            room_name = None
            area = None

            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                if re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', curr):
                    break

                if room_name is None and curr and not re.match(
                    r'^(NGF|UKRD|UKFD|OKFF|OKRF|LRH|[\d,]+\s*m|Schacht)', curr
                ):
                    room_name = curr

                ngf_match = re.match(r'^NGF:\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if ngf_match:
                    area = parse_german_number(ngf_match.group(1))
                    break

                if curr == 'NGF:' and j + 1 < len(lines):
                    area_match = re.match(r'^([\d.,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match:
                        area = parse_german_number(area_match.group(1))
                        break

                schacht_match = re.match(r'^(Schacht \d+)$', curr)
                if schacht_match:
                    room_name = schacht_match.group(1)
                    if j + 2 < len(lines):
                        type_line = lines[j + 1].strip()
                        area_line = lines[j + 2].strip()
                        if not re.match(r'^[\d,]', type_line):
                            room_name = f"{schacht_match.group(1)} ({type_line})"
                        area_match = re.match(r'^([\d,]+)\s*m[²2]?$', area_line)
                        if area_match:
                            area = parse_german_number(area_match.group(1))
                            break

            if area:
                rooms.append(ExtractedRoom(
                    room_number=room_num,
                    room_name=room_name or "Unknown",
                    area_m2=area,
                    counted_m2=area,
                    factor=1.0,
                    page=page_idx,
                    source_text=f"NGF: {area}",
                    category=categorize_room(room_name or ""),
                    extraction_pattern="NGF:",
                ))
                processed.add(room_num)

        i += 1

    return rooms


def extract_generic(lines: List[str], page_idx: int) -> List[ExtractedRoom]:
    """
    Generic flexible extractor for unknown blueprint formats.
    """
    rooms = []
    found_areas = []
    found_room_ids = {}

    # First pass: find all area values
    for i, line in enumerate(lines):
        line = line.strip()

        for pattern in FLEXIBLE_AREA_PATTERNS:
            match = pattern.search(line)
            if match:
                try:
                    area = parse_german_number(match.group(1))
                    if 0.5 <= area <= 10000:
                        found_areas.append({
                            'line_idx': i,
                            'area': area,
                            'source_line': line,
                            'pattern': pattern.pattern[:30],
                        })
                except (ValueError, IndexError):
                    pass
                break

    # Second pass: find all room identifiers
    for i, line in enumerate(lines):
        line = line.strip()

        for pattern in FLEXIBLE_ROOM_PATTERNS:
            match = pattern.match(line)
            if match:
                room_id = match.group(1)
                if room_id not in found_room_ids:
                    found_room_ids[room_id] = i
                break

    # Third pass: associate areas with nearest room IDs
    used_areas = set()

    for room_id, room_line_idx in found_room_ids.items():
        best_area = None
        best_distance = float('inf')
        best_area_idx = None

        for area_idx, area_info in enumerate(found_areas):
            if area_idx in used_areas:
                continue

            distance = abs(area_info['line_idx'] - room_line_idx)
            if area_info['line_idx'] > room_line_idx:
                distance -= 0.5

            if distance < best_distance and distance < 15:
                best_distance = distance
                best_area = area_info
                best_area_idx = area_idx

        if best_area:
            used_areas.add(best_area_idx)

            room_name = None
            start_search = room_line_idx + 1
            end_search = best_area['line_idx']

            for j in range(start_search, min(end_search, start_search + 5)):
                if j < len(lines):
                    candidate = lines[j].strip()
                    if (candidate and
                        len(candidate) > 1 and
                        not re.match(r'^[\d,.\s]+$', candidate) and
                        not re.match(r'^(NRF|NGF|F|U|LH|BA|B|W|D|OK|UK|UKRD|OKFF)[\s:=]', candidate, re.IGNORECASE) and
                        not re.match(r'^[\d.,]+\s*m[²2]?$', candidate)):
                        room_name = candidate
                        break

            rooms.append(ExtractedRoom(
                room_number=room_id,
                room_name=room_name or "Unknown",
                area_m2=best_area['area'],
                counted_m2=best_area['area'],
                factor=1.0,
                page=page_idx,
                source_text=best_area['source_line'],
                category=categorize_room(room_name or ""),
                extraction_pattern="generic",
            ))

    return rooms


# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================

def extract_room_areas(
    pdf_path: Union[str, Path],
    style: Optional[BlueprintStyle] = None,
    pages: Optional[List[int]] = None,
) -> ExtractionResult:
    """
    Extract room areas from PDF with automatic style detection.

    Args:
        pdf_path: Path to PDF file
        style: Optional blueprint style (auto-detected if None)
        pages: Optional list of page indices (all pages if None)

    Returns:
        ExtractionResult with rooms, totals, and metadata

    Example:
        >>> result = extract_room_areas("floorplan.pdf")
        >>> print(f"Found {result.room_count} rooms")
        >>> print(f"Total area: {result.total_area_m2} m²")
        >>> for room in result.rooms:
        ...     print(f"  {room.room_number}: {room.area_m2} m²")
    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF is required. Install with: pip install PyMuPDF")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    # Get full text for style detection
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    # Detect or use provided style
    detected_style = style or detect_blueprint_style(full_text)

    # Select extraction function
    extract_fn = {
        BlueprintStyle.HAARDTRING: extract_haardtring,
        BlueprintStyle.LEIQ: extract_leiq,
        BlueprintStyle.OMNITURM: extract_omniturm,
    }.get(detected_style)

    rooms: List[ExtractedRoom] = []
    warnings: List[str] = []

    if not extract_fn:
        warnings.append(f"Unknown blueprint style, trying flexible extraction")
        extract_fn = extract_generic

    # Process pages
    page_indices = pages if pages is not None else range(len(doc))

    for page_idx in page_indices:
        if page_idx >= len(doc):
            warnings.append(f"Page {page_idx} does not exist")
            continue

        page = doc[page_idx]
        text = page.get_text()
        lines = text.split('\n')

        page_rooms = extract_fn(lines, page_idx)
        rooms.extend(page_rooms)

        if not page_rooms:
            # Try other extractors as fallback
            for alt_style, alt_fn in [
                (BlueprintStyle.HAARDTRING, extract_haardtring),
                (BlueprintStyle.LEIQ, extract_leiq),
                (BlueprintStyle.OMNITURM, extract_omniturm),
            ]:
                if alt_fn != extract_fn:
                    alt_rooms = alt_fn(lines, page_idx)
                    if alt_rooms:
                        rooms.extend(alt_rooms)
                        warnings.append(f"Page {page_idx}: Used {alt_style.value} pattern as fallback")
                        break

            # If still no rooms, try generic
            if not page_rooms and extract_fn != extract_generic:
                generic_rooms = extract_generic(lines, page_idx)
                if generic_rooms:
                    rooms.extend(generic_rooms)
                    warnings.append(f"Page {page_idx}: Used generic flexible extraction")

    page_count = len(doc)
    doc.close()

    # Calculate totals
    total_area = round(sum(r.area_m2 for r in rooms), 2)
    total_counted = round(sum(r.counted_m2 for r in rooms), 2)

    # Calculate totals by category
    totals_by_category = {}
    for room in rooms:
        cat = room.category.value
        totals_by_category[cat] = totals_by_category.get(cat, 0) + room.counted_m2
    totals_by_category = {k: round(v, 2) for k, v in totals_by_category.items()}

    return ExtractionResult(
        rooms=rooms,
        total_area_m2=total_area,
        total_counted_m2=total_counted,
        room_count=len(rooms),
        page_count=page_count,
        blueprint_style=detected_style,
        extraction_method="unified_extraction",
        warnings=warnings,
        totals_by_category=totals_by_category,
    )


# =============================================================================
# CONVENIENCE API
# =============================================================================

def extract_to_dict(
    pdf_path: Union[str, Path],
    style: Optional[str] = None,
    pages: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Extract room areas and return as dictionary (JSON-serializable).
    """
    style_enum = BlueprintStyle(style) if style else None
    result = extract_room_areas(pdf_path, style_enum, pages)
    return result.to_dict()


def get_summary(result: ExtractionResult) -> Dict[str, Any]:
    """
    Generate a summary of extraction results.
    """
    return {
        "total_rooms": result.room_count,
        "total_area_m2": result.total_area_m2,
        "total_counted_m2": result.total_counted_m2,
        "blueprint_style": result.blueprint_style.value,
        "categories": result.totals_by_category,
        "has_warnings": len(result.warnings) > 0,
    }


# =============================================================================
# PDFPLUMBER FALLBACK (if PyMuPDF fails)
# =============================================================================

def extract_room_areas_pdfplumber(
    pdf_path: Union[str, Path],
    pages: Optional[List[int]] = None,
) -> ExtractionResult:
    """
    Fallback extraction using pdfplumber when PyMuPDF fails.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    rooms: List[ExtractedRoom] = []
    warnings: List[str] = ["Used pdfplumber fallback"]

    # Area pattern
    area_pattern = re.compile(r'NRF\s*:\s*(\d+[,.]?\d*)\s*m[²2]?', re.IGNORECASE)

    with pdfplumber.open(str(path)) as pdf:
        page_indices = pages if pages is not None else range(len(pdf.pages))
        room_counter = 0

        for page_idx in page_indices:
            if page_idx >= len(pdf.pages):
                continue

            page = pdf.pages[page_idx]
            text = page.extract_text() or ""

            for match in area_pattern.finditer(text):
                try:
                    room_counter += 1
                    area_str = match.group(1).replace(',', '.')
                    area_m2 = float(area_str)

                    rooms.append(ExtractedRoom(
                        room_number=f"room_{room_counter:03d}",
                        room_name="Unknown",
                        area_m2=area_m2,
                        counted_m2=area_m2,
                        factor=1.0,
                        page=page_idx,
                        source_text=match.group(0),
                        extraction_pattern="NRF:",
                    ))
                except ValueError:
                    pass

        page_count = len(pdf.pages)

    total_area = round(sum(r.area_m2 for r in rooms), 2)

    return ExtractionResult(
        rooms=rooms,
        total_area_m2=total_area,
        total_counted_m2=total_area,
        room_count=len(rooms),
        page_count=page_count,
        blueprint_style=BlueprintStyle.UNKNOWN,
        extraction_method="pdfplumber_fallback",
        warnings=warnings,
    )


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python area_extraction_standalone.py <pdf_path>")
        print("\nExample:")
        print("  python area_extraction_standalone.py floorplan.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print(f"\n📄 Extracting from: {pdf_path}")
    print("-" * 50)

    try:
        result = extract_room_areas(pdf_path)

        print(f"🏠 Blueprint Style: {result.blueprint_style.value}")
        print(f"📑 Pages: {result.page_count}")
        print(f"🚪 Rooms Found: {result.room_count}")
        print(f"📐 Total Area: {result.total_area_m2} m²")
        print(f"📊 Counted Area: {result.total_counted_m2} m²")

        if result.warnings:
            print(f"\n⚠️  Warnings:")
            for w in result.warnings:
                print(f"   - {w}")

        print(f"\n📋 Rooms by Category:")
        for cat, total in sorted(result.totals_by_category.items()):
            count = len([r for r in result.rooms if r.category.value == cat])
            print(f"   {cat}: {total} m² ({count} rooms)")

        print(f"\n📝 Room Details:")
        for room in result.rooms[:20]:  # Show first 20
            print(f"   {room.room_number}: {room.room_name} - {room.area_m2} m² (source: {room.source_text})")

        if len(result.rooms) > 20:
            print(f"   ... and {len(result.rooms) - 20} more rooms")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
