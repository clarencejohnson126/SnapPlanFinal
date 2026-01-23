"""
Door Label Detection Module

Detects door-specific text patterns from floor plans using deterministic regex patterns.
Part of the door geometry extraction pipeline.

Zero hallucination - all detected labels come from actual PDF text with full traceability.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import re
import logging

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# German/English Door Label Patterns
# =============================================================================

DOOR_LABEL_PATTERNS = {
    # Room-style door labels from blueprints
    # These are the primary door identifiers (e.g., "B.00.1.003", "B.03.2.015")
    "room_door": [
        r'\b([A-Z]+\.\d{2}\.\d+\.\d{3}(?:-\d+)?)\b',  # "B.00.1.003", "B.03.2.015-1"
        r'\b([A-Z]\.?\s*[A-Z]+\d+)\b',  # "F. ND1", "F ND1"
        r'\b([A-Z]{1,3}_\d{3,})\b',  # "BU_012"
    ],

    # Fire ratings
    "fire_rating": [
        r'\b(T\s*\d{2,3}(?:[-\s]RS)?)\b',  # "T30", "T 90-RS"
        r'\b(DSS|Rauchschutz)\b',  # Smoke protection
    ],

    # Dimension labels
    "dimension": [
        r'(\d+[,\.]\d{2})\s*[xX×]\s*(\d+[,\.]\d{2})',  # "0,90 x 2,10"
        r'(\d{2,3})\s*[xX×]\s*(\d{3})',  # "90 x 210" (cm)
    ],

    # NOTE: DD and WD can mean different things in different plans:
    # - In some plans: DD=Doppeltür (double door), WD=Wohnungstür (apartment door)
    # - In other plans: DD=Deckendurchbruch (ceiling penetration), WD=Wanddurchbruch (wall penetration)
    # These patterns are DISABLED by default to avoid misclassification.
    # Door identification should rely on door numbers (B.00.1.xxx format) and fire ratings instead.
}


@dataclass
class DoorLabel:
    """Detected door label from floor plan text."""
    label_text: str  # Normalized label text
    raw_text: str  # Original text before processing
    page_number: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1) in pixels
    confidence: float  # 0.7-1.0 based on pattern match
    pattern_type: str  # "german_door", "dimension", "room_door", "fire_rating"

    # Parsed attributes (if extractable)
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    door_type: Optional[str] = None  # "WD", "DD", etc.
    fire_rating: Optional[str] = None  # "T30", "T90", "DSS"

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label_text": self.label_text,
            "raw_text": self.raw_text,
            "page_number": self.page_number,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "pattern_type": self.pattern_type,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "door_type": self.door_type,
            "fire_rating": self.fire_rating,
            "metadata": self.metadata,
        }


def parse_dimension_from_text(text: str) -> Optional[Tuple[float, float]]:
    """
    Parse width x height from dimension text.

    Examples:
    - "0,90 x 2,10" → (0.90, 2.10)
    - "90 x 210" → (0.90, 2.10)  # Assumes cm if < 10

    Args:
        text: Text containing dimension pattern

    Returns:
        (width_m, height_m) tuple or None if parsing fails
    """
    # Try decimal meter format first (0,90 x 2,10)
    match = re.search(r'(\d+[,\.]\d{2})\s*[xX×]\s*(\d+[,\.]\d{2})', text)
    if match:
        width_str = match.group(1).replace(',', '.')
        height_str = match.group(2).replace(',', '.')
        try:
            width_m = float(width_str)
            height_m = float(height_str)
            return (width_m, height_m)
        except ValueError:
            pass

    # Try centimeter format (90 x 210)
    match = re.search(r'(\d{2,3})\s*[xX×]\s*(\d{3})', text)
    if match:
        try:
            width_cm = float(match.group(1))
            height_cm = float(match.group(2))
            # Convert cm to meters
            width_m = width_cm / 100.0
            height_m = height_cm / 100.0
            # Sanity check - typical door dimensions
            if 0.5 <= width_m <= 2.0 and 1.8 <= height_m <= 2.8:
                return (width_m, height_m)
        except ValueError:
            pass

    return None


def detect_door_labels(
    pdf_path: Path,
    page_number: int,
    dpi: int = 150
) -> List[DoorLabel]:
    """
    Detect door labels from page text with bounding boxes.

    Strategy:
    1. Extract text with bounding boxes using PyMuPDF page.get_text("dict")
    2. Reconstruct text blocks with spatial information
    3. Apply regex patterns to detect door labels
    4. Parse dimensions from matched text (handle German decimal comma)
    5. Return DoorLabel objects with full traceability

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        dpi: DPI for coordinate scaling (should match render DPI)

    Returns:
        List of DoorLabel objects with full traceability

    Raises:
        ImportError: If PyMuPDF is not available
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If page number is invalid
    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) is required for door label detection")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    detected_labels: List[DoorLabel] = []

    doc = fitz.open(str(pdf_path))
    try:
        # PyMuPDF uses 0-indexed pages
        page_idx = page_number - 1
        if page_idx < 0 or page_idx >= len(doc):
            raise ValueError(f"Invalid page number {page_number}, document has {len(doc)} pages")

        page = doc[page_idx]

        # Get scaling factor from PDF points to rendered pixels
        scale = dpi / 72.0

        # Extract text with detailed structure (dict format includes bboxes)
        text_dict = page.get_text("dict")

        # Process each text block
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # Skip non-text blocks
                continue

            # Process each line in the block
            for line in block.get("lines", []):
                # Combine all spans in the line to get full text
                line_text = ""
                line_bbox = None

                for span in line.get("spans", []):
                    line_text += span.get("text", "")

                    # Get bbox from first span (approximate)
                    if line_bbox is None:
                        bbox = span.get("bbox")  # (x0, y0, x1, y1) in PDF points
                        if bbox:
                            # Scale to pixel coordinates
                            line_bbox = (
                                bbox[0] * scale,
                                bbox[1] * scale,
                                bbox[2] * scale,
                                bbox[3] * scale,
                            )

                if not line_text.strip() or line_bbox is None:
                    continue

                # Apply patterns to detect door labels
                labels_from_line = _apply_patterns_to_text(
                    text=line_text,
                    bbox=line_bbox,
                    page_number=page_number
                )

                detected_labels.extend(labels_from_line)

    finally:
        doc.close()

    # Return ALL detected labels
    # The extraction pipeline will handle which ones become doors
    return detected_labels


def _apply_patterns_to_text(
    text: str,
    bbox: Tuple[float, float, float, float],
    page_number: int
) -> List[DoorLabel]:
    """
    Apply regex patterns to text and create DoorLabel objects.

    Args:
        text: Text to analyze
        bbox: Bounding box in pixels
        page_number: Page number

    Returns:
        List of DoorLabel objects found in text
    """
    labels = []

    # Try each pattern category
    for pattern_type, pattern_list in DOOR_LABEL_PATTERNS.items():
        for pattern in pattern_list:
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                matched_text = match.group(0)

                # Create base label
                label = DoorLabel(
                    label_text=matched_text.strip(),
                    raw_text=text,
                    page_number=page_number,
                    bbox=bbox,
                    confidence=0.8,  # Base confidence
                    pattern_type=pattern_type,
                )

                # Parse specific attributes based on pattern type
                if pattern_type == "dimension":
                    dims = parse_dimension_from_text(matched_text)
                    if dims:
                        label.width_m, label.height_m = dims
                        label.confidence = 0.95  # High confidence for explicit dimensions

                elif pattern_type == "german_door":
                    # Extract door type (WD, DD, etc.)
                    door_type_match = re.match(r'(WD|DD|SD|FD|TD|ND)', matched_text, re.IGNORECASE)
                    if door_type_match:
                        label.door_type = door_type_match.group(1).upper()
                        label.confidence = 0.9

                elif pattern_type == "fire_rating":
                    # Normalize fire rating
                    if "T" in matched_text.upper() and "30" in matched_text:
                        label.fire_rating = "T30"
                        label.confidence = 0.95
                    elif "T" in matched_text.upper() and "90" in matched_text:
                        label.fire_rating = "T90"
                        label.confidence = 0.95
                    elif "DSS" in matched_text.upper() or "Rauchschutz" in matched_text:
                        label.fire_rating = "DSS"
                        label.confidence = 0.9

                elif pattern_type == "room_door":
                    # Room-style labels have moderate confidence
                    label.confidence = 0.75

                labels.append(label)

    return labels


def _associate_attributes_with_doors(
    door_labels: List[DoorLabel],
    attribute_labels: List[DoorLabel],
    max_distance_px: float = 100
) -> List[DoorLabel]:
    """
    Associate fire ratings and dimensions with nearby door numbers.

    Example: Door "B.00.2.006-1" + nearby "T 30-RS" → door with fire_rating="T30"

    Args:
        door_labels: List of door number labels
        attribute_labels: List of fire rating and dimension labels
        max_distance_px: Maximum distance for association

    Returns:
        List of door labels with attributes merged in
    """
    # Make copies so we don't modify originals
    doors_with_attributes = []

    for door in door_labels:
        # Calculate door center
        dx = (door.bbox[0] + door.bbox[2]) / 2
        dy = (door.bbox[1] + door.bbox[3]) / 2

        # Find nearest fire rating and dimension
        nearest_fire_rating = None
        nearest_dimension = None
        min_fire_dist = max_distance_px
        min_dim_dist = max_distance_px

        for attr in attribute_labels:
            ax = (attr.bbox[0] + attr.bbox[2]) / 2
            ay = (attr.bbox[1] + attr.bbox[3]) / 2
            dist = ((dx - ax) ** 2 + (dy - ay) ** 2) ** 0.5

            if dist > max_distance_px:
                continue

            if attr.pattern_type == "fire_rating" and dist < min_fire_dist:
                nearest_fire_rating = attr
                min_fire_dist = dist

            elif attr.pattern_type == "dimension" and dist < min_dim_dist:
                nearest_dimension = attr
                min_dim_dist = dist

        # Create new label with merged attributes
        merged_door = DoorLabel(
            label_text=door.label_text,
            raw_text=door.raw_text,
            page_number=door.page_number,
            bbox=door.bbox,
            confidence=door.confidence,
            pattern_type=door.pattern_type,
            width_m=nearest_dimension.width_m if nearest_dimension else door.width_m,
            height_m=nearest_dimension.height_m if nearest_dimension else door.height_m,
            door_type=door.door_type,
            fire_rating=nearest_fire_rating.fire_rating if nearest_fire_rating else door.fire_rating,
            metadata={
                **door.metadata,
                "has_fire_rating": nearest_fire_rating is not None,
                "has_dimensions": nearest_dimension is not None,
            }
        )
        doors_with_attributes.append(merged_door)

    return doors_with_attributes


def split_compound_door_labels(labels: List[DoorLabel]) -> List[DoorLabel]:
    """
    Split merged labels that contain multiple door numbers into separate labels.

    Example: "B.00.2.009-1 B.00.2.010-1 T 30-RS" → two DoorLabel objects, both with fire_rating=T30

    Preserves shared attributes (fire_rating, dimensions) across all split labels.

    Args:
        labels: List of potentially compound labels

    Returns:
        List of split labels (one per door number)
    """
    split_labels = []

    # Door number pattern (B.00.X.XXX-Y format)
    door_number_pattern = re.compile(r'\b([A-Z]+\.\d{2}\.\d+\.\d{3}(?:-\d+)?)\b')

    for label in labels:
        # Find all door numbers in the label text
        door_numbers = door_number_pattern.findall(label.label_text)

        if len(door_numbers) >= 1:
            # Door numbers found - create one label per door number
            # Preserve shared attributes (fire_rating, dimensions) for all splits

            if len(door_numbers) > 1:
                # Multiple doors - split bbox evenly
                bbox_width = label.bbox[2] - label.bbox[0]
                segment_width = bbox_width / len(door_numbers)
            else:
                # Single door - use full bbox
                segment_width = label.bbox[2] - label.bbox[0]

            for idx, door_num in enumerate(door_numbers):
                # Create bbox for this door number
                if len(door_numbers) > 1:
                    x0 = label.bbox[0] + (idx * segment_width)
                    x1 = x0 + segment_width
                else:
                    x0 = label.bbox[0]
                    x1 = label.bbox[2]

                split_bbox = (x0, label.bbox[1], x1, label.bbox[3])

                # Create new label for this door number
                # IMPORTANT: Set label_text to ONLY the door number (not the full compound text)
                split_label = DoorLabel(
                    label_text=door_num,  # ONLY the door number
                    raw_text=label.raw_text,
                    page_number=label.page_number,
                    bbox=split_bbox,
                    confidence=label.confidence * 0.9 if len(door_numbers) > 1 else label.confidence,
                    pattern_type="room_door",  # These are door numbers
                    width_m=label.width_m,  # Preserve dimensions if present
                    height_m=label.height_m,
                    door_type=label.door_type,  # Preserve door type if present
                    fire_rating=label.fire_rating,  # Preserve fire rating (shared across doors)
                    metadata={
                        **label.metadata,
                        "split_from_compound": len(door_numbers) > 1,
                        "original_text": label.label_text,
                        "split_index": idx if len(door_numbers) > 1 else 0,
                        "total_splits": len(door_numbers)
                    }
                )
                split_labels.append(split_label)
        else:
            # No door numbers found - this is probably a fire rating or dimension label
            # Don't include it as a standalone door
            pass

    return split_labels


def group_nearby_labels(
    labels: List[DoorLabel],
    max_distance_px: float = 50
) -> List[DoorLabel]:
    """
    Group text blocks that are spatially close (compound labels).

    Example: "F. ND1" and "T 30-RS" on adjacent lines → single label

    Strategy:
    - Calculate center of each label bbox
    - Find labels within max_distance_px
    - Merge attributes (prefer explicit values)
    - Keep highest confidence

    Args:
        labels: List of detected labels
        max_distance_px: Maximum distance for grouping

    Returns:
        List of grouped labels
    """
    if not labels:
        return []

    # Calculate centers for all labels
    label_centers = []
    for label in labels:
        x0, y0, x1, y1 = label.bbox
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        label_centers.append((center_x, center_y))

    # Group labels by proximity
    grouped = []
    used_indices = set()

    for i, label in enumerate(labels):
        if i in used_indices:
            continue

        # Start a new group with this label
        group = [label]
        used_indices.add(i)

        # Find nearby labels
        cx1, cy1 = label_centers[i]

        for j, other_label in enumerate(labels):
            if j in used_indices or i == j:
                continue

            cx2, cy2 = label_centers[j]
            distance = ((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2) ** 0.5

            if distance <= max_distance_px:
                group.append(other_label)
                used_indices.add(j)

        # Merge group into single label
        merged = _merge_label_group(group)
        grouped.append(merged)

    return grouped


def _merge_label_group(group: List[DoorLabel]) -> DoorLabel:
    """
    Merge a group of nearby labels into a single label.

    Merging strategy:
    - Combine label_text (space-separated)
    - Take union bbox (min x0/y0, max x1/y1)
    - Prefer explicit dimensions/fire_rating/door_type
    - Take max confidence
    - Combine pattern_types

    Args:
        group: List of labels to merge

    Returns:
        Merged DoorLabel
    """
    if len(group) == 1:
        return group[0]

    # Sort by y-coordinate (top to bottom)
    group_sorted = sorted(group, key=lambda lbl: lbl.bbox[1])

    # Combine text
    combined_text = " ".join(lbl.label_text for lbl in group_sorted)
    combined_raw = " ".join(lbl.raw_text for lbl in group_sorted)

    # Union bbox
    x0_min = min(lbl.bbox[0] for lbl in group)
    y0_min = min(lbl.bbox[1] for lbl in group)
    x1_max = max(lbl.bbox[2] for lbl in group)
    y1_max = max(lbl.bbox[3] for lbl in group)
    union_bbox = (x0_min, y0_min, x1_max, y1_max)

    # Merge attributes (prefer explicit values)
    width_m = next((lbl.width_m for lbl in group if lbl.width_m is not None), None)
    height_m = next((lbl.height_m for lbl in group if lbl.height_m is not None), None)
    door_type = next((lbl.door_type for lbl in group if lbl.door_type is not None), None)
    fire_rating = next((lbl.fire_rating for lbl in group if lbl.fire_rating is not None), None)

    # Max confidence
    max_confidence = max(lbl.confidence for lbl in group)

    # Combine pattern types
    pattern_types = list(set(lbl.pattern_type for lbl in group))
    combined_pattern = "+".join(sorted(pattern_types))

    # Use first label's page number
    page_number = group[0].page_number

    return DoorLabel(
        label_text=combined_text,
        raw_text=combined_raw,
        page_number=page_number,
        bbox=union_bbox,
        confidence=max_confidence,
        pattern_type=combined_pattern,
        width_m=width_m,
        height_m=height_m,
        door_type=door_type,
        fire_rating=fire_rating,
        metadata={"merged_from": len(group)},
    )
