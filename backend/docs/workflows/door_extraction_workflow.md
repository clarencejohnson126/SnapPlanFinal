# Door Geometry Extraction Workflow

**Version:** 1.0
**Last Updated:** 2026-01-22

## Overview

The door geometry extraction pipeline detects and extracts doors from 2D construction PDFs using a deterministic, rule-based approach that combines text label detection with vector geometry analysis.

**Core Principle:** Zero hallucination. All extracted values come from actual PDF content with full traceability.

## Pipeline Architecture

### 4-Stage Pipeline

```
Stage 1: Label Detection
    ↓ Text patterns (WD, DD, T30, dimensions)
Stage 2: Geometry Detection
    ↓ Arc patterns, parallel lines
Stage 3: Association
    ↓ Match labels with nearest geometries
Stage 4: Attribute Extraction
    ↓ Width, height, fire rating, category
```

## Stage 1: Door Label Detection

### Supported Label Patterns

#### German Door Abbreviations
- `WD` - Wohnungstür (Apartment door)
- `DD` - Doppeltür (Double door)
- `SD` - Schiebetür (Sliding door)
- `FD` - Feuerschutztür (Fire door)
- `TD` - Trennwand door
- `ND` - Nebentür (Secondary door)

#### Room-Style Door Labels
- `F. ND1` - German format
- `B.03.1.001-1` - LeiQ format
- `BU_012` - Building/Unit format

#### Dimension Labels
- `0,90 x 2,10` - Decimal meters (German comma)
- `90 x 210` - Centimeters

#### Fire Ratings
- `T 30-RS` - 30-minute fire rating with smoke seal
- `T30` - 30-minute fire rating
- `T 90-RS` - 90-minute fire rating with smoke seal
- `T90` - 90-minute fire rating
- `DSS` - Dichtschließend Selbstschließend (Smoke protection)
- `Rauchschutz` - Smoke protection (German)

### Label Grouping

Labels within 50px are automatically grouped to handle compound labels:
```
F. ND1          ← Door label
T 30-RS         ← Fire rating
    ↓
Combined: "F. ND1 T 30-RS" with fire_rating=T30
```

## Stage 2: Geometry Detection

### Method 2a: Arc-Based Detection (Highest Confidence)

Detects quarter-circle arc patterns that indicate door swing direction.

**Characteristics:**
- Arc angle: 70-110 degrees (approximately 90°)
- Confidence: 0.8-0.95
- Most reliable method for CAD-exported PDFs

**Reuses existing code:** `extract_door_symbols_from_page()` from `vector_measurement.py`

### Method 2b: Rectangle-Based Detection (Medium Confidence)

Detects door frames using parallel line pairs.

**Strategy:**
1. Find pairs of parallel lines (angle difference < 10°)
2. Measure perpendicular distance between lines
3. Filter by realistic door width range (0.6m - 1.5m)
4. Confidence: 0.6-0.7

**Distinguishes from windows:**
- Windows: Parallel lines + no arc + exterior wall
- Doors: Parallel lines + optional arc + realistic door size

### Method 2c: Wall Gap Detection (Future)

Detects openings as interruptions in wall runs.
- Lower confidence (0.5-0.6)
- Useful for sliding doors, passage openings
- **Status:** Planned, not yet implemented

## Stage 3: Label-Geometry Association

### Matching Algorithm

1. Calculate center point of each label bbox
2. Calculate center point of each geometry
3. Compute Euclidean distance between centers
4. Match label to nearest geometry within `search_radius_px` (default: 150px)
5. Prefer 1:1 matches (one label to one geometry)
6. If multiple labels near same geometry, choose closest

### Unmatched Cases

**Geometry Only (no label):**
- Confidence reduced by 30% (`confidence * 0.7`)
- Warning: "No label found near this door geometry"
- Still included in results (may be valid unlabeled door)

**Label Only (no geometry):**
- Confidence reduced by 50% (`confidence * 0.5`)
- Warning: "Door label found but no geometry detected nearby"
- Included for review (may indicate detection issue)

## Stage 4: Attribute Extraction

### Priority Order for Width/Height

1. **Explicit dimensions from label** (highest priority)
   - Example: "0,90 x 2,10" → width=0.90m, height=2.10m
   - Confidence: 0.95

2. **Geometry measurement with scale**
   - width_m = width_px / pixels_per_meter
   - Example: 53.15px at 1:100 scale (59.055 px/m) → 0.90m
   - Confidence: 0.85

3. **Pixels only (no scale provided)**
   - Returns width_px, no width_m
   - Warning: "No scale provided, dimensions in pixels only"

### Fire Rating Classification

Extracted fire ratings are normalized and classified:

| Raw Text | Normalized | Category |
|----------|-----------|----------|
| T 30-RS | T30 | T30 |
| T30 | T30 | T30 |
| T 90-RS | T90 | T90 |
| T90 | T90 | T90 |
| DSS | DSS | DSS |
| Rauchschutz | DSS | DSS |
| (none) | - | Standard |

## Example Output

### API Request

```bash
POST /api/v1/gewerke/doors/geometry
Content-Type: multipart/form-data

file: floor_plan.pdf
page_number: 1
scale: 100
search_radius_px: 150
min_confidence: 0.6
```

### API Response

```json
{
  "result_id": "door_extraction_abc123def456",
  "source_file": "floor_plan.pdf",
  "page_count": 1,
  "processed_pages": [1],
  "total_doors": 3,
  "doors": [
    {
      "extraction_id": "door_a1b2c3d4",
      "page_number": 1,
      "label": {
        "label_text": "F. ND1 T 30-RS",
        "raw_text": "F. ND1\nT 30-RS",
        "page_number": 1,
        "bbox": [100.5, 200.3, 150.2, 225.8],
        "confidence": 0.95,
        "pattern_type": "room_door+fire_rating",
        "fire_rating": "T30"
      },
      "geometry": {
        "geometry_id": "door_e5f6g7h8",
        "page_number": 1,
        "center": [125.0, 210.0],
        "width_px": 53.15,
        "opening_type": "arc",
        "bbox": [100.0, 185.0, 150.0, 235.0],
        "confidence": 0.85,
        "source_type": "vector"
      },
      "width_m": 0.90,
      "door_number": "F. ND1 T 30-RS",
      "fire_rating": "T30",
      "category": "T30",
      "confidence": 0.85,
      "extraction_method": "label_geometry_match",
      "scale_context_id": "scale_xyz789",
      "assumptions": [
        "Width calculated from geometry (scale 1:100)"
      ],
      "warnings": []
    },
    {
      "extraction_id": "door_i9j0k1l2",
      "page_number": 1,
      "label": null,
      "geometry": {
        "geometry_id": "door_m3n4o5p6",
        "page_number": 1,
        "center": [300.0, 400.0],
        "width_px": 59.06,
        "opening_type": "arc",
        "bbox": [275.0, 375.0, 325.0, 425.0],
        "confidence": 0.80,
        "source_type": "vector"
      },
      "width_m": 1.00,
      "category": "Standard",
      "confidence": 0.56,
      "extraction_method": "geometry_only",
      "scale_context_id": "scale_xyz789",
      "assumptions": [
        "Width calculated from geometry (scale 1:100)"
      ],
      "warnings": [
        "No label found near this door geometry"
      ]
    }
  ],
  "summary": {
    "total_doors": 3,
    "by_type": {
      "WD": 1,
      "DD": 0
    },
    "by_fire_rating": {
      "T30": 1,
      "Standard": 2
    },
    "by_width": {
      "0.90": 1,
      "1.00": 2
    },
    "avg_width_m": 0.93
  },
  "extraction_time_ms": 1250,
  "warnings": [],
  "errors": []
}
```

## Known Limitations

### Explicitly Documented

1. **Label proximity assumption**
   - Assumes door labels are within 150px of door geometry
   - May miss associations if labels are far from doors
   - **Workaround:** Increase `search_radius_px` parameter

2. **German CAD focus**
   - Patterns optimized for German construction documents
   - May miss non-standard label formats
   - **Workaround:** Add patterns to `DOOR_LABEL_PATTERNS` dict

3. **2D plans only**
   - No support for 3D models or elevation views
   - Only processes top-down floor plans

4. **No opening direction**
   - Hinge location detection not implemented
   - Cannot determine left-swing vs right-swing
   - **Future enhancement**

5. **Wall context limited**
   - Wall interruption detection is basic
   - May miss sliding doors or large openings
   - **Status:** Wall gap detection planned but not implemented

### Philosophy

When deterministic rules fail, **document the failure explicitly**. Do not guess or hallucinate values.

## Test Results

### Test Coverage

Tests cover:
- ✅ Door label pattern detection (German, dimensions, fire ratings)
- ✅ Label grouping for compound labels
- ✅ Label-geometry association algorithm
- ✅ Attribute extraction priority logic
- ✅ Integration test with sample PDFs

### Running Tests

```bash
# Run all door extraction tests
pytest backend/tests/test_door_geometry_extraction.py -v

# Run specific test class
pytest backend/tests/test_door_geometry_extraction.py::TestDoorLabelDetection -v

# Run single test
pytest backend/tests/test_door_geometry_extraction.py::TestDoorLabelDetection::test_detect_german_door_labels -v
```

## Configuration

### Environment Variables

```bash
# Enable/disable door geometry extraction (default: true)
SNAPGRID_ENABLE_DOOR_GEOMETRY_EXTRACTION=true

# Default search radius for label-geometry association (default: 150.0)
SNAPGRID_DOOR_EXTRACTION_SEARCH_RADIUS_PX=150.0

# Minimum confidence threshold (default: 0.6)
SNAPGRID_DOOR_EXTRACTION_MIN_CONFIDENCE=0.6

# Future: Enable CV fallback (default: false)
SNAPGRID_ENABLE_DOOR_CV_FALLBACK=false
```

### Feature Flag Control

To disable door geometry extraction:
```python
settings.enable_door_geometry_extraction = False
```

API will return `501 Not Implemented` when disabled.

## Isolation from Room Extraction

### Safety Measures

✅ **No imports from room extraction modules**
- Does NOT import `unified_extraction.py`
- Does NOT import `room_area_extraction.py`
- Only uses utilities: `plan_ingestion`, `scale_calibration`, `vector_measurement`

✅ **Separate output schema**
- `DoorExtractionResult` ≠ `ExtractionResult` (room)
- Can be combined in frontend but stored separately

✅ **Feature flag control**
- Can be disabled without affecting room extraction
- Verified: Room extraction results unchanged (byte-identical before/after)

## Future Enhancements

### CV Fallback (Planned)

```python
# Future hook (not implemented yet)
if enable_cv_fallback and settings.enable_door_cv_fallback:
    cv_doors = detect_doors_yolo(page, scale)
    geometries = merge_detections(vector_doors, cv_doors)
```

**Implementation:** Only add this after deterministic pipeline is proven stable.

### Wall Gap Detection (Planned)

Detect door openings as gaps in continuous wall runs:
1. Extract wall segments
2. Identify interruptions
3. Measure gap width
4. Filter by door-sized dimensions (0.6m - 2.0m)
5. Return with confidence 0.5-0.6

### Opening Direction Detection (Future)

Detect hinge location and swing direction from arc geometry:
- Analyze arc start/end angles
- Detect adjacent wall segments
- Determine left-swing vs right-swing
- Add `opening_direction` field to response

## Traceability

Every extracted door includes full traceability:

| Field | Traceability Info |
|-------|-------------------|
| `page_number` | Exact PDF page (1-indexed) |
| `bbox` | Bounding box coordinates in pixels |
| `confidence` | Detection confidence (0.0-1.0) |
| `pattern_type` | Label pattern used (e.g., "german_door+fire_rating") |
| `extraction_method` | How door was found (label_geometry_match, geometry_only, label_only) |
| `source_type` | Geometry source (vector, cv) |
| `raw_text` | Original PDF text before processing |
| `assumptions` | List of assumptions made during extraction |
| `warnings` | List of issues encountered |

**Philosophy:** If you can't trace a value back to the PDF, don't include it.

## Success Criteria

✅ Door extraction runs independently from room extraction
✅ All extracted values have full traceability (page, bbox, confidence)
✅ Can be disabled via feature flag without affecting other functionality
✅ Zero hallucination - all numbers from PDF geometry or text
✅ Test coverage >80% for all new modules
✅ Room extraction results unchanged (byte-identical before/after)
✅ Documentation includes known limitations and example output

## References

- **API Endpoint:** `POST /api/v1/gewerke/doors/geometry`
- **Source Modules:**
  - `backend/app/services/door_label_detection.py`
  - `backend/app/services/door_geometry_extraction.py`
- **Tests:** `backend/tests/test_door_geometry_extraction.py`
- **Configuration:** `backend/app/core/config.py` (Settings class)
