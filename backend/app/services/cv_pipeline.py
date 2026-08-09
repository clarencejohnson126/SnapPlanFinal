"""
Computer Vision Pipeline Service

Object detection and image preprocessing for blueprint analysis.
Part of the Aufmaß Engine - Phase C implementation.

YOLO Integration:
- Set SNAPGRID_YOLO_MODEL_PATH to enable detection
- Set SNAPGRID_CV_PIPELINE_ENABLED=false to disable entirely
- Without YOLO configured, detection functions return empty results
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging
import time
import uuid

from ..core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Optional imports - gracefully handle missing dependencies
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV (cv2) not installed - CV preprocessing disabled")

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("Ultralytics not installed - YOLO detection disabled")

# Global model instance (lazy loaded)
_yolo_model: Optional[Any] = None
_yolo_model_path: Optional[str] = None


class ObjectType(Enum):
    """Types of objects detectable in construction blueprints."""

    DOOR = "door"
    WINDOW = "window"
    TOILET = "toilet"
    WASH_BASIN = "wash_basin"
    CONDUIT = "conduit"
    ROOM = "room"
    FIXTURE = "fixture"  # Sinks, toilets, appliances
    WALL = "wall"
    DIMENSION_LINE = "dimension_line"
    SCALE_ANNOTATION = "scale_annotation"
    STAIRS = "stairs"
    ELEVATOR = "elevator"
    COLUMN = "column"


@dataclass
class BoundingBox:
    """Bounding box for a detected object."""

    x: float  # Top-left x coordinate
    y: float  # Top-left y coordinate
    width: float
    height: float

    def to_tuple(self) -> Tuple[float, float, float, float]:
        """Return as (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @property
    def center(self) -> Tuple[float, float]:
        """Return center point of bounding box."""
        return (self.x + self.width / 2, self.y + self.height / 2)

    @property
    def area(self) -> float:
        """Return area of bounding box in pixels squared."""
        return self.width * self.height

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside this bounding box."""
        return (
            self.x <= x <= self.x + self.width
            and self.y <= y <= self.y + self.height
        )

    def overlaps(self, other: "BoundingBox") -> bool:
        """Check if this bounding box overlaps with another."""
        return not (
            self.x + self.width < other.x
            or other.x + other.width < self.x
            or self.y + self.height < other.y
            or other.y + other.height < self.y
        )


@dataclass
class DetectedObject:
    """
    Represents a detected object in a blueprint page.

    Attributes:
        object_id: Unique identifier for this detection
        object_type: Type of detected object
        bbox: Bounding box in pixel coordinates
        confidence: Detection confidence (0.0 - 1.0)
        page_number: Page where object was detected
        label: OCR-extracted label if found nearby
        attributes: Additional object-specific attributes
    """

    object_id: str
    object_type: ObjectType
    bbox: BoundingBox
    confidence: float
    page_number: int
    label: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "object_id": self.object_id,
            "object_type": self.object_type.value,
            "bbox": self.bbox.to_dict(),
            "confidence": self.confidence,
            "page_number": self.page_number,
            "label": self.label,
            "attributes": self.attributes,
        }


@dataclass
class DetectionResult:
    """Results from running object detection on a page."""

    document_id: str
    page_number: int
    objects: List[DetectedObject] = field(default_factory=list)
    processing_time_ms: int = 0
    model_version: str = "stub-v0"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "document_id": self.document_id,
            "page_number": self.page_number,
            "objects": [obj.to_dict() for obj in self.objects],
            "processing_time_ms": self.processing_time_ms,
            "model_version": self.model_version,
            "warnings": self.warnings,
        }

    @property
    def object_counts(self) -> Dict[str, int]:
        """Count objects by type."""
        counts: Dict[str, int] = {}
        for obj in self.objects:
            type_name = obj.object_type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts


def generate_object_id() -> str:
    """Generate a unique object ID."""
    return f"obj_{uuid.uuid4().hex[:12]}"


async def preprocess_page(
    image_path: str,
    enhance_contrast: bool = True,
    denoise: bool = True,
    binarize: bool = False,
) -> str:
    """
    Preprocess a blueprint page image for object detection.

    Args:
        image_path: Path to the source image
        enhance_contrast: Apply contrast enhancement
        denoise: Apply noise reduction
        binarize: Convert to binary image (for line detection)

    Returns:
        Path to the preprocessed image

    If OpenCV is not installed, the original path is returned unchanged.
    """
    if not CV2_AVAILABLE:
        return image_path

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Contrast Limited Adaptive Histogram Equalization
    if enhance_contrast:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

    # Denoise (use gentle filter to preserve thin lines)
    if denoise:
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=40, sigmaSpace=40)

    # Optional binarization for line extraction
    if binarize:
        gray = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=25,
            C=5,
        )

    # Persist to temp file
    import tempfile
    import os

    fd, out_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(out_path, gray)
    return out_path


async def detect_objects(
    image_path: str,
    object_types: Optional[List[ObjectType]] = None,
    confidence_threshold: float = 0.5,
    document_id: str = "",
    page_number: int = 1,
) -> DetectionResult:
    """
    Run object detection on a blueprint page.

    Args:
        image_path: Path to the page image
        object_types: Types of objects to detect (default: all)
        confidence_threshold: Minimum confidence for detections
        document_id: ID of the source document
        page_number: Page number in the document

    Returns:
        DetectionResult with detected objects

    Falls back to an empty result when YOLO is unavailable.
    """
    return run_object_detection_on_page(
        image_path=image_path,
        document_id=document_id,
        page_number=page_number,
        object_types=object_types,
        confidence_threshold=confidence_threshold,
    )


async def detect_doors(
    image_path: str,
    confidence_threshold: float = 0.5,
    document_id: str = "",
    page_number: int = 1,
) -> List[DetectedObject]:
    """
    Specialized door detection using arc + line pattern matching.

    Doors in floor plans typically consist of:
    - Arc: Quarter-circle showing swing direction
    - Line: Door leaf (the actual door panel)
    - Opening: Gap in wall where door sits

    Args:
        image_path: Path to the page image
        confidence_threshold: Minimum confidence for detections
        document_id: ID of the source document
        page_number: Page number in the document

    Returns:
        List of detected door objects with swing direction attributes

    """
    # Prefer production wall-opening detector; fall back to YOLO-only
    try:
        from .wall_opening_detector import detect_doors_yolo_primary
        from .wall_opening_detector import DetectionMode

        # detect_doors_yolo_primary renders internally; we only use page_number
        result = detect_doors_yolo_primary(
            pdf_path=document_id or image_path,
            page_number=page_number,
            confidence_threshold=confidence_threshold,
            mode=DetectionMode.BALANCED,
        )

        detected = []
        for door in result.doors:
            bbox = BoundingBox(
                x=door.center_x - door.width_px / 2,
                y=door.center_y - door.width_px / 2,
                width=door.width_px,
                height=door.width_px,
            )
            detected.append(
                DetectedObject(
                    object_id=door.opening_id,
                    object_type=ObjectType.DOOR,
                    bbox=bbox,
                    confidence=door.confidence,
                    page_number=page_number,
                    attributes={
                        "detection_method": "wall_opening",
                        "width_m": door.width_m,
                        "angle_degrees": door.angle_degrees,
                        "wall_thickness_px": door.wall_thickness_px,
                    },
                )
            )
        return detected
    except Exception as e:
        logger.debug(f"Door detection fallback to YOLO only: {e}")
        detection_result = run_object_detection_on_page(
            image_path=image_path,
            document_id=document_id or Path(image_path).stem,
            page_number=page_number,
            object_types=[ObjectType.DOOR],
            confidence_threshold=confidence_threshold,
        )
        return detection_result.objects


async def detect_rooms(
    image_path: str,
    min_area_px: float = 10000,
    document_id: str = "",
    page_number: int = 1,
) -> List[DetectedObject]:
    """
    Detect room boundaries from closed contours.

    Args:
        image_path: Path to the page image
        min_area_px: Minimum area in pixels to consider as room
        document_id: ID of the source document
        page_number: Page number in the document

    Returns:
        List of detected rooms with polygon points in attributes

    """
    try:
        from .room_polygon_detector import detect_room_polygons_from_image
        rooms = detect_room_polygons_from_image(
            file_path=image_path,
            page_number=page_number,
            dpi=150,
            min_room_area_m2=0.5,  # conservative
        )

        detected = []
        for room in rooms:
            # Compute bbox from polygon
            xs = [p[0] for p in room.points]
            ys = [p[1] for p in room.points]
            bbox = BoundingBox(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
            detected.append(
                DetectedObject(
                    object_id=room.id,
                    object_type=ObjectType.ROOM,
                    bbox=bbox,
                    confidence=room.confidence,
                    page_number=page_number,
                    label=room.label,
                    attributes={
                        "polygon": room.points,
                        "area_px": room.area_px,
                        "perimeter_px": room.perimeter_px,
                        "source": room.source,
                    },
                )
            )
        return detected
    except Exception as e:
        logger.debug(f"Room detection failed: {e}")
        return []


async def extract_labels(
    image_path: str,
    regions: Optional[List[BoundingBox]] = None,
    language: str = "deu",
) -> List[Dict[str, Any]]:
    """
    Extract text labels from an image using OCR.

    Args:
        image_path: Path to the image
        regions: Specific regions to extract from (default: full image)
        language: OCR language (default: German)

    Returns:
        List of dictionaries with text and bounding box

    """
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        logger.debug("OCR dependencies not installed; skipping label extraction")
        return []

    img = Image.open(image_path)
    results: List[Dict[str, Any]] = []

    if regions:
        for region in regions:
            crop = img.crop(
                (
                    int(region.x),
                    int(region.y),
                    int(region.x + region.width),
                    int(region.y + region.height),
                )
            )
            text = pytesseract.image_to_string(crop, lang=language).strip()
            if text:
                results.append({"text": text, "bbox": region.to_dict()})
    else:
        text = pytesseract.image_to_string(img, lang=language).strip()
        if text:
            results.append({"text": text, "bbox": None})

    return results


# ============================================
# YOLO Integration Functions
# ============================================


def get_yolo_model(settings: Optional[Settings] = None) -> Optional[Any]:
    """
    Get or initialize the YOLO model instance.

    Uses lazy loading to avoid loading the model until needed.
    Model is cached globally for reuse.

    Args:
        settings: Optional Settings instance

    Returns:
        YOLO model instance or None if not configured
    """
    global _yolo_model, _yolo_model_path

    if settings is None:
        settings = get_settings()

    # Check if YOLO is available and configured
    if not YOLO_AVAILABLE:
        logger.debug("YOLO not available - ultralytics not installed")
        return None

    if not settings.yolo_enabled:
        logger.debug("YOLO not enabled - model path not configured")
        return None

    model_path = settings.yolo_model_path

    # Check if model file exists
    if not Path(model_path).exists():
        logger.warning(f"YOLO model file not found: {model_path}")
        return None

    # Return cached model if same path
    if _yolo_model is not None and _yolo_model_path == model_path:
        return _yolo_model

    # Load new model
    try:
        logger.info(f"Loading YOLO model from: {model_path}")
        _yolo_model = YOLO(model_path)
        _yolo_model_path = model_path
        logger.info("YOLO model loaded successfully")
        return _yolo_model
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        return None


def is_cv_pipeline_available(settings: Optional[Settings] = None) -> bool:
    """
    Check if the CV pipeline is available and enabled.

    Returns True if:
    - cv_pipeline_enabled is True in settings
    - OpenCV is installed

    Note: YOLO may not be available even if pipeline is available.
    """
    if settings is None:
        settings = get_settings()

    return settings.cv_pipeline_enabled and CV2_AVAILABLE


def is_yolo_available(settings: Optional[Settings] = None) -> bool:
    """
    Check if YOLO detection is available and configured.

    Returns True if:
    - Ultralytics is installed
    - yolo_model_path is set
    - Model file exists
    """
    if settings is None:
        settings = get_settings()

    if not YOLO_AVAILABLE:
        return False

    if not settings.yolo_enabled:
        return False

    if settings.yolo_model_path and Path(settings.yolo_model_path).exists():
        return True

    return False


@dataclass
class CVPipelineStatus:
    """Status of the CV pipeline components."""

    cv_pipeline_enabled: bool
    opencv_installed: bool
    yolo_installed: bool
    yolo_model_configured: bool
    yolo_model_path: Optional[str]
    confidence_threshold: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "cv_pipeline_enabled": self.cv_pipeline_enabled,
            "opencv_installed": self.opencv_installed,
            "yolo_installed": self.yolo_installed,
            "yolo_model_configured": self.yolo_model_configured,
            "yolo_model_path": self.yolo_model_path,
            "confidence_threshold": self.confidence_threshold,
        }


def get_cv_pipeline_status(settings: Optional[Settings] = None) -> CVPipelineStatus:
    """
    Get the current status of the CV pipeline.

    Returns information about what features are available.
    """
    if settings is None:
        settings = get_settings()

    return CVPipelineStatus(
        cv_pipeline_enabled=settings.cv_pipeline_enabled,
        opencv_installed=CV2_AVAILABLE,
        yolo_installed=YOLO_AVAILABLE,
        yolo_model_configured=is_yolo_available(settings),
        yolo_model_path=settings.yolo_model_path,
        confidence_threshold=settings.yolo_confidence_threshold,
    )


def run_object_detection_on_page(
    image_path: str,
    document_id: str,
    page_number: int,
    object_types: Optional[List[ObjectType]] = None,
    confidence_threshold: Optional[float] = None,
    settings: Optional[Settings] = None,
) -> DetectionResult:
    """
    Run YOLO object detection on a blueprint page image.

    This is the main entry point for CV-based object detection.
    If YOLO is not configured, returns empty result with warning.

    Args:
        image_path: Path to the rendered page image
        document_id: ID of the source document
        page_number: Page number in the document
        object_types: Types of objects to detect (default: all)
        confidence_threshold: Minimum confidence (default: from settings)
        settings: Optional Settings instance

    Returns:
        DetectionResult with detected objects
    """
    if settings is None:
        settings = get_settings()

    if confidence_threshold is None:
        confidence_threshold = settings.yolo_confidence_threshold

    start_time = time.time()

    # Check if image exists
    if not Path(image_path).exists():
        return DetectionResult(
            document_id=document_id,
            page_number=page_number,
            objects=[],
            processing_time_ms=0,
            model_version="none",
            warnings=[f"Image file not found: {image_path}"],
        )

    # Check if YOLO is available
    model = get_yolo_model(settings)
    if model is None:
        return DetectionResult(
            document_id=document_id,
            page_number=page_number,
            objects=[],
            processing_time_ms=int((time.time() - start_time) * 1000),
            model_version="none",
            warnings=["YOLO not configured - set SNAPGRID_YOLO_MODEL_PATH to enable"],
        )

    try:
        # Run YOLO inference
        results = model(image_path, conf=confidence_threshold)

        # Process results
        detected_objects = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Extract box coordinates
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = result.names[cls_id]

                # Map YOLO class to ObjectType (if possible)
                obj_type = _map_yolo_class_to_object_type(cls_name)
                if obj_type is None:
                    logger.debug(f"Unknown YOLO class: {cls_name}")
                    continue

                # Filter by requested object types
                if object_types is not None and obj_type not in object_types:
                    continue

                bbox = BoundingBox(
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                )

                detected_obj = DetectedObject(
                    object_id=generate_object_id(),
                    object_type=obj_type,
                    bbox=bbox,
                    confidence=conf,
                    page_number=page_number,
                    label=None,  # TODO: OCR for nearby labels
                    attributes={
                        "yolo_class": cls_name,
                        "yolo_class_id": cls_id,
                    },
                )
                detected_objects.append(detected_obj)

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Get model version from file path
        model_version = Path(settings.yolo_model_path).stem if settings.yolo_model_path else "unknown"

        return DetectionResult(
            document_id=document_id,
            page_number=page_number,
            objects=detected_objects,
            processing_time_ms=processing_time_ms,
            model_version=model_version,
            warnings=[],
        )

    except Exception as e:
        logger.error(f"YOLO detection failed: {e}")
        return DetectionResult(
            document_id=document_id,
            page_number=page_number,
            objects=[],
            processing_time_ms=int((time.time() - start_time) * 1000),
            model_version="error",
            warnings=[f"Detection failed: {str(e)}"],
        )


def _map_yolo_class_to_object_type(class_name: str) -> Optional[ObjectType]:
    """
    Map YOLO class name to ObjectType enum.

    This mapping is configured for the floor-plan-object-detection model:
    https://github.com/sanatladkat/floor-plan-object-detection

    Model classes: Column, Curtain Wall, Dimension, Door, Railing,
                   Sliding Door, Stair Case, Wall, Window

    Args:
        class_name: YOLO class name from model

    Returns:
        ObjectType or None if no mapping exists
    """
    # Mapping for floor-plan-object-detection model
    mapping = {
        # Direct mappings
        "door": ObjectType.DOOR,
        "sliding door": ObjectType.DOOR,  # Also counts as door
        "window": ObjectType.WINDOW,
        "curtain wall": ObjectType.WINDOW,  # Glass walls = windows
        "wall": ObjectType.WALL,
        "column": ObjectType.COLUMN,
        "stair case": ObjectType.STAIRS,
        "dimension": ObjectType.DIMENSION_LINE,
        "railing": ObjectType.FIXTURE,  # Treat as fixture
        # Common aliases
        "stairs": ObjectType.STAIRS,
        "staircase": ObjectType.STAIRS,
        "room": ObjectType.ROOM,
        "toilet": ObjectType.FIXTURE,
        "sink": ObjectType.FIXTURE,
        "bathtub": ObjectType.FIXTURE,
        "shower": ObjectType.FIXTURE,
        "fixture": ObjectType.FIXTURE,
        "wc": ObjectType.TOILET,
        "toilet seat": ObjectType.TOILET,
        "lavatory": ObjectType.WASH_BASIN,
        "wash basin": ObjectType.WASH_BASIN,
        "washbasin": ObjectType.WASH_BASIN,
        "basin": ObjectType.WASH_BASIN,
        "conduit": ObjectType.CONDUIT,
        "pipe": ObjectType.CONDUIT,
        "duct": ObjectType.CONDUIT,
        "scale": ObjectType.SCALE_ANNOTATION,
        "elevator": ObjectType.ELEVATOR,
    }

    # Case-insensitive lookup
    return mapping.get(class_name.lower())


# ============================================
# PDF to Image Rendering
# ============================================


def render_pdf_page_to_image(
    pdf_path: str,
    page_number: int = 1,
    dpi: int = 150,
    output_path: Optional[str] = None,
) -> str:
    """
    Render a PDF page to an image for CV processing.

    Args:
        pdf_path: Path to the PDF file
        page_number: Page number (1-indexed)
        dpi: Resolution for rendering
        output_path: Optional output path (default: temp file)

    Returns:
        Path to the rendered image

    Raises:
        ImportError: If PyMuPDF is not available
        FileNotFoundError: If PDF doesn't exist
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF rendering")

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    try:
        page_idx = page_number - 1
        if page_idx < 0 or page_idx >= len(doc):
            raise ValueError(f"Invalid page {page_number}, PDF has {len(doc)} pages")

        page = doc[page_idx]

        # Render at specified DPI
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Determine output path
        if output_path is None:
            import tempfile
            fd, output_path = tempfile.mkstemp(suffix=".png")
            import os
            os.close(fd)

        pix.save(output_path)
        logger.info(f"Rendered page {page_number} at {dpi} DPI to {output_path}")

        return output_path

    finally:
        doc.close()


# ============================================
# Hybrid Detection (Vector + YOLO)
# ============================================


def detect_doors_hybrid(
    pdf_path: str,
    page_number: int = 1,
    scale: int = 100,
    dpi: int = 150,
    use_yolo: bool = True,
    use_vector: bool = True,
    confidence_threshold: float = 0.5,
    settings: Optional[Settings] = None,
) -> DetectionResult:
    """
    Hybrid door detection combining vector analysis and YOLO.

    Strategy:
    1. Run vector-based detection (fast, precise for CAD)
    2. Run YOLO detection (catches non-standard symbols)
    3. Merge results, removing duplicates

    Args:
        pdf_path: Path to the PDF file
        page_number: Page number (1-indexed)
        scale: Drawing scale denominator (e.g., 100 for 1:100)
        dpi: DPI for rendering
        use_yolo: Whether to use YOLO detection
        use_vector: Whether to use vector detection
        confidence_threshold: Minimum confidence
        settings: Optional Settings instance

    Returns:
        DetectionResult with merged detections
    """
    if settings is None:
        settings = get_settings()

    start_time = time.time()
    all_objects: List[DetectedObject] = []
    warnings: List[str] = []
    document_id = Path(pdf_path).stem

    # Vector-based detection
    if use_vector:
        try:
            from .vector_measurement import measure_doors_on_page

            INCHES_PER_METER = 39.3701
            pixels_per_meter = (1.0 / scale) * INCHES_PER_METER * dpi

            vector_doors = measure_doors_on_page(
                path=pdf_path,
                page_number=page_number,
                pixels_per_meter=pixels_per_meter,
                dpi=dpi,
            )

            for door in vector_doors:
                # Create bounding box around door arc
                cx, cy = door.arc_center
                r = door.arc_radius_px
                bbox = BoundingBox(
                    x=cx - r,
                    y=cy - r,
                    width=r * 2,
                    height=r * 2,
                )

                detected_obj = DetectedObject(
                    object_id=door.door_id,
                    object_type=ObjectType.DOOR,
                    bbox=bbox,
                    confidence=door.confidence,
                    page_number=page_number,
                    label=door.label,
                    attributes={
                        "detection_method": "vector",
                        "width_m": door.width_m,
                        "arc_radius_px": door.arc_radius_px,
                    },
                )
                all_objects.append(detected_obj)

            logger.info(f"Vector detection found {len(vector_doors)} doors")

        except Exception as e:
            logger.warning(f"Vector detection failed: {e}")
            warnings.append(f"Vector detection failed: {str(e)}")

    # YOLO-based detection
    if use_yolo and is_yolo_available(settings):
        try:
            # Render PDF page to image
            image_path = render_pdf_page_to_image(pdf_path, page_number, dpi)

            try:
                yolo_result = run_object_detection_on_page(
                    image_path=image_path,
                    document_id=document_id,
                    page_number=page_number,
                    object_types=[ObjectType.DOOR],
                    confidence_threshold=confidence_threshold,
                    settings=settings,
                )

                # Add YOLO detections (marking source)
                for obj in yolo_result.objects:
                    obj.attributes["detection_method"] = "yolo"
                    all_objects.append(obj)

                logger.info(f"YOLO detection found {len(yolo_result.objects)} doors")
                warnings.extend(yolo_result.warnings)

            finally:
                # Clean up temp image
                import os
                if os.path.exists(image_path):
                    os.remove(image_path)

        except Exception as e:
            logger.warning(f"YOLO detection failed: {e}")
            warnings.append(f"YOLO detection failed: {str(e)}")

    elif use_yolo and not is_yolo_available(settings):
        warnings.append("YOLO not available - set SNAPGRID_YOLO_MODEL_PATH")

    # Remove duplicate detections (overlapping bboxes)
    final_objects = _merge_overlapping_detections(all_objects)

    processing_time_ms = int((time.time() - start_time) * 1000)

    return DetectionResult(
        document_id=document_id,
        page_number=page_number,
        objects=final_objects,
        processing_time_ms=processing_time_ms,
        model_version="hybrid-v1",
        warnings=warnings,
    )


def _merge_overlapping_detections(
    objects: List[DetectedObject],
    iou_threshold: float = 0.5,
) -> List[DetectedObject]:
    """
    Merge overlapping detections, keeping highest confidence.

    Args:
        objects: List of detected objects
        iou_threshold: IoU threshold for considering overlap

    Returns:
        Deduplicated list of objects
    """
    if len(objects) <= 1:
        return objects

    # Sort by confidence (descending)
    sorted_objects = sorted(objects, key=lambda x: x.confidence, reverse=True)

    kept: List[DetectedObject] = []
    suppressed: set = set()

    for i, obj in enumerate(sorted_objects):
        if i in suppressed:
            continue

        kept.append(obj)

        # Suppress lower-confidence overlapping detections
        for j in range(i + 1, len(sorted_objects)):
            if j in suppressed:
                continue

            iou = _compute_iou(obj.bbox, sorted_objects[j].bbox)
            if iou > iou_threshold:
                suppressed.add(j)

    return kept


def _compute_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """Compute Intersection over Union for two bounding boxes."""
    x1 = max(box1.x, box2.x)
    y1 = max(box1.y, box2.y)
    x2 = min(box1.x + box1.width, box2.x + box2.width)
    y2 = min(box1.y + box1.height, box2.y + box2.height)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    union = box1.area + box2.area - intersection

    return intersection / union if union > 0 else 0.0


# ============================================
# Detection Persistence Helper
# ============================================


def store_detections(
    result: DetectionResult,
    file_id: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Store detection results to Supabase.

    Args:
        result: DetectionResult to store
        file_id: File ID to associate with detections
        settings: Optional Settings instance

    Returns:
        Dict with success status and stored IDs
    """
    if settings is None:
        settings = get_settings()

    if not settings.supabase_enabled:
        return {
            "supabase_enabled": False,
            "stored_count": 0,
        }

    # Import here to avoid circular dependency
    from .supabase_client import get_supabase_client

    client = get_supabase_client(settings)
    if client is None:
        return {
            "supabase_enabled": True,
            "success": False,
            "error": "Failed to initialize Supabase client",
        }

    analysis_id = str(uuid.uuid4())
    stored_ids = []
    errors = []

    for obj in result.objects:
        try:
            detection_data = {
                "id": obj.object_id,
                "file_id": file_id,
                "analysis_id": analysis_id,
                "object_type": obj.object_type.value,
                "label": obj.label,
                "page_number": obj.page_number,
                "bbox_x": obj.bbox.x,
                "bbox_y": obj.bbox.y,
                "bbox_width": obj.bbox.width,
                "bbox_height": obj.bbox.height,
                "confidence": obj.confidence,
                "detection_method": "yolo",
                "model_version": result.model_version,
                "attributes": obj.attributes,
            }

            insert_result = client.table("detected_objects").insert(detection_data).execute()
            stored_ids.append(obj.object_id)

        except Exception as e:
            logger.error(f"Failed to store detection {obj.object_id}: {e}")
            errors.append(str(e))

    return {
        "supabase_enabled": True,
        "success": len(errors) == 0,
        "analysis_id": analysis_id,
        "stored_count": len(stored_ids),
        "stored_ids": stored_ids,
        "errors": errors if errors else None,
    }
