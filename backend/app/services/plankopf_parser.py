"""
Plankopf (Title Block/Legend) Parser

Detects and parses the legend/title block region of German construction blueprints
to extract symbol-label mappings for materials like Trockenbau, Mauerwerk, etc.

The Plankopf is typically located on the right side of the blueprint and contains:
- Material legends (symbol + label pairs)
- Scale information
- Project metadata
- Revision notes
"""

import re
import math
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import fitz  # PyMuPDF


class PatternType(str, Enum):
    """Types of fill patterns in blueprints."""
    HATCHING = "hatching"           # Parallel diagonal lines
    CROSSHATCH = "crosshatch"       # Two sets of perpendicular lines
    SOLID_FILL = "solid_fill"       # Uniform color fill
    DOT_PATTERN = "dots"            # Regular dot pattern
    STIPPLE = "stipple"             # Random dots
    NONE = "none"                   # No fill


@dataclass
class BoundingBox:
    """Bounding box for a region."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return abs(self.x1 - self.x0)

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def to_fitz_rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)

    def overlaps(self, other: "BoundingBox", min_overlap: float = 0.0) -> bool:
        """Check if this bbox overlaps with another."""
        x_overlap = max(0, min(self.x1, other.x1) - max(self.x0, other.x0))
        y_overlap = max(0, min(self.y1, other.y1) - max(self.y0, other.y0))
        overlap_area = x_overlap * y_overlap
        min_area = min(self.area, other.area)
        if min_area == 0:
            return False
        return (overlap_area / min_area) >= min_overlap

    def to_dict(self) -> Dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_fitz_rect(cls, rect: fitz.Rect) -> "BoundingBox":
        return cls(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)


@dataclass
class PatternInfo:
    """Characteristics of a visual pattern."""
    pattern_type: PatternType
    stroke_color: Optional[Tuple[float, float, float]] = None  # RGB 0-1
    fill_color: Optional[Tuple[float, float, float]] = None
    hatching_angle: Optional[float] = None      # Degrees
    hatching_spacing: Optional[float] = None    # PDF points
    line_count: int = 0
    secondary_angle: Optional[float] = None     # For crosshatch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "stroke_color": self.stroke_color,
            "fill_color": self.fill_color,
            "hatching_angle": self.hatching_angle,
            "hatching_spacing": self.hatching_spacing,
            "line_count": self.line_count,
            "secondary_angle": self.secondary_angle,
        }


@dataclass
class LegendSymbol:
    """A symbol from the Plankopf legend."""
    symbol_id: str
    label: str                      # Original label text
    label_normalized: str           # Lowercase, stripped
    bbox: BoundingBox               # Location of symbol in legend
    pattern_info: PatternInfo       # Visual pattern characteristics
    material_type: Optional[str] = None  # Detected material category
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "label": self.label,
            "label_normalized": self.label_normalized,
            "bbox": self.bbox.to_dict(),
            "pattern_info": self.pattern_info.to_dict(),
            "material_type": self.material_type,
            "confidence": self.confidence,
        }


@dataclass
class PlankopfResult:
    """Parsed title block/legend."""
    page_number: int
    plankopf_bbox: BoundingBox
    symbols: List[LegendSymbol] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)  # Scale, date, project, etc.
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "plankopf_bbox": self.plankopf_bbox.to_dict(),
            "symbols": [s.to_dict() for s in self.symbols],
            "metadata": self.metadata,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


# German material keywords for classification
DRYWALL_KEYWORDS = [
    "trockenbau", "trockenbauwand", "trockenbaukonstruktion",
    "gipskarton", "gkb", "gkf", "rigips",
    "ständerwand", "vorsatzschale", "abhangdecke",
    "leichtbauwand", "montagewand", "gipsplatte",
    "trockenputz", "gipsfaser",
]

MASONRY_KEYWORDS = [
    "mauerwerk", "mw", "ziegel", "kalksandstein", "kls",
    "porenbeton", "ytong", "backstein", "klinker",
]

CONCRETE_KEYWORDS = [
    "beton", "stahlbeton", "stb", "ortbeton",
    "fertigteil", "betonwand",
]

INSULATION_KEYWORDS = [
    "dämmung", "wärmedämmung", "isolierung",
    "mineralwolle", "styropor", "eps", "xps",
    "wdvs", "perimeterdämmung",
]

WOOD_KEYWORDS = [
    "holz", "holzständer", "holzrahmen", "holzbau",
    "bsh", "kvh", "osb", "spanplatte",
]

# Metadata patterns for title block
SCALE_PATTERNS = [
    r"(?:Maßstab|Massstab|Scale|M)\s*[=:]\s*1\s*[:/]\s*(\d+)",
    r"1\s*[:/]\s*(\d+)",
]

DATE_PATTERNS = [
    r"(?:Datum|Date|Stand)[:\s]+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    r"(\d{1,2}\.\d{1,2}\.\d{4})",
]


def _generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:8]


def detect_plankopf_region(page: fitz.Page) -> Optional[BoundingBox]:
    """
    Detect the title block/legend region on a blueprint page.

    Strategy:
    1. German blueprints typically have Plankopf on the right 20-35% of page
    2. Look for regions with higher text density than the main drawing
    3. Verify by checking for characteristic text (Maßstab, Projekt, etc.)

    Args:
        page: PyMuPDF page object

    Returns:
        BoundingBox of detected Plankopf region, or None if not found
    """
    page_rect = page.rect
    page_width = page_rect.width
    page_height = page_rect.height

    # Candidate regions (right side of page)
    candidates = [
        # Full right strip (25%)
        fitz.Rect(page_width * 0.75, 0, page_width, page_height),
        # Full right strip (30%)
        fitz.Rect(page_width * 0.70, 0, page_width, page_height),
        # Lower right quadrant
        fitz.Rect(page_width * 0.65, page_height * 0.5, page_width, page_height),
        # Right third
        fitz.Rect(page_width * 0.67, 0, page_width, page_height),
    ]

    best_candidate = None
    best_score = 0.0

    for rect in candidates:
        score = _score_plankopf_candidate(page, rect)
        if score > best_score:
            best_score = score
            best_candidate = rect

    if best_candidate and best_score > 0.3:
        # Refine the region by finding actual content boundaries
        refined = _refine_plankopf_region(page, best_candidate)
        return BoundingBox.from_fitz_rect(refined)

    return None


def _score_plankopf_candidate(page: fitz.Page, rect: fitz.Rect) -> float:
    """
    Score a candidate region for being a Plankopf.

    Criteria:
    - Text density (title blocks have more text than drawing area)
    - Presence of characteristic keywords (Maßstab, Projekt, etc.)
    - Rectangular frames (title blocks are often framed)
    """
    score = 0.0

    # Extract text in region
    text = page.get_text("text", clip=rect)
    text_lower = text.lower()

    # Text density score
    text_length = len(text.strip())
    area = rect.width * rect.height
    density = text_length / area if area > 0 else 0

    # Higher density is better (but not too high - that might be a schedule)
    if 0.001 < density < 0.05:
        score += 0.3
    elif 0.0005 < density < 0.001:
        score += 0.2

    # Keyword score
    plankopf_keywords = [
        "maßstab", "massstab", "scale", "projekt", "project",
        "bauherr", "architekt", "datum", "date", "index",
        "gezeichnet", "geprüft", "zeichnung", "plan", "blatt",
    ]
    keyword_matches = sum(1 for kw in plankopf_keywords if kw in text_lower)
    score += min(0.4, keyword_matches * 0.08)

    # Material legend keywords
    material_keywords = DRYWALL_KEYWORDS + MASONRY_KEYWORDS + CONCRETE_KEYWORDS
    material_matches = sum(1 for kw in material_keywords if kw in text_lower)
    score += min(0.3, material_matches * 0.1)

    return score


def _refine_plankopf_region(page: fitz.Page, initial_rect: fitz.Rect) -> fitz.Rect:
    """
    Refine the Plankopf region by finding actual content boundaries.
    """
    # Get text blocks in region
    blocks = page.get_text("dict", clip=initial_rect).get("blocks", [])

    if not blocks:
        return initial_rect

    # Find bounding box of all text
    x0_min = initial_rect.x1
    y0_min = initial_rect.y1
    x1_max = initial_rect.x0
    y1_max = initial_rect.y0

    for block in blocks:
        if block.get("type") != 0:  # Skip images
            continue
        bbox = block.get("bbox", (0, 0, 0, 0))
        x0_min = min(x0_min, bbox[0])
        y0_min = min(y0_min, bbox[1])
        x1_max = max(x1_max, bbox[2])
        y1_max = max(y1_max, bbox[3])

    # Add margin
    margin = 20
    return fitz.Rect(
        max(initial_rect.x0, x0_min - margin),
        max(initial_rect.y0, y0_min - margin),
        min(initial_rect.x1, x1_max + margin),
        min(initial_rect.y1, y1_max + margin),
    )


def extract_text_spans(
    page: fitz.Page,
    region: fitz.Rect,
) -> List[Tuple[str, BoundingBox, Dict[str, Any]]]:
    """
    Extract text spans with their positions from a region.

    Returns list of (text, bbox, metadata) tuples.
    """
    spans = []
    raw = page.get_text("dict", clip=region)

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue

                bbox_tuple = span.get("bbox", (0, 0, 0, 0))
                bbox = BoundingBox(
                    x0=bbox_tuple[0],
                    y0=bbox_tuple[1],
                    x1=bbox_tuple[2],
                    y1=bbox_tuple[3],
                )

                metadata = {
                    "font": span.get("font", ""),
                    "size": span.get("size", 0),
                    "flags": span.get("flags", 0),
                }

                spans.append((text, bbox, metadata))

    return spans


def extract_drawings_in_region(
    page: fitz.Page,
    region: fitz.Rect,
) -> List[Dict[str, Any]]:
    """
    Extract vector drawings (paths) within a region.
    """
    all_drawings = page.get_drawings()
    drawings_in_region = []

    for drawing in all_drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue

        drawing_rect = fitz.Rect(rect)
        # Check if drawing is mostly within region
        intersection = drawing_rect & region
        if intersection.is_empty:
            continue

        # At least 50% overlap
        if intersection.get_area() >= drawing_rect.get_area() * 0.5:
            drawings_in_region.append(drawing)

    return drawings_in_region


def analyze_pattern(drawing: Dict[str, Any]) -> PatternInfo:
    """
    Analyze a drawing to extract pattern characteristics.
    """
    items = drawing.get("items", [])
    stroke_color = drawing.get("color")
    fill_color = drawing.get("fill")

    # Extract line segments
    lines = []
    for item in items:
        if len(item) < 3:
            continue
        cmd = item[0]
        if cmd == "l":  # Line command
            p1, p2 = item[1], item[2]
            if hasattr(p1, 'x') and hasattr(p2, 'x'):
                lines.append({
                    "x1": p1.x, "y1": p1.y,
                    "x2": p2.x, "y2": p2.y,
                })

    if len(lines) < 2:
        # Not enough lines for hatching
        if fill_color:
            return PatternInfo(
                pattern_type=PatternType.SOLID_FILL,
                fill_color=fill_color,
                stroke_color=stroke_color,
            )
        return PatternInfo(pattern_type=PatternType.NONE, stroke_color=stroke_color)

    # Analyze line angles
    angles = []
    for line in lines:
        dx = line["x2"] - line["x1"]
        dy = line["y2"] - line["y1"]
        if dx == 0 and dy == 0:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        # Normalize to 0-180 range
        angle = angle % 180
        angles.append(angle)

    if not angles:
        return PatternInfo(pattern_type=PatternType.NONE, stroke_color=stroke_color)

    # Cluster angles
    angle_clusters = _cluster_angles(angles, tolerance=10.0)

    if len(angle_clusters) == 1:
        # Simple hatching
        dominant_angle = angle_clusters[0]["center"]
        spacing = _estimate_line_spacing(lines, dominant_angle)

        return PatternInfo(
            pattern_type=PatternType.HATCHING,
            stroke_color=stroke_color,
            fill_color=fill_color,
            hatching_angle=dominant_angle,
            hatching_spacing=spacing,
            line_count=len(lines),
        )

    elif len(angle_clusters) == 2:
        # Cross-hatch
        angles_sorted = sorted(angle_clusters, key=lambda c: c["count"], reverse=True)
        return PatternInfo(
            pattern_type=PatternType.CROSSHATCH,
            stroke_color=stroke_color,
            fill_color=fill_color,
            hatching_angle=angles_sorted[0]["center"],
            secondary_angle=angles_sorted[1]["center"],
            line_count=len(lines),
        )

    # Complex pattern
    return PatternInfo(
        pattern_type=PatternType.HATCHING,
        stroke_color=stroke_color,
        fill_color=fill_color,
        line_count=len(lines),
    )


def _cluster_angles(angles: List[float], tolerance: float = 10.0) -> List[Dict[str, Any]]:
    """
    Cluster angles into groups.
    """
    if not angles:
        return []

    sorted_angles = sorted(angles)
    clusters = []
    current_cluster = [sorted_angles[0]]

    for angle in sorted_angles[1:]:
        if angle - current_cluster[-1] <= tolerance:
            current_cluster.append(angle)
        else:
            if current_cluster:
                clusters.append({
                    "center": sum(current_cluster) / len(current_cluster),
                    "count": len(current_cluster),
                    "angles": current_cluster,
                })
            current_cluster = [angle]

    if current_cluster:
        clusters.append({
            "center": sum(current_cluster) / len(current_cluster),
            "count": len(current_cluster),
            "angles": current_cluster,
        })

    # Filter small clusters
    return [c for c in clusters if c["count"] >= 2]


def _estimate_line_spacing(lines: List[Dict], dominant_angle: float) -> Optional[float]:
    """
    Estimate spacing between parallel lines.
    """
    if len(lines) < 2:
        return None

    # Calculate perpendicular distances from origin for lines at similar angle
    distances = []
    angle_rad = math.radians(dominant_angle)

    for line in lines:
        # Perpendicular distance using line midpoint
        mx = (line["x1"] + line["x2"]) / 2
        my = (line["y1"] + line["y2"]) / 2
        # Distance along perpendicular direction
        dist = mx * math.sin(angle_rad) - my * math.cos(angle_rad)
        distances.append(abs(dist))

    if len(distances) < 2:
        return None

    # Sort and find median spacing
    distances.sort()
    spacings = [distances[i+1] - distances[i] for i in range(len(distances)-1)]
    spacings = [s for s in spacings if s > 0.1]  # Filter near-zero

    if spacings:
        return sum(spacings) / len(spacings)

    return None


def find_pattern_left_of_text(
    drawings: List[Dict[str, Any]],
    text_bbox: BoundingBox,
    max_distance: float = 100.0,
) -> Optional[Dict[str, Any]]:
    """
    Find a drawing pattern immediately to the left of text.
    """
    best_match = None
    best_distance = max_distance

    text_left = text_bbox.x0
    text_center_y = (text_bbox.y0 + text_bbox.y1) / 2

    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue

        drawing_right = rect[2]  # x1
        drawing_center_y = (rect[1] + rect[3]) / 2

        # Must be to the left of text
        if drawing_right > text_left:
            continue

        # Check horizontal distance
        h_distance = text_left - drawing_right
        if h_distance > max_distance:
            continue

        # Check vertical alignment
        v_distance = abs(text_center_y - drawing_center_y)
        if v_distance > text_bbox.height * 2:
            continue

        # Combined distance score
        distance = h_distance + v_distance * 0.5

        if distance < best_distance:
            best_distance = distance
            best_match = drawing

    return best_match


def classify_material_type(label: str) -> Optional[str]:
    """
    Classify material type from label text.
    """
    label_lower = label.lower()

    for keyword in DRYWALL_KEYWORDS:
        if keyword in label_lower:
            return "drywall"

    for keyword in MASONRY_KEYWORDS:
        if keyword in label_lower:
            return "masonry"

    for keyword in CONCRETE_KEYWORDS:
        if keyword in label_lower:
            return "concrete"

    for keyword in INSULATION_KEYWORDS:
        if keyword in label_lower:
            return "insulation"

    for keyword in WOOD_KEYWORDS:
        if keyword in label_lower:
            return "wood"

    return None


def extract_metadata(page: fitz.Page, region: fitz.Rect) -> Dict[str, str]:
    """
    Extract metadata from Plankopf (scale, date, project name, etc.).
    """
    text = page.get_text("text", clip=region)
    metadata = {}

    # Extract scale
    for pattern in SCALE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metadata["scale"] = f"1:{match.group(1)}"
            break

    # Extract date
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metadata["date"] = match.group(1)
            break

    # Extract project name (often after "Projekt:" or "Bauvorhaben:")
    project_match = re.search(
        r"(?:Projekt|Bauvorhaben|Project)[:\s]+([^\n]+)",
        text,
        re.IGNORECASE
    )
    if project_match:
        metadata["project"] = project_match.group(1).strip()

    return metadata


def extract_legend_symbols(
    page: fitz.Page,
    plankopf_rect: fitz.Rect,
) -> List[LegendSymbol]:
    """
    Extract symbol-label pairs from the legend area.

    Strategy:
    1. Get all text spans with positions
    2. Get all vector drawings (patterns)
    3. Match: pattern LEFT OF text = symbol for that label
    4. Extract pattern characteristics
    """
    # Get text spans
    text_spans = extract_text_spans(page, plankopf_rect)

    # Get vector drawings
    drawings = extract_drawings_in_region(page, plankopf_rect)

    symbols = []

    for text, text_bbox, text_meta in text_spans:
        # Skip short text (likely not a label)
        if len(text) < 3:
            continue

        # Skip numeric-only text
        if text.replace(",", "").replace(".", "").replace(" ", "").isdigit():
            continue

        # Check if this looks like a material label
        material_type = classify_material_type(text)
        if material_type is None:
            # Check if it might still be a legend entry (near a pattern)
            nearby_pattern = find_pattern_left_of_text(drawings, text_bbox, max_distance=80)
            if nearby_pattern is None:
                continue
        else:
            nearby_pattern = find_pattern_left_of_text(drawings, text_bbox, max_distance=100)

        if nearby_pattern:
            pattern_info = analyze_pattern(nearby_pattern)
            pattern_bbox = BoundingBox(
                x0=nearby_pattern["rect"][0],
                y0=nearby_pattern["rect"][1],
                x1=nearby_pattern["rect"][2],
                y1=nearby_pattern["rect"][3],
            )

            confidence = 0.7  # Base confidence
            if material_type:
                confidence += 0.2  # Higher if we recognized the material
            if pattern_info.pattern_type != PatternType.NONE:
                confidence += 0.1  # Higher if pattern detected

            symbol = LegendSymbol(
                symbol_id=f"sym_{_generate_id()}",
                label=text,
                label_normalized=text.lower().strip(),
                bbox=pattern_bbox,
                pattern_info=pattern_info,
                material_type=material_type,
                confidence=min(1.0, confidence),
            )
            symbols.append(symbol)

    return symbols


def parse_plankopf(page: fitz.Page, page_number: int = 0) -> Optional[PlankopfResult]:
    """
    Parse the Plankopf (title block/legend) from a blueprint page.

    Args:
        page: PyMuPDF page object
        page_number: Page number for reference

    Returns:
        PlankopfResult with detected symbols and metadata, or None if not found
    """
    warnings = []

    # Step 1: Detect Plankopf region
    plankopf_bbox = detect_plankopf_region(page)
    if plankopf_bbox is None:
        return None

    plankopf_rect = plankopf_bbox.to_fitz_rect()

    # Step 2: Extract metadata
    metadata = extract_metadata(page, plankopf_rect)
    if "scale" not in metadata:
        warnings.append("Scale not detected in Plankopf - assuming 1:100")
        metadata["scale"] = "1:100"

    # Step 3: Extract legend symbols
    symbols = extract_legend_symbols(page, plankopf_rect)

    if not symbols:
        warnings.append("No material symbols found in legend")

    # Calculate overall confidence
    if symbols:
        confidence = sum(s.confidence for s in symbols) / len(symbols)
    else:
        confidence = 0.3  # Low confidence if no symbols found

    return PlankopfResult(
        page_number=page_number,
        plankopf_bbox=plankopf_bbox,
        symbols=symbols,
        metadata=metadata,
        confidence=confidence,
        warnings=warnings,
    )


def get_drywall_symbols(plankopf: PlankopfResult) -> List[LegendSymbol]:
    """
    Filter Plankopf symbols to get only drywall-related ones.
    """
    return [s for s in plankopf.symbols if s.material_type == "drywall"]
