"""
Material Pattern Detector

Detects and matches hatching/fill patterns in PDF vector graphics.
Used to find occurrences of materials (like drywall) in the main drawing
based on patterns learned from the Plankopf legend.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import fitz  # PyMuPDF

from app.services.plankopf_parser import (
    BoundingBox,
    PatternInfo,
    PatternType,
    LegendSymbol,
)


@dataclass
class DetectedRegion:
    """A region in the drawing that matches a pattern."""
    region_id: str
    bbox: BoundingBox
    pattern_info: PatternInfo
    matched_symbol: Optional[LegendSymbol] = None
    confidence: float = 0.0

    # Measurement data
    length_px: float = 0.0       # Length in PDF points
    length_m: Optional[float] = None  # Length in meters (if scale known)

    # For wall segments
    wall_thickness_px: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "bbox": self.bbox.to_dict(),
            "pattern_info": self.pattern_info.to_dict(),
            "matched_symbol_id": self.matched_symbol.symbol_id if self.matched_symbol else None,
            "confidence": self.confidence,
            "length_px": self.length_px,
            "length_m": self.length_m,
            "wall_thickness_px": self.wall_thickness_px,
        }


@dataclass
class PatternMatchResult:
    """Result of pattern matching across a page."""
    page_number: int
    target_pattern: PatternInfo
    detected_regions: List[DetectedRegion] = field(default_factory=list)
    total_length_px: float = 0.0
    total_length_m: float = 0.0
    segment_count: int = 0
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "target_pattern": self.target_pattern.to_dict(),
            "detected_regions": [r.to_dict() for r in self.detected_regions],
            "total_length_px": self.total_length_px,
            "total_length_m": self.total_length_m,
            "segment_count": self.segment_count,
            "confidence": self.confidence,
            "warnings": self.warnings,
        }


def color_distance(c1: Optional[Tuple], c2: Optional[Tuple]) -> float:
    """
    Calculate RGB color distance between two colors.
    Returns value between 0 (identical) and 1.73 (max difference).
    """
    if c1 is None or c2 is None:
        return 0.0 if c1 == c2 else 1.0

    if len(c1) < 3 or len(c2) < 3:
        return 0.5

    dr = c1[0] - c2[0]
    dg = c1[1] - c2[1]
    db = c1[2] - c2[2]

    return math.sqrt(dr*dr + dg*dg + db*db)


def angle_distance(a1: Optional[float], a2: Optional[float]) -> float:
    """
    Calculate angular distance between two angles (in degrees).
    Returns value between 0 and 90 degrees.
    """
    if a1 is None or a2 is None:
        return 45.0  # Default mid-range distance

    # Normalize to 0-180 range
    a1 = a1 % 180
    a2 = a2 % 180

    diff = abs(a1 - a2)
    return min(diff, 180 - diff)


def patterns_match(
    pattern1: PatternInfo,
    pattern2: PatternInfo,
    color_tolerance: float = 0.2,
    angle_tolerance: float = 15.0,
    spacing_tolerance: float = 0.3,
) -> Tuple[bool, float]:
    """
    Check if two patterns match within tolerance.

    Returns:
        (matches: bool, confidence: float)
    """
    # Pattern type must match
    if pattern1.pattern_type != pattern2.pattern_type:
        # Allow solid fill to match hatching if colors match
        if not ({pattern1.pattern_type, pattern2.pattern_type} <=
                {PatternType.SOLID_FILL, PatternType.HATCHING}):
            return False, 0.0

    confidence = 1.0

    # Check stroke color
    stroke_dist = color_distance(pattern1.stroke_color, pattern2.stroke_color)
    if stroke_dist > color_tolerance:
        confidence *= 0.5
        if stroke_dist > color_tolerance * 2:
            return False, 0.0

    # Check fill color
    fill_dist = color_distance(pattern1.fill_color, pattern2.fill_color)
    if fill_dist > color_tolerance:
        confidence *= 0.7

    # For hatching patterns, check angle
    if pattern1.pattern_type in (PatternType.HATCHING, PatternType.CROSSHATCH):
        angle_dist = angle_distance(pattern1.hatching_angle, pattern2.hatching_angle)
        if angle_dist > angle_tolerance:
            confidence *= 0.5
            if angle_dist > angle_tolerance * 2:
                return False, 0.0

    # Check spacing if available
    if pattern1.hatching_spacing and pattern2.hatching_spacing:
        spacing_diff = abs(pattern1.hatching_spacing - pattern2.hatching_spacing)
        spacing_ratio = spacing_diff / max(pattern1.hatching_spacing, pattern2.hatching_spacing)
        if spacing_ratio > spacing_tolerance:
            confidence *= 0.7

    return confidence > 0.3, confidence


def analyze_drawing_pattern(drawing: Dict[str, Any]) -> PatternInfo:
    """
    Analyze a PDF drawing to extract its pattern characteristics.
    """
    items = drawing.get("items", [])
    stroke_color = drawing.get("color")
    fill_color = drawing.get("fill")

    # Extract line segments
    lines = []
    current_pos = None

    for item in items:
        if len(item) < 2:
            continue

        cmd = item[0]

        if cmd == "m":  # Move
            current_pos = item[1] if len(item) > 1 else None

        elif cmd == "l" and current_pos is not None:  # Line
            p2 = item[1] if len(item) > 1 else None
            if p2 and hasattr(current_pos, 'x') and hasattr(p2, 'x'):
                lines.append({
                    "x1": current_pos.x, "y1": current_pos.y,
                    "x2": p2.x, "y2": p2.y,
                })
                current_pos = p2

        elif cmd == "l" and len(item) >= 3:  # Line with both points
            p1, p2 = item[1], item[2]
            if hasattr(p1, 'x') and hasattr(p2, 'x'):
                lines.append({
                    "x1": p1.x, "y1": p1.y,
                    "x2": p2.x, "y2": p2.y,
                })
                current_pos = p2

    if len(lines) < 2:
        if fill_color:
            return PatternInfo(
                pattern_type=PatternType.SOLID_FILL,
                fill_color=fill_color,
                stroke_color=stroke_color,
            )
        return PatternInfo(pattern_type=PatternType.NONE, stroke_color=stroke_color)

    # Analyze line angles
    angles = []
    total_length = 0.0

    for line in lines:
        dx = line["x2"] - line["x1"]
        dy = line["y2"] - line["y1"]
        length = math.sqrt(dx*dx + dy*dy)
        total_length += length

        if length < 0.1:
            continue

        angle = math.degrees(math.atan2(dy, dx)) % 180
        angles.append(angle)

    if not angles:
        return PatternInfo(pattern_type=PatternType.NONE, stroke_color=stroke_color)

    # Cluster angles
    angle_clusters = _cluster_values(angles, tolerance=15.0)

    if len(angle_clusters) == 1:
        return PatternInfo(
            pattern_type=PatternType.HATCHING,
            stroke_color=stroke_color,
            fill_color=fill_color,
            hatching_angle=angle_clusters[0]["center"],
            line_count=len(lines),
        )
    elif len(angle_clusters) == 2:
        sorted_clusters = sorted(angle_clusters, key=lambda c: c["count"], reverse=True)
        return PatternInfo(
            pattern_type=PatternType.CROSSHATCH,
            stroke_color=stroke_color,
            fill_color=fill_color,
            hatching_angle=sorted_clusters[0]["center"],
            secondary_angle=sorted_clusters[1]["center"],
            line_count=len(lines),
        )

    # Multiple angle groups - complex pattern
    return PatternInfo(
        pattern_type=PatternType.HATCHING,
        stroke_color=stroke_color,
        fill_color=fill_color,
        line_count=len(lines),
    )


def _cluster_values(values: List[float], tolerance: float) -> List[Dict[str, Any]]:
    """Cluster numerical values by proximity."""
    if not values:
        return []

    sorted_vals = sorted(values)
    clusters = []
    current = [sorted_vals[0]]

    for val in sorted_vals[1:]:
        if val - current[-1] <= tolerance:
            current.append(val)
        else:
            if current:
                clusters.append({
                    "center": sum(current) / len(current),
                    "count": len(current),
                })
            current = [val]

    if current:
        clusters.append({
            "center": sum(current) / len(current),
            "count": len(current),
        })

    return [c for c in clusters if c["count"] >= 2]


def calculate_region_length(drawing: Dict[str, Any]) -> float:
    """
    Calculate the total length of a drawing region.
    For wall-like shapes, this represents the wall length.
    """
    items = drawing.get("items", [])
    total_length = 0.0

    # Track the bounding box to estimate primary dimension
    x_coords = []
    y_coords = []

    current_pos = None

    for item in items:
        if len(item) < 2:
            continue

        cmd = item[0]

        if cmd == "m":
            current_pos = item[1] if len(item) > 1 else None
            if current_pos and hasattr(current_pos, 'x'):
                x_coords.append(current_pos.x)
                y_coords.append(current_pos.y)

        elif cmd == "l":
            if len(item) >= 3:
                p1, p2 = item[1], item[2]
            elif current_pos and len(item) >= 2:
                p1, p2 = current_pos, item[1]
            else:
                continue

            if hasattr(p1, 'x') and hasattr(p2, 'x'):
                x_coords.extend([p1.x, p2.x])
                y_coords.extend([p1.y, p2.y])

                dx = p2.x - p1.x
                dy = p2.y - p1.y
                total_length += math.sqrt(dx*dx + dy*dy)
                current_pos = p2

        elif cmd == "re" and len(item) >= 2:  # Rectangle
            rect = item[1]
            if hasattr(rect, 'x0'):
                x_coords.extend([rect.x0, rect.x1])
                y_coords.extend([rect.y0, rect.y1])
                # Rectangle perimeter (or use longest side for walls)
                width = abs(rect.x1 - rect.x0)
                height = abs(rect.y1 - rect.y0)
                total_length += 2 * (width + height)

    # If we have coordinates, use the longest dimension as length
    if x_coords and y_coords:
        x_span = max(x_coords) - min(x_coords)
        y_span = max(y_coords) - min(y_coords)
        # Return the longer dimension (wall length)
        return max(x_span, y_span)

    return total_length / 2  # Approximate for closed paths


def estimate_wall_thickness(drawing: Dict[str, Any]) -> float:
    """
    Estimate wall thickness from a drawing.
    """
    rect = drawing.get("rect")
    if rect is None:
        return 0.0

    width = abs(rect[2] - rect[0])
    height = abs(rect[3] - rect[1])

    # Wall thickness is the shorter dimension
    return min(width, height)


def find_matching_patterns(
    page: fitz.Page,
    target_pattern: PatternInfo,
    exclude_region: Optional[fitz.Rect] = None,
    min_size: float = 10.0,
    color_tolerance: float = 0.25,
    angle_tolerance: float = 15.0,
    min_aspect_ratio: float = 2.0,  # Wall-like shapes should be elongated
) -> List[DetectedRegion]:
    """
    Scan a page for drawings that match the target pattern.

    Args:
        page: PyMuPDF page
        target_pattern: Pattern to match against
        exclude_region: Region to exclude (e.g., Plankopf area)
        min_size: Minimum size (in points) for detected regions
        color_tolerance: How much color variation to allow
        angle_tolerance: How much angle variation to allow (degrees)

    Returns:
        List of detected regions matching the pattern
    """
    drawings = page.get_drawings()
    matches = []
    region_counter = 0

    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue

        drawing_rect = fitz.Rect(rect)

        # Skip small drawings
        if drawing_rect.width < min_size and drawing_rect.height < min_size:
            continue

        # Filter for wall-like shapes (elongated rectangles)
        # Walls are typically much longer than they are wide
        width = drawing_rect.width
        height = drawing_rect.height
        if width > 0 and height > 0:
            aspect_ratio = max(width, height) / min(width, height)
            if aspect_ratio < min_aspect_ratio:
                continue  # Skip square-ish shapes (likely not walls)

        # Skip if in excluded region
        if exclude_region:
            intersection = drawing_rect & exclude_region
            if not intersection.is_empty:
                overlap_ratio = intersection.get_area() / drawing_rect.get_area()
                if overlap_ratio > 0.5:
                    continue

        # Analyze pattern
        pattern = analyze_drawing_pattern(drawing)

        # Check if patterns match
        matches_pattern, confidence = patterns_match(
            pattern,
            target_pattern,
            color_tolerance=color_tolerance,
            angle_tolerance=angle_tolerance,
        )

        if matches_pattern:
            region_counter += 1

            length_px = calculate_region_length(drawing)
            thickness_px = estimate_wall_thickness(drawing)

            bbox = BoundingBox(
                x0=rect[0], y0=rect[1],
                x1=rect[2], y1=rect[3],
            )

            region = DetectedRegion(
                region_id=f"region_{region_counter:04d}",
                bbox=bbox,
                pattern_info=pattern,
                confidence=confidence,
                length_px=length_px,
                wall_thickness_px=thickness_px,
            )
            matches.append(region)

    return matches


def merge_adjacent_regions(
    regions: List[DetectedRegion],
    merge_distance: float = 5.0,
) -> List[DetectedRegion]:
    """
    Merge adjacent detected regions that likely form a single wall.
    """
    if len(regions) <= 1:
        return regions

    # Sort by position
    sorted_regions = sorted(regions, key=lambda r: (r.bbox.y0, r.bbox.x0))

    merged = []
    current = sorted_regions[0]

    for region in sorted_regions[1:]:
        # Check if adjacent
        x_gap = max(0, region.bbox.x0 - current.bbox.x1)
        y_gap = max(0, region.bbox.y0 - current.bbox.y1)

        if x_gap <= merge_distance and y_gap <= merge_distance:
            # Merge regions
            current = DetectedRegion(
                region_id=current.region_id,
                bbox=BoundingBox(
                    x0=min(current.bbox.x0, region.bbox.x0),
                    y0=min(current.bbox.y0, region.bbox.y0),
                    x1=max(current.bbox.x1, region.bbox.x1),
                    y1=max(current.bbox.y1, region.bbox.y1),
                ),
                pattern_info=current.pattern_info,
                confidence=(current.confidence + region.confidence) / 2,
                length_px=current.length_px + region.length_px,
                wall_thickness_px=(current.wall_thickness_px + region.wall_thickness_px) / 2,
            )
        else:
            merged.append(current)
            current = region

    merged.append(current)
    return merged


def convert_to_meters(
    length_px: float,
    scale: str,
    page_dpi: float = 72.0,
) -> float:
    """
    Convert PDF points to real-world meters using drawing scale.

    Args:
        length_px: Length in PDF points (72 points = 1 inch)
        scale: Drawing scale string (e.g., "1:100")
        page_dpi: PDF resolution (default 72 dpi)

    Returns:
        Length in meters
    """
    import re

    # Parse scale
    match = re.match(r"1\s*[:/]\s*(\d+)", scale)
    if match:
        scale_factor = int(match.group(1))
    else:
        scale_factor = 100  # Default assumption

    # PDF points to mm (72 points = 1 inch = 25.4mm)
    length_mm_on_paper = length_px * 25.4 / page_dpi

    # Apply scale to get real-world mm
    real_mm = length_mm_on_paper * scale_factor

    # Convert to meters
    return real_mm / 1000


def detect_pattern_in_page(
    page: fitz.Page,
    target_symbol: LegendSymbol,
    plankopf_bbox: Optional[BoundingBox] = None,
    scale: str = "1:100",
    page_number: int = 0,
) -> PatternMatchResult:
    """
    Detect all occurrences of a pattern in a page.

    Args:
        page: PyMuPDF page
        target_symbol: Legend symbol with pattern to match
        plankopf_bbox: Region to exclude (legend area)
        scale: Drawing scale for measurement conversion
        page_number: Page number for reference

    Returns:
        PatternMatchResult with all detected regions
    """
    warnings = []

    exclude_rect = plankopf_bbox.to_fitz_rect() if plankopf_bbox else None

    # Find matching patterns with balanced tolerances
    # Blueprint hatching patterns often have slight variations
    regions = find_matching_patterns(
        page,
        target_symbol.pattern_info,
        exclude_region=exclude_rect,
        color_tolerance=0.4,       # Moderately relaxed for blueprint variations
        angle_tolerance=25.0,      # Moderately relaxed for angle differences
        min_aspect_ratio=1.0,      # Include all shapes (walls can have various proportions)
    )

    # Merge adjacent regions
    merged_regions = merge_adjacent_regions(regions)

    # Convert measurements
    total_length_px = 0.0
    total_length_m = 0.0

    for region in merged_regions:
        region.matched_symbol = target_symbol
        region.length_m = convert_to_meters(region.length_px, scale)
        total_length_px += region.length_px
        total_length_m += region.length_m

    # Calculate overall confidence
    if merged_regions:
        confidence = sum(r.confidence for r in merged_regions) / len(merged_regions)
    else:
        confidence = 0.0
        warnings.append("No matching patterns found in drawing area")

    return PatternMatchResult(
        page_number=page_number,
        target_pattern=target_symbol.pattern_info,
        detected_regions=merged_regions,
        total_length_px=total_length_px,
        total_length_m=total_length_m,
        segment_count=len(merged_regions),
        confidence=confidence,
        warnings=warnings,
    )
