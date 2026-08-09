"""
Dimension Annotation Extraction

Pulls numeric dimension strings (e.g., "1.50", "2,75", "160,02°") directly
from the PDF text layer. This is a deterministic helper used by the CV
pipeline when no explicit scale is provided.
"""

from typing import List, Optional, Tuple
import logging
import re

from .cv_output_schema import CVElement, CVElementType, DerivedMeasure, generate_element_id

logger = logging.getLogger(__name__)

# Matches metric dimensions and angular annotations commonly seen on plans.
DIMENSION_PATTERN = re.compile(
    r"""
    ^-?\d{1,3}[.,]\d{2}$|        # 1.50 / 2,75
    ^-?\d{2,4}$|                 # 1500 (implicit mm)
    ^-?\d{1,3}[.,]\d{2}°$        # 160,02°
    """,
    re.VERBOSE,
)


def extract_dimension_annotations(pdf_path: str, page_number: int = 1) -> List[CVElement]:
    """Extract short numeric dimension strings with bounding boxes."""
    try:
        import fitz  # type: ignore
    except ImportError:
        logger.debug("PyMuPDF not installed; skipping dimension extraction")
        return []

    path = pdf_path
    elements: List[CVElement] = []

    doc = fitz.open(path)
    try:
        page = doc[page_number - 1]
        words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)

        for w in words:
            text = w[4].strip()
            if not DIMENSION_PATTERN.match(text):
                continue

            value, unit = _parse_dimension_value(text)
            x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
            bbox = (x0, y0, x1 - x0, y1 - y0)

            derived = [
                DerivedMeasure(
                    name="value",
                    value=value,
                    unit=unit or "unknown",
                    method="text_dimension",
                    confidence=0.65,
                )
            ]

            elements.append(
                CVElement(
                    element_id=generate_element_id("dim"),
                    element_type=CVElementType.DIMENSION,
                    page_number=page_number,
                    bbox=bbox,
                    confidence=0.65,
                    source="text_layer",
                    attributes={"text": text},
                    derived=derived,
                    needs_review=False if value is not None else True,
                )
            )

    finally:
        doc.close()

    return elements


def _parse_dimension_value(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Convert raw text to numeric value and unit."""
    unit = None
    if text.endswith("°"):
        unit = "deg"
        text = text[:-1]

    normalized = text.replace(",", ".")

    try:
        value = float(normalized)
    except ValueError:
        return None, unit

    # If value is large (>= 20) and no explicit unit, assume mm → convert to m
    if unit is None and value >= 20:
        unit = "mm"
        value = value / 1000.0
        unit = "m"
    elif unit is None:
        unit = "m"

    return value, unit

