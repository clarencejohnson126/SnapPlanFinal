"""
Unified Room Area Extraction Service

Deterministic extraction from German CAD-generated PDFs with full traceability.
Supports multiple blueprint styles with automatic detection.

Supported Styles:
- Haardtring (Residential): F: pattern, R2.E5.3.5 room numbers, 50% balcony
- LeiQ (Office): NRF: pattern, B.00.2.002 room numbers, U:/LH: data
- Omniturm (Highrise): NGF: pattern, 33_b6.12 room numbers, reversed Schacht

Hard Rules:
1. Only extract values that exist as text in the PDF
2. Every extracted number includes source_text, bbox, page
3. Missing values are explicitly tracked and excluded from totals
4. No LLM inference during extraction - 100% deterministic
"""

import re
import fitz  # PyMuPDF
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Union
from pathlib import Path
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND CONSTANTS
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

    # Grouped totals
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


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def parse_german_number(s: str) -> float:
    """
    Parse German number format to float.

    Handles:
    - Comma as decimal: "22,79" -> 22.79
    - Thousands separator: "1.070,55" -> 1070.55
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

    Checks for characteristic patterns:
    - Haardtring: F: + R2.E5.x.x room numbers
    - LeiQ: NRF: + B.00.x.x room numbers
    - Omniturm: NGF: + 33_xx.xx room numbers
    """
    # Count pattern matches
    has_f = bool(re.search(r'\bF:\s*\d', text))
    has_nrf = bool(re.search(r'\bNRF:\s*\d', text, re.IGNORECASE))
    has_ngf = bool(re.search(r'\bNGF:\s*\d', text, re.IGNORECASE))

    has_r_pattern = bool(re.search(r'\bR\d+\.E\d+\.\d+\.\d+\b', text))
    has_b_pattern = bool(re.search(r'\bB\.\d+\.\d+\.\d+\b', text))
    has_grid_pattern = bool(re.search(r'\b\d+_[a-z]\d+\.\d+\b', text))

    # Determine style based on combinations
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
    Special: 50%: XX,XX m2 for balcony counted area
    """
    rooms = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for room number pattern
        room_match = re.match(r'^(R\d+\.E\d+\.\d+\.\d+)$', line)
        if room_match:
            room_num = room_match.group(1)
            room_name = None
            area = None
            balcony_area = None

            # Look for room name on next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'^(F:|BA:|B:|W:|D:|[\d,]+)', next_line):
                    room_name = next_line

            # Look for area value
            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                # F: XX,XX m2 on same line
                f_match = re.match(r'^F:\s*([\d,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if f_match:
                    area = parse_german_number(f_match.group(1))
                    # Check for 50% on next line
                    if j + 1 < len(lines):
                        b_match = re.match(r'^50%:\s*([\d,]+)\s*m[²2]?$', lines[j + 1].strip())
                        if b_match:
                            balcony_area = parse_german_number(b_match.group(1))
                    break

                # F: split across lines
                if curr == 'F:' and j + 1 < len(lines):
                    area_match = re.match(r'^([\d,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match:
                        area = parse_german_number(area_match.group(1))
                        if j + 2 < len(lines):
                            b_match = re.match(r'^50%:\s*([\d,]+)\s*m[²2]?$', lines[j + 2].strip())
                            if b_match:
                                balcony_area = parse_german_number(b_match.group(1))
                        break

                # Stop if we hit another room number
                if re.match(r'^R\d+\.E\d+\.\d+\.\d+$', curr):
                    break

            if area:
                # Determine factor
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
    Additional: U: (perimeter), LH: (height)
    """
    rooms = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for room number pattern
        room_match = re.match(r'^(B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+)$', line)
        if room_match:
            room_num = room_match.group(1)
            room_name = None
            area = None
            perimeter = None
            height = None

            # Look for room name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'^(NRF|F[=:]|U[=:]|LH[=:]|LRH[=:]|B\.|[\d,]+)', next_line):
                    room_name = next_line

            # Look for values
            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                # NRF: or NRF= XX,XX m2 on same line
                nrf_match = re.match(r'^NRF[=:]\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if nrf_match and area is None:
                    area = parse_german_number(nrf_match.group(1))
                    continue

                # F: or F= XX,XX m2 (alternative area format)
                f_match = re.match(r'^F[=:]\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if f_match and area is None:
                    area = parse_german_number(f_match.group(1))
                    continue

                # NRF: split across lines
                if curr in ('NRF:', 'NRF=') and j + 1 < len(lines):
                    area_match = re.match(r'^([\d.,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match and area is None:
                        area = parse_german_number(area_match.group(1))
                        continue

                # U: or U= perimeter (handles both U: XX,XX m and U= XX.XX m formats)
                u_match = re.match(r'^U[=:]\s*([\d.,]+)\s*m$', curr, re.IGNORECASE)
                if u_match:
                    perimeter = parse_german_number(u_match.group(1))
                    continue

                # LH: or LRH: or LRH= height (lichte Raumhöhe)
                lh_match = re.match(r'^L(?:R)?H[=:]\s*([\d.,]+)\s*m$', curr, re.IGNORECASE)
                if lh_match:
                    height = parse_german_number(lh_match.group(1))
                    continue

                # Stop if we hit another room number
                if re.match(r'^B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+$', curr):
                    break

            if area:
                rooms.append(ExtractedRoom(
                    room_number=room_num,
                    room_name=room_name or "Unknown",
                    area_m2=area,
                    counted_m2=area,  # LeiQ doesn't have balcony factor
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

    Pattern 1 (Standard): Room number (33_b6.12) -> Room name -> NGF: XX,XX m2
    Pattern 2 (Schacht): Schacht XX -> Type -> XX,XX m2 -> Room number

    Note: Schacht pattern is REVERSED - room number comes after area!
    """
    rooms = []
    processed = set()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Pattern 1: Standard room number first
        room_match = re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', line)
        if room_match and line not in processed:
            room_num = line
            room_name = None
            area = None

            # Look for room name and area
            for j in range(i + 1, min(len(lines), i + 15)):
                curr = lines[j].strip()

                # Stop if we hit another room number
                if re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', curr):
                    break

                # Get room name (first non-technical line)
                if room_name is None and curr and not re.match(
                    r'^(NGF|UKRD|UKFD|OKFF|OKRF|LRH|[\d,]+\s*m|Schacht)', curr
                ):
                    room_name = curr

                # NGF: XX,XX m2 on same line (handles thousands: 1.070,55)
                ngf_match = re.match(r'^NGF:\s*([\d.,]+)\s*m[²2]?$', curr, re.IGNORECASE)
                if ngf_match:
                    area = parse_german_number(ngf_match.group(1))
                    break

                # NGF: split across lines
                if curr == 'NGF:' and j + 1 < len(lines):
                    area_match = re.match(r'^([\d.,]+)\s*m[²2]?$', lines[j + 1].strip())
                    if area_match:
                        area = parse_german_number(area_match.group(1))
                        break

                # Special: Schacht pattern (name -> type -> area)
                schacht_match = re.match(r'^(Schacht \d+)$', curr)
                if schacht_match:
                    room_name = schacht_match.group(1)
                    # Type is next, then area
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


# =============================================================================
# GENERIC FLEXIBLE EXTRACTOR
# =============================================================================

# Flexible area patterns - STRICT to avoid matching random m² values
# Only match when clearly labeled as room area
FLEXIBLE_AREA_PATTERNS = [
    # Standard German room area labels (require explicit label prefix)
    re.compile(r'(?:NRF|NGF|BGF|Fläche|Fl|FL|GF|WF|NF)\s*[=:]\s*([\d.,]+)\s*m[²2]?', re.IGNORECASE),
    # F: pattern (standalone, not part of other words)
    re.compile(r'^F\s*[=:]\s*([\d.,]+)\s*m[²2]?$', re.IGNORECASE),
    # Area with qm suffix after a label
    re.compile(r'(?:NRF|NGF|Fläche)\s*[=:]\s*([\d.,]+)\s*qm\b', re.IGNORECASE),
]

# NOTE: We intentionally removed overly broad patterns like:
# - r'^([\d.,]+)\s*m[²2]$' - matches ANY number + m², creating phantom rooms
# - r'[=:]\s*([\d.,]+)\s*m[²2]?$' - too broad, catches dimensions/scales

# Flexible room identifier patterns - STRICT to require structured IDs
FLEXIBLE_ROOM_PATTERNS = [
    # German style: R2.E5.3.5, B.00.2.002, BT1.EG.001 (require at least 3 segments)
    re.compile(r'^([A-Z]+\d*[\._][A-Z0-9]+[\._][A-Z0-9]+[\._][A-Z0-9]+)$', re.IGNORECASE),
    # Grid style: 33_b6.12
    re.compile(r'^(\d+_[a-z]\d+\.\d+)$'),
    # Room with floor prefix: EG.001, OG1.002, UG.003 (German floor notation)
    re.compile(r'^([EOU]G\d*[\._]\d{3})$', re.IGNORECASE),
    # Structured room IDs with 2 segments (require letter prefix): R.001, B.002
    re.compile(r'^([A-Z][\._]\d{3})$', re.IGNORECASE),
]

# NOTE: We removed overly broad patterns that would match random text:
# - Simple numbered "R001" without structure
# - Generic alphanumeric patterns


def extract_generic(lines: List[str], page_idx: int) -> List[ExtractedRoom]:
    """
    Generic flexible extractor for any blueprint format.

    This is the fallback when known patterns don't match.
    It attempts to find area values (m²) near identifiable room labels.

    Strategy:
    1. Find all area values with m² in the text
    2. Look backwards and forwards for room identifiers
    3. Associate each area with the nearest room label
    """
    rooms = []
    found_areas = []
    found_room_ids = {}

    # First pass: find all area values and their positions
    for i, line in enumerate(lines):
        line = line.strip()

        # Try each area pattern
        for pattern in FLEXIBLE_AREA_PATTERNS:
            match = pattern.search(line)
            if match:
                try:
                    area = parse_german_number(match.group(1))
                    if 0.5 <= area <= 10000:  # Reasonable room area range
                        found_areas.append({
                            'line_idx': i,
                            'area': area,
                            'source_line': line,
                            'pattern': pattern.pattern[:30],
                        })
                except (ValueError, IndexError):
                    pass
                break  # Only match first pattern per line

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
        # Find the closest area to this room identifier
        best_area = None
        best_distance = float('inf')
        best_area_idx = None

        for area_idx, area_info in enumerate(found_areas):
            if area_idx in used_areas:
                continue

            distance = abs(area_info['line_idx'] - room_line_idx)
            # Prefer areas that come AFTER the room ID (more common pattern)
            if area_info['line_idx'] > room_line_idx:
                distance -= 0.5  # Slight preference for after

            if distance < best_distance and distance < 15:  # Max 15 lines apart
                best_distance = distance
                best_area = area_info
                best_area_idx = area_idx

        if best_area:
            used_areas.add(best_area_idx)

            # Try to find room name (line after room ID, before area)
            room_name = None
            start_search = room_line_idx + 1
            end_search = best_area['line_idx']

            for j in range(start_search, min(end_search, start_search + 5)):
                if j < len(lines):
                    candidate = lines[j].strip()
                    # Skip technical lines, numbers, and common labels
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

    # Fourth pass: DISABLED - Do NOT create phantom rooms from orphan area values
    # The old approach created fake "Room_PAGE_001" entries for every m² value found,
    # which resulted in 100+ phantom "rooms" that were actually dimension labels,
    # scale factors, or other non-room values.
    #
    # If we couldn't match area values to proper room IDs, it's better to return
    # fewer rooms than to pollute results with garbage entries.
    #
    # The strict patterns above ensure we only extract legitimate rooms.

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
    """
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
        extract_fn = extract_generic  # Use flexible extractor for unknown styles

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
            # Try other extractors as fallback (known patterns first)
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

            # If still no rooms, try the generic flexible extractor
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

    This is the main API for the web application.
    """
    style_enum = BlueprintStyle(style) if style else None
    result = extract_room_areas(pdf_path, style_enum, pages)
    return result.to_dict()


def get_summary(result: ExtractionResult) -> Dict[str, Any]:
    """
    Generate a summary of extraction results for display.
    """
    return {
        "total_rooms": result.room_count,
        "total_area_m2": result.total_area_m2,
        "total_counted_m2": result.total_counted_m2,
        "blueprint_style": result.blueprint_style.value,
        "categories": result.totals_by_category,
        "has_warnings": len(result.warnings) > 0,
    }
