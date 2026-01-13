"""
SnapGrid Backend API

FastAPI application for deterministic construction document extraction.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.schedules import router as schedules_router
from .api.plans import router as plans_router
from .api.gewerke import router as gewerke_router
from .api.cv import router as cv_router
from .api.jobs import router as jobs_router
from .api.extraction import router as extraction_router
from .api.projections import router as projections_router
from .api.drywall_detection import router as drywall_detection_router
from .api.artifacts import router as artifacts_router
from .core.config import settings

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
## SnapGrid API

Deterministic extraction of construction document data.

### Core Principle: No Hallucinated Numbers

All extracted values come from actual PDF content with full auditability:
- Page numbers
- Confidence scores
- Raw values before normalization

### Current Capabilities

- **Schedule Extraction**: Extract door lists (Türenliste), room lists, and other tabular schedules from PDF documents.
- **Plan Analysis**: API endpoints for blueprint analysis, object detection, and measurement.
- **Gewerke (Trade Modules)**: Trade-specific quantity takeoff:
  - Doors: Parse door schedules, classify by category (T30, T90, DSS, Standard)
  - Drywall: Calculate wall length and area for sectors

### Computer Vision (Universal Blueprint Support)

- **Input Analysis**: Detect PDF type (CAD with text, CAD no text, scanned, photo)
- **Roboflow CV**: Wall, room, and door detection for scans/photos
- **Hybrid Pipeline**: Combines text extraction with CV for best results

### Coming Soon

- **Phase E**: Sector queries and material takeoff
- **International Support**: US and other blueprint standards
    """,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for frontend and Supabase Edge Functions
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
        "http://localhost:3001",  # Alternative port
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
        "http://localhost:3004",
        "http://127.0.0.1:3004",
        "http://localhost:3005",
        "http://127.0.0.1:3005",
        "http://localhost:3006",
        "http://127.0.0.1:3006",
        "https://*.supabase.co",  # Supabase Edge Functions
        "https://*.supabase.net",  # Supabase alternate domain
        # Production domains
        "https://snapplan.tech",
        "https://www.snapplan.tech",
        "https://*.vercel.app",  # Vercel preview deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routers
app.include_router(schedules_router, prefix="/api/v1")
app.include_router(plans_router, prefix="/api/v1")
app.include_router(gewerke_router, prefix="/api/v1")
app.include_router(cv_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(extraction_router, prefix="/api/v1")
app.include_router(projections_router, prefix="/api/v1")
app.include_router(drywall_detection_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "Deterministic construction document extraction API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    """Global health check endpoint."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }
