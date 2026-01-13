"""
Revision Cloud Detection Service

Detects revision clouds (Revisionswolken) in CAD-derived PDFs.
These scalloped/wavy outlines indicate changes or unfinished areas
that require attention from construction managers and architects.

Technical approach:
- Extract vector paths from PDF using PyMuPDF
- Identify red/magenta colored paths (common revision cloud colors)
- Detect characteristic scalloped pattern (series of small arcs)
- Calculate bounding boxes and affected areas
"""

import fitz  # PyMuPDF
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import math


@dataclass
class BoundingBox:
    """Represents a rectangular bounding box."""
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

    def overlaps(self, other: "BoundingBox", threshold: float = 0.1) -> bool:
        """Check if this bbox overlaps with another by at least threshold percentage."""
        # Calculate intersection
        x_overlap = max(0, min(self.x1, other.x1) - max(self.x0, other.x0))
        y_overlap = max(0, min(self.y1, other.y1) - max(self.y0, other.y0))
        intersection = x_overlap * y_overlap

        # Calculate union
        union = self.area + other.area - intersection
        if union == 0:
            return False

        # IoU (Intersection over Union)
        iou = intersection / union
        return iou > threshold

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside this bbox."""
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def to_dict(self) -> Dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass
class RevisionCloud:
    """Represents a detected revision cloud."""
    page: int
    bbox: BoundingBox
    color: Tuple[float, float, float]  # RGB 0-1
    confidence: float  # 0-1 confidence score
    arc_count: int  # Number of arcs detected
    path_length: float  # Total path length
    associated_text: Optional[str] = None  # Any text found near the cloud
    affected_room_numbers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "bbox": self.bbox.to_dict(),
            "color": {
                "r": int(self.color[0] * 255),
                "g": int(self.color[1] * 255),
                "b": int(self.color[2] * 255),
            },
            "confidence": round(self.confidence, 2),
            "arc_count": self.arc_count,
            "associated_text": self.associated_text,
            "affected_room_numbers": self.affected_room_numbers,
        }


@dataclass
class RevisionCloudResult:
    """Result of revision cloud detection."""
    clouds: List[RevisionCloud]
    total_count: int
    pages_with_clouds: List[int]
    warning_message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clouds": [c.to_dict() for c in self.clouds],
            "total_count": self.total_count,
            "pages_with_clouds": self.pages_with_clouds,
            "warning_message": self.warning_message,
        }


def is_revision_cloud_color(color: Tuple[float, float, float], tolerance: float = 0.3) -> bool:
    """
    Check if a color matches typical revision cloud colors.

    Common colors:
    - Red: (1, 0, 0) - most common
    - Magenta: (1, 0, 1)
    - Orange-red: (1, 0.5, 0)
    - Dark red: (0.5, 0, 0)
    """
    if not color or len(color) < 3:
        return False

    r, g, b = color[0], color[1], color[2]

    # Red (most common for revision clouds) - lowered threshold
    if r > 0.5 and g < 0.5 and b < 0.5 and r > g and r > b:
        return True

    # Bright red
    if r > 0.8 and g < 0.3 and b < 0.3:
        return True

    # Magenta/Pink
    if r > 0.6 and g < 0.4 and b > 0.4:
        return True

    # Orange-red
    if r > 0.7 and 0.2 < g < 0.6 and b < 0.4:
        return True

    # Dark red (some CAD software uses darker reds)
    if 0.4 < r < 0.7 and g < 0.2 and b < 0.2:
        return True

    return False


def analyze_path_for_scallops(path_items: List, min_arcs: int = 3) -> Tuple[bool, int, float]:
    """
    Analyze a path to determine if it has the characteristic scalloped pattern
    of a revision cloud.

    Returns: (is_scalloped, arc_count, total_length)
    """
    if not path_items:
        return False, 0, 0

    arc_count = 0
    curve_count = 0
    line_count = 0
    total_length = 0

    prev_point = None

    for item in path_items:
        if not item:
            continue

        cmd = item[0] if item else None

        if cmd == "m":  # moveto
            if len(item) >= 3:
                prev_point = (item[1], item[2])
        elif cmd == "l":  # lineto
            if len(item) >= 3 and prev_point:
                dx = item[1] - prev_point[0]
                dy = item[2] - prev_point[1]
                total_length += math.sqrt(dx*dx + dy*dy)
                prev_point = (item[1], item[2])
            line_count += 1
        elif cmd == "c":  # cubic bezier curve
            curve_count += 1
            # Cubic bezier curves are often used for arcs in revision clouds
            if len(item) >= 7 and prev_point:
                # Estimate arc length (rough approximation)
                dx = item[5] - prev_point[0]
                dy = item[6] - prev_point[1]
                # Bezier curves are typically longer than straight line
                total_length += math.sqrt(dx*dx + dy*dy) * 1.3
                prev_point = (item[5], item[6])
            arc_count += 1
        elif cmd == "v":  # cubic bezier (variant)
            curve_count += 1
            arc_count += 1
        elif cmd == "y":  # cubic bezier (variant)
            curve_count += 1
            arc_count += 1
        elif cmd == "re":  # rectangle - not a cloud
            return False, 0, 0

    # Revision clouds typically have many small arcs
    # A typical cloud has 10-50+ arcs depending on size
    is_scalloped = arc_count >= min_arcs and curve_count > line_count

    return is_scalloped, arc_count, total_length


def get_path_bbox(path_items: List) -> Optional[BoundingBox]:
    """Extract bounding box from path items."""
    if not path_items:
        return None

    points = []

    for item in path_items:
        if not item:
            continue
        cmd = item[0] if item else None

        if cmd == "m" and len(item) >= 3:  # moveto
            points.append((item[1], item[2]))
        elif cmd == "l" and len(item) >= 3:  # lineto
            points.append((item[1], item[2]))
        elif cmd == "c" and len(item) >= 7:  # cubic bezier
            points.append((item[1], item[2]))
            points.append((item[3], item[4]))
            points.append((item[5], item[6]))
        elif cmd == "re" and len(item) >= 5:  # rectangle
            x, y, w, h = item[1], item[2], item[3], item[4]
            points.append((x, y))
            points.append((x + w, y + h))

    if not points:
        return None

    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]

    return BoundingBox(
        x0=min(x_coords),
        y0=min(y_coords),
        x1=max(x_coords),
        y1=max(y_coords)
    )


def find_text_near_cloud(page: fitz.Page, cloud_bbox: BoundingBox, margin: float = 50) -> Optional[str]:
    """Find revision-related text near a cloud."""
    # Expand bbox to search area
    search_rect = fitz.Rect(
        cloud_bbox.x0 - margin,
        cloud_bbox.y0 - margin,
        cloud_bbox.x1 + margin,
        cloud_bbox.y1 + margin
    )

    # Get text in area
    text = page.get_text("text", clip=search_rect)

    # Look for revision-related keywords
    keywords = ["REV", "Rev", "Revision", "Änderung", "Index", "Datum", "Stand"]

    for line in text.split("\n"):
        line = line.strip()
        for keyword in keywords:
            if keyword.lower() in line.lower():
                return line

    return None


def detect_revision_clouds(
    pdf_path: Path,
    pages: Optional[List[int]] = None,
    min_confidence: float = 0.3,
) -> RevisionCloudResult:
    """
    Detect revision clouds in a PDF document.

    Args:
        pdf_path: Path to the PDF file
        pages: Optional list of page numbers to process (0-indexed)
        min_confidence: Minimum confidence threshold for detection

    Returns:
        RevisionCloudResult with detected clouds and summary
    """
    import logging
    logger = logging.getLogger(__name__)

    doc = fitz.open(str(pdf_path))
    clouds: List[RevisionCloud] = []
    pages_with_clouds: List[int] = []

    page_range = pages if pages else range(len(doc))

    for page_num in page_range:
        if page_num >= len(doc):
            continue

        page = doc[page_num]

        # Method 1: Check annotations (revision clouds often stored as Polygon/PolyLine annotations)
        try:
            annots = page.annots()
            if annots:
                for annot in annots:
                    annot_type = annot.type[1]  # Get annotation type name
                    if annot_type in ["Polygon", "PolyLine", "Ink", "FreeText"]:
                        # Check if it has revision-related info
                        info = annot.info
                        rect = annot.rect
                        colors = annot.colors

                        # Check for red/magenta stroke color
                        stroke = colors.get("stroke")
                        if stroke and is_revision_cloud_color(stroke):
                            bbox = BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
                            if bbox.area > 100:
                                cloud = RevisionCloud(
                                    page=page_num,
                                    bbox=bbox,
                                    color=stroke if stroke else (1, 0, 0),
                                    confidence=0.8,
                                    arc_count=10,  # Estimate for annotations
                                    path_length=0,
                                    associated_text=info.get("content", ""),
                                )
                                clouds.append(cloud)
                                if page_num not in pages_with_clouds:
                                    pages_with_clouds.append(page_num)
                                logger.info(f"Found revision cloud annotation on page {page_num}")
        except Exception as e:
            logger.debug(f"Annotation check failed: {e}")

        # Method 2: Get all drawings/paths on the page
        try:
            drawings = page.get_drawings()
        except Exception:
            continue

        for drawing in drawings:
            # Check color
            stroke_color = drawing.get("color")
            fill_color = drawing.get("fill")

            # Use stroke color primarily, fall back to fill
            color = stroke_color if stroke_color else fill_color

            if not is_revision_cloud_color(color):
                continue

            # Analyze path for scalloped pattern
            items = drawing.get("items", [])
            is_scalloped, arc_count, path_length = analyze_path_for_scallops(items)

            # If not strictly scalloped, still consider it if it has many curves and is red
            # (some CAD software renders revision clouds differently)
            if not is_scalloped:
                # Fallback: Large red path with some curves
                if arc_count >= 2 and len(items) > 5:
                    # Might still be a revision cloud
                    pass
                else:
                    continue

            # Get bounding box
            rect = drawing.get("rect")
            if rect:
                bbox = BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
            else:
                bbox = get_path_bbox(items)

            if not bbox:
                continue

            # Skip very small detections (likely noise)
            if bbox.area < 100:
                continue

            # Calculate confidence based on arc count and pattern
            confidence = min(1.0, arc_count / 20)  # More arcs = higher confidence

            if confidence < min_confidence:
                continue

            # Find associated text
            associated_text = find_text_near_cloud(page, bbox)

            cloud = RevisionCloud(
                page=page_num,
                bbox=bbox,
                color=color if color else (1, 0, 0),
                confidence=confidence,
                arc_count=arc_count,
                path_length=path_length,
                associated_text=associated_text,
            )

            clouds.append(cloud)

            if page_num not in pages_with_clouds:
                pages_with_clouds.append(page_num)

    doc.close()

    # Generate warning message
    if clouds:
        warning_message = (
            f"⚠️ {len(clouds)} revision cloud(s) detected on {len(pages_with_clouds)} page(s). "
            f"These areas may have pending changes or require approval."
        )
    else:
        warning_message = ""

    return RevisionCloudResult(
        clouds=clouds,
        total_count=len(clouds),
        pages_with_clouds=sorted(pages_with_clouds),
        warning_message=warning_message,
    )


def match_clouds_to_rooms(
    clouds: List[RevisionCloud],
    rooms: List[Dict[str, Any]],
) -> List[RevisionCloud]:
    """
    Match revision clouds to rooms based on bounding box overlap.
    Updates the affected_room_numbers field of each cloud.

    Args:
        clouds: List of detected revision clouds
        rooms: List of room data with bbox information

    Returns:
        Updated clouds with affected_room_numbers populated
    """
    for cloud in clouds:
        affected = []

        for room in rooms:
            room_bbox_data = room.get("bbox")
            if not room_bbox_data:
                continue

            room_bbox = BoundingBox(
                x0=room_bbox_data.get("x0", 0),
                y0=room_bbox_data.get("y0", 0),
                x1=room_bbox_data.get("x1", 0),
                y1=room_bbox_data.get("y1", 0),
            )

            # Check if cloud and room are on same page and overlap
            if room.get("page") == cloud.page:
                if cloud.bbox.overlaps(room_bbox, threshold=0.05):
                    room_number = room.get("room_number", "")
                    if room_number and room_number not in affected:
                        affected.append(room_number)

        cloud.affected_room_numbers = affected

    return clouds
