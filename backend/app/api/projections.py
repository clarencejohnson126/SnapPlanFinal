"""
Trade Material Projection API Endpoints

Endpoints for calculating material projections for construction trades.
Takes extraction results (ground truth) and produces:
- Aufmass items (calculated from measured quantities)
- Projected materials (estimates with assumptions and confidence)
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime

from app.services.trade_projection import (
    TradeType,
    TradeParams,
    MaterialProjectionResult,
    TRADE_METADATA,
)
from app.services.projections import (
    project_screed,
    project_drywall,
    project_scaffolding,
    project_floor_finish,
    project_waterproofing,
)


router = APIRouter(prefix="/projections", tags=["projections"])


# ==================
# REQUEST/RESPONSE MODELS
# ==================

class ProjectionParamsRequest(BaseModel):
    """Parameters for material projection."""
    waste_factor: float = Field(1.10, ge=1.0, le=2.0, description="Waste factor (1.0-2.0)")

    # Scaffolding
    scaffold_height_m: Optional[float] = Field(None, gt=0, description="Scaffold height in meters")
    scaffold_type: str = Field("standard", description="Scaffold type: standard, rollgeruest, fassade")

    # Drywall
    wall_height_m: Optional[float] = Field(None, gt=0, description="Wall height in meters")
    drywall_system: str = Field("single", description="Drywall system: single, double, fire_rated")
    stud_spacing_mm: int = Field(625, gt=0, description="Stud spacing in mm")

    # Screed
    screed_type: str = Field("ct", description="Screed type: ct, ca, ma")
    screed_thickness_mm: int = Field(50, gt=0, description="Screed thickness in mm")

    # Floor finish
    finish_type: str = Field("laminate", description="Floor finish: laminate, parquet, tile, carpet")

    # Waterproofing
    waterproofing_type: str = Field("liquid", description="Waterproofing: liquid, membrane, bitumen")
    waterproofing_wall_height_m: float = Field(2.0, gt=0, description="Wall height to waterproof")


class ProjectionRequest(BaseModel):
    """Request for material projection calculation."""
    extraction_result: Dict[str, Any] = Field(..., description="Extraction result JSON")
    trade_type: str = Field(..., description="Trade type: scaffolding, drywall, screed, floor_finish, waterproofing")
    params: ProjectionParamsRequest = Field(default_factory=ProjectionParamsRequest)
    use_llm: bool = Field(False, description="Enable LLM suggestions (feature flag)")


class AufmassItemResponse(BaseModel):
    """Response model for Aufmass item."""
    item_id: str
    position: str
    description: str
    quantity: float
    unit: str
    formula: str
    formula_description: str
    is_ground_truth: bool = True


class ProjectedMaterialResponse(BaseModel):
    """Response model for projected material."""
    material_id: str
    name: str
    quantity: float
    effective_quantity: float
    unit: str
    method: str
    confidence: float
    confidence_level: str
    assumptions: List[str]
    is_estimate: bool = True


class ProjectionResponse(BaseModel):
    """Response for material projection calculation."""
    projection_id: str
    trade_type: str
    trade_name_de: str
    source_extraction_id: str
    processed_at: str
    status: str
    aufmass_items: List[Dict[str, Any]]
    projected_materials: List[Dict[str, Any]]
    total_aufmass_quantity: float
    errors: List[str]
    warnings: List[str]
    disclaimer: str
    summary: Dict[str, Any]


class TradeInfoResponse(BaseModel):
    """Information about a single trade."""
    type: str
    name_de: str
    name_en: str
    icon: str
    required_params: List[str]
    optional_params: List[str]
    uses_perimeter: bool
    uses_area: bool


class TradeListResponse(BaseModel):
    """List of available trades."""
    trades: List[TradeInfoResponse]


# ==================
# HELPER FUNCTIONS
# ==================

def _convert_params(trade_type: TradeType, params: ProjectionParamsRequest) -> TradeParams:
    """Convert API params to internal TradeParams."""
    return TradeParams(
        trade_type=trade_type,
        waste_factor=params.waste_factor,
        scaffold_height_m=params.scaffold_height_m,
        scaffold_type=params.scaffold_type,
        wall_height_m=params.wall_height_m,
        drywall_system=params.drywall_system,
        stud_spacing_mm=params.stud_spacing_mm,
        screed_type=params.screed_type,
        screed_thickness_mm=params.screed_thickness_mm,
        finish_type=params.finish_type,
        waterproofing_type=params.waterproofing_type,
        waterproofing_wall_height_m=params.waterproofing_wall_height_m,
    )


# ==================
# ENDPOINTS
# ==================

@router.get("/trades", response_model=TradeListResponse)
async def list_available_trades():
    """
    List available trades with their parameters and requirements.

    Returns information about each trade including:
    - German and English names
    - Required and optional parameters
    - Whether it needs perimeter/area data
    """
    trades = []
    for trade_type, metadata in TRADE_METADATA.items():
        trades.append(TradeInfoResponse(
            type=trade_type.value,
            name_de=metadata["name_de"],
            name_en=metadata["name_en"],
            icon=metadata["icon"],
            required_params=metadata["required_params"],
            optional_params=metadata["optional_params"],
            uses_perimeter=metadata["uses_perimeter"],
            uses_area=metadata["uses_area"],
        ))
    return TradeListResponse(trades=trades)


@router.get("/trades/{trade_type}")
async def get_trade_info(trade_type: str):
    """Get detailed information about a specific trade."""
    try:
        trade_enum = TradeType(trade_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trade type: {trade_type}. Valid types: {[t.value for t in TradeType]}"
        )

    metadata = TRADE_METADATA.get(trade_enum)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Trade metadata not found: {trade_type}")

    return {
        "type": trade_enum.value,
        **metadata,
    }


@router.post("/calculate", response_model=ProjectionResponse)
async def calculate_projection(request: ProjectionRequest):
    """
    Calculate material projection for a trade.

    Takes extraction results (ground truth) and trade parameters,
    returns:
    - Aufmass items (calculated from measured quantities)
    - Projected materials (estimates with assumptions and confidence)

    The projection clearly separates:
    - Ground truth: Values derived directly from extraction with formulas
    - Estimates: Projected quantities with documented assumptions

    Args:
        request: ProjectionRequest with extraction_result, trade_type, and params

    Returns:
        ProjectionResponse with aufmass_items, projected_materials, and metadata
    """
    # Validate trade type
    try:
        trade_type = TradeType(request.trade_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trade type: {request.trade_type}. Valid types: {[t.value for t in TradeType]}"
        )

    # Convert params
    params = _convert_params(trade_type, request.params)

    # Validate params
    param_errors = params.validate()
    if param_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid parameters: {'; '.join(param_errors)}"
        )

    # Route to appropriate projection engine
    projection_engines = {
        TradeType.SCAFFOLDING: project_scaffolding,
        TradeType.DRYWALL: project_drywall,
        TradeType.SCREED: project_screed,
        TradeType.FLOOR_FINISH: project_floor_finish,
        TradeType.WATERPROOFING: project_waterproofing,
    }

    engine = projection_engines.get(trade_type)
    if not engine:
        raise HTTPException(
            status_code=501,
            detail=f"Projection engine not implemented for: {trade_type.value}"
        )

    # Execute projection
    try:
        result: MaterialProjectionResult = engine(request.extraction_result, params)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Projection calculation failed: {str(e)}"
        )

    # TODO: If use_llm is True and LLM enhancement is enabled, enhance result
    # if request.use_llm:
    #     result = enhance_with_llm(result, request.extraction_result)

    return result.to_dict()


@router.post("/calculate/batch")
async def calculate_batch_projections(
    extraction_result: Dict[str, Any],
    trade_types: List[str] = Query(..., description="List of trade types to calculate"),
    params: ProjectionParamsRequest = None,
):
    """
    Calculate projections for multiple trades at once.

    Useful for getting all material projections from a single extraction.

    Args:
        extraction_result: Extraction result JSON
        trade_types: List of trade types (e.g., ["screed", "drywall"])
        params: Shared parameters (individual trades use relevant params)

    Returns:
        Dict mapping trade_type -> ProjectionResponse
    """
    if params is None:
        params = ProjectionParamsRequest()

    results = {}

    for trade_type_str in trade_types:
        try:
            trade_type = TradeType(trade_type_str.lower())
        except ValueError:
            results[trade_type_str] = {
                "status": "error",
                "error": f"Unknown trade type: {trade_type_str}"
            }
            continue

        trade_params = _convert_params(trade_type, params)

        projection_engines = {
            TradeType.SCAFFOLDING: project_scaffolding,
            TradeType.DRYWALL: project_drywall,
            TradeType.SCREED: project_screed,
            TradeType.FLOOR_FINISH: project_floor_finish,
            TradeType.WATERPROOFING: project_waterproofing,
        }

        engine = projection_engines.get(trade_type)
        if not engine:
            results[trade_type_str] = {
                "status": "error",
                "error": f"Engine not implemented: {trade_type.value}"
            }
            continue

        try:
            result = engine(extraction_result, trade_params)
            results[trade_type_str] = result.to_dict()
        except Exception as e:
            results[trade_type_str] = {
                "status": "error",
                "error": str(e)
            }

    return {"results": results}


@router.post("/export/json")
async def export_projection_json(projection: Dict[str, Any]):
    """
    Export projection to JSON format.

    Returns the projection data formatted for download/storage.
    """
    # Add export metadata
    export_data = {
        "export_version": "1.0",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "projection": projection,
    }
    return export_data


# Note: Excel export can be added later using the existing excel_export.py pattern
# @router.post("/export/excel")
# async def export_projection_excel(projection: Dict[str, Any]):
#     """Export projection to Excel format."""
#     pass
