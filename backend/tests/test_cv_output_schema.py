import pytest

from app.services.cv_output_schema import (
    CVElement,
    CVElementType,
    DerivedMeasure,
    CVPageResult,
)


def test_cv_element_to_dict():
    dm = DerivedMeasure(name="length", value=1.23, unit="m", method="bbox_scaled", confidence=0.8)
    elem = CVElement(
        element_id="e1",
        element_type=CVElementType.WALL,
        page_number=1,
        bbox=(10, 20, 30, 40),
        confidence=0.9,
        source="test",
        derived=[dm],
        needs_review=False,
        attributes={"foo": "bar"},
    )

    data = elem.to_dict()
    assert data["id"] == "e1"
    assert data["type"] == "wall"
    assert data["bbox"]["width"] == 30
    assert data["derived"][0]["unit"] == "m"


def test_page_needs_review_flag():
    dm = DerivedMeasure(name="count", value=1, unit="count", method="count", confidence=0.2)
    elem = CVElement(
        element_id="e2",
        element_type=CVElementType.DOOR,
        page_number=1,
        bbox=(0, 0, 5, 5),
        confidence=0.3,
        source="test",
        derived=[dm],
        needs_review=True,
    )
    page = CVPageResult(document_id="doc", page_number=1, dpi=200, elements=[elem])
    assert page.needs_review is True

