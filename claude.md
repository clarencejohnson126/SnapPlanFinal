# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

SnapPlan: Deterministic extraction of construction document data with 100% traceability and zero hallucination. All extracted numbers must come from vector geometry, table extraction, computer vision, or OCR - never generated.

## Development Commands

```bash
# Backend (FastAPI)
cd backend && source venv/bin/activate
pip install -r requirements.txt               # Install dependencies
uvicorn app.main:app --reload --port 8000     # Dev server with hot reload
pytest tests/ -v                              # Run all tests
pytest tests/test_gewerke_doors.py -v         # Run single test file
pytest tests/test_gewerke_doors.py::test_door_category_classification -v  # Single test

# Frontend (Next.js)
cd frontend
npm install      # Install dependencies
npm run dev      # Dev server at localhost:3000
npm run build    # Production build
npm run lint     # ESLint

# API Documentation
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

## Architecture

```
INPUT ROUTER (input_router.py)
├── CAD PDF with annotations → Text Extraction (pdfplumber)
├── CAD PDF no annotations → Vector + CV (PyMuPDF + YOLO)
├── Scanned PDF → Roboflow CV
└── Photo → Roboflow CV
          ↓
MEASUREMENT ENGINE → Quantities (m², count, dimensions)
          ↓
EXPORT → Excel/CSV with full audit trail
```

### Backend Services (`backend/app/services/`)

| Service | Purpose |
|---------|---------|
| `input_router.py` | Detects `InputType.CAD_WITH_TEXT`, `CAD_NO_TEXT`, `SCANNED_PDF`, or `PHOTO` |
| `unified_extraction.py` | Multi-style room extraction (Haardtring, LeiQ, Omniturm patterns) |
| `room_area_extraction.py` | Deterministic NRF extraction with full traceability |
| `gewerke.py` | Trade modules: door classification, flooring/drywall area extraction |
| `vector_measurement.py` | PDF geometry parsing with PyMuPDF |
| `scale_calibration.py` | Scale detection (Maßstab 1:100) |
| `schedule_extraction.py` | Table parsing via pdfplumber |
| `cv_pipeline.py` | YOLO door detection + Roboflow integration |
| `llm_interpretation.py` | OpenAI-powered summaries (post-extraction only) |
| `excel_export.py` | Aufmaß-ready Excel/CSV export |
| `persistence.py` | Supabase storage (optional) |

### Frontend Structure (`frontend/`)

| Path | Purpose |
|------|---------|
| `app/page.tsx` | Public landing page |
| `app/app/` | Protected routes (dashboard, scan, projects, settings) |
| `app/app/scan/page.tsx` | Main PDF upload and extraction UI |
| `lib/api.ts` | FastAPI client - all backend API calls |
| `lib/types.ts` | TypeScript interfaces matching backend models |
| `lib/supabase/` | Supabase client utilities |

### Trade Modules (Gewerke)

| Trade | Primary Method | Key Patterns |
|-------|----------------|--------------|
| Doors | Schedule text extraction | `DoorCategory` enum (T30, T90, DSS, Standard) |
| Flooring | NRF text values | Area in m² from annotations |
| Drywall | Perimeter × height | U-values × wall_height_m |

## Core Patterns

**Traceability**: Every extracted quantity must include `page_number`, `source_type`, `confidence_score`, `raw_value`.

**German CAD Priority**: Optimized for German construction documents. Key terms:
- Türenliste = Door schedule
- NRF = Net floor area (m²)
- U = Perimeter values (m)
- Maßstab = Scale (1:100)
- T30-RS, T90 = Fire ratings

**Drywall vs Flooring**: Flooring uses NRF area values. Drywall uses `perimeter × wall_height` (not raw vector segments, which include furniture/text).

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/extraction/rooms` | **Primary**: Extract room areas with auto-detected style |
| `POST /api/v1/extraction/rooms/with-summary` | Room extraction + LLM summary |
| `GET /api/v1/extraction/export/{job_id}` | Download Excel/CSV export |
| `POST /api/v1/gewerke/doors/from-schedule` | Door schedule → structured list |
| `POST /api/v1/gewerke/flooring/nrf` | **Deterministic NRF extraction** (m²) with full traceability |
| `POST /api/v1/gewerke/flooring/from-plan` | NRF extraction (m²) |
| `POST /api/v1/gewerke/drywall/from-plan` | Perimeter × height (m²) |
| `POST /api/v1/gewerke/*/smart` | Auto-route based on input type |
| `POST /api/v1/cv/detect/{rooms,walls,doors}` | Roboflow CV |
| `POST /api/v1/cv/analyze-input` | Detect input type |

## Environment Variables

Backend `.env`:
```
SNAPGRID_SUPABASE_URL=https://xxx.supabase.co
SNAPGRID_SUPABASE_SERVICE_KEY=sb_secret_xxx
SNAPGRID_YOLO_MODEL_PATH=/path/to/door_detector_custom.pt
ROBOFLOW_API_KEY=xxx
OPENAI_API_KEY=sk-xxx  # For LLM interpretation (summaries only)
```

Frontend `.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_SNAPGRID_API_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

## Blueprint Style Detection

The `unified_extraction.py` service auto-detects building types:

| Style | Pattern | Room Format | Building Type |
|-------|---------|-------------|---------------|
| Haardtring | `F:` | `R2.E5.3.5` | Residential |
| LeiQ | `NRF:` | `B.00.2.002` | Commercial/Office |
| Omniturm | `NGF:` | `33_b6.12` | Highrise |

**Pattern Detection Strategy:**
1. First try `NRF:` pattern (Netto-Raumfläche)
2. Then try `F:` pattern (Fläche)
3. Auto-detect room number format

**Key extraction rules:**
- German blueprints use `F:` or `NRF:` for area in m²
- Outdoor spaces (Dachterrasse, Terrasse, Balkon) get 50% factor
- Text extraction may split values across two lines
- Always convert German decimal comma `,` to `.` for parsing
- LeiQ includes U: (perimeter) and LH: (height) - useful for drywall/volume

## Test Files

Sample PDFs in `PLANS/` directory. Sample door schedule: `Tuerenliste_Bauteil_B_OG1.pdf`.

```bash
# Test with sample
curl -X POST "http://localhost:8000/api/v1/schedules/extract?use_sample=true"
```

### Key Test Modules

| Test File | Coverage |
|-----------|----------|
| `test_room_area_extraction.py` | NRF/F:/NGF pattern extraction, multi-style |
| `test_gewerke_doors.py` | Door classification, DoorCategory enum |
| `test_gewerke_drywall.py` | Perimeter × height calculations |
| `test_vector_measurement.py` | PDF geometry, wall detection |
| `test_scale_calibration.py` | Scale detection (Maßstab 1:100) |
| `test_cv_pipeline.py` | YOLO + Roboflow integration |
| `test_schedule_extraction.py` | Door schedule table parsing |

## Database Schema (Supabase)

Core tables: `projects`, `files`, `jobs`, `area_results`, `job_totals`, `scale_contexts`, `sectors`, `detected_objects`, `measurements`. Schema in `backend/infra/supabase/mvp_schema.sql`.

## YOLO Door Detector

Custom YOLOv8n model for door detection in architectural blueprints:
- Model path: `backend/models/door_detector_custom.pt`
- Confidence threshold: 0.25 (lowered for blueprints)
- Training data: 5,508 annotations from 260 floor plans

## Custom Skills

- `/vector-measurement` - Extract and measure vector geometry from CAD-derived PDFs
- `/pdf-ingestion` - Ingest PDF blueprints and classify pages
- `/schedule-extraction` - Extract structured tables from schedule pages
- `/project-docs` - Read and update project documentation

## Verified Extraction Workflows

Documented extraction workflows with verified test results in `backend/docs/workflows/`:

| Workflow | Building Type | Area Label | Doc |
|----------|--------------|------------|-----|
| Haardtring Riegel | Residential | F: | `m2_extraction_haardtring_riegel_building.md` |
| LeiQ Office | Commercial | NRF: | `m2_extraction_leiq_office_building.md` |
| Omniturm Highrise | Highrise | NGF: | `m2_extraction_omniturm_highrise.md` |
