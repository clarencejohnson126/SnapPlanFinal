"""
Debug overlay utilities for CV outputs.

Creates PNG overlays with bounding boxes and labels so analysts can verify
detections manually without affecting the deterministic pipelines.
"""

from pathlib import Path
from typing import List, Optional, Tuple
import os

import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not installed - debug overlays disabled")

COLOR_TABLE = {
    "door": (0, 165, 255),        # orange
    "window": (255, 0, 0),        # blue
    "wall": (0, 255, 0),          # green
    "toilet": (128, 0, 128),      # purple
    "wash_basin": (255, 105, 180),# pink
    "conduit": (0, 255, 255),     # yellow
    "dimension": (255, 255, 255), # white
    "unknown": (128, 128, 128),
}


def draw_overlays(
    image_path: str,
    elements: List["CVElementProtocol"],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Draw colored bounding boxes for the provided elements.

    Args:
        image_path: Source image path
        elements: Objects exposing type, bbox, confidence
        output_path: Optional target path; temp file is created otherwise
    """
    if not CV2_AVAILABLE:
        return None

    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"Failed to read image for overlay: {image_path}")
        return None

    if output_path is None:
        fd, output_path = _temp_png()
        os.close(fd)

    for el in elements:
        x, y, w, h = el.bbox
        color = COLOR_TABLE.get(el.element_type.value if hasattr(el, "element_type") else getattr(el, "type", "unknown"), (128, 128, 128))
        cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), color, 2)

        label = f"{getattr(el, 'element_type', getattr(el, 'type', ''))}: {el.confidence:.2f}"
        cv2.putText(
            img,
            label,
            (int(x), max(15, int(y) - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.imwrite(output_path, img)
    return output_path


def _temp_png() -> Tuple[int, str]:
    import tempfile
    return tempfile.mkstemp(suffix=".png")


class CVElementProtocol:
    """Structural protocol to type-hint overlay inputs."""

    bbox: Tuple[float, float, float, float]
    confidence: float
    element_type: any
    type: str

