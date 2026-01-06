"""
Unit tests for Room Area Extraction Engine.

Tests the deterministic extraction of room areas from CAD-generated PDFs.
Uses real blueprint files from GRUNDRISSE BTB 2 directory.
"""

import pytest
from pathlib import Path

from app.services.room_area_extraction import (
    extract_room_areas,
    extract_room_areas_auto,
    extract_text_with_positions,
    extract_area_from_line,
    extract_counted_area_from_line,
    find_nearest_room_name,
    is_balcony_type,
    parse_german_decimal,
    BoundingBox,
    TextSpan,
    TextLine,
    RoomAreaItem,
    RoomAreaResult,
    AREA_PATTERN,
    COUNTED_AREA_PATTERN,
    ALT_AREA_PATTERNS,
)


# =============================================================================
# TEST DATA PATHS
# =============================================================================

# Real blueprint files for testing
BLUEPRINTS_DIR = Path("/Users/clarence/Desktop/SnapPlan/GRUNDRISSE BTB 2")
SAMPLE_PDF_1OG = BLUEPRINTS_DIR / "HMA-ARC-5-UP-WP-01-B0-0001-05-v-Bauteil B - šbersichtsplan Grundriss 1. Obergeschoss.pdf"
SAMPLE_PDF_2OG = BLUEPRINTS_DIR / "HMA-ARC-5-UP-WP-02-B0-0001-05-v-Bauteil B - šbersichtsplan Grundriss 2. Obergeschoss.pdf"
SAMPLE_PDF_EG = BLUEPRINTS_DIR / "HMA-ARC-5-UP-WP-00-B0-0001-07-v-Bauteil B - šbersichtsplan Grundriss Erdgeschoss.pdf"


@pytest.fixture
def sample_pdf_1og():
    """First floor plan (1. Obergeschoss)."""
    if not SAMPLE_PDF_1OG.exists():
        pytest.skip(f"Sample PDF not found: {SAMPLE_PDF_1OG}")
    return SAMPLE_PDF_1OG


@pytest.fixture
def sample_pdf_2og():
    """Second floor plan (2. Obergeschoss)."""
    if not SAMPLE_PDF_2OG.exists():
        pytest.skip(f"Sample PDF not found: {SAMPLE_PDF_2OG}")
    return SAMPLE_PDF_2OG


@pytest.fixture
def sample_pdf_eg():
    """Ground floor plan (Erdgeschoss)."""
    if not SAMPLE_PDF_EG.exists():
        pytest.skip(f"Sample PDF not found: {SAMPLE_PDF_EG}")
    return SAMPLE_PDF_EG


# =============================================================================
# UNIT TESTS: REGEX PATTERNS
# =============================================================================

class TestRegexPatterns:
    """Test regex pattern matching for NRF area values."""

    def test_nrf_pattern_basic(self):
        """Test 'NRF: 10,90 m' pattern (primary German CAD format)."""
        match = AREA_PATTERN.search("NRF: 10,90 m")
        assert match is not None
        assert match.group(1) == "10,90"

    def test_nrf_pattern_german_comma(self):
        """Test German decimal comma format."""
        match = AREA_PATTERN.search("NRF: 22,79 m")
        assert match is not None
        assert match.group(1) == "22,79"

    def test_nrf_pattern_decimal_point(self):
        """Test decimal point format."""
        match = AREA_PATTERN.search("NRF: 22.79 m²")
        assert match is not None
        assert match.group(1) == "22.79"

    def test_nrf_pattern_three_decimals(self):
        """Test NRF with three decimal places (common in CAD)."""
        match = AREA_PATTERN.search("NRF: 42,180 m")
        assert match is not None
        assert match.group(1) == "42,180"

    def test_nrf_pattern_no_space(self):
        """Test 'NRF:22,79m²' pattern without spaces."""
        match = AREA_PATTERN.search("NRF:22,79m²")
        assert match is not None
        assert match.group(1) == "22,79"

    def test_nrf_pattern_with_superscript(self):
        """Test NRF with m² superscript."""
        match = AREA_PATTERN.search("NRF: 10,90 m²")
        assert match is not None
        assert match.group(1) == "10,90"

    def test_bgf_pattern(self):
        """Test 'BGF: 100,00 m' pattern (Bruttogrundfläche)."""
        bgf_pattern = ALT_AREA_PATTERNS[0]  # BGF is first alt pattern
        match = bgf_pattern.search("BGF: 100,00 m")
        assert match is not None
        assert match.group(1) == "100,00"

    def test_counted_area_pattern(self):
        """Test '50%: 1,15 m²' pattern."""
        match = COUNTED_AREA_PATTERN.search("50%: 1,15 m²")
        assert match is not None
        assert match.group(1) == "50"
        assert match.group(2) == "1,15"

    def test_counted_area_pattern_other_percentages(self):
        """Test other percentage values."""
        for pct in ["25", "30", "75", "100"]:
            match = COUNTED_AREA_PATTERN.search(f"{pct}%: 5,00 m²")
            assert match is not None
            assert match.group(1) == pct


class TestGermanDecimalParsing:
    """Test German decimal comma parsing."""

    def test_comma_decimal(self):
        assert parse_german_decimal("22,79") == 22.79

    def test_point_decimal(self):
        assert parse_german_decimal("22.79") == 22.79

    def test_no_decimal(self):
        assert parse_german_decimal("22") == 22.0

    def test_leading_zero(self):
        assert parse_german_decimal("0,50") == 0.50

    def test_three_decimals(self):
        """Test three decimal places (common in CAD exports)."""
        assert parse_german_decimal("42,180") == 42.180


# =============================================================================
# UNIT TESTS: BALCONY DETECTION
# =============================================================================

class TestBalconyDetection:
    """Test balcony/terrace type detection."""

    def test_balkon_detection(self):
        is_bal, room_type = is_balcony_type("Balkon")
        assert is_bal is True
        assert room_type == "balkon"

    def test_terrasse_detection(self):
        is_bal, room_type = is_balcony_type("Terrasse")
        assert is_bal is True
        assert room_type == "terrasse"

    def test_loggia_detection(self):
        is_bal, room_type = is_balcony_type("Loggia")
        assert is_bal is True
        assert room_type == "loggia"

    def test_regular_room_not_detected(self):
        is_bal, room_type = is_balcony_type("Wohnzimmer")
        assert is_bal is False
        assert room_type == "standard"

    def test_case_insensitive(self):
        is_bal, _ = is_balcony_type("BALKON")
        assert is_bal is True

    def test_partial_match_in_longer_text(self):
        is_bal, room_type = is_balcony_type("Balkon 1.OG")
        assert is_bal is True
        assert room_type == "balkon"


# =============================================================================
# UNIT TESTS: TEXT LINE EXTRACTION
# =============================================================================

class TestTextLineExtraction:
    """Test text extraction from TextLine objects."""

    def test_extract_area_nrf_pattern(self):
        """Test NRF: pattern extraction."""
        line = TextLine(
            spans=[TextSpan("NRF: 45,50 m", BoundingBox(100, 200, 200, 215), "helv", 10)],
            bbox=BoundingBox(100, 200, 200, 215)
        )
        result = extract_area_from_line(line)
        assert result is not None
        area, _ = result
        assert area == 45.50

    def test_extract_counted_area(self):
        """Test counted area (50%) extraction."""
        line = TextLine(
            spans=[TextSpan("50%: 1,15 m²", BoundingBox(100, 220, 200, 235), "helv", 10)],
            bbox=BoundingBox(100, 220, 200, 235)
        )
        result = extract_counted_area_from_line(line)
        assert result is not None
        percentage, area, source = result
        assert percentage == 0.5
        assert area == 1.15


# =============================================================================
# UNIT TESTS: ROOM NAME ASSOCIATION
# =============================================================================

class TestRoomNameAssociation:
    """Test finding nearest room name above area value."""

    def test_find_name_directly_above(self):
        """Test finding room name directly above area."""
        area_line = TextLine(
            spans=[TextSpan("NRF: 22,79 m", BoundingBox(100, 220, 200, 235), "helv", 10)],
            bbox=BoundingBox(100, 220, 200, 235)
        )
        all_lines = [
            TextLine(
                spans=[TextSpan("Wohnzimmer", BoundingBox(100, 200, 180, 215), "helv", 10)],
                bbox=BoundingBox(100, 200, 180, 215)
            ),
            area_line,
        ]

        result = find_nearest_room_name(area_line, all_lines)
        assert result is not None
        name, source = result
        assert name == "Wohnzimmer"

    def test_skip_area_lines_as_names(self):
        """Test that area lines are not picked as names."""
        area_line = TextLine(
            spans=[TextSpan("NRF: 22,79 m", BoundingBox(100, 250, 200, 265), "helv", 10)],
            bbox=BoundingBox(100, 250, 200, 265)
        )
        all_lines = [
            TextLine(
                spans=[TextSpan("NRF: 15,00 m", BoundingBox(100, 200, 200, 215), "helv", 10)],
                bbox=BoundingBox(100, 200, 200, 215)
            ),  # This should be skipped (it's an area, not a name)
            TextLine(
                spans=[TextSpan("Schlafzimmer", BoundingBox(100, 230, 180, 245), "helv", 10)],
                bbox=BoundingBox(100, 230, 180, 245)
            ),
            area_line,
        ]

        result = find_nearest_room_name(area_line, all_lines)
        assert result is not None
        name, _ = result
        assert name == "Schlafzimmer"


# =============================================================================
# INTEGRATION TESTS: REAL BLUEPRINT EXTRACTION
# =============================================================================

class TestRealBlueprintExtraction:
    """Integration tests with real blueprint PDFs."""

    def test_extract_rooms_from_1og(self, sample_pdf_1og):
        """Test extraction from 1st floor plan."""
        result = extract_room_areas(sample_pdf_1og)

        assert isinstance(result, RoomAreaResult)
        assert len(result.rooms) > 0, "Should extract at least one room"
        assert result.total_area_m2 > 0, "Total area should be positive"

        # Verify all rooms have required traceability
        for room in result.rooms:
            assert room.source_text is not None
            assert "NRF:" in room.source_text, f"Expected NRF: pattern in source: {room.source_text}"
            assert room.bbox is not None
            assert room.page == 0

    def test_extract_rooms_from_2og(self, sample_pdf_2og):
        """Test extraction from 2nd floor plan."""
        result = extract_room_areas(sample_pdf_2og)

        assert len(result.rooms) > 0
        assert result.total_area_m2 > 0

    def test_extraction_method_is_dict(self, sample_pdf_1og):
        """Test that extraction method is documented."""
        result = extract_room_areas(sample_pdf_1og)
        # Should be "pymupdf_rawdict" (legacy name) or similar
        assert "pymupdf" in result.extraction_method.lower()

    def test_all_rooms_have_source_text(self, sample_pdf_1og):
        """Test that all rooms have traceable source text."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            assert room.source_text is not None
            assert len(room.source_text) > 0
            # Source should contain area pattern
            assert "m" in room.source_text.lower()

    def test_all_rooms_have_bbox(self, sample_pdf_1og):
        """Test that all rooms have bounding box coordinates."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            assert room.bbox is not None
            assert isinstance(room.bbox, BoundingBox)
            assert room.bbox.x0 >= 0
            assert room.bbox.y0 >= 0
            assert room.bbox.x1 > room.bbox.x0
            assert room.bbox.y1 > room.bbox.y0

    def test_totals_match_sum_of_rooms(self, sample_pdf_1og):
        """Test that totals are sum of individual rooms."""
        result = extract_room_areas(sample_pdf_1og)

        expected_total = round(sum(r.area_m2 for r in result.rooms), 2)
        expected_counted = round(sum(r.counted_m2 for r in result.rooms), 2)

        assert result.total_area_m2 == expected_total
        assert result.sum_counted_m2 == expected_counted

    def test_nrf_values_extracted_correctly(self, sample_pdf_1og):
        """Test that NRF values are extracted with correct format."""
        result = extract_room_areas(sample_pdf_1og)

        # All source texts should contain NRF: pattern
        nrf_rooms = [r for r in result.rooms if "NRF:" in r.source_text]
        assert len(nrf_rooms) > 0, "Should find rooms with NRF: pattern"

        # Verify German decimal format is parsed
        for room in nrf_rooms:
            assert room.area_m2 > 0
            assert isinstance(room.area_m2, float)


class TestBoundingBox:
    """Test BoundingBox data class."""

    def test_center_calculation(self):
        bbox = BoundingBox(100, 200, 200, 300)
        center = bbox.center()
        assert center == (150, 250)

    def test_y_center_calculation(self):
        bbox = BoundingBox(100, 200, 200, 300)
        assert bbox.y_center() == 250

    def test_to_dict(self):
        bbox = BoundingBox(100, 200, 200, 300)
        d = bbox.to_dict()
        assert d == {"x0": 100, "y0": 200, "x1": 200, "y1": 300}

    def test_from_dict(self):
        bbox = BoundingBox.from_dict({"x0": 100, "y0": 200, "x1": 200, "y1": 300})
        assert bbox.x0 == 100
        assert bbox.y0 == 200

    def test_from_tuple(self):
        bbox = BoundingBox.from_tuple((100, 200, 200, 300))
        assert bbox.x0 == 100
        assert bbox.y1 == 300


class TestRoomAreaItemSerialization:
    """Test RoomAreaItem serialization."""

    def test_to_dict(self):
        item = RoomAreaItem(
            room_id="room_001",
            name="Wohnzimmer",
            area_m2=22.79,
            counted_m2=22.79,
            factor=1.0,
            page=0,
            source_text="NRF: 22,79 m",
            bbox=BoundingBox(100, 200, 200, 215),
            room_type="standard"
        )
        d = item.to_dict()

        assert d["room_id"] == "room_001"
        assert d["name"] == "Wohnzimmer"
        assert d["area_m2"] == 22.79
        assert d["source_text"] == "NRF: 22,79 m"
        assert "bbox" in d

    def test_from_dict(self):
        d = {
            "room_id": "room_001",
            "name": "Wohnzimmer",
            "area_m2": 22.79,
            "counted_m2": 22.79,
            "factor": 1.0,
            "page": 0,
            "source_text": "NRF: 22,79 m",
            "bbox": {"x0": 100, "y0": 200, "x1": 200, "y1": 215},
            "room_type": "standard"
        }
        item = RoomAreaItem.from_dict(d)

        assert item.room_id == "room_001"
        assert item.area_m2 == 22.79


class TestAutoExtraction:
    """Test the auto-extraction API that returns dict."""

    def test_auto_returns_dict(self, sample_pdf_1og):
        """Test that extract_room_areas_auto returns a dict."""
        result = extract_room_areas_auto(sample_pdf_1og)

        assert isinstance(result, dict)
        assert "rooms" in result
        assert "total_area_m2" in result
        assert "sum_counted_m2" in result
        assert "missing" in result
        assert "extraction_method" in result


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_file_not_found(self):
        """Test handling of non-existent file."""
        with pytest.raises(FileNotFoundError):
            extract_room_areas("/nonexistent/path/to/file.pdf")


# =============================================================================
# TRACEABILITY TESTS
# =============================================================================

class TestTraceability:
    """Test that all values have proper traceability."""

    def test_room_has_source_text(self, sample_pdf_1og):
        """Test that rooms have source_text."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            assert room.source_text is not None
            assert len(room.source_text) > 0

    def test_room_has_bbox(self, sample_pdf_1og):
        """Test that rooms have bounding box."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            assert room.bbox is not None
            assert isinstance(room.bbox, BoundingBox)

    def test_room_has_page_number(self, sample_pdf_1og):
        """Test that rooms have page number."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            assert room.page is not None
            assert room.page >= 0


# =============================================================================
# DETERMINISTIC EXTRACTION TESTS
# =============================================================================

class TestDeterministicExtraction:
    """Test that extraction is deterministic and traceable."""

    def test_same_input_same_output(self, sample_pdf_1og):
        """Test that running extraction twice gives same result."""
        result1 = extract_room_areas(sample_pdf_1og)
        result2 = extract_room_areas(sample_pdf_1og)

        assert result1.total_area_m2 == result2.total_area_m2
        assert result1.sum_counted_m2 == result2.sum_counted_m2
        assert len(result1.rooms) == len(result2.rooms)

        for r1, r2 in zip(result1.rooms, result2.rooms):
            assert r1.area_m2 == r2.area_m2
            assert r1.source_text == r2.source_text

    def test_no_hallucinated_values(self, sample_pdf_1og):
        """Test that all values come from PDF text, not generated."""
        result = extract_room_areas(sample_pdf_1og)

        for room in result.rooms:
            # Source text must contain the area value
            area_str = str(room.area_m2).replace(".", ",")
            # At least partial match (accounting for decimal precision)
            area_parts = area_str.split(",")
            assert area_parts[0] in room.source_text, \
                f"Area {room.area_m2} not traceable to source: {room.source_text}"
