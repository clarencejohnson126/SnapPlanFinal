"""
Door Geometry Extraction Module

Main extraction pipeline that coordinates label detection, geometry detection, and association.
Implements a deterministic, rule-based approach with full traceability.

Zero hallucination - all measurements come from PDF geometry or text, never generated.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Union
import math
import uuid
import time
import logging
import re

from .door_label_detection import DoorLabel, detect_door_labels
from .vector_measurement import (
    DoorSymbol,
    LineSegment,
    extract_door_symbols_from_page,
    extract_line_segments_from_page,
)
from .scale_calibration import ScaleContext
from .gewerke import DoorCategory

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class DoorGeometry:
    """Detected door shape/opening from vector analysis."""
    geometry_id: str  # Unique ID
    page_number: int
    center: Tuple[float, float]  # Center point in pixels
    width_px: float  # Width in pixels
    height_px: Optional[float] = None  # Height if detectable
    orientation_deg: float = 0.0  # Wall orientation angle
    opening_type: str = "unknown"  # "arc", "rectangle", "gap"
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    confidence: float = 0.8
    source_type: str = "vector"  # "vector", "cv" (future)

    # Geometry details
    arc_center: Optional[Tuple[float, float]] = None  # For arc doors
    arc_radius_px: Optional[float] = None
    leaf_line: Optional[LineSegment] = None  # Door panel
    parallel_lines: Optional[List[LineSegment]] = None  # For rectangles

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "geometry_id": self.geometry_id,
            "page_number": self.page_number,
            "center": self.center,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "orientation_deg": self.orientation_deg,
            "opening_type": self.opening_type,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "source_type": self.source_type,
            "arc_center": self.arc_center,
            "arc_radius_px": self.arc_radius_px,
            "leaf_line": self.leaf_line.to_dict() if self.leaf_line else None,
            "parallel_lines": [line.to_dict() for line in self.parallel_lines] if self.parallel_lines else None,
            "metadata": self.metadata,
        }


@dataclass
class DoorExtraction:
    """Complete door with label + geometry association."""
    extraction_id: str
    page_number: int

    # Components
    label: Optional[DoorLabel] = None
    geometry: Optional[DoorGeometry] = None

    # Extracted attributes
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    door_type: Optional[str] = None  # "WD", "DD", etc.
    door_number: Optional[str] = None  # "ND1", "T01"
    fire_rating: Optional[str] = None  # "T30", "T90"
    category: Optional[str] = None  # Using existing DoorCategory enum

    # Traceability
    confidence: float = 0.0
    extraction_method: str = "unknown"  # "label_geometry_match", "geometry_only", "label_only"
    scale_context_id: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "extraction_id": self.extraction_id,
            "page_number": self.page_number,
            "label": self.label.to_dict() if self.label else None,
            "geometry": self.geometry.to_dict() if self.geometry else None,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "door_type": self.door_type,
            "door_number": self.door_number,
            "fire_rating": self.fire_rating,
            "category": self.category,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
            "scale_context_id": self.scale_context_id,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
        }


@dataclass
class DoorExtractionResult:
    """Complete result from door extraction pipeline."""
    result_id: str
    source_file: str
    page_count: int
    processed_pages: List[int]
    total_doors: int
    doors: List[DoorExtraction]

    # Summary statistics
    by_type: Dict[str, int]  # Count by door type (WD, DD, etc.)
    by_fire_rating: Dict[str, int]  # Count by fire rating (T30, T90, etc.)
    by_width: Dict[str, int]  # Grouped by width (0.9, 1.0, 1.25)
    avg_width_m: Optional[float] = None

    # Metadata
    extraction_time_ms: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "result_id": self.result_id,
            "source_file": self.source_file,
            "page_count": self.page_count,
            "processed_pages": self.processed_pages,
            "total_doors": self.total_doors,
            "doors": [door.to_dict() for door in self.doors],
            "by_type": self.by_type,
            "by_fire_rating": self.by_fire_rating,
            "by_width": self.by_width,
            "avg_width_m": self.avg_width_m,
            "extraction_time_ms": self.extraction_time_ms,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def extract_doors_from_pdf(
    pdf_path: Path,
    page_number: Optional[int] = None,
    scale_factor: Optional[int] = None,  # e.g., 100 for 1:100
    search_radius_px: float = 150,
    min_confidence: float = 0.6,
    dpi: int = 150,
) -> DoorExtractionResult:
    """
    Main entry point for door extraction pipeline.

    4-stage pipeline:
    1. Detect door labels from text
    2. Detect door geometries from vector paths
    3. Associate labels with nearest geometries
    4. Extract attributes and build result

    Args:
        pdf_path: Path to PDF file
        page_number: Specific page to process (1-indexed), or None for all pages
        scale_factor: Scale denominator (e.g., 100 for 1:100), used to calculate pixels_per_meter
        search_radius_px: Max distance between label and geometry for association
        min_confidence: Minimum confidence threshold for door detection
        dpi: DPI for rendering and coordinate scaling

    Returns:
        DoorExtractionResult with all detected doors

    Raises:
        ImportError: If PyMuPDF is not available
        FileNotFoundError: If PDF file doesn't exist
    """
    if not FITZ_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) is required for door extraction")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    start_time = time.time()

    # Determine pages to process
    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    doc.close()

    if page_number is not None:
        pages_to_process = [page_number]
    else:
        pages_to_process = list(range(1, page_count + 1))

    # Calculate scale context if provided
    scale_context = None
    if scale_factor:
        # Compute pixels_per_meter from scale factor
        # For 1:100 scale at 150 DPI: 1 meter in reality = 0.01m on paper
        # 0.01m = 0.01 * 39.37 inches = 0.3937 inches on paper
        # At 150 DPI: 0.3937 * 150 = 59.055 pixels per real meter
        pixels_per_meter = (dpi / (72.0 * scale_factor)) * (72.0 * 39.37)
        scale_context = ScaleContext(
            id=f"scale_{uuid.uuid4().hex[:8]}",
            scale_factor=scale_factor,
            pixels_per_meter=pixels_per_meter,
            detection_method="user_provided",
        )

    # Process each page
    all_doors = []
    all_warnings = []

    for page_num in pages_to_process:
        try:
            page_doors = _extract_doors_from_page(
                pdf_path=pdf_path,
                page_number=page_num,
                scale_context=scale_context,
                search_radius_px=search_radius_px,
                min_confidence=min_confidence,
                dpi=dpi,
            )
            all_doors.extend(page_doors)

        except Exception as e:
            logger.error(f"Error processing page {page_num}: {e}")
            all_warnings.append(f"Page {page_num}: {str(e)}")

    # Build summary statistics
    by_type: Dict[str, int] = {}
    by_fire_rating: Dict[str, int] = {}
    by_width: Dict[str, int] = {}

    total_width = 0.0
    width_count = 0

    for door in all_doors:
        # Count by type
        if door.door_type:
            by_type[door.door_type] = by_type.get(door.door_type, 0) + 1

        # Count by fire rating
        if door.fire_rating:
            by_fire_rating[door.fire_rating] = by_fire_rating.get(door.fire_rating, 0) + 1
        else:
            by_fire_rating["Standard"] = by_fire_rating.get("Standard", 0) + 1

        # Group by width (rounded to nearest 0.05m)
        if door.width_m:
            width_rounded = round(door.width_m * 20) / 20  # Round to nearest 0.05
            width_key = f"{width_rounded:.2f}"
            by_width[width_key] = by_width.get(width_key, 0) + 1

            total_width += door.width_m
            width_count += 1

    avg_width_m = (total_width / width_count) if width_count > 0 else None

    elapsed_ms = int((time.time() - start_time) * 1000)

    return DoorExtractionResult(
        result_id=f"door_extraction_{uuid.uuid4().hex[:12]}",
        source_file=pdf_path.name,
        page_count=page_count,
        processed_pages=pages_to_process,
        total_doors=len(all_doors),
        doors=all_doors,
        by_type=by_type,
        by_fire_rating=by_fire_rating,
        by_width=by_width,
        avg_width_m=avg_width_m,
        extraction_time_ms=elapsed_ms,
        warnings=all_warnings,
        errors=[],
    )


def _extract_doors_from_page(
    pdf_path: Path,
    page_number: int,
    scale_context: Optional[ScaleContext],
    search_radius_px: float,
    min_confidence: float,
    dpi: int,
) -> List[DoorExtraction]:
    """
    Extract doors from a single page.

    4-stage pipeline:
    1. Detect door labels from text
    2. Detect door geometries from vector paths
    3. Associate labels with nearest geometries
    4. Extract attributes and build result

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        scale_context: Scale context for measurements
        search_radius_px: Max distance for label-geometry association
        min_confidence: Minimum confidence threshold
        dpi: DPI for coordinate scaling

    Returns:
        List of DoorExtraction objects for this page
    """
    # Stage 1: Detect door labels from text
    labels = detect_door_labels(
        pdf_path=pdf_path,
        page_number=page_number,
        dpi=dpi
    )

    # Stage 2: Detect door geometries
    geometries = []

    # 2a: Arc-based detection (reuse existing code)
    arc_geometries = detect_door_arcs(
        pdf_path=pdf_path,
        page_number=page_number,
        scale_context=scale_context,
        dpi=dpi
    )
    geometries.extend(arc_geometries)

    # 2b: Rectangle-based detection (parallel lines)
    rect_geometries = detect_door_rectangles(
        pdf_path=pdf_path,
        page_number=page_number,
        scale_context=scale_context,
        dpi=dpi
    )
    geometries.extend(rect_geometries)

    # Stage 3: Associate labels with geometries
    doors = associate_labels_with_geometries(
        labels=labels,
        geometries=geometries,
        max_distance_px=search_radius_px
    )

    # Stage 4: Extract attributes
    for door in doors:
        extract_door_attributes(door, scale_context)

    # Filter by minimum confidence
    doors = [door for door in doors if door.confidence >= min_confidence]

    # CRITICAL: Deduplicate by door_number AND filter out room numbers
    # Only count door numbers with suffix (B.00.X.XXX-Y format)
    # Room numbers without suffix (B.00.X.XXX) should be excluded
    door_number_with_suffix = re.compile(r'B\.\d{2}\.\d+\.\d{3}-\d+')

    unique_doors = {}
    for door in doors:
        door_num = door.door_number
        if door_num:
            # Only include doors with suffix (B.00.X.XXX-Y)
            if door_number_with_suffix.match(door_num):
                # Keep the highest confidence version if duplicates
                if door_num not in unique_doors or door.confidence > unique_doors[door_num].confidence:
                    unique_doors[door_num] = door
        else:
            # No door number (geometry-only) - keep all
            unique_id = door.extraction_id
            unique_doors[unique_id] = door

    final_doors = list(unique_doors.values())

    print(f"Filtering: {len(doors)} → {len(final_doors)} doors (only with -X suffix)")

    return final_doors


def detect_door_arcs(
    pdf_path: Path,
    page_number: int,
    scale_context: Optional[ScaleContext],
    dpi: int = 150
) -> List[DoorGeometry]:
    """
    Wrapper around existing arc detection from vector_measurement.py.

    Calls: extract_door_symbols_from_page()
    Converts: DoorSymbol → DoorGeometry

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        scale_context: Scale context for filtering by realistic door sizes
        dpi: DPI for coordinate scaling

    Returns:
        List of DoorGeometry objects detected from arcs
    """
    geometries = []

    # Determine pixels_per_meter for filtering
    pixels_per_meter = scale_context.pixels_per_meter if scale_context else None

    try:
        # Call existing door symbol extraction
        door_symbols = extract_door_symbols_from_page(
            path=pdf_path,
            page_number=page_number,
            dpi=dpi,
            min_door_width_m=0.5,
            max_door_width_m=2.5,
            pixels_per_meter=pixels_per_meter,
        )

        # Convert DoorSymbol to DoorGeometry
        for symbol in door_symbols:
            geometry = DoorGeometry(
                geometry_id=symbol.door_id,
                page_number=symbol.page_number,
                center=symbol.arc_center,
                width_px=symbol.arc_radius_px,
                orientation_deg=0.0,  # Calculate from leaf line if available
                opening_type="arc",
                bbox=_calculate_bbox_from_arc(
                    symbol.arc_center,
                    symbol.arc_radius_px
                ),
                confidence=symbol.confidence,
                source_type="vector",
                arc_center=symbol.arc_center,
                arc_radius_px=symbol.arc_radius_px,
                leaf_line=symbol.leaf_line,
            )

            geometries.append(geometry)

    except Exception as e:
        logger.warning(f"Arc detection failed for page {page_number}: {e}")

    return geometries


def detect_door_rectangles(
    pdf_path: Path,
    page_number: int,
    scale_context: Optional[ScaleContext],
    dpi: int = 150,
    min_door_width_m: float = 0.6,
    max_door_width_m: float = 1.5,
) -> List[DoorGeometry]:
    """
    Detect door rectangles using parallel line pairs.

    Strategy:
    1. Extract all line segments from page
    2. Find pairs of parallel lines (5-15cm apart)
    3. Filter by door-like aspect ratio and dimensions
    4. Exclude windows (no nearby arc indicator)
    5. Return DoorGeometry objects

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        scale_context: Scale context for realistic door sizing
        dpi: DPI for coordinate scaling
        min_door_width_m: Minimum door width in meters
        max_door_width_m: Maximum door width in meters

    Returns:
        List of DoorGeometry objects detected from rectangles
    """
    geometries = []

    if not scale_context or not scale_context.pixels_per_meter:
        # Can't filter by real-world dimensions without scale
        return geometries

    pixels_per_meter = scale_context.pixels_per_meter

    try:
        # Extract all line segments
        segments = extract_line_segments_from_page(
            path=pdf_path,
            page_number=page_number,
            dpi=dpi,
            min_length_px=10.0,
        )

        # Find parallel line pairs
        for i, seg1 in enumerate(segments):
            for seg2 in segments[i+1:]:
                # Check if lines are approximately parallel
                angle_diff = abs(seg1.angle_degrees - seg2.angle_degrees)
                if angle_diff > 10:  # Allow 10 degree tolerance
                    continue

                # Calculate distance between parallel lines
                distance_px = _distance_between_parallel_lines(seg1, seg2)

                # Convert to meters
                distance_m = distance_px / pixels_per_meter

                # Check if distance matches door width range
                if min_door_width_m <= distance_m <= max_door_width_m:
                    # Calculate center point
                    mid1 = seg1.midpoint
                    mid2 = seg2.midpoint
                    center = (
                        (mid1[0] + mid2[0]) / 2,
                        (mid1[1] + mid2[1]) / 2,
                    )

                    # Calculate bbox
                    x0 = min(seg1.x1, seg1.x2, seg2.x1, seg2.x2)
                    y0 = min(seg1.y1, seg1.y2, seg2.y1, seg2.y2)
                    x1 = max(seg1.x1, seg1.x2, seg2.x1, seg2.x2)
                    y1 = max(seg1.y1, seg1.y2, seg2.y1, seg2.y2)
                    bbox = (x0, y0, x1, y1)

                    # Create geometry
                    geometry = DoorGeometry(
                        geometry_id=f"door_rect_{uuid.uuid4().hex[:8]}",
                        page_number=page_number,
                        center=center,
                        width_px=distance_px,
                        height_px=max(seg1.length_px, seg2.length_px),
                        orientation_deg=seg1.angle_degrees,
                        opening_type="rectangle",
                        bbox=bbox,
                        confidence=0.6,  # Lower confidence for rectangles
                        source_type="vector",
                        parallel_lines=[seg1, seg2],
                    )

                    geometries.append(geometry)

    except Exception as e:
        logger.warning(f"Rectangle detection failed for page {page_number}: {e}")

    return geometries


def associate_labels_with_geometries(
    labels: List[DoorLabel],
    geometries: List[DoorGeometry],
    max_distance_px: float = 150
) -> List[DoorExtraction]:
    """
    Match door labels with nearest door geometries.

    Algorithm:
    1. For each label, find nearest geometry within search radius
    2. Match using Euclidean distance between label bbox center and geometry center
    3. Create DoorExtraction with label + geometry
    4. Mark unmatched geometries as geometry_only (lower confidence)
    5. Mark unmatched labels as label_only (for warning/review)

    Prioritization:
    - Prefer 1:1 matches (one label to one geometry)
    - If multiple labels near same geometry, choose closest
    - Prefer arc-based geometries over rectangles (higher confidence)

    Args:
        labels: List of detected labels
        geometries: List of detected geometries
        max_distance_px: Maximum distance for association

    Returns:
        List of DoorExtraction objects (label+geometry associations)
    """
    doors = []
    matched_geometry_ids = set()
    matched_label_indices = set()

    # Sort geometries by confidence (prefer arc over rectangle)
    geometries_sorted = sorted(geometries, key=lambda g: g.confidence, reverse=True)

    # Match labels to geometries
    for i, label in enumerate(labels):
        # Calculate label center
        lx0, ly0, lx1, ly1 = label.bbox
        label_center = ((lx0 + lx1) / 2, (ly0 + ly1) / 2)

        # Find nearest geometry
        nearest_geometry = None
        nearest_distance = float('inf')

        for geometry in geometries_sorted:
            if geometry.geometry_id in matched_geometry_ids:
                continue  # Already matched

            # Calculate distance
            distance = math.sqrt(
                (geometry.center[0] - label_center[0]) ** 2 +
                (geometry.center[1] - label_center[1]) ** 2
            )

            if distance < nearest_distance and distance <= max_distance_px:
                nearest_distance = distance
                nearest_geometry = geometry

        if nearest_geometry:
            # Create matched door
            door = DoorExtraction(
                extraction_id=f"door_{uuid.uuid4().hex[:8]}",
                page_number=label.page_number,
                label=label,
                geometry=nearest_geometry,
                extraction_method="label_geometry_match",
                confidence=min(label.confidence, nearest_geometry.confidence),  # Conservative
            )
            doors.append(door)

            matched_geometry_ids.add(nearest_geometry.geometry_id)
            matched_label_indices.add(i)

    # Add unmatched geometries (geometry_only)
    for geometry in geometries_sorted:
        if geometry.geometry_id not in matched_geometry_ids:
            door = DoorExtraction(
                extraction_id=f"door_{uuid.uuid4().hex[:8]}",
                page_number=geometry.page_number,
                geometry=geometry,
                extraction_method="geometry_only",
                confidence=geometry.confidence * 0.7,  # Reduce confidence without label
                warnings=["No label found near this door geometry"],
            )
            doors.append(door)

    # Add unmatched labels (label_only) with warning
    # ONLY create doors from labels that contain door numbers (not fire ratings)
    door_number_pattern = re.compile(r'B\.\d{2}\.\d+\.\d{3}(?:-\d+)?')

    for i, label in enumerate(labels):
        if i not in matched_label_indices:
            # Only create door if label contains a door number
            if label.pattern_type == "room_door" or door_number_pattern.search(label.label_text):
                # Look for nearby fire rating to add
                fire_rating = None
                for other_label in labels:
                    if other_label.pattern_type == "fire_rating":
                        # Check if close enough (within 100px)
                        lx = (label.bbox[0] + label.bbox[2]) / 2
                        ly = (label.bbox[1] + label.bbox[3]) / 2
                        ox = (other_label.bbox[0] + other_label.bbox[2]) / 2
                        oy = (other_label.bbox[1] + other_label.bbox[3]) / 2
                        dist = math.sqrt((lx - ox) ** 2 + (ly - oy) ** 2)

                        if dist < 100:
                            fire_rating = other_label.fire_rating
                            break

                # Update label with fire rating if found
                if fire_rating and not label.fire_rating:
                    label.fire_rating = fire_rating

                door = DoorExtraction(
                    extraction_id=f"door_{uuid.uuid4().hex[:8]}",
                    page_number=label.page_number,
                    label=label,
                    extraction_method="label_only",
                    confidence=label.confidence * 0.8,  # Reasonable confidence for text labels
                    warnings=["Door label found but no geometry detected nearby"],
                )
                doors.append(door)

    return doors


def extract_door_attributes(
    extraction: DoorExtraction,
    scale_context: Optional[ScaleContext]
) -> None:
    """
    Extract final attributes from label and geometry (in-place modification).

    Priority order:
    1. Width/height from label text (if dimension pattern matched)
    2. Width from geometry measurement (arc radius or line length)
    3. Door type from label (WD, DD, etc.)
    4. Fire rating from label (T30, T90, DSS)
    5. Category classification using existing _classify_door_category()

    Confidence scoring:
    - Label + geometry match: 0.8-0.95
    - Geometry only: 0.5-0.7
    - Label only: 0.3-0.5 (warning)

    Args:
        extraction: DoorExtraction object to populate (modified in-place)
        scale_context: Scale context for converting pixels to meters
    """
    # Extract width/height
    if extraction.label and extraction.label.width_m:
        # Priority 1: Explicit dimension from label
        extraction.width_m = extraction.label.width_m
        extraction.height_m = extraction.label.height_m
        extraction.assumptions.append("Width/height from label text")

    elif extraction.geometry and scale_context and scale_context.pixels_per_meter:
        # Priority 2: Calculate from geometry
        extraction.width_m = extraction.geometry.width_px / scale_context.pixels_per_meter

        if extraction.geometry.height_px:
            extraction.height_m = extraction.geometry.height_px / scale_context.pixels_per_meter

        extraction.assumptions.append(f"Width calculated from geometry (scale 1:{scale_context.scale_factor})")

    # Extract door type
    if extraction.label and extraction.label.door_type:
        extraction.door_type = extraction.label.door_type

    # Extract fire rating
    if extraction.label and extraction.label.fire_rating:
        extraction.fire_rating = extraction.label.fire_rating

    # Extract door number (from label text)
    if extraction.label:
        extraction.door_number = extraction.label.label_text

    # Classify category
    if extraction.fire_rating:
        if "T90" in extraction.fire_rating:
            extraction.category = DoorCategory.T90.value
        elif "T30" in extraction.fire_rating:
            extraction.category = DoorCategory.T30.value
        elif "DSS" in extraction.fire_rating or "Rauchschutz" in extraction.fire_rating:
            extraction.category = DoorCategory.DSS.value
        else:
            extraction.category = DoorCategory.STANDARD.value
    else:
        extraction.category = DoorCategory.STANDARD.value

    # Set scale context ID
    if scale_context:
        extraction.scale_context_id = scale_context.id


def _calculate_bbox_from_arc(
    center: Tuple[float, float],
    radius_px: float
) -> Tuple[float, float, float, float]:
    """Calculate bounding box for an arc."""
    x, y = center
    return (x - radius_px, y - radius_px, x + radius_px, y + radius_px)


def _distance_between_parallel_lines(
    seg1: LineSegment,
    seg2: LineSegment
) -> float:
    """
    Calculate perpendicular distance between two parallel line segments.

    Uses point-to-line distance formula.

    Args:
        seg1: First line segment
        seg2: Second line segment

    Returns:
        Distance in pixels
    """
    # Use midpoint of seg2 as reference point
    px, py = seg2.midpoint

    # Line equation for seg1: ax + by + c = 0
    # From two points (x1,y1) and (x2,y2):
    # a = y2 - y1
    # b = x1 - x2
    # c = x2*y1 - x1*y2

    a = seg1.y2 - seg1.y1
    b = seg1.x1 - seg1.x2
    c = seg1.x2 * seg1.y1 - seg1.x1 * seg1.y2

    # Distance = |ax + by + c| / sqrt(a^2 + b^2)
    numerator = abs(a * px + b * py + c)
    denominator = math.sqrt(a ** 2 + b ** 2)

    if denominator == 0:
        return 0.0

    return numerator / denominator
