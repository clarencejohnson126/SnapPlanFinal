"""
Drywall Detection API

Endpoints for Plankopf-based drywall symbol detection and measurement.
"""

import tempfile
import os
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, File, UploadFile, Query, HTTPException
from pydantic import BaseModel, Field

from app.services.drywall_symbol_extraction import (
    extract_drywall_from_bytes,
    FullExtractionResult,
)


router = APIRouter(prefix="/drywall-detection", tags=["drywall-detection"])


# ==================
# RESPONSE MODELS
# ==================

class BoundingBoxResponse(BaseModel):
    """Bounding box coordinates."""
    x0: float
    y0: float
    x1: float
    y1: float


class PatternInfoResponse(BaseModel):
    """Pattern characteristics."""
    pattern_type: str
    stroke_color: Optional[List[float]] = None
    fill_color: Optional[List[float]] = None
    hatching_angle: Optional[float] = None
    hatching_spacing: Optional[float] = None
    line_count: int = 0


class LegendSymbolResponse(BaseModel):
    """A symbol from the Plankopf legend."""
    symbol_id: str
    label: str
    label_normalized: str
    material_type: Optional[str] = None
    pattern_info: PatternInfoResponse
    confidence: float


class DrywallSegmentResponse(BaseModel):
    """A detected drywall segment."""
    segment_id: str
    bbox: BoundingBoxResponse
    length_m: float
    area_m2: float
    wall_height_m: float
    confidence: float
    page_number: int


class DrywallResultResponse(BaseModel):
    """Detection result for a single drywall type."""
    detection_id: str
    material_label: str
    material_type: str
    segments: List[DrywallSegmentResponse]
    total_count: int
    total_length_m: float
    total_area_m2: float
    wall_height_m: float
    scale: str
    confidence: float
    pages_analyzed: List[int]
    assumptions: List[str]
    warnings: List[str]


class DrywallDetectionResponse(BaseModel):
    """Full detection response."""
    extraction_id: str
    filename: str
    page_count: int
    status: str = Field(description="ok, partial, or error")

    # Plankopf info
    plankopf_found: bool
    plankopf_page: Optional[int] = None
    legend_symbols: List[LegendSymbolResponse] = []

    # Drywall results
    drywall_results: List[DrywallResultResponse] = []

    # Totals
    grand_total_length_m: float
    grand_total_area_m2: float
    grand_total_segments: int

    # Settings used
    scale: str
    wall_height_m: float

    # Metadata
    processed_at: str
    errors: List[str] = []
    warnings: List[str] = []


def _convert_to_response(result: FullExtractionResult) -> DrywallDetectionResponse:
    """Convert internal result to API response."""
    legend_symbols = []
    for sym in result.all_legend_symbols:
        sym_dict = sym.to_dict()
        pattern_dict = sym_dict.get("pattern_info", {})
        legend_symbols.append(LegendSymbolResponse(
            symbol_id=sym_dict["symbol_id"],
            label=sym_dict["label"],
            label_normalized=sym_dict["label_normalized"],
            material_type=sym_dict.get("material_type"),
            pattern_info=PatternInfoResponse(**pattern_dict),
            confidence=sym_dict["confidence"],
        ))

    drywall_results = []
    for dr in result.drywall_results:
        dr_dict = dr.to_dict()
        segments = []
        for seg in dr_dict.get("segments", []):
            segments.append(DrywallSegmentResponse(
                segment_id=seg["segment_id"],
                bbox=BoundingBoxResponse(**seg["bbox"]),
                length_m=seg["length_m"],
                area_m2=seg["area_m2"],
                wall_height_m=seg["wall_height_m"],
                confidence=seg["confidence"],
                page_number=seg["page_number"],
            ))

        drywall_results.append(DrywallResultResponse(
            detection_id=dr_dict["detection_id"],
            material_label=dr_dict["material_label"],
            material_type=dr_dict["material_type"],
            segments=segments,
            total_count=dr_dict["total_count"],
            total_length_m=dr_dict["total_length_m"],
            total_area_m2=dr_dict["total_area_m2"],
            wall_height_m=dr_dict["wall_height_m"],
            scale=dr_dict["scale"],
            confidence=dr_dict["confidence"],
            pages_analyzed=dr_dict["pages_analyzed"],
            assumptions=dr_dict["assumptions"],
            warnings=dr_dict["warnings"],
        ))

    return DrywallDetectionResponse(
        extraction_id=result.extraction_id,
        filename=result.filename,
        page_count=result.page_count,
        status=result.status,
        plankopf_found=result.plankopf_found,
        plankopf_page=result.plankopf_page,
        legend_symbols=legend_symbols,
        drywall_results=drywall_results,
        grand_total_length_m=result.grand_total_length_m,
        grand_total_area_m2=result.grand_total_area_m2,
        grand_total_segments=result.grand_total_segments,
        scale=result.scale,
        wall_height_m=result.wall_height_m,
        processed_at=result.processed_at,
        errors=result.errors,
        warnings=result.warnings,
    )


# ==================
# ENDPOINTS
# ==================

@router.post("/from-symbols", response_model=DrywallDetectionResponse)
async def detect_drywall_from_symbols(
    file: UploadFile = File(..., description="Blueprint PDF file"),
    wall_height_m: float = Query(
        2.8,
        ge=1.0,
        le=10.0,
        description="Wall height in meters for area calculation"
    ),
    target_label: Optional[str] = Query(
        None,
        description="Specific material label to match (e.g., 'Trockenbaukonstruktion')"
    ),
    scale: Optional[str] = Query(
        None,
        description="Override detected scale (e.g., '1:100')"
    ),
    page_numbers: Optional[str] = Query(
        None,
        description="Comma-separated page numbers to analyze (0-indexed). Leave empty for all pages."
    ),
) -> DrywallDetectionResponse:
    """
    Detect drywall using Plankopf (title block/legend) symbol matching.

    This endpoint:
    1. **Parses the Plankopf** (legend on right side of blueprint) to learn material symbols
    2. **Identifies drywall patterns** (Trockenbaukonstruktion, etc.) in the legend
    3. **Scans the main drawing** for matching patterns
    4. **Measures** total length and area with full traceability

    ## How It Works

    German construction blueprints include a "Plankopf" (title block/legend) that defines
    what each hatching pattern represents. This endpoint reads the legend first to learn
    the visual vocabulary, then searches for those patterns in the drawing.

    ## Returns

    - **legend_symbols**: All materials found in the Plankopf
    - **drywall_results**: Detected drywall segments with measurements
    - **grand_total_length_m**: Total drywall length in meters
    - **grand_total_area_m2**: Total drywall area (length × wall_height)

    ## Assumptions

    - Wall height is applied uniformly to all segments
    - Measurements are single-sided (multiply by 2 for both sides if needed)
    - Detected segments may include door/window openings
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document"
        )

    # Parse page numbers if provided
    pages: Optional[List[int]] = None
    if page_numbers:
        try:
            pages = [int(p.strip()) for p in page_numbers.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid page_numbers format. Use comma-separated integers (e.g., '0,1,2')"
            )

    # Read file
    try:
        pdf_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read uploaded file: {str(e)}"
        )

    # Process
    result = extract_drywall_from_bytes(
        pdf_bytes=pdf_bytes,
        filename=file.filename,
        wall_height_m=wall_height_m,
        page_numbers=pages,
        target_label=target_label,
        scale_override=scale,
    )

    if result.status == "error":
        raise HTTPException(
            status_code=422,
            detail=result.errors[0] if result.errors else "Processing failed"
        )

    return _convert_to_response(result)


@router.post("/analyze-legend", response_model=Dict[str, Any])
async def analyze_legend_only(
    file: UploadFile = File(..., description="Blueprint PDF file"),
    page_number: int = Query(
        0,
        ge=0,
        description="Page number to analyze (0-indexed)"
    ),
) -> Dict[str, Any]:
    """
    Analyze only the Plankopf/legend without scanning for patterns.

    Use this to preview what symbols are available in a blueprint
    before running the full detection.

    Returns all detected legend symbols with their characteristics.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document"
        )

    try:
        pdf_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read file: {str(e)}"
        )

    import fitz
    from app.services.plankopf_parser import parse_plankopf

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse PDF: {str(e)}"
        )

    if page_number >= len(doc):
        doc.close()
        raise HTTPException(
            status_code=400,
            detail=f"Page {page_number} does not exist. Document has {len(doc)} pages."
        )

    page = doc[page_number]
    plankopf = parse_plankopf(page, page_number=page_number)
    doc.close()

    if plankopf is None:
        return {
            "plankopf_found": False,
            "page_number": page_number,
            "symbols": [],
            "metadata": {},
            "warnings": ["No Plankopf/legend detected on this page"],
        }

    return {
        "plankopf_found": True,
        "page_number": page_number,
        "plankopf_bbox": plankopf.plankopf_bbox.to_dict(),
        "symbols": [s.to_dict() for s in plankopf.symbols],
        "metadata": plankopf.metadata,
        "confidence": plankopf.confidence,
        "warnings": plankopf.warnings,
        "drywall_symbols": [
            s.to_dict() for s in plankopf.symbols
            if s.material_type == "drywall"
        ],
    }


@router.get("/supported-materials")
async def get_supported_materials() -> Dict[str, Any]:
    """
    Get list of material types that can be detected.

    Returns German keywords used for material classification.
    """
    from app.services.plankopf_parser import (
        DRYWALL_KEYWORDS,
        MASONRY_KEYWORDS,
        CONCRETE_KEYWORDS,
        INSULATION_KEYWORDS,
        WOOD_KEYWORDS,
    )

    return {
        "drywall": {
            "name_de": "Trockenbau",
            "name_en": "Drywall",
            "keywords": DRYWALL_KEYWORDS,
            "detection_status": "supported",
        },
        "masonry": {
            "name_de": "Mauerwerk",
            "name_en": "Masonry",
            "keywords": MASONRY_KEYWORDS,
            "detection_status": "planned",
        },
        "concrete": {
            "name_de": "Beton",
            "name_en": "Concrete",
            "keywords": CONCRETE_KEYWORDS,
            "detection_status": "planned",
        },
        "insulation": {
            "name_de": "Dämmung",
            "name_en": "Insulation",
            "keywords": INSULATION_KEYWORDS,
            "detection_status": "planned",
        },
        "wood": {
            "name_de": "Holz",
            "name_en": "Wood",
            "keywords": WOOD_KEYWORDS,
            "detection_status": "planned",
        },
    }
