"""
Geometry/Symbol CV Analysis Pipeline

Adds a computer-vision-first path for plans without usable room text.
The pipeline is isolated from the deterministic m² extractor and can be
feature-flagged via Settings.cv_symbol_pipeline_enabled.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import logging
import os
import tempfile
import time

from ..core.config import Settings, get_settings
from .cv_pipeline import (
    render_pdf_page_to_image,
    run_object_detection_on_page,
    ObjectType,
    DetectedObject,
    BoundingBox,
    _compute_iou,
)
from .cv_output_schema import (
    CVElement,
    CVElementType,
    CVExtractionResult,
    CVPageResult,
    DerivedMeasure,
    generate_element_id,
)
from .scale_calibration import ScaleContext
from .debug_overlay import draw_overlays

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.debug("OpenCV not available for classical CV")

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


class DetectionTarget(str, Enum):
    DOORS = "doors"
    WINDOWS = "windows"
    WALLS = "walls"
    TOILETS = "toilets"
    WASH_BASINS = "wash_basins"
    CONDUITS = "conduits"
    DIMENSIONS = "dimensions"
    ROOMS = "rooms"


@dataclass
class CVAnalysisConfig:
    """Runtime configuration for a CV analysis run."""

    dpi: int = 200
    use_yolo: bool = True
    use_classical: bool = True
    confidence_threshold: float = 0.35
    needs_review_threshold: float = 0.5
    debug: bool = False
    keep_intermediate: bool = False


def run_cv_page_analysis(
    pdf_path: str,
    page_number: int = 1,
    detection_targets: Optional[Sequence[DetectionTarget]] = None,
    scale_context: Optional[ScaleContext] = None,
    settings: Optional[Settings] = None,
    config: Optional[CVAnalysisConfig] = None,
) -> CVPageResult:
    """
    Main entry point for CV-based page analysis.

    - Renders PDF to raster
    - Runs YOLO detection (if available)
    - Runs classical detectors (wall mask, openings, vector thin-lines)
    - Produces explainable JSON with derived measurements
    """
    settings = settings or get_settings()
    if config is None:
        config = CVAnalysisConfig(
            dpi=settings.cv_default_dpi,
            use_yolo=settings.cv_pipeline_enabled,
            use_classical=settings.cv_classical_enabled,
            confidence_threshold=settings.yolo_confidence_threshold,
            needs_review_threshold=settings.cv_needs_review_threshold,
            debug=settings.cv_debug_overlays,
        )

    if not settings.cv_symbol_pipeline_enabled:
        return CVPageResult(
            document_id=Path(pdf_path).stem,
            page_number=page_number,
            dpi=config.dpi,
            elements=[],
            warnings=["CV symbol pipeline disabled via settings"],
        )

    start = time.time()
    detection_targets = detection_targets or list(DetectionTarget)
    document_id = Path(pdf_path).stem
    warnings: List[str] = []
    elements: List[CVElement] = []
    debug_images: Dict[str, str] = {}

    image_path = render_pdf_page_to_image(pdf_path, page_number, dpi=config.dpi)
    temp_paths = [image_path]

    try:
        # -----------------------------
        # YOLO detection (symbol model)
        # -----------------------------
        if config.use_yolo:
            requested_types = _map_targets_to_object_types(detection_targets)
            yolo_result = run_object_detection_on_page(
                image_path=image_path,
                document_id=document_id,
                page_number=page_number,
                object_types=requested_types,
                confidence_threshold=config.confidence_threshold,
                settings=settings,
            )
            warnings.extend(yolo_result.warnings)

            for obj in yolo_result.objects:
                elem = _detected_to_element(
                    obj,
                    scale_context=scale_context,
                    needs_review_threshold=config.needs_review_threshold,
                    confidence_floor=settings.cv_confidence_floor,
                )
                elements.append(elem)

        # -----------------------------
        # Classical detection
        # -----------------------------
        if config.use_classical:
            classical_elements, classical_debug, classical_warnings = _run_classical_detectors(
                pdf_path=pdf_path,
                image_path=image_path,
                page_number=page_number,
                detection_targets=detection_targets,
                scale_context=scale_context,
                dpi=config.dpi,
                needs_review_threshold=config.needs_review_threshold,
                confidence_floor=settings.cv_confidence_floor,
            )
            elements.extend(classical_elements)
            debug_images.update(classical_debug)
            warnings.extend(classical_warnings)

        # -----------------------------
        # Deduplicate across detectors
        # -----------------------------
        elements = _deduplicate_elements(elements)

        # -----------------------------
        # Debug overlay
        # -----------------------------
        if config.debug and CV2_AVAILABLE:
            overlay_dir = _ensure_debug_dir()
            overlay_path = os.path.join(
                overlay_dir, f"{document_id}_p{page_number}_overlay.png"
            )
            overlay = draw_overlays(image_path, elements, output_path=overlay_path)
            if overlay:
                debug_images["overlay"] = overlay

        processing_ms = int((time.time() - start) * 1000)

        return CVPageResult(
            document_id=document_id,
            page_number=page_number,
            dpi=config.dpi,
            elements=elements,
            warnings=warnings,
            debug_images=debug_images,
            processing_time_ms=processing_ms,
        )

    finally:
        if not config.keep_intermediate:
            for p in temp_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass


def run_cv_document_analysis(
    pdf_path: str,
    pages: Optional[Sequence[int]] = None,
    detection_targets: Optional[Sequence[DetectionTarget]] = None,
    scale_context: Optional[ScaleContext] = None,
    settings: Optional[Settings] = None,
    config: Optional[CVAnalysisConfig] = None,
) -> CVExtractionResult:
    """Multi-page convenience wrapper."""
    document_id = Path(pdf_path).stem
    settings = settings or get_settings()
    config = config or CVAnalysisConfig(dpi=settings.cv_default_dpi)

    if pages is None:
        pages = [1]

    page_results = []
    warnings: List[str] = []

    # Attempt scale detection if not provided
    if scale_context is None:
        try:
            from .plan_ingestion import load_plan_document
            from .scale_calibration import detect_scale_from_document

            plan = load_plan_document(pdf_path)
            scale_context = detect_scale_from_document(plan, search_pages=list(pages))
            if not getattr(scale_context, "has_scale", False):
                warnings.append("Scale not detected; derived measurements set to 'unknown'")
        except Exception as exc:
            warnings.append(f"Scale detection failed: {exc}")
            scale_context = None

    for page in pages:
        try:
            page_results.append(
                run_cv_page_analysis(
                    pdf_path=pdf_path,
                    page_number=page,
                    detection_targets=detection_targets,
                    scale_context=scale_context,
                    settings=settings,
                    config=config,
                )
            )
        except Exception as exc:
            warnings.append(f"Page {page}: {exc}")

    return CVExtractionResult(
        document_id=document_id,
        pages=page_results,
        scale_string=getattr(scale_context, "scale_string", None) if scale_context else None,
        pixels_per_meter=getattr(scale_context, "pixels_per_meter", None) if scale_context else None,
        warnings=warnings,
    )


# -----------------------------------------------------------------------------
# Classical Detectors
# -----------------------------------------------------------------------------


def _run_classical_detectors(
    pdf_path: str,
    image_path: str,
    page_number: int,
    detection_targets: Sequence[DetectionTarget],
    scale_context: Optional[ScaleContext],
    dpi: int,
    needs_review_threshold: float,
    confidence_floor: float,
) -> Tuple[List[CVElement], Dict[str, str], List[str]]:
    """Run wall mask, openings, vector thin-line detectors."""
    elements: List[CVElement] = []
    debug_images: Dict[str, str] = {}
    warnings: List[str] = []

    # Wall mask once; reused for walls, doors/windows fallback
    wall_mask = None
    wall_mask_info: Dict[str, Any] = {}

    if CV2_AVAILABLE:
        try:
            from .wall_opening_detector import render_pdf_page_high_dpi, extract_wall_mask

            rendered_path = render_pdf_page_high_dpi(pdf_path, page_number, dpi)
            wall_mask, wall_mask_info = extract_wall_mask(
                rendered_path,
                debug_output_dir=None,
            )
            # Keep rendered path for cleanup and possible debug
            if rendered_path != image_path:
                try:
                    os.remove(rendered_path)
                except Exception:
                    pass
            if wall_mask is None or (np is not None and np.sum(wall_mask) == 0):
                warnings.append("Wall mask empty - skipping wall/window detection")
        except Exception as exc:
            warnings.append(f"Wall mask failed: {exc}")

    # Walls
    if DetectionTarget.WALLS in detection_targets and wall_mask is not None:
        walls = _wall_mask_to_elements(
            wall_mask=wall_mask,
            page_number=page_number,
            scale_context=scale_context,
            needs_review_threshold=needs_review_threshold,
            confidence_floor=confidence_floor,
        )
        elements.extend(walls)

    # Doors & windows using openings on wall mask
    if wall_mask is not None and CV2_AVAILABLE:
        openings_elems, open_warnings = _openings_to_doors_windows(
            wall_mask=wall_mask,
            pdf_path=pdf_path,
            page_number=page_number,
            scale_context=scale_context,
            detection_targets=detection_targets,
            needs_review_threshold=needs_review_threshold,
            confidence_floor=confidence_floor,
        )
        elements.extend(openings_elems)
        warnings.extend(open_warnings)

    # Conduits via thin vector lines
    if DetectionTarget.CONDUITS in detection_targets:
        conduits, conduit_warn = _detect_conduits_vector(
            pdf_path,
            page_number,
            scale_context,
            needs_review_threshold,
            confidence_floor,
        )
        elements.extend(conduits)
        warnings.extend(conduit_warn)

    # Dimension annotations
    if DetectionTarget.DIMENSIONS in detection_targets:
        try:
            from .dimension_extraction import extract_dimension_annotations

            dims = extract_dimension_annotations(pdf_path, page_number)
            for dim in dims:
                dim.needs_review = dim.confidence < needs_review_threshold
            elements.extend(dims)
        except Exception as exc:
            warnings.append(f"Dimension extraction failed: {exc}")

    # Room polygons (geometry only, no text)
    if DetectionTarget.ROOMS in detection_targets:
        try:
            from .room_polygon_detector import detect_room_polygons_from_pdf

            rooms = detect_room_polygons_from_pdf(
                pdf_path,
                page_number=page_number,
                dpi=dpi,
                min_room_area_m2=0.5,
            )
            for room in rooms:
                xs = [p[0] for p in room.points]
                ys = [p[1] for p in room.points]
                bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                derived = []
                if scale_context and scale_context.has_scale and room.area_px:
                    area_m2 = room.area_px / (scale_context.pixels_per_meter ** 2)
                    derived.append(
                        DerivedMeasure(
                            name="area",
                            value=area_m2,
                            unit="m2",
                            method="polygon_area",
                            confidence=room.confidence,
                        )
                    )
                elements.append(
                    CVElement(
                        element_id=room.id,
                        element_type=CVElementType.ROOM_BOUNDARY,
                        page_number=page_number,
                        bbox=bbox,
                        confidence=room.confidence,
                        source="room_contour",
                        polygon=room.points,
                        attributes={"source": room.source},
                        derived=derived,
                        needs_review=room.confidence < needs_review_threshold,
                    )
                )
        except Exception as exc:
            warnings.append(f"Room polygon detection failed: {exc}")

    return elements, debug_images, warnings


def _wall_mask_to_elements(
    wall_mask: "np.ndarray",
    page_number: int,
    scale_context: Optional[ScaleContext],
    needs_review_threshold: float,
    confidence_floor: float,
) -> List[CVElement]:
    """Convert binary wall mask to CVElement walls via contour bounding boxes."""
    if not CV2_AVAILABLE:
        return []

    contours, _ = cv2.findContours(wall_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    elements: List[CVElement] = []

    for idx, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        length_px = max(w, h)
        derived: List[DerivedMeasure] = []

        if scale_context and getattr(scale_context, "pixels_per_meter", None):
            length_m = length_px / scale_context.pixels_per_meter
            derived.append(
                DerivedMeasure(
                    name="length",
                    value=round(length_m, 3),
                    unit="m",
                    method="bbox_scaled",
                    confidence=0.7,
                )
            )

        confidence = 0.7
        needs_review = confidence < needs_review_threshold or (derived and any(d.value is None for d in derived))

        elements.append(
            CVElement(
                element_id=generate_element_id("wall"),
                element_type=CVElementType.WALL,
                page_number=page_number,
                bbox=(float(x), float(y), float(w), float(h)),
                confidence=confidence,
                source="wall_mask",
                attributes={"contour_area_px": float(cv2.contourArea(contour))},
                derived=derived,
                needs_review=needs_review or confidence < confidence_floor,
            )
        )

    return elements


def _openings_to_doors_windows(
    wall_mask: "np.ndarray",
    pdf_path: str,
    page_number: int,
    scale_context: Optional[ScaleContext],
    detection_targets: Sequence[DetectionTarget],
    needs_review_threshold: float,
    confidence_floor: float,
) -> Tuple[List[CVElement], List[str]]:
    """Find wall openings and classify as doors/windows."""
    elements: List[CVElement] = []
    warnings: List[str] = []

    if not CV2_AVAILABLE:
        return elements, warnings

    try:
        from .wall_opening_detector import find_wall_openings
    except Exception as exc:
        warnings.append(f"Openings detection unavailable: {exc}")
        return elements, warnings

    # Estimate pixels_per_meter from scale_context if possible; otherwise fallback to heuristic
    if scale_context and getattr(scale_context, "pixels_per_meter", None):
        ppm = scale_context.pixels_per_meter
    else:
        # Heuristic: assume 1:100 at current DPI
        dpi_guess = 200
        ppm = (1.0 / 100.0) * (1 / 0.0254) * dpi_guess
        warnings.append("Scale missing; using heuristic 1:100 for opening size filters")

    min_opening_px = int(0.6 * ppm)   # 0.6m minimum width
    max_opening_px = int(4.0 * ppm)   # up to large sliding door/window

    openings = find_wall_openings(
        wall_mask,
        min_opening_px=min_opening_px,
        max_opening_px=max_opening_px,
        page_number=page_number,
    )

    for opening in openings:
        bbox = (
            opening.center_x - opening.width_px / 2,
            opening.center_y - opening.width_px / 2,
            opening.width_px,
            opening.width_px,
        )

        width_m = None
        if scale_context and getattr(scale_context, "pixels_per_meter", None):
            width_m = opening.width_px / scale_context.pixels_per_meter

        derived = []
        if width_m is not None:
            derived.append(
                DerivedMeasure(
                    name="width",
                    value=round(width_m, 3),
                    unit="m",
                    method="opening_width",
                    confidence=opening.confidence,
                )
            )

        # Classification: if doors requested, treat as door else window
        elem_type = CVElementType.WINDOW
        if DetectionTarget.DOORS in detection_targets:
            # Doors preferred for openings within DIN range
            if width_m and 0.6 <= width_m <= 1.3:
                elem_type = CVElementType.DOOR
            elif width_m is None:
                elem_type = CVElementType.DOOR

        confidence = opening.confidence
        needs_review = confidence < needs_review_threshold or (width_m is None)

        if elem_type == CVElementType.DOOR and DetectionTarget.DOORS not in detection_targets:
            continue
        if elem_type == CVElementType.WINDOW and DetectionTarget.WINDOWS not in detection_targets:
            continue

        elements.append(
            CVElement(
                element_id=opening.opening_id,
                element_type=elem_type,
                page_number=page_number,
                bbox=bbox,
                confidence=confidence,
                source="wall_opening",
                attributes={
                    "angle_degrees": opening.angle_degrees,
                    "wall_thickness_px": opening.wall_thickness_px,
                },
                derived=derived,
                needs_review=needs_review or confidence < confidence_floor,
            )
        )

    return elements, warnings


def _detect_conduits_vector(
    pdf_path: str,
    page_number: int,
    scale_context: Optional[ScaleContext],
    needs_review_threshold: float,
    confidence_floor: float,
) -> Tuple[List[CVElement], List[str]]:
    """Detect conduits as thin vector line segments."""
    try:
        from .vector_measurement import extract_line_segments_from_page, FITZ_AVAILABLE
    except Exception as exc:
        return [], [f"Vector extraction unavailable: {exc}"]

    if not FITZ_AVAILABLE:
        return [], ["PyMuPDF missing; conduit detection skipped"]

    segments = extract_line_segments_from_page(
        path=pdf_path,
        page_number=page_number,
        dpi=150,
        min_length_px=30.0,
    )

    elements: List[CVElement] = []
    warnings: List[str] = []

    for seg in segments:
        # Conduits are thin lines; prefer stroke_width <= 1.2
        if seg.stroke_width is not None and seg.stroke_width > 1.2:
            continue

        length_px = seg.length_px
        if length_px < 40:
            continue

        length_m = None
        if scale_context and getattr(scale_context, "pixels_per_meter", None):
            length_m = length_px / scale_context.pixels_per_meter

        derived = [
            DerivedMeasure(
                name="length",
                value=round(length_m, 3) if length_m is not None else None,
                unit="m" if length_m is not None else "unknown",
                method="vector_geometry",
                confidence=0.6,
            )
        ]

        needs_review = (
            length_m is None or derived[0].confidence < needs_review_threshold
        )

        bbox = (
            min(seg.x1, seg.x2),
            min(seg.y1, seg.y2),
            abs(seg.x2 - seg.x1),
            abs(seg.y2 - seg.y1),
        )

        elements.append(
            CVElement(
                element_id=generate_element_id("conduit"),
                element_type=CVElementType.CONDUIT,
                page_number=page_number,
                bbox=bbox,
                confidence=0.6,
                source="vector_lines",
                attributes={
                    "stroke_width": seg.stroke_width,
                    "angle_degrees": seg.angle_degrees,
                },
                derived=derived,
                needs_review=needs_review or 0.6 < confidence_floor,
            )
        )

    return elements, warnings


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def _map_targets_to_object_types(targets: Sequence[DetectionTarget]) -> List[ObjectType]:
    """Map DetectionTarget enums to YOLO ObjectType list."""
    mapping = {
        DetectionTarget.DOORS: ObjectType.DOOR,
        DetectionTarget.WINDOWS: ObjectType.WINDOW,
        DetectionTarget.TOILETS: ObjectType.TOILET,
        DetectionTarget.WASH_BASINS: ObjectType.WASH_BASIN,
        DetectionTarget.CONDUITS: ObjectType.CONDUIT,
        DetectionTarget.WALLS: ObjectType.WALL,
    }
    return [mapping[t] for t in targets if t in mapping]


def _detected_to_element(
    obj: DetectedObject,
    scale_context: Optional[ScaleContext],
    needs_review_threshold: float,
    confidence_floor: float,
) -> CVElement:
    """Convert DetectedObject to CVElement with derived measures."""
    bbox = obj.bbox.to_tuple()
    derived: List[DerivedMeasure] = []
    needs_review = obj.confidence < needs_review_threshold

    # Derived measurements
    if obj.object_type in {ObjectType.WALL, ObjectType.CONDUIT}:
        length_px = max(obj.bbox.width, obj.bbox.height)
        length_m = None
        if scale_context and getattr(scale_context, "pixels_per_meter", None):
            length_m = length_px / scale_context.pixels_per_meter
        derived.append(
            DerivedMeasure(
                name="length",
                value=round(length_m, 3) if length_m is not None else None,
                unit="m" if length_m is not None else "unknown",
                method="bbox_scaled",
                confidence=obj.confidence,
            )
        )
        if length_m is None:
            needs_review = True

    if obj.object_type in {ObjectType.DOOR, ObjectType.WINDOW, ObjectType.TOILET, ObjectType.WASH_BASIN}:
        width_m = None
        if scale_context and getattr(scale_context, "pixels_per_meter", None):
            width_px = max(obj.bbox.width, obj.bbox.height)
            width_m = width_px / scale_context.pixels_per_meter
        derived.append(
            DerivedMeasure(
                name="width" if obj.object_type in {ObjectType.DOOR, ObjectType.WINDOW} else "count",
                value=round(width_m, 3) if width_m is not None else (1 if obj.object_type in {ObjectType.TOILET, ObjectType.WASH_BASIN} else None),
                unit="m" if width_m is not None else ("count" if obj.object_type in {ObjectType.TOILET, ObjectType.WASH_BASIN} else "unknown"),
                method="bbox_scaled" if width_m is not None else "count",
                confidence=obj.confidence,
            )
        )
        if width_m is None and obj.object_type in {ObjectType.DOOR, ObjectType.WINDOW}:
            needs_review = True

    element_type = _object_type_to_element_type(obj.object_type)

    return CVElement(
        element_id=obj.object_id,
        element_type=element_type,
        page_number=obj.page_number,
        bbox=bbox,
        confidence=obj.confidence,
        source=obj.attributes.get("detection_method", "yolo"),
        attributes=obj.attributes,
        derived=derived,
        needs_review=needs_review or obj.confidence < confidence_floor,
    )


def _object_type_to_element_type(obj_type: ObjectType) -> CVElementType:
    mapping = {
        ObjectType.DOOR: CVElementType.DOOR,
        ObjectType.WINDOW: CVElementType.WINDOW,
        ObjectType.WALL: CVElementType.WALL,
        ObjectType.TOILET: CVElementType.TOILET,
        ObjectType.WASH_BASIN: CVElementType.WASH_BASIN,
        ObjectType.CONDUIT: CVElementType.CONDUIT,
        ObjectType.ROOM: CVElementType.ROOM_BOUNDARY,
        ObjectType.DIMENSION_LINE: CVElementType.DIMENSION,
        ObjectType.SCALE_ANNOTATION: CVElementType.SCALE,
    }
    return mapping.get(obj_type, CVElementType.UNKNOWN)


def _deduplicate_elements(elements: List[CVElement], iou_threshold: float = 0.5) -> List[CVElement]:
    """Merge overlapping detections, keeping higher-confidence elements."""
    if len(elements) <= 1:
        return elements

    sorted_elems = sorted(elements, key=lambda e: e.confidence, reverse=True)
    kept: List[CVElement] = []

    for candidate in sorted_elems:
        duplicate = False
        for existing in kept:
            if _compute_iou_bbox(existing.bbox, candidate.bbox) > iou_threshold and existing.element_type == candidate.element_type:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def _compute_iou_bbox(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Compute IoU between two (x, y, w, h) boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xa = max(x1, x2)
    ya = max(y1, y2)
    xb = min(x1 + w1, x2 + w2)
    yb = min(y1 + h1, y2 + h2)

    if xb <= xa or yb <= ya:
        return 0.0

    inter = (xb - xa) * (yb - ya)
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0.0


def _ensure_debug_dir() -> str:
    path = Path(tempfile.gettempdir()) / "snapplan_cv_debug"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
