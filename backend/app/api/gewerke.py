"""
Gewerke (Trade Modules) API routes.

Provides endpoints for trade-specific quantity takeoff:
- Doors: Parse door schedules and return structured door lists
- Drywall: Calculate wall length and drywall area for sectors
"""

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..services.gewerke import (
    DoorCategory,
    DoorGewerkResult,
    DrywallGewerkResult,
    run_door_gewerk_from_schedule,
    run_drywall_gewerk_for_sector,
)
from ..services.schedule_extraction import extract_schedules_from_pdf
from ..services.measurement_engine import Sector
from ..services.scale_calibration import ScaleContext, compute_pixels_per_meter
from ..services.persistence import get_scale_context, get_sector
from ..services.vector_measurement import (
    extract_door_symbols_from_page,
    measure_doors_on_page,
    DoorSymbol,
)
from ..services.cv_pipeline import (
    detect_doors_hybrid,
    is_yolo_available,
    get_cv_pipeline_status,
    ObjectType,
)


router = APIRouter(prefix="/gewerke", tags=["gewerke"])


# =============================================================================
# Door Gewerk Models
# =============================================================================


class DoorGewerkItemResponse(BaseModel):
    """Response model for a single door item."""
    item_id: str
    position: Optional[str] = None
    door_number: Optional[str] = None
    room: Optional[str] = None
    door_type: Optional[str] = None
    fire_rating: Optional[str] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    remarks: Optional[str] = None
    category: str
    source_page: int
    source_row_index: int
    confidence: float


class DoorGewerkSummaryResponse(BaseModel):
    """Response model for door gewerk summary."""
    total_doors: int
    count_t30: int
    count_t90: int
    count_dss: int
    count_standard: int
    count_unknown: int
    by_type: Dict[str, int]
    by_fire_rating: Dict[str, int]
    by_category: Dict[str, int]
    unique_widths: List[float]
    unique_heights: List[float]


class DoorGewerkResponse(BaseModel):
    """Response model for the door gewerk endpoint."""
    gewerk_id: str
    gewerk_type: str = "doors"
    source_file: str
    extraction_id: str
    processed_at: str
    status: str
    items: List[DoorGewerkItemResponse]
    summary: DoorGewerkSummaryResponse
    errors: List[str]
    warnings: List[str]


# =============================================================================
# Drywall Gewerk Models
# =============================================================================


class DrywallSectorRequest(BaseModel):
    """Request model for drywall sector calculation."""
    file_id: str = Field(..., description="UUID of the file in storage")
    sector_id: str = Field(..., description="UUID of the sector to calculate")
    wall_height_m: float = Field(..., gt=0, description="Wall height in meters")
    pdf_path: Optional[str] = Field(
        None,
        description="Optional direct path to PDF (for testing without storage)",
    )
    render_dpi: int = Field(150, ge=72, le=300, description="DPI for PDF rendering")


class DrywallGewerkItemResponse(BaseModel):
    """Response model for a single drywall measurement."""
    item_id: str
    sector_id: str
    sector_name: str
    page_number: int
    wall_length_m: float
    wall_height_m: float
    drywall_area_m2: float
    wall_segment_count: int
    measurement_ids: List[str]
    scale_context_id: Optional[str]
    confidence: float
    assumptions: List[str]


class DrywallGewerkSummaryResponse(BaseModel):
    """Response model for drywall gewerk summary."""
    total_sectors: int
    total_wall_length_m: float
    total_drywall_area_m2: float
    average_wall_height_m: float


class DrywallGewerkResponse(BaseModel):
    """Response model for the drywall gewerk endpoint."""
    gewerk_id: str
    gewerk_type: str = "drywall"
    source_file: str
    processed_at: str
    status: str
    items: List[DrywallGewerkItemResponse]
    summary: DrywallGewerkSummaryResponse
    errors: List[str]
    warnings: List[str]


# =============================================================================
# Health Endpoint
# =============================================================================


class GewerkHealthResponse(BaseModel):
    """Health check response for gewerke service."""
    status: str
    service: str
    available_gewerke: List[str]


@router.get("/health", response_model=GewerkHealthResponse)
async def health_check():
    """
    Check if the gewerke service is healthy.

    Returns list of available trade modules.
    """
    settings = get_settings()
    available = ["doors", "flooring", "drywall"]

    # Add door_geometry if enabled
    if settings.door_geometry_extraction_enabled:
        available.append("door_geometry")

    return GewerkHealthResponse(
        status="ok",
        service="gewerke",
        available_gewerke=available,
    )


# =============================================================================
# Door Gewerk Endpoints
# =============================================================================


@router.post("/doors/from-schedule", response_model=DoorGewerkResponse)
async def process_door_schedule(
    file: UploadFile = File(..., description="Door schedule PDF file"),
    include_raw_data: bool = Query(
        False,
        description="Include raw extraction data in response (verbose)",
    ),
):
    """
    Process a door schedule PDF and return structured door list.

    This endpoint:
    1. Uploads the door schedule PDF
    2. Extracts tables using pdfplumber
    3. Normalizes German headers to standard field names
    4. Classifies each door by category (T30, T90, DSS, Standard)
    5. Returns structured list with summary statistics

    **Expected PDF Format:**
    - German door schedules (Türlisten)
    - Tables with columns like: Pos, Türnummer, Typ, BS, B[m], H[m], Bemerkung

    **Returns:**
    - items: List of normalized door entries
    - summary: Counts by category, unique dimensions
    """
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

        # Extract schedules from PDF
        extraction_result = extract_schedules_from_pdf(str(temp_path))

        # Run door gewerk
        gewerk_result = run_door_gewerk_from_schedule(extraction_result)

        # Build response items
        items = []
        for item in gewerk_result.items:
            items.append(DoorGewerkItemResponse(
                item_id=item.item_id,
                position=item.position,
                door_number=item.door_number,
                room=item.room,
                door_type=item.door_type,
                fire_rating=item.fire_rating,
                width_m=item.width_m,
                height_m=item.height_m,
                remarks=item.remarks,
                category=item.category.value,
                source_page=item.source_page,
                source_row_index=item.source_row_index,
                confidence=item.confidence,
            ))

        # Build summary response
        summary = DoorGewerkSummaryResponse(
            total_doors=gewerk_result.summary.total_doors,
            count_t30=gewerk_result.summary.count_t30,
            count_t90=gewerk_result.summary.count_t90,
            count_dss=gewerk_result.summary.count_dss,
            count_standard=gewerk_result.summary.count_standard,
            count_unknown=gewerk_result.summary.count_unknown,
            by_type=gewerk_result.summary.by_type,
            by_fire_rating=gewerk_result.summary.by_fire_rating,
            by_category=gewerk_result.summary.by_category,
            unique_widths=gewerk_result.summary.unique_widths,
            unique_heights=gewerk_result.summary.unique_heights,
        )

        return DoorGewerkResponse(
            gewerk_id=gewerk_result.gewerk_id,
            gewerk_type=gewerk_result.gewerk_type,
            source_file=file.filename,
            extraction_id=gewerk_result.extraction_id,
            processed_at=gewerk_result.processed_at,
            status=gewerk_result.status,
            items=items,
            summary=summary,
            errors=gewerk_result.errors,
            warnings=gewerk_result.warnings,
        )

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Floor Plan Door Detection (Vector-based)
# =============================================================================


class DetectedDoorResponse(BaseModel):
    """Response model for a single detected door from floor plan."""
    door_id: str
    door_label: Optional[str] = None  # e.g., "B.03.1.001-1"
    page_number: int
    width_m: Optional[float] = None
    arc_radius_px: Optional[float] = None
    fire_rating: Optional[str] = None  # e.g., "T 90-RS", "T 30-RS", None
    fire_category: Optional[str] = None  # "T90", "T30", "DSS", "Standard"
    confidence: float
    detection_method: str = "arc_pattern"


class FireRatingSummary(BaseModel):
    """Summary of fire-rated doors."""
    total_fire_rated: int
    count_t90: int
    count_t30: int
    count_dss: int
    count_standard: int
    t90_doors: List[str] = []  # List of door labels
    t30_doors: List[str] = []  # List of door labels


class FloorPlanDoorsResponse(BaseModel):
    """Response model for floor plan door detection."""
    gewerk_id: str
    gewerk_type: str = "doors_floorplan"
    source_file: str
    page_number: int
    scale_used: str
    total_doors: int
    doors: List[DetectedDoorResponse]
    by_width: Dict[str, int]
    by_fire_rating: FireRatingSummary
    detection_methods_used: List[str]
    processing_time_ms: int
    warnings: List[str]


def extract_door_labels_and_fire_ratings(pdf_path: str, page_number: int) -> Dict[str, Dict]:
    """
    Extract door labels and fire ratings from PDF text.

    The PDF format is typically:
        B.06.1.001-1    <- door label
        T 30-RS         <- fire rating for the door ABOVE
        B.06.1.002-1    <- next door label
        -               <- dash means NO fire rating

    Returns a dict mapping door labels to their fire ratings.
    E.g., {"B.03.1.001-1": {"fire_rating": "T 90-RS", "category": "T90"}, ...}
    """
    import fitz
    import re

    result = {}

    try:
        doc = fitz.open(pdf_path)
        if page_number > len(doc):
            doc.close()
            return result

        page = doc[page_number - 1]
        text = page.get_text()
        doc.close()

        # Find all door labels (B.XX.X.XXX-X format)
        door_label_pattern = r'(B\.\d{2}\.\d\.\d{3}-\d+)'
        door_labels = re.findall(door_label_pattern, text)

        # Initialize all doors as standard
        for label in set(door_labels):
            result[label] = {"fire_rating": None, "category": "Standard"}

        # Parse line by line - fire rating applies to the PREVIOUS door label
        lines = text.split('\n')
        last_door_label = None

        for line in lines:
            line_stripped = line.strip()

            # Check if this line is a door label
            door_match = re.match(door_label_pattern, line_stripped)
            if door_match:
                last_door_label = door_match.group(1)
                continue

            # Check if this line is a fire rating (only if we have a previous door)
            if last_door_label and last_door_label in result:
                # T90 fire rating
                if re.match(r'^T\s*90[-\s]?RS$|^T\s*90$', line_stripped, re.IGNORECASE):
                    result[last_door_label] = {"fire_rating": "T 90-RS", "category": "T90"}
                    last_door_label = None  # Reset - don't apply to next door
                    continue

                # T30 fire rating
                if re.match(r'^T\s*30[-\s]?RS$|^T\s*30$', line_stripped, re.IGNORECASE):
                    result[last_door_label] = {"fire_rating": "T 30-RS", "category": "T30"}
                    last_door_label = None
                    continue

                # DSS (smoke protection)
                if re.match(r'^DSS$', line_stripped, re.IGNORECASE):
                    result[last_door_label] = {"fire_rating": "DSS", "category": "DSS"}
                    last_door_label = None
                    continue

                # Dash or empty means no fire rating - keep as standard
                if line_stripped in ['-', '--', '---', '']:
                    last_door_label = None
                    continue

    except Exception as e:
        # Log but don't fail - fire rating is supplementary
        print(f"Warning: Could not extract fire ratings: {e}")

    return result


@router.post("/doors/from-plan", response_model=FloorPlanDoorsResponse)
async def detect_doors_from_plan(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    scale: int = Query(100, gt=0, description="Scale denominator (e.g., 100 for 1:100)"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
    use_yolo: bool = Query(True, description="Use YOLO CV detection (hybrid mode - combines with vector)"),
    use_vector: bool = Query(True, description="Use vector-based arc detection"),
    yolo_confidence: float = Query(0.15, ge=0.05, le=1.0, description="YOLO confidence threshold"),
):
    """
    Detect doors from a floor plan PDF using HYBRID detection.

    This endpoint combines two detection methods for best results:

    **1. Vector Detection (precise for CAD exports):**
    - Extracts vector paths (lines, curves) from the PDF
    - Identifies quarter-circle arcs (door swing indicators)
    - Matches arcs with nearby lines of similar length (door leaves)
    - Very precise for clean CAD-exported PDFs

    **2. YOLO CV Detection (catches non-standard symbols):**
    - Renders PDF page to image
    - Runs YOLOv8 object detection model trained on floor plans
    - Catches doors that may not have standard arc symbols

    **3. Fire Rating Extraction:**
    - Extracts door labels (B.XX.X.XXX-X format) from PDF text
    - Identifies fire ratings (T 90-RS, T 30-RS, DSS) near labels
    - Associates fire ratings with detected doors

    Results from both methods are merged, with duplicates removed.

    **Parameters:**
    - file: Floor plan PDF
    - scale: Drawing scale (e.g., 100 for 1:100)
    - page_number: Which page to analyze
    - use_yolo: Enable YOLO detection (default: true)
    - use_vector: Enable vector detection (default: true)
    - yolo_confidence: Minimum confidence for YOLO detections

    **Returns:**
    - total_doors: Number of doors detected
    - doors: List of detected doors with measurements and fire ratings
    - by_width: Count of doors grouped by width
    - by_fire_rating: Summary of fire-rated doors (T90, T30, DSS counts)
    - detection_methods_used: Which methods were used
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Save to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        settings = get_settings()
        render_dpi = 150

        # Run hybrid detection
        detection_result = detect_doors_hybrid(
            pdf_path=str(temp_path),
            page_number=page_number,
            scale=scale,
            dpi=render_dpi,
            use_yolo=use_yolo,
            use_vector=use_vector,
            confidence_threshold=yolo_confidence,
            settings=settings,
        )

        # Extract door labels and fire ratings from PDF text
        door_fire_ratings = extract_door_labels_and_fire_ratings(str(temp_path), page_number)

        # Build response
        door_responses = []
        width_counts: Dict[str, int] = {}
        methods_used = set()

        # Fire rating counters
        fire_rating_counts = {"T90": 0, "T30": 0, "DSS": 0, "Standard": 0}
        t90_door_labels = []
        t30_door_labels = []

        # First, add doors from text extraction (with fire ratings)
        for label, info in door_fire_ratings.items():
            door_responses.append(DetectedDoorResponse(
                door_id=f"text_{label}",
                door_label=label,
                page_number=page_number,
                width_m=None,  # Will be matched with vector detection if available
                arc_radius_px=None,
                fire_rating=info.get("fire_rating"),
                fire_category=info.get("category", "Standard"),
                confidence=0.95,
                detection_method="text_extraction",
            ))

            category = info.get("category", "Standard")
            fire_rating_counts[category] = fire_rating_counts.get(category, 0) + 1

            if category == "T90":
                t90_door_labels.append(label)
            elif category == "T30":
                t30_door_labels.append(label)

        methods_used.add("text_extraction")

        # Also add vector-detected doors (for width measurements)
        vector_door_count = 0
        for obj in detection_result.objects:
            if obj.object_type != ObjectType.DOOR:
                continue

            method = obj.attributes.get("detection_method", "unknown")
            methods_used.add(method)

            width_m = obj.attributes.get("width_m")
            arc_radius_px = obj.attributes.get("arc_radius_px")
            vector_door_count += 1

            # Group by width (rounded to nearest 10cm)
            if width_m:
                width_key = f"{round(width_m * 10) / 10:.1f}"
                width_counts[width_key] = width_counts.get(width_key, 0) + 1

        warnings = list(detection_result.warnings)

        # Use text-extracted count as primary (includes fire ratings)
        # Fall back to vector count if no labels found
        total_doors = len(door_fire_ratings) if door_fire_ratings else vector_door_count

        # If we have vector doors but no text labels, use vector results
        if not door_fire_ratings and vector_door_count > 0:
            door_responses = []
            for obj in detection_result.objects:
                if obj.object_type != ObjectType.DOOR:
                    continue
                method = obj.attributes.get("detection_method", "unknown")
                width_m = obj.attributes.get("width_m")
                arc_radius_px = obj.attributes.get("arc_radius_px")
                door_responses.append(DetectedDoorResponse(
                    door_id=obj.object_id,
                    door_label=None,
                    page_number=obj.page_number,
                    width_m=round(width_m, 2) if width_m else None,
                    arc_radius_px=round(arc_radius_px, 1) if arc_radius_px else None,
                    fire_rating=None,
                    fire_category="Standard",
                    confidence=obj.confidence,
                    detection_method=method,
                ))
            fire_rating_counts = {"T90": 0, "T30": 0, "DSS": 0, "Standard": vector_door_count}

        if len(door_responses) == 0:
            warnings.append("No door symbols detected. Ensure the PDF contains vector graphics (CAD export), not raster images.")

        # Check for unusual widths
        for door in door_responses:
            if door.width_m and (door.width_m < 0.5 or door.width_m > 2.5):
                if "unusual_widths" not in [w.split(":")[0] for w in warnings]:
                    warnings.append("unusual_widths: Some doors have unusual widths (<0.5m or >2.5m). Check scale setting.")
                break

        # Report on detection methods
        if use_yolo and not is_yolo_available(settings):
            warnings.append("YOLO detection requested but not available. Set SNAPGRID_YOLO_MODEL_PATH to enable.")

        # Build fire rating summary
        fire_rating_summary = FireRatingSummary(
            total_fire_rated=fire_rating_counts.get("T90", 0) + fire_rating_counts.get("T30", 0) + fire_rating_counts.get("DSS", 0),
            count_t90=fire_rating_counts.get("T90", 0),
            count_t30=fire_rating_counts.get("T30", 0),
            count_dss=fire_rating_counts.get("DSS", 0),
            count_standard=fire_rating_counts.get("Standard", 0),
            t90_doors=t90_door_labels,
            t30_doors=t30_door_labels,
        )

        return FloorPlanDoorsResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            source_file=file.filename,
            page_number=page_number,
            scale_used=f"1:{scale}",
            total_doors=total_doors,
            doors=door_responses,
            by_width=width_counts,
            by_fire_rating=fire_rating_summary,
            detection_methods_used=list(methods_used),
            processing_time_ms=detection_result.processing_time_ms,
            warnings=warnings,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Drywall Gewerk Endpoints
# =============================================================================


@router.post("/drywall/from-plan", response_model=DrywallGewerkResponse)
async def calculate_drywall_from_plan(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    wall_height_m: float = Query(2.6, gt=0, description="Wall height in meters"),
    scale: int = Query(100, gt=0, description="Scale denominator (e.g., 100 for 1:100)"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
):
    """
    Upload a floor plan PDF and calculate drywall area.

    This endpoint uses **room perimeter data** (U values from room annotations)
    to calculate wall length, then multiplies by wall height for drywall area.

    Formula: Drywall Area = Total Room Perimeter × Wall Height

    This is more accurate than vector extraction because:
    - Room perimeters (U values) are explicitly annotated in the PDF
    - Vector extraction picks up ALL lines (furniture, text, etc.)

    **Note**: This returns single-sided wall area. For both sides, multiply by 2.
    """
    import fitz  # PyMuPDF
    import re
    from datetime import datetime
    from uuid import uuid4

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Save to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        doc = fitz.open(str(temp_path))
        if page_number > len(doc):
            raise HTTPException(status_code=400, detail=f"Page {page_number} not found, PDF has {len(doc)} pages")

        page = doc[page_number - 1]
        text = page.get_text()
        doc.close()

        # Extract perimeter (U) values from room annotations
        # Pattern: "U:" followed by a number (possibly on next line)
        lines = text.split('\n')
        total_perimeter_m = 0.0
        room_count = 0
        warnings = []

        room_id_pattern = r'^(B\.\d{2}\.\d\.\d{3})$'
        u_same_line = r'U\s*[=:]?\s*([\d,\.]+)\s*m(?![²2])'
        u_split_value = r'^([\d,\.]+)\s*m$'

        expecting_u_value = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Handle split U: value on next line
            if expecting_u_value:
                val_match = re.match(u_split_value, line_stripped)
                if val_match:
                    u_value = float(val_match.group(1).replace(',', '.'))
                    total_perimeter_m += u_value
                    room_count += 1
                expecting_u_value = False
                continue

            # Check for "U:" alone (value on next line)
            if line_stripped == 'U:':
                expecting_u_value = True
                continue

            # Extract U (same line format like "U: 42.50 m")
            u_match = re.search(u_same_line, line_stripped, re.IGNORECASE)
            if u_match:
                u_value = float(u_match.group(1).replace(',', '.'))
                total_perimeter_m += u_value
                room_count += 1

        # Calculate drywall area
        drywall_area_m2 = total_perimeter_m * wall_height_m

        if room_count == 0:
            warnings.append("No room perimeter (U) values found in PDF. Ensure PDF contains room annotations with U values.")

        # Build response
        gewerk_id = f"gew_{uuid4().hex[:12]}"
        item_id = f"drywall_{uuid4().hex[:8]}"

        items = [DrywallGewerkItemResponse(
            item_id=item_id,
            sector_id="full_page",
            sector_name="Full Page",
            page_number=page_number,
            wall_length_m=round(total_perimeter_m, 2),
            wall_height_m=wall_height_m,
            drywall_area_m2=round(drywall_area_m2, 2),
            wall_segment_count=room_count,
            measurement_ids=[item_id],
            scale_context_id=None,
            confidence=0.95 if room_count > 0 else 0.0,
            assumptions=[
                "Drywall area = Total room perimeter × Wall height",
                "Perimeter values extracted from room annotations (U values)",
                "Single-sided wall area (multiply by 2 for both sides)",
                f"Rooms with perimeter data: {room_count}",
            ],
        )]

        summary = DrywallGewerkSummaryResponse(
            total_sectors=1,
            total_wall_length_m=round(total_perimeter_m, 2),
            total_drywall_area_m2=round(drywall_area_m2, 2),
            average_wall_height_m=wall_height_m,
        )

        return DrywallGewerkResponse(
            gewerk_id=gewerk_id,
            gewerk_type="drywall",
            source_file=file.filename,
            processed_at=datetime.utcnow().isoformat() + "Z",
            status="ok" if room_count > 0 else "warning",
            items=items,
            summary=summary,
            errors=[],
            warnings=warnings,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Flooring Gewerk Endpoints
# =============================================================================


class RoomDataResponse(BaseModel):
    """Response model for a single room's data."""
    room_id: str
    room_name: Optional[str] = None
    room_type: Optional[str] = None
    area_m2: Optional[float] = None
    perimeter_m: Optional[float] = None
    ceiling_height_m: Optional[float] = None
    page_number: int
    confidence: float


class FlooringGewerkResponse(BaseModel):
    """Response model for flooring extraction from floor plans."""
    gewerk_id: str
    gewerk_type: str = "flooring"
    source_file: str
    page_number: int
    total_rooms: int
    total_area_m2: float
    rooms: List[RoomDataResponse]
    by_room_type: Dict[str, float]  # area by type
    processing_time_ms: int
    warnings: List[str]


@router.post("/flooring/from-plan", response_model=FlooringGewerkResponse)
async def extract_flooring_from_plan(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
):
    """
    Extract room/flooring data from a floor plan PDF.

    This endpoint reads German architectural floor plans and extracts:
    - Room IDs (e.g., B.03.1.001)
    - Room names/types (e.g., TRH B1, Nutzungseinheit, Balkon, WC)
    - NRF (Netto-Raumfläche) - Net room area in m²
    - U (Umfang) - Perimeter in meters
    - LH (Lichte Höhe) - Ceiling height in meters

    **Works best with:**
    - German architectural CAD exports
    - Plans with room stamps containing NRF/U/LH values
    - PDF text annotations (not scanned images)
    """
    import fitz
    import re
    import time
    from uuid import uuid4

    start_time = time.time()

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Save to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        doc = fitz.open(str(temp_path))
        if page_number > len(doc):
            raise HTTPException(
                status_code=400,
                detail=f"Page {page_number} not found, PDF has {len(doc)} pages"
            )

        page = doc[page_number - 1]
        text = page.get_text()
        doc.close()

        # Extract room data from text annotations
        rooms = []
        warnings = []
        seen_room_ids = set()

        # Split into lines for line-by-line parsing
        lines = text.split('\n')

        # Pattern for room IDs (without door suffix like -1, -2)
        room_id_pattern = r'^(B\.\d{2}\.\d\.\d{3})$'

        # Patterns - handle both formats:
        # 1. "NRF: 42,18 m2" (value on same line)
        # 2. "NRF:" followed by "267,30 m2" (value on next line)
        nrf_same_line = r'NRF\s*[=:]?\s*([\d,\.]+)\s*m[²2]?'
        nrf_split_value = r'^([\d,\.]+)\s*m[²2]?$'
        u_same_line = r'U\s*[=:]?\s*([\d,\.]+)\s*m(?![²2])'
        u_split_value = r'^([\d,\.]+)\s*m$'
        lh_same_line = r'LH\s*[=:]?\s*([\d,\.]+)\s*m'

        # First pass: find room IDs and their associated data in subsequent lines
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check if this line is a room ID (without door suffix)
            room_match = re.match(room_id_pattern, line)
            if room_match:
                room_id = room_match.group(1)

                # Skip if we've already seen this room
                if room_id in seen_room_ids:
                    i += 1
                    continue

                # Look ahead for room name and measurements
                room_name = None
                nrf_value = None
                u_value = None
                lh_value = None
                expecting_nrf_value = False
                expecting_u_value = False

                # Check next 15 lines for associated data
                for j in range(i + 1, min(i + 15, len(lines))):
                    next_line = lines[j].strip()

                    # Stop if we hit another room ID
                    if re.match(room_id_pattern, next_line):
                        break

                    # Handle split NRF: value on next line
                    if expecting_nrf_value:
                        val_match = re.match(nrf_split_value, next_line)
                        if val_match:
                            nrf_value = float(val_match.group(1).replace(',', '.'))
                        expecting_nrf_value = False
                        continue

                    # Handle split U: value on next line
                    if expecting_u_value:
                        val_match = re.match(u_split_value, next_line)
                        if val_match:
                            u_value = float(val_match.group(1).replace(',', '.'))
                        expecting_u_value = False
                        continue

                    # Check for "NRF:" alone (value on next line)
                    if next_line == 'NRF:' and nrf_value is None:
                        expecting_nrf_value = True
                        continue

                    # Check for "U:" alone (value on next line)
                    if next_line == 'U:' and u_value is None:
                        expecting_u_value = True
                        continue

                    # Extract room name (first meaningful word)
                    if not room_name and not next_line.startswith(('NRF', 'U:', 'LH', 'U ', 'm²', 'm2')):
                        name_match = re.match(r'^([A-Za-zÄÖÜäöüß\-]+(?:\s+[A-Za-zÄÖÜäöüß0-9\-]+)?)', next_line)
                        if name_match and len(name_match.group(1)) > 1 and not re.match(r'^[\d,\.]+', next_line):
                            room_name = name_match.group(1)

                    # Extract NRF (same line format)
                    if nrf_value is None:
                        nrf_match = re.search(nrf_same_line, next_line, re.IGNORECASE)
                        if nrf_match:
                            nrf_value = float(nrf_match.group(1).replace(',', '.'))

                    # Extract U (same line format)
                    if u_value is None:
                        u_match = re.search(u_same_line, next_line, re.IGNORECASE)
                        if u_match:
                            u_value = float(u_match.group(1).replace(',', '.'))

                    # Extract LH (ceiling height)
                    if lh_value is None:
                        lh_match = re.search(lh_same_line, next_line, re.IGNORECASE)
                        if lh_match:
                            lh_value = float(lh_match.group(1).replace(',', '.'))

                # Only add if we found an area
                if nrf_value is not None:
                    seen_room_ids.add(room_id)
                    rooms.append(RoomDataResponse(
                        room_id=room_id,
                        room_name=room_name,
                        room_type=_classify_room_type(room_name) if room_name else None,
                        area_m2=nrf_value,
                        perimeter_m=u_value,
                        ceiling_height_m=lh_value,
                        page_number=page_number,
                        confidence=0.95,
                    ))

            i += 1

        # Calculate totals
        total_area = sum(r.area_m2 for r in rooms if r.area_m2)

        # Group by room type
        by_type: Dict[str, float] = {}
        for room in rooms:
            room_type = room.room_type or "Unknown"
            by_type[room_type] = by_type.get(room_type, 0) + (room.area_m2 or 0)

        if not rooms:
            warnings.append("No room data found. Ensure PDF contains text annotations with NRF values (not scanned images).")

        processing_time = int((time.time() - start_time) * 1000)

        return FlooringGewerkResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            source_file=file.filename,
            page_number=page_number,
            total_rooms=len(rooms),
            total_area_m2=round(total_area, 2),
            rooms=rooms,
            by_room_type=by_type,
            processing_time_ms=processing_time,
            warnings=warnings,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _classify_room_type(room_name: Optional[str]) -> Optional[str]:
    """Classify room by name into standard types."""
    if not room_name:
        return None

    name_lower = room_name.lower()

    if 'trh' in name_lower or 'treppenhaus' in name_lower:
        return 'Stairwell'
    elif 'balkon' in name_lower:
        return 'Balcony'
    elif 'wc' in name_lower or 'toilette' in name_lower:
        return 'WC'
    elif 'flur' in name_lower or 'gang' in name_lower:
        return 'Corridor'
    elif 'nutzungseinheit' in name_lower:
        return 'Unit'
    elif 'büro' in name_lower or 'office' in name_lower:
        return 'Office'
    elif 'lager' in name_lower:
        return 'Storage'
    elif 'technik' in name_lower:
        return 'Technical'
    else:
        return room_name


@router.post("/drywall/sector", response_model=DrywallGewerkResponse)
async def calculate_drywall_for_sector(request: DrywallSectorRequest):
    """
    Calculate drywall area for a sector.

    This endpoint:
    1. Loads the ScaleContext for the file
    2. Loads the Sector by sector_id
    3. Extracts wall segments from the PDF using vector geometry
    4. Computes wall length in meters for segments inside the sector
    5. Computes drywall area = wall_length * wall_height

    **Requirements:**
    - The file must have an active scale context (detected or calibrated)
    - A sector must be defined for the file/page
    - PDF file must be accessible

    **Returns:**
    - items: Drywall measurement for the sector
    - summary: Total wall length and drywall area
    """
    settings = get_settings()

    # Get scale context
    scale_context = get_scale_context(file_id=request.file_id, settings=settings)
    if scale_context is None or not scale_context.has_scale:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_scale_context",
                "message": "No active scale context found for file. Please detect or calibrate scale first.",
            },
        )

    # Get sector
    sector = get_sector(sector_id=request.sector_id, settings=settings)
    if sector is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sector not found: {request.sector_id}",
        )

    # Determine PDF path
    pdf_path = request.pdf_path
    if not pdf_path:
        # TODO: Look up file path from storage
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_pdf_path",
                "message": "pdf_path is required (storage lookup not yet implemented)",
            },
        )

    # Validate PDF exists
    if not Path(pdf_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found: {pdf_path}",
        )

    # Run drywall gewerk
    gewerk_result = run_drywall_gewerk_for_sector(
        pdf_path=pdf_path,
        sector=sector,
        scale_context=scale_context,
        wall_height_m=request.wall_height_m,
        render_dpi=request.render_dpi,
    )

    # Check for errors
    if gewerk_result.status == "error":
        raise HTTPException(
            status_code=500,
            detail={
                "error": "calculation_failed",
                "errors": gewerk_result.errors,
            },
        )

    # Build response items
    items = []
    for item in gewerk_result.items:
        items.append(DrywallGewerkItemResponse(
            item_id=item.item_id,
            sector_id=item.sector_id,
            sector_name=item.sector_name,
            page_number=item.page_number,
            wall_length_m=item.wall_length_m,
            wall_height_m=item.wall_height_m,
            drywall_area_m2=item.drywall_area_m2,
            wall_segment_count=item.wall_segment_count,
            measurement_ids=item.measurement_ids,
            scale_context_id=item.scale_context_id,
            confidence=item.confidence,
            assumptions=item.assumptions,
        ))

    # Build summary response
    summary = DrywallGewerkSummaryResponse(
        total_sectors=gewerk_result.summary.total_sectors,
        total_wall_length_m=gewerk_result.summary.total_wall_length_m,
        total_drywall_area_m2=gewerk_result.summary.total_drywall_area_m2,
        average_wall_height_m=gewerk_result.summary.average_wall_height_m,
    )

    return DrywallGewerkResponse(
        gewerk_id=gewerk_result.gewerk_id,
        gewerk_type=gewerk_result.gewerk_type,
        source_file=gewerk_result.source_file,
        processed_at=gewerk_result.processed_at,
        status=gewerk_result.status,
        items=items,
        summary=summary,
        errors=gewerk_result.errors,
        warnings=gewerk_result.warnings,
    )


# =============================================================================
# Smart Endpoints (Auto-routing with CV Fallback)
# =============================================================================


class SmartFlooringResponse(BaseModel):
    """Response model for smart flooring extraction."""
    gewerk_id: str
    gewerk_type: str = "flooring"
    source_file: str
    page_number: int
    pipeline_used: str
    input_type: str
    total_rooms: int
    total_area_m2: float
    rooms: List[RoomDataResponse]
    by_room_type: Dict[str, float]
    processing_time_ms: int
    warnings: List[str]


class SmartDrywallResponse(BaseModel):
    """Response model for smart drywall calculation."""
    gewerk_id: str
    gewerk_type: str = "drywall"
    source_file: str
    page_number: int
    pipeline_used: str
    input_type: str
    total_wall_length_m: float
    wall_height_m: float
    total_drywall_area_m2: float
    processing_time_ms: int
    warnings: List[str]


@router.post("/flooring/smart", response_model=SmartFlooringResponse)
async def extract_flooring_smart(
    file: UploadFile = File(..., description="Floor plan PDF or image"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
    scale: int = Query(100, gt=0, description="Scale denominator (e.g., 100 for 1:100)"),
):
    """
    Smart flooring extraction with automatic pipeline selection.

    This endpoint automatically detects the input type and routes to the best pipeline:

    1. **German CAD PDF with annotations** → Text extraction (NRF values)
    2. **CAD PDF without annotations** → Hybrid (vector + CV)
    3. **Scanned PDF / Photo** → Roboflow CV (room segmentation)

    **Best for:**
    - Universal blueprint support (any input type)
    - Automatic fallback when text extraction fails

    **Returns:**
    - Room areas (m²)
    - Pipeline used for extraction
    - Input type detected
    """
    import time
    from datetime import datetime
    from ..services.input_router import analyze_input, InputType, ProcessingPipeline
    from ..services.roboflow_service import detect_rooms, is_roboflow_available

    start_time = time.time()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        settings = get_settings()

        # Analyze input type
        analysis = analyze_input(str(temp_path))
        warnings = list(analysis.warnings)

        rooms = []
        total_area_m2 = 0.0
        by_type: Dict[str, float] = {}
        pipeline_used = "unknown"

        # Route based on input type
        if analysis.input_type == InputType.CAD_WITH_TEXT:
            # Use text extraction (existing implementation)
            pipeline_used = "text_extraction"

            import fitz
            doc = fitz.open(str(temp_path))
            if page_number > len(doc):
                raise HTTPException(
                    status_code=400,
                    detail=f"Page {page_number} not found, PDF has {len(doc)} pages"
                )

            page = doc[page_number - 1]
            text = page.get_text()
            doc.close()

            # Extract room data (same logic as extract_flooring_from_plan)
            lines = text.split('\n')
            seen_room_ids = set()
            room_id_pattern = r'^(B\.\d{2}\.\d\.\d{3})$'
            nrf_same_line = r'NRF\s*[=:]?\s*([\d,\.]+)\s*m[²2]?'
            nrf_split_value = r'^([\d,\.]+)\s*m[²2]?$'
            u_same_line = r'U\s*[=:]?\s*([\d,\.]+)\s*m(?![²2])'
            u_split_value = r'^([\d,\.]+)\s*m$'
            lh_same_line = r'LH\s*[=:]?\s*([\d,\.]+)\s*m'

            i = 0
            while i < len(lines):
                line = lines[i].strip()
                room_match = re.match(room_id_pattern, line)
                if room_match:
                    room_id = room_match.group(1)
                    if room_id in seen_room_ids:
                        i += 1
                        continue

                    room_name = None
                    nrf_value = None
                    u_value = None
                    lh_value = None
                    expecting_nrf_value = False
                    expecting_u_value = False

                    for j in range(i + 1, min(i + 15, len(lines))):
                        next_line = lines[j].strip()
                        if re.match(room_id_pattern, next_line):
                            break

                        if expecting_nrf_value:
                            val_match = re.match(nrf_split_value, next_line)
                            if val_match:
                                nrf_value = float(val_match.group(1).replace(',', '.'))
                            expecting_nrf_value = False
                            continue

                        if expecting_u_value:
                            val_match = re.match(u_split_value, next_line)
                            if val_match:
                                u_value = float(val_match.group(1).replace(',', '.'))
                            expecting_u_value = False
                            continue

                        if next_line == 'NRF:' and nrf_value is None:
                            expecting_nrf_value = True
                            continue

                        if next_line == 'U:' and u_value is None:
                            expecting_u_value = True
                            continue

                        if not room_name and not next_line.startswith(('NRF', 'U:', 'LH', 'U ', 'm²', 'm2')):
                            name_match = re.match(r'^([A-Za-zÄÖÜäöüß\-]+(?:\s+[A-Za-zÄÖÜäöüß0-9\-]+)?)', next_line)
                            if name_match and len(name_match.group(1)) > 1 and not re.match(r'^[\d,\.]+', next_line):
                                room_name = name_match.group(1)

                        if nrf_value is None:
                            nrf_match = re.search(nrf_same_line, next_line, re.IGNORECASE)
                            if nrf_match:
                                nrf_value = float(nrf_match.group(1).replace(',', '.'))

                        if u_value is None:
                            u_match = re.search(u_same_line, next_line, re.IGNORECASE)
                            if u_match:
                                u_value = float(u_match.group(1).replace(',', '.'))

                        if lh_value is None:
                            lh_match = re.search(lh_same_line, next_line, re.IGNORECASE)
                            if lh_match:
                                lh_value = float(lh_match.group(1).replace(',', '.'))

                    if nrf_value is not None:
                        seen_room_ids.add(room_id)
                        room_type = _classify_room_type(room_name) if room_name else None
                        rooms.append(RoomDataResponse(
                            room_id=room_id,
                            room_name=room_name,
                            room_type=room_type,
                            area_m2=nrf_value,
                            perimeter_m=u_value,
                            ceiling_height_m=lh_value,
                            page_number=page_number,
                            confidence=0.95,
                        ))

                        by_type[room_type or "Unknown"] = by_type.get(room_type or "Unknown", 0) + nrf_value

                i += 1

            total_area_m2 = sum(r.area_m2 for r in rooms if r.area_m2)

            if len(rooms) == 0:
                warnings.append("Text extraction found no rooms. Falling back to CV...")
                # Fall through to CV fallback
                analysis.input_type = InputType.SCANNED_PDF

        # CV fallback for scanned/photo/failed text extraction
        if analysis.input_type in [InputType.SCANNED_PDF, InputType.PHOTO, InputType.CAD_NO_TEXT] or len(rooms) == 0:
            if is_roboflow_available(settings):
                pipeline_used = "roboflow_cv"

                # Render PDF to image if needed
                suffix = temp_path.suffix.lower()
                if suffix == ".pdf":
                    from ..services.cv_pipeline import render_pdf_page_to_image
                    import os

                    image_path = render_pdf_page_to_image(str(temp_path), page_number, dpi=150)
                    try:
                        cv_result = detect_rooms(image_path, scale=scale, dpi=150, settings=settings)
                    finally:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                else:
                    cv_result = detect_rooms(str(temp_path), scale=scale, dpi=150, settings=settings)

                # Convert CV results to room responses
                rooms = []
                for idx, room_data in enumerate(cv_result.get("rooms", [])):
                    rooms.append(RoomDataResponse(
                        room_id=f"cv_room_{idx+1}",
                        room_name=room_data.get("class_name"),
                        room_type=room_data.get("class_name"),
                        area_m2=room_data.get("area_m2"),
                        perimeter_m=room_data.get("perimeter_m"),
                        ceiling_height_m=None,
                        page_number=page_number,
                        confidence=room_data.get("confidence", 0.7),
                    ))

                    room_type = room_data.get("class_name", "Unknown")
                    by_type[room_type] = by_type.get(room_type, 0) + room_data.get("area_m2", 0)

                total_area_m2 = cv_result.get("total_area_m2", 0)
                warnings.extend(cv_result.get("warnings", []))

            else:
                warnings.append("Roboflow not available. Configure SNAPGRID_ROBOFLOW_API_KEY for CV support.")
                pipeline_used = "none"

        processing_time = int((time.time() - start_time) * 1000)

        return SmartFlooringResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            source_file=file.filename,
            page_number=page_number,
            pipeline_used=pipeline_used,
            input_type=analysis.input_type.value,
            total_rooms=len(rooms),
            total_area_m2=round(total_area_m2, 2),
            rooms=rooms,
            by_room_type=by_type,
            processing_time_ms=processing_time,
            warnings=warnings,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/drywall/smart", response_model=SmartDrywallResponse)
async def calculate_drywall_smart(
    file: UploadFile = File(..., description="Floor plan PDF or image"),
    wall_height_m: float = Query(2.6, gt=0, description="Wall height in meters"),
    scale: int = Query(100, gt=0, description="Scale denominator (e.g., 100 for 1:100)"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
):
    """
    Smart drywall calculation with automatic pipeline selection.

    This endpoint automatically detects the input type and routes to the best pipeline:

    1. **German CAD PDF with annotations** → Text extraction (U/perimeter values)
    2. **CAD PDF without annotations** → Hybrid (vector + CV)
    3. **Scanned PDF / Photo** → Roboflow CV (wall segmentation)

    **Formula:** Drywall Area = Total Wall Perimeter × Wall Height

    **Returns:**
    - Wall perimeter (m)
    - Drywall area (m²)
    - Pipeline used for extraction
    """
    import time
    from datetime import datetime
    from ..services.input_router import analyze_input, InputType, ProcessingPipeline
    from ..services.roboflow_service import detect_walls, is_roboflow_available

    start_time = time.time()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        settings = get_settings()

        # Analyze input type
        analysis = analyze_input(str(temp_path))
        warnings = list(analysis.warnings)

        total_perimeter_m = 0.0
        pipeline_used = "unknown"

        # Route based on input type
        if analysis.input_type == InputType.CAD_WITH_TEXT:
            # Use text extraction (perimeter values)
            pipeline_used = "text_extraction"

            import fitz
            doc = fitz.open(str(temp_path))
            if page_number > len(doc):
                raise HTTPException(
                    status_code=400,
                    detail=f"Page {page_number} not found, PDF has {len(doc)} pages"
                )

            page = doc[page_number - 1]
            text = page.get_text()
            doc.close()

            # Extract perimeter (U) values
            lines = text.split('\n')
            room_count = 0
            u_same_line = r'U\s*[=:]?\s*([\d,\.]+)\s*m(?![²2])'
            u_split_value = r'^([\d,\.]+)\s*m$'
            expecting_u_value = False

            for i, line in enumerate(lines):
                line_stripped = line.strip()

                if expecting_u_value:
                    val_match = re.match(u_split_value, line_stripped)
                    if val_match:
                        u_value = float(val_match.group(1).replace(',', '.'))
                        total_perimeter_m += u_value
                        room_count += 1
                    expecting_u_value = False
                    continue

                if line_stripped == 'U:':
                    expecting_u_value = True
                    continue

                u_match = re.search(u_same_line, line_stripped, re.IGNORECASE)
                if u_match:
                    u_value = float(u_match.group(1).replace(',', '.'))
                    total_perimeter_m += u_value
                    room_count += 1

            if room_count == 0:
                warnings.append("Text extraction found no perimeter values. Falling back to CV...")
                analysis.input_type = InputType.SCANNED_PDF

        # CV fallback
        if analysis.input_type in [InputType.SCANNED_PDF, InputType.PHOTO, InputType.CAD_NO_TEXT] or total_perimeter_m == 0:
            if is_roboflow_available(settings):
                pipeline_used = "roboflow_cv"

                suffix = temp_path.suffix.lower()
                if suffix == ".pdf":
                    from ..services.cv_pipeline import render_pdf_page_to_image
                    import os

                    image_path = render_pdf_page_to_image(str(temp_path), page_number, dpi=150)
                    try:
                        cv_result = detect_walls(image_path, scale=scale, dpi=150, settings=settings)
                    finally:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                else:
                    cv_result = detect_walls(str(temp_path), scale=scale, dpi=150, settings=settings)

                total_perimeter_m = cv_result.get("total_perimeter_m", 0)
                warnings.extend(cv_result.get("warnings", []))

            else:
                warnings.append("Roboflow not available. Configure SNAPGRID_ROBOFLOW_API_KEY for CV support.")
                pipeline_used = "none"

        # Calculate drywall area
        drywall_area_m2 = total_perimeter_m * wall_height_m
        processing_time = int((time.time() - start_time) * 1000)

        return SmartDrywallResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            source_file=file.filename,
            page_number=page_number,
            pipeline_used=pipeline_used,
            input_type=analysis.input_type.value,
            total_wall_length_m=round(total_perimeter_m, 2),
            wall_height_m=wall_height_m,
            total_drywall_area_m2=round(drywall_area_m2, 2),
            processing_time_ms=processing_time,
            warnings=warnings,
        )

    finally:
        # Clean up temp files
        if temp_path.exists():
            temp_path.unlink()
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Geometry-First Flooring Pipeline
# =============================================================================


class GeometryFlooringRoomResponse(BaseModel):
    """Response model for a room detected by geometry pipeline."""
    id: str
    label: Optional[str] = None
    area_m2: Optional[float] = None
    area_px: float
    perimeter_m: Optional[float] = None
    perimeter_px: float
    confidence: float
    source: str
    vertex_count: int


class GeometryFlooringResponse(BaseModel):
    """Response model for geometry-first flooring extraction."""
    gewerk_id: str
    source_file: str
    page_number: int
    pipeline_used: str
    total_rooms: int
    total_area_m2: Optional[float] = None
    total_area_px: float
    scale_string: Optional[str] = None
    scale_detected: bool
    pixels_per_meter: Optional[float] = None
    rooms: List[GeometryFlooringRoomResponse]
    processing_time_ms: int
    needs_user_confirmation: bool
    confirmation_reason: Optional[str] = None
    warnings: List[str]


@router.post("/flooring/geometry", response_model=GeometryFlooringResponse)
async def extract_flooring_geometry(
    file: UploadFile = File(..., description="Floor plan PDF or image"),
    page_number: int = Query(1, gt=0, description="Page number to analyze"),
    scale: Optional[int] = Query(None, gt=0, description="Scale denominator (e.g., 50 for 1:50). If not provided, auto-detect."),
    dpi: int = Query(150, ge=72, le=600, description="Render DPI for processing"),
):
    """
    Geometry-first flooring extraction using OpenCV contour detection.

    This endpoint uses a deterministic, geometry-based approach:

    1. **Render** PDF page to image at specified DPI
    2. **Preprocess** with adaptive thresholding
    3. **Close gaps** in walls using morphological operations
    4. **Detect contours** representing enclosed room regions
    5. **Filter** by area, aspect ratio, and circularity
    6. **Convert** pixel areas to m² using detected/provided scale

    **When to use:**
    - When text extraction (NRF values) is not available
    - When Roboflow segmentation is unreliable
    - For any floor plan with clear wall boundaries

    **Scale Detection:**
    - Searches for "M 1:50", "Maßstab 1:100", etc. in page text
    - Falls back to user-provided scale if not found
    - Returns `needs_user_confirmation=true` if no scale available

    **Returns:**
    - List of detected room polygons with areas
    - Total floor area (m² if scale available, px otherwise)
    - Scale information and detection method
    """
    from ..services.flooring_pipeline import analyze_flooring, PipelineMethod

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Run geometry-first pipeline
        result = analyze_flooring(
            file_path=str(temp_path),
            page_number=page_number,
            scale=scale,
            dpi=dpi,
        )

        # Convert rooms to response format
        rooms = []
        for room in result.rooms:
            rooms.append(GeometryFlooringRoomResponse(
                id=room.id,
                label=room.label,
                area_m2=round(room.area_m2, 2) if room.area_m2 else None,
                area_px=round(room.area_px, 1),
                perimeter_m=round(room.perimeter_m, 2) if room.perimeter_m else None,
                perimeter_px=round(room.perimeter_px, 1),
                confidence=round(room.confidence, 2),
                source=room.source,
                vertex_count=len(room.points),
            ))

        # Build response
        return GeometryFlooringResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            source_file=file.filename,
            page_number=page_number,
            pipeline_used=result.pipeline_used.value,
            total_rooms=result.room_count,
            total_area_m2=round(result.total_area_m2, 2) if result.total_area_m2 else None,
            total_area_px=round(result.total_area_px, 1),
            scale_string=result.scale.scale_string if result.scale else None,
            scale_detected=result.scale.has_scale if result.scale else False,
            pixels_per_meter=round(result.scale.pixels_per_meter, 2) if result.scale and result.scale.pixels_per_meter else None,
            rooms=rooms,
            processing_time_ms=int(result.processing_time_ms),
            needs_user_confirmation=result.needs_user_confirmation,
            confirmation_reason=result.confirmation_reason,
            warnings=result.warnings,
        )

    finally:
        # Clean up temp files
        if temp_path.exists():
            temp_path.unlink()
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Room Area Extraction (NRF-based, Deterministic)
# =============================================================================


class RoomAreaItemResponse(BaseModel):
    """Response model for a single room with extracted NRF area."""
    room_id: str
    name: Optional[str] = None
    area_m2: float
    counted_m2: float
    factor: float
    page: int
    source_text: str
    bbox: Dict[str, float]
    room_type: str = "standard"
    name_source: Optional[Dict[str, Any]] = None
    factor_source: Optional[Dict[str, Any]] = None


class RoomAreaResponse(BaseModel):
    """Response model for room area extraction."""
    gewerk_id: str
    gewerk_type: str = "flooring"
    source_file: str
    extraction_method: str
    rooms: List[RoomAreaItemResponse]
    total_area_m2: float
    sum_counted_m2: float
    page_count: int
    missing: List[Dict[str, Any]]
    warnings: List[str]


@router.post("/flooring/nrf", response_model=RoomAreaResponse)
async def extract_room_areas_nrf(
    file: UploadFile = File(..., description="Floor plan PDF with NRF annotations"),
    pages: Optional[str] = Query(
        None,
        description="Comma-separated page numbers (0-indexed). Leave empty for all pages.",
    ),
    balcony_factor: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
        description="Factor for balcony/terrace areas (default 0.5 = 50%)",
    ),
):
    """
    Deterministic extraction of room areas from German CAD PDFs.

    Extracts NRF (Netto-Raumfläche) values from text annotations with full traceability.
    Every extracted value includes source_text and bounding box coordinates.

    **Hard Rules:**
    - Only extracts values that exist as text in the PDF
    - No inference, no guessing, no LLM generation
    - Missing values are explicitly tracked and excluded from totals

    **Patterns Recognized:**
    - "NRF: 22,79 m²" (primary pattern)
    - "BGF: 100,00 m²" (Bruttogrundfläche)
    - "NGF: 50,00 m²" (Nettogrundfläche)

    **Balcony Handling:**
    - Rooms with "Balkon", "Terrasse", "Loggia" in name get reduced factor
    - If "50%: X m²" explicit value found, uses that instead of calculation

    **Returns:**
    - rooms: List of extracted rooms with full traceability
    - total_area_m2: Sum of all area_m2 values
    - sum_counted_m2: Sum of all counted_m2 values (after balcony factor)
    - missing: Pages where no patterns were found
    """
    from ..services.room_area_extraction import extract_room_areas

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

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract room areas using deterministic NRF extraction
        result = extract_room_areas(
            pdf_path=temp_path,
            pages=page_list,
            default_balcony_factor=balcony_factor,
        )

        # Convert rooms to response format
        rooms = []
        for room in result.rooms:
            rooms.append(RoomAreaItemResponse(
                room_id=room.room_id,
                name=room.name,
                area_m2=room.area_m2,
                counted_m2=room.counted_m2,
                factor=room.factor,
                page=room.page,
                source_text=room.source_text,
                bbox=room.bbox.to_dict(),
                room_type=room.room_type,
                name_source=room.name_source,
                factor_source=room.factor_source,
            ))

        # Convert missing to response format
        missing = [m.to_dict() for m in result.missing]

        return RoomAreaResponse(
            gewerk_id=f"gew_{uuid4().hex[:12]}",
            gewerk_type="flooring",
            source_file=file.filename or "unknown.pdf",
            extraction_method=result.extraction_method,
            rooms=rooms,
            total_area_m2=result.total_area_m2,
            sum_counted_m2=result.sum_counted_m2,
            page_count=result.page_count,
            missing=missing,
            warnings=result.warnings,
        )

    finally:
        # Clean up temp files
        if temp_path.exists():
            temp_path.unlink()
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Door Geometry Extraction (Label + Vector Detection)
# =============================================================================


class DoorGeometryLabelResponse(BaseModel):
    """Response model for a detected door label."""
    label_text: str
    raw_text: str
    page_number: int
    bbox: List[float]  # [x0, y0, x1, y1]
    confidence: float
    pattern_type: str
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    door_type: Optional[str] = None
    fire_rating: Optional[str] = None


class DoorGeometryShapeResponse(BaseModel):
    """Response model for a detected door geometry."""
    geometry_id: str
    page_number: int
    center: List[float]  # [x, y]
    width_px: float
    height_px: Optional[float] = None
    orientation_deg: float
    opening_type: str  # "arc", "rectangle", "gap"
    bbox: List[float]  # [x0, y0, x1, y1]
    confidence: float
    source_type: str


class DoorExtractionItemResponse(BaseModel):
    """Response model for a single extracted door."""
    extraction_id: str
    page_number: int
    label: Optional[DoorGeometryLabelResponse] = None
    geometry: Optional[DoorGeometryShapeResponse] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    door_type: Optional[str] = None
    door_number: Optional[str] = None
    fire_rating: Optional[str] = None
    category: Optional[str] = None
    confidence: float
    extraction_method: str
    scale_context_id: Optional[str] = None
    assumptions: List[str]
    warnings: List[str]


class DoorExtractionSummaryResponse(BaseModel):
    """Summary statistics for door geometry extraction."""
    total_doors: int
    by_type: Dict[str, int]
    by_fire_rating: Dict[str, int]
    by_width: Dict[str, int]
    avg_width_m: Optional[float] = None


class DoorGeometryExtractionResponse(BaseModel):
    """Response for door geometry extraction endpoint."""
    result_id: str
    source_file: str
    page_count: int
    processed_pages: List[int]
    total_doors: int
    doors: List[DoorExtractionItemResponse]
    summary: DoorExtractionSummaryResponse
    extraction_time_ms: int
    warnings: List[str]
    errors: List[str]


@router.post("/doors/geometry", response_model=DoorGeometryExtractionResponse)
async def extract_door_geometry(
    file: UploadFile = File(..., description="Floor plan PDF file"),
    page_number: Optional[int] = Query(None, ge=1, description="Specific page to process (1-indexed). Leave empty for all pages."),
    scale: Optional[int] = Query(None, gt=0, description="Scale factor (e.g., 100 for 1:100). If not provided, dimensions will be in pixels only."),
    search_radius_px: float = Query(150, ge=50, le=500, description="Max distance between label and geometry for association"),
    min_confidence: float = Query(0.6, ge=0, le=1, description="Minimum confidence threshold for door detection"),
    dpi: int = Query(150, ge=72, le=300, description="DPI for PDF rendering and coordinate scaling"),
):
    """
    Extract doors from floor plan using label + geometry detection.

    **4-stage pipeline:**
    1. **Detect door labels** from text (WD, DD, dimensions, fire ratings)
    2. **Detect door geometries** (arcs, rectangles, wall gaps)
    3. **Associate labels** with nearest geometries
    4. **Extract dimensions** and attributes

    **What it detects:**
    - **Arc-based doors**: Quarter-circle swing indicators (most reliable)
    - **Rectangle doors**: Parallel line pairs indicating door frame
    - **Door labels**: Text patterns like "WD", "T 30-RS", "0,90 x 2,10"
    - **Fire ratings**: T30, T90, DSS classifications

    **Returns:**
    - Structured door list with full traceability
    - Every door includes: page, bbox, confidence, source method
    - Summary statistics: counts by type, fire rating, width

    **Scale parameter:**
    - Required for real-world dimensions (meters)
    - Without scale, dimensions are in pixels only
    - Example: scale=100 for 1:100 drawings

    **Use cases:**
    - Door schedules without tables (visual floor plans)
    - Fire-rated door audits
    - Door count verification
    """
    from ..services.door_geometry_extraction import extract_doors_from_pdf

    settings = get_settings()

    # Check if feature is enabled
    if not settings.door_geometry_extraction_enabled:
        raise HTTPException(
            status_code=501,
            detail="Door geometry extraction is disabled. Enable SNAPGRID_ENABLE_DOOR_GEOMETRY_EXTRACTION in settings."
        )

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be a PDF, got: {file.filename}"
        )

    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / file.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Run door geometry extraction
        result = extract_doors_from_pdf(
            pdf_path=temp_path,
            page_number=page_number,
            scale_factor=scale,
            search_radius_px=search_radius_px,
            min_confidence=min_confidence,
            dpi=dpi,
        )

        # Convert to response format
        doors = []
        for door in result.doors:
            # Convert label
            label_response = None
            if door.label:
                label_response = DoorGeometryLabelResponse(
                    label_text=door.label.label_text,
                    raw_text=door.label.raw_text,
                    page_number=door.label.page_number,
                    bbox=list(door.label.bbox),
                    confidence=door.label.confidence,
                    pattern_type=door.label.pattern_type,
                    width_m=door.label.width_m,
                    height_m=door.label.height_m,
                    door_type=door.label.door_type,
                    fire_rating=door.label.fire_rating,
                )

            # Convert geometry
            geometry_response = None
            if door.geometry:
                geometry_response = DoorGeometryShapeResponse(
                    geometry_id=door.geometry.geometry_id,
                    page_number=door.geometry.page_number,
                    center=list(door.geometry.center),
                    width_px=door.geometry.width_px,
                    height_px=door.geometry.height_px,
                    orientation_deg=door.geometry.orientation_deg,
                    opening_type=door.geometry.opening_type,
                    bbox=list(door.geometry.bbox),
                    confidence=door.geometry.confidence,
                    source_type=door.geometry.source_type,
                )

            # Build door item
            doors.append(DoorExtractionItemResponse(
                extraction_id=door.extraction_id,
                page_number=door.page_number,
                label=label_response,
                geometry=geometry_response,
                width_m=door.width_m,
                height_m=door.height_m,
                door_type=door.door_type,
                door_number=door.door_number,
                fire_rating=door.fire_rating,
                category=door.category,
                confidence=door.confidence,
                extraction_method=door.extraction_method,
                scale_context_id=door.scale_context_id,
                assumptions=door.assumptions,
                warnings=door.warnings,
            ))

        # Build summary
        summary = DoorExtractionSummaryResponse(
            total_doors=result.total_doors,
            by_type=result.by_type,
            by_fire_rating=result.by_fire_rating,
            by_width=result.by_width,
            avg_width_m=result.avg_width_m,
        )

        return DoorGeometryExtractionResponse(
            result_id=result.result_id,
            source_file=result.source_file,
            page_count=result.page_count,
            processed_pages=result.processed_pages,
            total_doors=result.total_doors,
            doors=doors,
            summary=summary,
            extraction_time_ms=result.extraction_time_ms,
            warnings=result.warnings,
            errors=result.errors,
        )

    finally:
        # Clean up temp files
        if temp_path.exists():
            temp_path.unlink()
        if Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
