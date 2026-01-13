"""
Drywall Symbol Extraction

Orchestrates the full pipeline for extracting drywall quantities from blueprints
using Plankopf-based symbol detection.

Pipeline:
1. Parse Plankopf to learn symbol vocabulary
2. Find drywall symbol(s) in legend
3. Scan drawing for matching patterns
4. Measure and return results with full traceability
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import fitz  # PyMuPDF

from app.services.plankopf_parser import (
    parse_plankopf,
    get_drywall_symbols,
    PlankopfResult,
    LegendSymbol,
    BoundingBox,
    DRYWALL_KEYWORDS,
)
from app.services.material_pattern_detector import (
    detect_pattern_in_page,
    PatternMatchResult,
    DetectedRegion,
    convert_to_meters,
)


@dataclass
class DrywallSegment:
    """A single detected drywall segment."""
    segment_id: str
    bbox: BoundingBox
    length_m: float
    area_m2: float          # Length × wall_height
    wall_height_m: float
    confidence: float
    page_number: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "bbox": self.bbox.to_dict(),
            "length_m": round(self.length_m, 3),
            "area_m2": round(self.area_m2, 3),
            "wall_height_m": self.wall_height_m,
            "confidence": round(self.confidence, 3),
            "page_number": self.page_number,
        }


@dataclass
class DrywallDetectionResult:
    """Result of drywall symbol detection for a single material type."""
    detection_id: str
    material_label: str         # Original label from legend (e.g., "Trockenbaukonstruktion")
    material_type: str          # Normalized type (e.g., "drywall")

    # What we found
    segments: List[DrywallSegment] = field(default_factory=list)
    total_count: int = 0

    # Measurements
    total_length_m: float = 0.0
    total_area_m2: float = 0.0
    wall_height_m: float = 2.8

    # Source info
    source_symbol: Optional[LegendSymbol] = None
    pages_analyzed: List[int] = field(default_factory=list)

    # Traceability
    detection_method: str = "plankopf_symbol_matching"
    scale: str = "1:100"
    confidence: float = 0.0
    processed_at: str = ""

    # Audit trail
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detection_id": self.detection_id,
            "material_label": self.material_label,
            "material_type": self.material_type,
            "segments": [s.to_dict() for s in self.segments],
            "total_count": self.total_count,
            "total_length_m": round(self.total_length_m, 3),
            "total_area_m2": round(self.total_area_m2, 3),
            "wall_height_m": self.wall_height_m,
            "source_symbol": self.source_symbol.to_dict() if self.source_symbol else None,
            "pages_analyzed": self.pages_analyzed,
            "detection_method": self.detection_method,
            "scale": self.scale,
            "confidence": round(self.confidence, 3),
            "processed_at": self.processed_at,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
        }


@dataclass
class FullExtractionResult:
    """Complete extraction result for a PDF document."""
    extraction_id: str
    filename: str
    page_count: int

    # Plankopf info
    plankopf_found: bool = False
    plankopf_page: Optional[int] = None
    all_legend_symbols: List[LegendSymbol] = field(default_factory=list)

    # Drywall results (may have multiple types)
    drywall_results: List[DrywallDetectionResult] = field(default_factory=list)

    # Totals across all drywall types
    grand_total_length_m: float = 0.0
    grand_total_area_m2: float = 0.0
    grand_total_segments: int = 0

    # Metadata
    scale: str = "1:100"
    wall_height_m: float = 2.8
    processed_at: str = ""

    # Status
    status: str = "ok"  # "ok", "partial", "error"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extraction_id": self.extraction_id,
            "filename": self.filename,
            "page_count": self.page_count,
            "plankopf_found": self.plankopf_found,
            "plankopf_page": self.plankopf_page,
            "all_legend_symbols": [s.to_dict() for s in self.all_legend_symbols],
            "drywall_results": [r.to_dict() for r in self.drywall_results],
            "grand_total_length_m": round(self.grand_total_length_m, 3),
            "grand_total_area_m2": round(self.grand_total_area_m2, 3),
            "grand_total_segments": self.grand_total_segments,
            "scale": self.scale,
            "wall_height_m": self.wall_height_m,
            "processed_at": self.processed_at,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _generate_id(prefix: str = "det") -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _is_drywall_label(label: str, target_label: Optional[str] = None) -> bool:
    """
    Check if a label refers to drywall.

    Args:
        label: Label text from legend
        target_label: Specific label to match (if provided)
    """
    label_lower = label.lower()

    if target_label:
        return target_label.lower() in label_lower

    for keyword in DRYWALL_KEYWORDS:
        if keyword in label_lower:
            return True

    return False


def extract_drywall_from_pdf(
    pdf_path: str,
    wall_height_m: float = 2.8,
    page_numbers: Optional[List[int]] = None,
    target_label: Optional[str] = None,
    scale_override: Optional[str] = None,
) -> FullExtractionResult:
    """
    Extract drywall quantities from a PDF using Plankopf symbol detection.

    This is the main entry point for the drywall extraction pipeline.

    Args:
        pdf_path: Path to PDF file
        wall_height_m: Wall height for area calculation
        page_numbers: Specific pages to analyze (None = all pages)
        target_label: Specific material label to match
        scale_override: Override detected scale (e.g., "1:100")

    Returns:
        FullExtractionResult with all detected drywall segments
    """
    extraction_id = _generate_id("ext")
    processed_at = datetime.now(timezone.utc).isoformat()

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return FullExtractionResult(
            extraction_id=extraction_id,
            filename=pdf_path.split("/")[-1],
            page_count=0,
            status="error",
            errors=[f"Failed to open PDF: {str(e)}"],
            processed_at=processed_at,
        )

    filename = pdf_path.split("/")[-1]
    page_count = len(doc)
    pages_to_analyze = page_numbers or list(range(page_count))

    result = FullExtractionResult(
        extraction_id=extraction_id,
        filename=filename,
        page_count=page_count,
        wall_height_m=wall_height_m,
        processed_at=processed_at,
    )

    # Step 1: Find and parse Plankopf
    plankopf: Optional[PlankopfResult] = None

    for page_num in pages_to_analyze:
        if page_num >= page_count:
            continue

        page = doc[page_num]
        parsed = parse_plankopf(page, page_number=page_num)

        if parsed and parsed.symbols:
            plankopf = parsed
            result.plankopf_found = True
            result.plankopf_page = page_num
            result.all_legend_symbols = parsed.symbols
            result.warnings.extend(parsed.warnings)

            # Get scale from Plankopf
            if scale_override:
                result.scale = scale_override
            elif "scale" in parsed.metadata:
                result.scale = parsed.metadata["scale"]
            else:
                result.scale = "1:100"
                result.warnings.append("Scale not detected - using default 1:100")

            break

    if not plankopf:
        result.status = "partial"
        result.warnings.append("No Plankopf (legend) found in document")
        doc.close()
        return result

    # Step 2: Find drywall symbols in legend
    drywall_symbols = [
        s for s in plankopf.symbols
        if _is_drywall_label(s.label, target_label) or s.material_type == "drywall"
    ]

    if not drywall_symbols:
        result.status = "partial"
        result.warnings.append("No drywall symbols found in Plankopf legend")
        doc.close()
        return result

    # Step 3: For each drywall symbol, scan pages for matches
    for symbol in drywall_symbols:
        detection_result = DrywallDetectionResult(
            detection_id=_generate_id("dw"),
            material_label=symbol.label,
            material_type=symbol.material_type or "drywall",
            source_symbol=symbol,
            wall_height_m=wall_height_m,
            scale=result.scale,
            processed_at=processed_at,
        )

        all_segments: List[DrywallSegment] = []

        for page_num in pages_to_analyze:
            if page_num >= page_count:
                continue

            page = doc[page_num]

            # Detect patterns matching this symbol
            match_result = detect_pattern_in_page(
                page=page,
                target_symbol=symbol,
                plankopf_bbox=plankopf.plankopf_bbox if page_num == result.plankopf_page else None,
                scale=result.scale,
                page_number=page_num,
            )

            detection_result.pages_analyzed.append(page_num)
            detection_result.warnings.extend(match_result.warnings)

            # Convert detected regions to segments
            for region in match_result.detected_regions:
                segment = DrywallSegment(
                    segment_id=_generate_id("seg"),
                    bbox=region.bbox,
                    length_m=region.length_m or 0.0,
                    area_m2=(region.length_m or 0.0) * wall_height_m,
                    wall_height_m=wall_height_m,
                    confidence=region.confidence,
                    page_number=page_num,
                )
                all_segments.append(segment)

        # Aggregate results
        detection_result.segments = all_segments
        detection_result.total_count = len(all_segments)
        detection_result.total_length_m = sum(s.length_m for s in all_segments)
        detection_result.total_area_m2 = sum(s.area_m2 for s in all_segments)

        if all_segments:
            detection_result.confidence = sum(s.confidence for s in all_segments) / len(all_segments)

        # Add assumptions
        detection_result.assumptions = [
            f"Wall height: {wall_height_m}m",
            f"Scale: {result.scale}",
            f"Pattern matched: {symbol.pattern_info.pattern_type.value}",
            "Single-sided measurement (multiply by 2 for both sides if needed)",
            "Segments may include door/window openings",
        ]

        result.drywall_results.append(detection_result)

    # Step 4: Calculate grand totals
    result.grand_total_length_m = sum(r.total_length_m for r in result.drywall_results)
    result.grand_total_area_m2 = sum(r.total_area_m2 for r in result.drywall_results)
    result.grand_total_segments = sum(r.total_count for r in result.drywall_results)

    if result.grand_total_segments == 0:
        result.status = "partial"
        result.warnings.append("Drywall symbols found in legend but no matching patterns detected in drawing")

    doc.close()
    return result


def extract_drywall_from_bytes(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
    wall_height_m: float = 2.8,
    page_numbers: Optional[List[int]] = None,
    target_label: Optional[str] = None,
    scale_override: Optional[str] = None,
) -> FullExtractionResult:
    """
    Extract drywall from PDF bytes (for file uploads).

    Args:
        pdf_bytes: PDF file content as bytes
        filename: Original filename
        wall_height_m: Wall height for area calculation
        page_numbers: Specific pages to analyze
        target_label: Specific label to match
        scale_override: Override detected scale

    Returns:
        FullExtractionResult
    """
    extraction_id = _generate_id("ext")
    processed_at = datetime.now(timezone.utc).isoformat()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return FullExtractionResult(
            extraction_id=extraction_id,
            filename=filename,
            page_count=0,
            status="error",
            errors=[f"Failed to parse PDF: {str(e)}"],
            processed_at=processed_at,
        )

    page_count = len(doc)
    pages_to_analyze = page_numbers or list(range(page_count))

    result = FullExtractionResult(
        extraction_id=extraction_id,
        filename=filename,
        page_count=page_count,
        wall_height_m=wall_height_m,
        processed_at=processed_at,
    )

    # Step 1: Find and parse Plankopf
    plankopf: Optional[PlankopfResult] = None

    for page_num in pages_to_analyze:
        if page_num >= page_count:
            continue

        page = doc[page_num]
        parsed = parse_plankopf(page, page_number=page_num)

        if parsed and parsed.symbols:
            plankopf = parsed
            result.plankopf_found = True
            result.plankopf_page = page_num
            result.all_legend_symbols = parsed.symbols
            result.warnings.extend(parsed.warnings)

            if scale_override:
                result.scale = scale_override
            elif "scale" in parsed.metadata:
                result.scale = parsed.metadata["scale"]
            else:
                result.scale = "1:100"
                result.warnings.append("Scale not detected - using default 1:100")

            break

    if not plankopf:
        result.status = "partial"
        result.warnings.append("No Plankopf (legend) found in document")
        doc.close()
        return result

    # Step 2: Find drywall symbols
    drywall_symbols = [
        s for s in plankopf.symbols
        if _is_drywall_label(s.label, target_label) or s.material_type == "drywall"
    ]

    if not drywall_symbols:
        result.status = "partial"
        result.warnings.append("No drywall symbols found in Plankopf legend")
        doc.close()
        return result

    # Step 3: Scan for matches
    for symbol in drywall_symbols:
        detection_result = DrywallDetectionResult(
            detection_id=_generate_id("dw"),
            material_label=symbol.label,
            material_type=symbol.material_type or "drywall",
            source_symbol=symbol,
            wall_height_m=wall_height_m,
            scale=result.scale,
            processed_at=processed_at,
        )

        all_segments: List[DrywallSegment] = []

        for page_num in pages_to_analyze:
            if page_num >= page_count:
                continue

            page = doc[page_num]

            match_result = detect_pattern_in_page(
                page=page,
                target_symbol=symbol,
                plankopf_bbox=plankopf.plankopf_bbox if page_num == result.plankopf_page else None,
                scale=result.scale,
                page_number=page_num,
            )

            detection_result.pages_analyzed.append(page_num)
            detection_result.warnings.extend(match_result.warnings)

            for region in match_result.detected_regions:
                segment = DrywallSegment(
                    segment_id=_generate_id("seg"),
                    bbox=region.bbox,
                    length_m=region.length_m or 0.0,
                    area_m2=(region.length_m or 0.0) * wall_height_m,
                    wall_height_m=wall_height_m,
                    confidence=region.confidence,
                    page_number=page_num,
                )
                all_segments.append(segment)

        detection_result.segments = all_segments
        detection_result.total_count = len(all_segments)
        detection_result.total_length_m = sum(s.length_m for s in all_segments)
        detection_result.total_area_m2 = sum(s.area_m2 for s in all_segments)

        if all_segments:
            detection_result.confidence = sum(s.confidence for s in all_segments) / len(all_segments)

        detection_result.assumptions = [
            f"Wall height: {wall_height_m}m",
            f"Scale: {result.scale}",
            f"Pattern matched: {symbol.pattern_info.pattern_type.value}",
            "Single-sided measurement",
            "Segments may include openings",
        ]

        result.drywall_results.append(detection_result)

    # Grand totals
    result.grand_total_length_m = sum(r.total_length_m for r in result.drywall_results)
    result.grand_total_area_m2 = sum(r.total_area_m2 for r in result.drywall_results)
    result.grand_total_segments = sum(r.total_count for r in result.drywall_results)

    if result.grand_total_segments == 0:
        result.status = "partial"
        result.warnings.append("Symbols found but no patterns matched in drawing")

    doc.close()
    return result
