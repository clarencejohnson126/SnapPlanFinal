"""
Room Area Extraction API routes.

Provides endpoints for extracting room areas from German CAD PDFs.
Supports multiple blueprint styles with automatic detection.

Styles supported:
- Haardtring (Residential): F: pattern
- LeiQ (Office): NRF: pattern
- Omniturm (Highrise): NGF: pattern
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..services.unified_extraction import (
    extract_to_dict,
    extract_room_areas,
    detect_blueprint_style,
    BlueprintStyle,
    RoomCategory,
)
from ..services.llm_interpretation import (
    interpret_extraction,
    generate_quick_summary,
    InterpretationType,
)
from ..services.excel_export import (
    export_extraction_to_excel,
    export_to_csv,
    is_excel_available,
)


router = APIRouter(prefix="/extraction", tags=["extraction"])


# =============================================================================
# Response Models
# =============================================================================


class ExtractedRoomResponse(BaseModel):
    """Response model for a single extracted room."""
    room_number: str
    room_name: str
    area_m2: float
    counted_m2: float
    factor: float
    page: int
    source_text: str
    category: str
    extraction_pattern: str
    bbox: Optional[Dict[str, float]] = None
    perimeter_m: Optional[float] = None
    height_m: Optional[float] = None
    factor_source: Optional[str] = None


class CategoryTotalResponse(BaseModel):
    """Response model for category totals."""
    category: str
    area_m2: float
    room_count: int


class ExtractionSummaryResponse(BaseModel):
    """Response model for extraction summary."""
    total_rooms: int
    total_area_m2: float
    total_counted_m2: float
    blueprint_style: str
    page_count: int
    by_category: List[CategoryTotalResponse]


class RoomExtractionResponse(BaseModel):
    """Response model for room extraction endpoint."""
    extraction_id: str
    source_file: str
    extracted_at: str
    summary: ExtractionSummaryResponse
    rooms: List[ExtractedRoomResponse]
    warnings: List[str]


class StyleDetectionResponse(BaseModel):
    """Response model for blueprint style detection."""
    detected_style: str
    confidence: str
    patterns_found: Dict[str, bool]


# =============================================================================
# Health Endpoint
# =============================================================================


class ExtractionHealthResponse(BaseModel):
    """Health check response for extraction service."""
    status: str
    service: str
    supported_styles: List[str]
    supported_patterns: List[str]


@router.get("/health", response_model=ExtractionHealthResponse)
async def health_check():
    """
    Check if the extraction service is healthy.

    Returns list of supported blueprint styles and patterns.
    """
    return ExtractionHealthResponse(
        status="ok",
        service="room_area_extraction",
        supported_styles=["haardtring", "leiq", "omniturm"],
        supported_patterns=["F:", "NRF:", "NGF:"],
    )


# =============================================================================
# Main Extraction Endpoint
# =============================================================================


@router.post("/rooms", response_model=RoomExtractionResponse)
async def extract_rooms(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    style: Optional[str] = Query(
        None,
        description="Blueprint style (haardtring, leiq, omniturm). Auto-detected if not provided.",
    ),
    pages: Optional[str] = Query(
        None,
        description="Comma-separated page numbers (0-indexed). Leave empty for all pages.",
    ),
):
    """
    Extract room areas from a German CAD PDF blueprint.

    This endpoint automatically detects the blueprint style and extracts all room
    areas with full traceability. Supports three major German blueprint formats.

    **Supported Styles:**

    1. **Haardtring (Residential)**
       - Pattern: `F: XX,XX m²`
       - Room numbers: `R2.E5.3.5`
       - Special: 50% factor for balconies

    2. **LeiQ (Office)**
       - Pattern: `NRF: XX,XX m²`
       - Room numbers: `B.00.2.002`
       - Additional: U: (perimeter), LH: (height)

    3. **Omniturm (Highrise)**
       - Pattern: `NGF: XX,XX m²`
       - Room numbers: `33_b6.12` or `BT1.EG.001`
       - Special: Reversed Schacht pattern

    **Returns:**
    - Extracted rooms with areas and traceability
    - Summary with totals by category
    - Detected blueprint style
    - Any warnings encountered
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be a PDF, got: {file.filename}",
        )

    # Parse pages parameter
    page_list = None
    if pages:
        try:
            page_list = [int(p.strip()) for p in pages.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pages parameter: {pages}. Use comma-separated integers.",
            )

    # Parse style parameter
    style_enum = None
    if style:
        try:
            style_enum = BlueprintStyle(style.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid style: {style}. Use: haardtring, leiq, or omniturm.",
            )

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract room areas
        result = extract_room_areas(
            pdf_path=temp_path,
            style=style_enum,
            pages=page_list,
        )

        # Build response
        rooms = []
        for room in result.rooms:
            rooms.append(ExtractedRoomResponse(
                room_number=room.room_number,
                room_name=room.room_name,
                area_m2=room.area_m2,
                counted_m2=room.counted_m2,
                factor=room.factor,
                page=room.page,
                source_text=room.source_text,
                category=room.category.value,
                extraction_pattern=room.extraction_pattern,
                bbox=room.bbox.to_dict() if room.bbox else None,
                perimeter_m=room.perimeter_m,
                height_m=room.height_m,
                factor_source=room.factor_source,
            ))

        # Build category totals
        category_totals = []
        for cat, total in result.totals_by_category.items():
            room_count = len([r for r in result.rooms if r.category.value == cat])
            category_totals.append(CategoryTotalResponse(
                category=cat,
                area_m2=total,
                room_count=room_count,
            ))

        # Build summary
        summary = ExtractionSummaryResponse(
            total_rooms=result.room_count,
            total_area_m2=result.total_area_m2,
            total_counted_m2=result.total_counted_m2,
            blueprint_style=result.blueprint_style.value,
            page_count=result.page_count,
            by_category=category_totals,
        )

        return RoomExtractionResponse(
            extraction_id=f"ext_{uuid4().hex[:12]}",
            source_file=file.filename,
            extracted_at=datetime.utcnow().isoformat() + "Z",
            summary=summary,
            rooms=rooms,
            warnings=result.warnings,
        )

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Style Detection Endpoint
# =============================================================================


@router.post("/detect-style", response_model=StyleDetectionResponse)
async def detect_style(
    file: UploadFile = File(..., description="Floor plan PDF file"),
):
    """
    Detect the blueprint style without extracting rooms.

    Useful for previewing which extraction pattern will be used.

    **Returns:**
    - Detected style (haardtring, leiq, omniturm, unknown)
    - Confidence level
    - Which patterns were found in the PDF
    """
    import fitz
    import re

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be a PDF, got: {file.filename}",
        )

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Read PDF text
        doc = fitz.open(str(temp_path))
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        # Detect patterns
        patterns_found = {
            "F:": bool(re.search(r'\bF:\s*\d', full_text)),
            "NRF:": bool(re.search(r'\bNRF:\s*\d', full_text, re.IGNORECASE)),
            "NGF:": bool(re.search(r'\bNGF:\s*\d', full_text, re.IGNORECASE)),
            "R_pattern": bool(re.search(r'\bR\d+\.E\d+\.\d+\.\d+\b', full_text)),
            "B_pattern": bool(re.search(r'\bB\.\d+\.\d+\.\d+\b', full_text)),
            "grid_pattern": bool(re.search(r'\b\d+_[a-z]\d+\.\d+\b', full_text)),
        }

        # Detect style
        style = detect_blueprint_style(full_text)

        # Determine confidence
        if style == BlueprintStyle.UNKNOWN:
            confidence = "low"
        elif sum(patterns_found.values()) >= 2:
            confidence = "high"
        else:
            confidence = "medium"

        return StyleDetectionResponse(
            detected_style=style.value,
            confidence=confidence,
            patterns_found=patterns_found,
        )

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Category List Endpoint
# =============================================================================


@router.get("/categories")
async def list_categories():
    """
    List all room categories used for grouping.

    **Returns:**
    List of category names with descriptions.
    """
    return {
        "categories": [
            {"id": "office", "name": "Office", "keywords": ["büro", "office", "nutzungseinheit"]},
            {"id": "residential", "name": "Residential", "keywords": ["schlafen", "wohnen", "essen", "kochen"]},
            {"id": "circulation", "name": "Circulation", "keywords": ["flur", "diele", "schleuse", "lobby"]},
            {"id": "stairs", "name": "Stairs", "keywords": ["treppe", "treppenhaus", "trh"]},
            {"id": "elevators", "name": "Elevators", "keywords": ["aufzug", "lift"]},
            {"id": "shafts", "name": "Shafts", "keywords": ["schacht", "lüftung", "medien"]},
            {"id": "technical", "name": "Technical", "keywords": ["elektro", "technik", "hwr"]},
            {"id": "sanitary", "name": "Sanitary", "keywords": ["wc", "bad", "dusche"]},
            {"id": "storage", "name": "Storage", "keywords": ["lager", "abstellraum", "müll"]},
            {"id": "outdoor", "name": "Outdoor", "keywords": ["balkon", "terrasse", "loggia"]},
            {"id": "other", "name": "Other", "keywords": []},
        ]
    }


# =============================================================================
# LLM Interpretation Endpoints
# =============================================================================


class InterpretationRequest(BaseModel):
    """Request model for LLM interpretation."""
    extraction_data: Dict[str, Any] = Field(..., description="Extraction result data")
    interpretation_type: str = Field(
        "summary",
        description="Type of interpretation: summary, smart_tips, cost_estimate, full_report"
    )
    language: str = Field("de", description="Output language: de (German) or en (English)")
    custom_prompt: Optional[str] = Field(None, description="Optional custom prompt")


class InterpretationResponse(BaseModel):
    """Response model for LLM interpretation."""
    success: bool
    interpretation_type: str
    content: str
    language: str
    tokens_used: int
    model: str
    error: Optional[str] = None


@router.post("/interpret", response_model=InterpretationResponse)
async def interpret_results(request: InterpretationRequest):
    """
    Generate LLM interpretation of extraction results.

    This endpoint uses OpenAI to interpret already-extracted data and generate:
    - Natural language summaries
    - Smart tips for construction professionals
    - Rough cost estimates
    - Full reports

    **IMPORTANT**: The LLM only interprets data - it does NOT extract values.
    All numbers come from deterministic extraction with full traceability.

    **Interpretation Types:**
    - `summary`: Overview of room areas by category
    - `smart_tips`: Practical advice for construction teams
    - `cost_estimate`: Rough cost calculations (with disclaimer)
    - `full_report`: Comprehensive report with all of the above

    **Languages:**
    - `de`: German (default)
    - `en`: English
    """
    try:
        interp_type = InterpretationType(request.interpretation_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interpretation_type: {request.interpretation_type}. "
                   f"Use: summary, smart_tips, cost_estimate, or full_report"
        )

    result = interpret_extraction(
        extraction_data=request.extraction_data,
        interpretation_type=interp_type,
        language=request.language,
        custom_prompt=request.custom_prompt,
    )

    return InterpretationResponse(
        success=result.success,
        interpretation_type=result.interpretation_type.value,
        content=result.content,
        language=result.language,
        tokens_used=result.tokens_used,
        model=result.model,
        error=result.error,
    )


class QuickSummaryResponse(BaseModel):
    """Response model for quick summary."""
    summary: str
    language: str


@router.post("/quick-summary", response_model=QuickSummaryResponse)
async def get_quick_summary(request: InterpretationRequest):
    """
    Generate a quick summary without using LLM API.

    This is a fast, free alternative that provides basic summary formatting
    without requiring an API call. Useful for previews and when API is unavailable.

    **Returns:**
    - Formatted markdown summary of extraction results
    """
    summary = generate_quick_summary(
        extraction_data=request.extraction_data,
        language=request.language,
    )

    return QuickSummaryResponse(
        summary=summary,
        language=request.language,
    )


# =============================================================================
# Combined Extract + Interpret Endpoint
# =============================================================================


class ExtractAndInterpretResponse(BaseModel):
    """Response model for combined extraction and interpretation."""
    extraction_id: str
    source_file: str
    extracted_at: str
    summary: ExtractionSummaryResponse
    rooms: List[ExtractedRoomResponse]
    warnings: List[str]
    interpretation: Optional[InterpretationResponse] = None
    quick_summary: str


@router.post("/extract-and-interpret", response_model=ExtractAndInterpretResponse)
async def extract_and_interpret(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    style: Optional[str] = Query(None, description="Blueprint style"),
    pages: Optional[str] = Query(None, description="Comma-separated page numbers"),
    interpretation_type: str = Query("summary", description="Type of LLM interpretation"),
    language: str = Query("de", description="Output language"),
    use_llm: bool = Query(True, description="Whether to use LLM for interpretation"),
):
    """
    Extract room areas AND generate interpretation in one call.

    This is the main endpoint for the web application - uploads a PDF,
    extracts all room areas, and generates an AI-powered interpretation.

    **Process:**
    1. Upload PDF
    2. Auto-detect blueprint style
    3. Extract all room areas with traceability
    4. Generate quick summary (always)
    5. Generate LLM interpretation (if use_llm=true)

    **Returns:**
    - Extraction results with rooms and totals
    - Quick summary (no API required)
    - LLM interpretation (if requested)
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be a PDF, got: {file.filename}",
        )

    # Parse pages parameter
    page_list = None
    if pages:
        try:
            page_list = [int(p.strip()) for p in pages.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pages parameter: {pages}. Use comma-separated integers.",
            )

    # Parse style parameter
    style_enum = None
    if style:
        try:
            style_enum = BlueprintStyle(style.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid style: {style}. Use: haardtring, leiq, or omniturm.",
            )

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract room areas
        result = extract_room_areas(
            pdf_path=temp_path,
            style=style_enum,
            pages=page_list,
        )

        # Build extraction response
        rooms = []
        for room in result.rooms:
            rooms.append(ExtractedRoomResponse(
                room_number=room.room_number,
                room_name=room.room_name,
                area_m2=room.area_m2,
                counted_m2=room.counted_m2,
                factor=room.factor,
                page=room.page,
                source_text=room.source_text,
                category=room.category.value,
                extraction_pattern=room.extraction_pattern,
                bbox=room.bbox.to_dict() if room.bbox else None,
                perimeter_m=room.perimeter_m,
                height_m=room.height_m,
                factor_source=room.factor_source,
            ))

        # Build category totals
        category_totals = []
        for cat, total in result.totals_by_category.items():
            room_count = len([r for r in result.rooms if r.category.value == cat])
            category_totals.append(CategoryTotalResponse(
                category=cat,
                area_m2=total,
                room_count=room_count,
            ))

        summary = ExtractionSummaryResponse(
            total_rooms=result.room_count,
            total_area_m2=result.total_area_m2,
            total_counted_m2=result.total_counted_m2,
            blueprint_style=result.blueprint_style.value,
            page_count=result.page_count,
            by_category=category_totals,
        )

        # Generate quick summary (always)
        extraction_dict = result.to_dict()
        quick_summary = generate_quick_summary(extraction_dict, language)

        # Generate LLM interpretation (if requested)
        interpretation = None
        if use_llm:
            try:
                interp_type = InterpretationType(interpretation_type)
                interp_result = interpret_extraction(
                    extraction_data=extraction_dict,
                    interpretation_type=interp_type,
                    language=language,
                )
                interpretation = InterpretationResponse(
                    success=interp_result.success,
                    interpretation_type=interp_result.interpretation_type.value,
                    content=interp_result.content,
                    language=interp_result.language,
                    tokens_used=interp_result.tokens_used,
                    model=interp_result.model,
                    error=interp_result.error,
                )
            except Exception as e:
                # Don't fail the whole request if LLM fails
                interpretation = InterpretationResponse(
                    success=False,
                    interpretation_type=interpretation_type,
                    content="",
                    language=language,
                    tokens_used=0,
                    model="none",
                    error=str(e),
                )

        return ExtractAndInterpretResponse(
            extraction_id=f"ext_{uuid4().hex[:12]}",
            source_file=file.filename,
            extracted_at=datetime.utcnow().isoformat() + "Z",
            summary=summary,
            rooms=rooms,
            warnings=result.warnings,
            interpretation=interpretation,
            quick_summary=quick_summary,
        )

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Excel Export Endpoints
# =============================================================================


class ExcelExportRequest(BaseModel):
    """Request model for Excel export."""
    extraction_data: Dict[str, Any] = Field(..., description="Extraction result data")
    source_filename: str = Field("blueprint.pdf", description="Original filename")
    include_summary: bool = Field(True, description="Include summary sheet")
    include_details: bool = Field(True, description="Include details sheet")
    include_categories: bool = Field(False, description="Create sheet per category")
    language: str = Field("de", description="Output language (de/en)")


@router.post("/export/excel")
async def export_to_excel(request: ExcelExportRequest):
    """
    Export extraction results to Excel file.

    Generates a professional Aufmaß (measurement take-off) Excel file with:
    - Summary sheet with totals by category
    - Detailed room list with all extracted data
    - Optional separate sheets per category

    **Output Format:**
    - German number format (comma as decimal)
    - Professional formatting suitable for construction documents
    - Color-coded categories and outdoor areas

    **Returns:**
    - Excel file download (.xlsx)
    """
    if not is_excel_available():
        raise HTTPException(
            status_code=503,
            detail="Excel export not available. Install openpyxl: pip install openpyxl"
        )

    result = export_extraction_to_excel(
        extraction_data=request.extraction_data,
        source_filename=request.source_filename,
        include_summary_sheet=request.include_summary,
        include_details_sheet=request.include_details,
        include_category_sheets=request.include_categories,
        language=request.language,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Excel export failed: {result.error}"
        )

    return StreamingResponse(
        io.BytesIO(result.file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={result.filename}"}
    )


@router.post("/export/csv")
async def export_to_csv_endpoint(request: ExcelExportRequest):
    """
    Export extraction results to CSV file.

    Fallback option when Excel is not needed. Uses semicolon delimiter
    and German number format for compatibility with Excel.

    **Returns:**
    - CSV file download (.csv)
    """
    result = export_to_csv(
        extraction_data=request.extraction_data,
        source_filename=request.source_filename,
        language=request.language,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"CSV export failed: {result.error}"
        )

    return StreamingResponse(
        io.BytesIO(result.file_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={result.filename}"}
    )


@router.post("/extract-and-export")
async def extract_and_export_excel(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    style: Optional[str] = Query(None, description="Blueprint style"),
    pages: Optional[str] = Query(None, description="Comma-separated page numbers"),
    language: str = Query("de", description="Output language"),
    format: str = Query("xlsx", description="Export format: xlsx or csv"),
):
    """
    Extract room areas and directly export to Excel/CSV.

    One-step endpoint that uploads a PDF, extracts all data, and returns
    an Excel or CSV file ready for use in construction workflows.

    **Use Cases:**
    - Quick Aufmaß generation from blueprint
    - Batch processing of floor plans
    - Integration with construction management software

    **Returns:**
    - Excel or CSV file download
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be a PDF, got: {file.filename}",
        )

    # Parse pages parameter
    page_list = None
    if pages:
        try:
            page_list = [int(p.strip()) for p in pages.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pages parameter: {pages}. Use comma-separated integers.",
            )

    # Parse style parameter
    style_enum = None
    if style:
        try:
            style_enum = BlueprintStyle(style.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid style: {style}. Use: haardtring, leiq, or omniturm.",
            )

    # Validate format
    if format not in ["xlsx", "csv"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format: {format}. Use: xlsx or csv.",
        )

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract room areas
        result = extract_room_areas(
            pdf_path=temp_path,
            style=style_enum,
            pages=page_list,
        )

        # Convert to dict for export
        extraction_dict = result.to_dict()

        # Export based on format
        if format == "xlsx":
            if not is_excel_available():
                raise HTTPException(
                    status_code=503,
                    detail="Excel export not available. Use format=csv instead."
                )

            export_result = export_extraction_to_excel(
                extraction_data=extraction_dict,
                source_filename=file.filename,
                include_summary_sheet=True,
                include_details_sheet=True,
                include_category_sheets=False,
                language=language,
            )

            if not export_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Export failed: {export_result.error}"
                )

            return StreamingResponse(
                io.BytesIO(export_result.file_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={export_result.filename}"}
            )

        else:  # csv
            export_result = export_to_csv(
                extraction_data=extraction_dict,
                source_filename=file.filename,
                language=language,
            )

            if not export_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Export failed: {export_result.error}"
                )

            return StreamingResponse(
                io.BytesIO(export_result.file_bytes),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={export_result.filename}"}
            )

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)
