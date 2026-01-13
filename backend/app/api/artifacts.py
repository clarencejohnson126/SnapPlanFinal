"""
Artifact Studio API routes.

Provides endpoints for generating and managing interactive construction detail sketches.
Uses Claude AI to generate SVG, Mermaid, and HTML artifacts from natural language prompts.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.artifact_generation import (
    generate_artifact,
    get_prompt_templates,
    ArtifactType,
)
from ..core.config import settings

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

# MVP storage path - JSON file for persistence
ARTIFACTS_FILE = Path(settings.data_dir) / "artifacts.json"


# =============================================================================
# Request/Response Models
# =============================================================================


class ArtifactContext(BaseModel):
    """Context fields for artifact generation."""
    project: Optional[str] = Field(None, description="Project name or ID")
    floor: Optional[str] = Field(None, description="Floor level (e.g., EG, OG1)")
    grid_axis: Optional[str] = Field(None, description="Grid axis reference")
    wall_id: Optional[str] = Field(None, description="Wall identifier")
    detail_type: Optional[str] = Field(None, description="Type of detail")


class GenerateRequest(BaseModel):
    """Request to generate a new artifact."""
    prompt: str = Field(
        ...,
        min_length=10,
        description="Natural language description of the desired construction detail"
    )
    trade_preset: Optional[str] = Field(
        None,
        description="Trade category: flooring, drywall, electrical, insulation, doors"
    )
    context: Optional[ArtifactContext] = Field(
        None,
        description="Optional context fields for more specific generation"
    )


class ArtifactResponse(BaseModel):
    """Response containing a generated or retrieved artifact."""
    artifact_id: str
    title: str
    type: str  # svg, mermaid, html
    summary: str
    bullet_points: List[str]
    code: str
    assets: Optional[Dict[str, Any]] = None
    created_at: str
    input_prompt: str
    trade_preset: Optional[str] = None
    context: Optional[Dict[str, str]] = None
    version_number: int = 1
    parent_id: Optional[str] = None


class GenerateResponse(BaseModel):
    """Response from artifact generation endpoint."""
    success: bool
    artifact: Optional[ArtifactResponse] = None
    error: Optional[str] = None
    tokens_used: int = 0
    model: str = ""


class ArtifactListResponse(BaseModel):
    """Response containing a list of artifacts."""
    artifacts: List[ArtifactResponse]
    total_count: int


class TemplateResponse(BaseModel):
    """A prompt template."""
    id: str
    name_de: str
    name_en: str
    prompt: str
    trade: str


class TemplateListResponse(BaseModel):
    """Response containing available templates."""
    templates: List[TemplateResponse]


# =============================================================================
# Storage Helpers (MVP - JSON file)
# =============================================================================


def _ensure_data_dir():
    """Ensure data directory exists."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def _load_artifacts() -> Dict[str, Any]:
    """Load artifacts from JSON file."""
    _ensure_data_dir()
    if not ARTIFACTS_FILE.exists():
        return {"artifacts": []}
    try:
        with open(ARTIFACTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"artifacts": []}


def _save_artifacts(data: Dict[str, Any]) -> None:
    """Save artifacts to JSON file."""
    _ensure_data_dir()
    with open(ARTIFACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/generate", response_model=GenerateResponse)
async def generate_artifact_endpoint(request: GenerateRequest):
    """
    Generate a new artifact using Claude AI.

    Creates an interactive construction detail sketch based on the natural language prompt.
    Supports trade presets and contextual information for more accurate results.

    **Trade Presets:**
    - `flooring`: Floor finish details, transitions, junctions
    - `drywall`: Trockenbau details, wall connections, partitions
    - `electrical`: Cable routing, socket placement, firestopping
    - `insulation`: Thermal and acoustic insulation details
    - `doors`: Door schedules, frames, fire ratings

    **Output Types:**
    - `svg`: Scalable vector graphics (preferred for technical diagrams)
    - `mermaid`: Flowcharts and decision trees
    - `html`: Tables and text-heavy content

    All output is sanitized for security (no scripts, no event handlers).
    """
    if not settings.anthropic_enabled:
        raise HTTPException(
            status_code=503,
            detail="Artifact generation not available. SNAPGRID_ANTHROPIC_API_KEY not configured."
        )

    # Convert context to dict if provided
    context_dict = None
    if request.context:
        context_dict = {
            k: v for k, v in request.context.model_dump().items() if v
        }

    # Generate artifact
    result = generate_artifact(
        prompt=request.prompt,
        trade_preset=request.trade_preset,
        context=context_dict,
        retry_count=1,
    )

    if not result.success:
        return GenerateResponse(
            success=False,
            error=result.error,
            tokens_used=result.tokens_used,
            model=result.model,
        )

    # Create artifact record
    artifact_id = f"art_{uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"

    artifact_response = ArtifactResponse(
        artifact_id=artifact_id,
        title=result.artifact.title,
        type=result.artifact.type.value,
        summary=result.artifact.summary,
        bullet_points=result.artifact.bullet_points,
        code=result.artifact.code,
        assets=result.artifact.assets,
        created_at=now,
        input_prompt=request.prompt,
        trade_preset=request.trade_preset,
        context=context_dict,
        version_number=1,
        parent_id=None,
    )

    # Save to storage
    data = _load_artifacts()
    data["artifacts"].append(artifact_response.model_dump())
    _save_artifacts(data)

    return GenerateResponse(
        success=True,
        artifact=artifact_response,
        tokens_used=result.tokens_used,
        model=result.model,
    )


@router.get("/list", response_model=ArtifactListResponse)
async def list_artifacts(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of artifacts to return"),
    offset: int = Query(0, ge=0, description="Number of artifacts to skip"),
):
    """
    List all saved artifacts.

    Returns artifacts sorted by creation date (newest first).
    Supports pagination with limit and offset parameters.
    """
    data = _load_artifacts()
    artifacts = data.get("artifacts", [])

    # Sort by created_at descending (newest first)
    artifacts.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Paginate
    total_count = len(artifacts)
    paginated = artifacts[offset:offset + limit]

    return ArtifactListResponse(
        artifacts=[ArtifactResponse(**a) for a in paginated],
        total_count=total_count,
    )


@router.get("/templates/list", response_model=TemplateListResponse)
async def list_templates():
    """
    Get available prompt templates.

    Returns pre-built templates for common construction details.
    Each template includes German and English names, the prompt text,
    and the associated trade category.
    """
    templates = get_prompt_templates()
    return TemplateListResponse(
        templates=[TemplateResponse(**t) for t in templates]
    )


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: str):
    """
    Get a specific artifact by ID.

    Returns the full artifact including code, summary, and metadata.
    """
    data = _load_artifacts()
    for artifact in data.get("artifacts", []):
        if artifact.get("artifact_id") == artifact_id:
            return ArtifactResponse(**artifact)

    raise HTTPException(status_code=404, detail="Artifact not found")


@router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str):
    """
    Delete an artifact by ID.

    Permanently removes the artifact from storage.
    """
    data = _load_artifacts()
    original_count = len(data.get("artifacts", []))
    data["artifacts"] = [
        a for a in data.get("artifacts", [])
        if a.get("artifact_id") != artifact_id
    ]

    if len(data["artifacts"]) == original_count:
        raise HTTPException(status_code=404, detail="Artifact not found")

    _save_artifacts(data)
    return {"success": True, "message": "Artifact deleted"}


@router.post("/{artifact_id}/version", response_model=GenerateResponse)
async def create_version(artifact_id: str, request: GenerateRequest):
    """
    Create a new version of an existing artifact.

    Generates a new artifact based on the provided prompt while linking
    it to the parent artifact for version history tracking.
    """
    if not settings.anthropic_enabled:
        raise HTTPException(
            status_code=503,
            detail="Artifact generation not available. SNAPGRID_ANTHROPIC_API_KEY not configured."
        )

    # Find parent artifact
    data = _load_artifacts()
    parent = None
    parent_version = 0
    for artifact in data.get("artifacts", []):
        if artifact.get("artifact_id") == artifact_id:
            parent = artifact
            parent_version = artifact.get("version_number", 1)
            break

    if not parent:
        raise HTTPException(status_code=404, detail="Parent artifact not found")

    # Convert context to dict if provided
    context_dict = None
    if request.context:
        context_dict = {
            k: v for k, v in request.context.model_dump().items() if v
        }

    # Generate new version
    result = generate_artifact(
        prompt=request.prompt,
        trade_preset=request.trade_preset,
        context=context_dict,
        retry_count=1,
    )

    if not result.success:
        return GenerateResponse(
            success=False,
            error=result.error,
            tokens_used=result.tokens_used,
            model=result.model,
        )

    # Create new version record
    new_artifact_id = f"art_{uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat() + "Z"

    artifact_response = ArtifactResponse(
        artifact_id=new_artifact_id,
        title=result.artifact.title,
        type=result.artifact.type.value,
        summary=result.artifact.summary,
        bullet_points=result.artifact.bullet_points,
        code=result.artifact.code,
        assets=result.artifact.assets,
        created_at=now,
        input_prompt=request.prompt,
        trade_preset=request.trade_preset,
        context=context_dict,
        version_number=parent_version + 1,
        parent_id=artifact_id,
    )

    # Save to storage
    data["artifacts"].append(artifact_response.model_dump())
    _save_artifacts(data)

    return GenerateResponse(
        success=True,
        artifact=artifact_response,
        tokens_used=result.tokens_used,
        model=result.model,
    )


@router.get("/health", tags=["health"])
async def health_check():
    """Check artifact service health status."""
    return {
        "status": "healthy",
        "service": "artifacts",
        "anthropic_enabled": settings.anthropic_enabled,
    }
