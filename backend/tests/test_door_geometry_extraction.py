"""
Tests for door geometry extraction pipeline.

Tests cover:
- Door label pattern detection
- Geometry detection (arcs, rectangles)
- Label-geometry association
- Attribute extraction
- Full pipeline integration
"""

import pytest
from pathlib import Path
from typing import List

from app.services.door_label_detection import (
    DoorLabel,
    parse_dimension_from_text,
    detect_door_labels,
    group_nearby_labels,
    _apply_patterns_to_text,
)
from app.services.door_geometry_extraction import (
    DoorGeometry,
    DoorExtraction,
    detect_door_arcs,
    detect_door_rectangles,
    associate_labels_with_geometries,
    extract_door_attributes,
    extract_doors_from_pdf,
)
from app.services.scale_calibration import ScaleContext


# =============================================================================
# Test Door Label Detection
# =============================================================================


class TestDoorLabelDetection:
    """Test door label pattern detection."""

    def test_detect_german_door_labels(self):
        """Detect WD, DD patterns."""
        text = "Wohnungstür WD steht hier"
        bbox = (100.0, 200.0, 150.0, 220.0)
        labels = _apply_patterns_to_text(text, bbox, page_number=1)

        assert len(labels) > 0
        assert any(lbl.door_type == "WD" for lbl in labels)
        assert all(lbl.pattern_type == "german_door" for lbl in labels)

    def test_detect_dimension_labels(self):
        """Detect '0,90 x 2,10' patterns."""
        text = "Tür: 0,90 x 2,10"
        bbox = (100.0, 200.0, 150.0, 220.0)
        labels = _apply_patterns_to_text(text, bbox, page_number=1)

        dimension_labels = [lbl for lbl in labels if lbl.pattern_type == "dimension"]
        assert len(dimension_labels) > 0

        label = dimension_labels[0]
        assert label.width_m == pytest.approx(0.90, abs=0.01)
        assert label.height_m == pytest.approx(2.10, abs=0.01)

    def test_detect_room_door_labels(self):
        """Detect 'F. ND1', 'B.03.1.001-1' patterns."""
        test_cases = [
            "F. ND1",
            "B.03.1.001-1",
            "BU_012",
        ]

        for text in test_cases:
            bbox = (100.0, 200.0, 150.0, 220.0)
            labels = _apply_patterns_to_text(text, bbox, page_number=1)

            room_labels = [lbl for lbl in labels if lbl.pattern_type == "room_door"]
            assert len(room_labels) > 0, f"Failed to detect room door label: {text}"

    def test_detect_fire_rating_labels(self):
        """Detect 'T 30-RS', 'T90' patterns."""
        test_cases = [
            ("T 30-RS", "T30"),
            ("T30", "T30"),
            ("T 90-RS", "T90"),
            ("T90", "T90"),
            ("DSS", "DSS"),
        ]

        for text, expected_rating in test_cases:
            bbox = (100.0, 200.0, 150.0, 220.0)
            labels = _apply_patterns_to_text(text, bbox, page_number=1)

            fire_labels = [lbl for lbl in labels if lbl.pattern_type == "fire_rating"]
            assert len(fire_labels) > 0, f"Failed to detect fire rating: {text}"
            assert fire_labels[0].fire_rating == expected_rating

    def test_parse_german_dimensions(self):
        """Parse German decimal comma in dimensions."""
        test_cases = [
            ("0,90 x 2,10", (0.90, 2.10)),
            ("1,25 x 2,00", (1.25, 2.00)),
            ("90 x 210", (0.90, 2.10)),  # cm format
        ]

        for text, expected in test_cases:
            result = parse_dimension_from_text(text)
            assert result is not None, f"Failed to parse: {text}"
            width, height = result
            assert width == pytest.approx(expected[0], abs=0.01)
            assert height == pytest.approx(expected[1], abs=0.01)

    def test_parse_dimension_rejects_invalid(self):
        """Invalid dimension strings should return None."""
        invalid_cases = [
            "abc x def",
            "1 x 2",  # Too small
            "100 x 300",  # Unrealistic door size
        ]

        for text in invalid_cases:
            result = parse_dimension_from_text(text)
            # Either None or not matching realistic door dimensions
            if result:
                width, height = result
                # Check if dimensions are realistic
                assert 0.5 <= width <= 2.0 and 1.8 <= height <= 2.8


class TestLabelGrouping:
    """Test label grouping for compound labels."""

    def test_group_nearby_labels(self):
        """Labels within max_distance should be grouped."""
        label1 = DoorLabel(
            label_text="F. ND1",
            raw_text="F. ND1",
            page_number=1,
            bbox=(100.0, 100.0, 150.0, 120.0),
            confidence=0.8,
            pattern_type="room_door",
        )

        label2 = DoorLabel(
            label_text="T 30-RS",
            raw_text="T 30-RS",
            page_number=1,
            bbox=(100.0, 125.0, 150.0, 145.0),  # 5px below label1
            confidence=0.9,
            pattern_type="fire_rating",
            fire_rating="T30",
        )

        grouped = group_nearby_labels([label1, label2], max_distance_px=50)

        # Should be merged into 1 label
        assert len(grouped) == 1
        merged = grouped[0]
        assert "F. ND1" in merged.label_text
        assert "T 30-RS" in merged.label_text
        assert merged.fire_rating == "T30"  # Preserved from label2

    def test_group_distant_labels_kept_separate(self):
        """Labels beyond max_distance should remain separate."""
        label1 = DoorLabel(
            label_text="WD",
            raw_text="WD",
            page_number=1,
            bbox=(100.0, 100.0, 150.0, 120.0),
            confidence=0.8,
            pattern_type="german_door",
        )

        label2 = DoorLabel(
            label_text="DD",
            raw_text="DD",
            page_number=1,
            bbox=(300.0, 300.0, 350.0, 320.0),  # Far away
            confidence=0.8,
            pattern_type="german_door",
        )

        grouped = group_nearby_labels([label1, label2], max_distance_px=50)

        # Should remain separate
        assert len(grouped) == 2


# =============================================================================
# Test Label-Geometry Association
# =============================================================================


class TestLabelGeometryAssociation:
    """Test label-geometry matching."""

    def test_associate_label_with_nearby_geometry(self):
        """Labels should match nearest geometry."""
        label = DoorLabel(
            label_text="WD",
            raw_text="WD",
            page_number=1,
            bbox=(100.0, 100.0, 120.0, 110.0),
            confidence=0.9,
            pattern_type="german_door",
            door_type="WD",
        )

        geometry = DoorGeometry(
            geometry_id="door_001",
            page_number=1,
            center=(115.0, 105.0),  # 15px from label center
            width_px=50.0,
            opening_type="arc",
            confidence=0.85,
        )

        doors = associate_labels_with_geometries(
            labels=[label],
            geometries=[geometry],
            max_distance_px=50
        )

        assert len(doors) == 1
        door = doors[0]
        assert door.label is not None
        assert door.geometry is not None
        assert door.extraction_method == "label_geometry_match"
        assert door.confidence > 0  # Should have non-zero confidence

    def test_unmatched_geometry_has_lower_confidence(self):
        """Geometry-only doors should have reduced confidence."""
        geometry = DoorGeometry(
            geometry_id="door_001",
            page_number=1,
            center=(115.0, 105.0),
            width_px=50.0,
            opening_type="arc",
            confidence=0.85,
        )

        doors = associate_labels_with_geometries(
            labels=[],  # No labels
            geometries=[geometry],
            max_distance_px=50
        )

        assert len(doors) == 1
        door = doors[0]
        assert door.label is None
        assert door.geometry is not None
        assert door.extraction_method == "geometry_only"
        assert door.confidence < geometry.confidence  # Reduced confidence
        assert len(door.warnings) > 0

    def test_multiple_labels_choose_closest_geometry(self):
        """Ambiguous cases should prefer closest match."""
        label1 = DoorLabel(
            label_text="WD1",
            raw_text="WD1",
            page_number=1,
            bbox=(100.0, 100.0, 120.0, 110.0),
            confidence=0.9,
            pattern_type="german_door",
        )

        label2 = DoorLabel(
            label_text="WD2",
            raw_text="WD2",
            page_number=1,
            bbox=(200.0, 100.0, 220.0, 110.0),
            confidence=0.9,
            pattern_type="german_door",
        )

        geometry = DoorGeometry(
            geometry_id="door_001",
            page_number=1,
            center=(115.0, 105.0),  # Closer to label1
            width_px=50.0,
            opening_type="arc",
            confidence=0.85,
        )

        doors = associate_labels_with_geometries(
            labels=[label1, label2],
            geometries=[geometry],
            max_distance_px=150
        )

        # Should prefer label1 (closer)
        matched_doors = [d for d in doors if d.extraction_method == "label_geometry_match"]
        assert len(matched_doors) == 1
        assert matched_doors[0].label.label_text == "WD1"


# =============================================================================
# Test Attribute Extraction
# =============================================================================


class TestDoorAttributeExtraction:
    """Test attribute extraction."""

    def test_extract_width_from_dimension_label(self):
        """'0,90 x 2,10' → width_m=0.90, height_m=2.10."""
        label = DoorLabel(
            label_text="0,90 x 2,10",
            raw_text="0,90 x 2,10",
            page_number=1,
            bbox=(100.0, 100.0, 150.0, 110.0),
            confidence=0.95,
            pattern_type="dimension",
            width_m=0.90,
            height_m=2.10,
        )

        door = DoorExtraction(
            extraction_id="door_test",
            page_number=1,
            label=label,
            extraction_method="label_only",
        )

        extract_door_attributes(door, scale_context=None)

        assert door.width_m == pytest.approx(0.90, abs=0.01)
        assert door.height_m == pytest.approx(2.10, abs=0.01)

    def test_extract_width_from_geometry_with_scale(self):
        """Use arc radius / pixels_per_meter."""
        scale_context = ScaleContext(
            id="scale_test",
            scale_factor=100,
            pixels_per_meter=59.055,  # 1:100 at 150 DPI
            has_scale=True,
        )

        geometry = DoorGeometry(
            geometry_id="door_001",
            page_number=1,
            center=(100.0, 100.0),
            width_px=53.15,  # ~0.90m at this scale
            opening_type="arc",
            confidence=0.85,
        )

        door = DoorExtraction(
            extraction_id="door_test",
            page_number=1,
            geometry=geometry,
            extraction_method="geometry_only",
        )

        extract_door_attributes(door, scale_context)

        assert door.width_m is not None
        assert door.width_m == pytest.approx(0.90, abs=0.05)

    def test_classify_fire_rating(self):
        """'T 30-RS' → category=T30."""
        label = DoorLabel(
            label_text="T 30-RS",
            raw_text="T 30-RS",
            page_number=1,
            bbox=(100.0, 100.0, 150.0, 110.0),
            confidence=0.95,
            pattern_type="fire_rating",
            fire_rating="T30",
        )

        door = DoorExtraction(
            extraction_id="door_test",
            page_number=1,
            label=label,
            extraction_method="label_only",
        )

        extract_door_attributes(door, scale_context=None)

        assert door.fire_rating == "T30"
        assert door.category == "T30"


# =============================================================================
# Integration Test
# =============================================================================


class TestDoorExtractionPipeline:
    """Test full pipeline with sample PDFs."""

    @pytest.mark.skipif(
        not Path("PLANS").exists(),
        reason="PLANS directory not available"
    )
    def test_extract_doors_from_sample_pdf(self):
        """
        Use sample PDF from PLANS/ directory.

        Assert:
        - total_doors >= 0 (may be 0 if no doors on page)
        - Each door has page_number, confidence, bbox (if geometry present)
        - Summary statistics populated
        - Warnings list present (may be empty)
        """
        # Find a sample PDF (use any available plan)
        plans_dir = Path("PLANS")
        pdf_files = list(plans_dir.rglob("*.pdf"))

        if not pdf_files:
            pytest.skip("No PDF files found in PLANS directory")

        sample_pdf = pdf_files[0]

        result = extract_doors_from_pdf(
            pdf_path=sample_pdf,
            page_number=1,  # Test first page only
            scale_factor=100,
            search_radius_px=150,
            min_confidence=0.5,
        )

        # Basic assertions
        assert result is not None
        assert result.total_doors >= 0
        assert result.page_count > 0
        assert len(result.processed_pages) > 0

        # Check each door has required fields
        for door in result.doors:
            assert door.page_number > 0
            assert 0.0 <= door.confidence <= 1.0
            assert door.extraction_method in ["label_geometry_match", "geometry_only", "label_only"]

            # If geometry present, check bbox
            if door.geometry:
                assert len(door.geometry.bbox) == 4
                assert door.geometry.confidence > 0

        # Summary statistics should be populated
        assert isinstance(result.by_type, dict)
        assert isinstance(result.by_fire_rating, dict)
        assert isinstance(result.by_width, dict)

        # Warnings list should be present
        assert isinstance(result.warnings, list)


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def sample_door_label():
    """Fixture for a sample door label."""
    return DoorLabel(
        label_text="WD",
        raw_text="Wohnungstür WD",
        page_number=1,
        bbox=(100.0, 100.0, 150.0, 120.0),
        confidence=0.9,
        pattern_type="german_door",
        door_type="WD",
    )


@pytest.fixture
def sample_door_geometry():
    """Fixture for a sample door geometry."""
    return DoorGeometry(
        geometry_id="door_001",
        page_number=1,
        center=(125.0, 110.0),
        width_px=50.0,
        opening_type="arc",
        bbox=(100.0, 85.0, 150.0, 135.0),
        confidence=0.85,
    )


@pytest.fixture
def sample_scale_context():
    """Fixture for a sample scale context."""
    return ScaleContext(
        id="scale_test",
        scale_factor=100,
        pixels_per_meter=59.055,
        has_scale=True,
    )
