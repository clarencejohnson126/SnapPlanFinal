"""
SnapGrid configuration settings.

Manages application settings via environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SNAPGRID_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "SnapGrid"
    app_version: str = "0.1.0"
    debug: bool = False

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent.parent
    data_dir: Path = project_root / "data"
    uploads_dir: Path = data_dir / "uploads"

    # Sample files (for POC)
    sample_door_schedule: Path = project_root / "Tuerenliste_Bauteil_B_OG1.pdf"

    # PDF Extraction settings
    pdf_extraction_method: str = "pdfplumber"  # "pdfplumber" or "camelot"

    # CV Pipeline / YOLO Configuration
    yolo_model_path: Optional[str] = None  # Path to YOLO model weights (.pt file)
    yolo_confidence_threshold: float = 0.15  # Lower threshold for architectural blueprints
    cv_pipeline_enabled: bool = True  # Set False to disable CV features entirely

    @property
    def yolo_enabled(self) -> bool:
        """Check if YOLO is properly configured for object detection."""
        return bool(self.yolo_model_path and self.cv_pipeline_enabled)

    # Roboflow Configuration (for scanned PDFs, photos, international blueprints)
    roboflow_api_key: Optional[str] = None
    roboflow_publishable_key: Optional[str] = None
    roboflow_api_url: str = "https://serverless.roboflow.com"

    # Roboflow feature flags
    # Set to False to disable Roboflow segmentation (unreliable for German CAD plans)
    # Geometry-first pipeline is preferred for room area extraction
    use_roboflow_for_rooms: bool = False  # Disabled - use geometry pipeline instead
    use_roboflow_for_doors: bool = True   # Keep enabled for door detection

    # Roboflow model configurations (from Roboflow Universe)
    roboflow_floor_plan_model: str = "floor-plan-segmentation-dtr4r/1"  # IIITBangalore
    roboflow_room_segmentation_model: str = "room-segmentation-model/1"  # Floor Plan Rendering
    roboflow_door_detection_model: str = "detecting-doors-from-floor-plan/2"  # Door detection
    roboflow_wall_floor_model: str = "wall-floor-2zskh/1"  # Wall-floor segmentation
    roboflow_confidence_threshold: float = 0.3

    @property
    def roboflow_enabled(self) -> bool:
        """Check if Roboflow is properly configured for CV processing."""
        return bool(self.roboflow_api_key and self.cv_pipeline_enabled)

    @property
    def roboflow_rooms_enabled(self) -> bool:
        """Check if Roboflow room segmentation is enabled."""
        return self.roboflow_enabled and self.use_roboflow_for_rooms

    @property
    def roboflow_doors_enabled(self) -> bool:
        """Check if Roboflow door detection is enabled."""
        return self.roboflow_enabled and self.use_roboflow_for_doors

    # Supabase Configuration (optional - persistence disabled if not set)
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None
    supabase_bucket_name: str = "snapgrid-files"

    @property
    def supabase_enabled(self) -> bool:
        """Check if Supabase is properly configured for persistence."""
        return bool(self.supabase_url and self.supabase_service_key)

    # Anthropic Configuration (for Artifact Studio)
    anthropic_api_key: Optional[str] = None

    @property
    def anthropic_enabled(self) -> bool:
        """Check if Anthropic API is configured for artifact generation."""
        return bool(self.anthropic_api_key)


# Global settings instance
settings = Settings()


def get_sample_pdf_path() -> Path:
    """Get path to the sample door schedule PDF for testing."""
    return settings.sample_door_schedule


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
