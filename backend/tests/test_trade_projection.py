"""
Unit tests for Trade Material Projection module.

Tests cover:
- Data model serialization
- Projection formula calculations
- Parameter validation
- Traceability requirements
"""

import pytest
from app.services.trade_projection import (
    TradeType,
    TradeParams,
    ProjectionMethod,
    ConfidenceLevel,
    MaterialProjectionResult,
    AufmassItem,
    ProjectedMaterial,
    GroundTruthMeasurement,
    create_ground_truth_measurement,
    create_aufmass_item,
    create_projected_material,
    create_projection_result,
    _get_confidence_level,
    TRADE_METADATA,
)
from app.services.projections.screed import project_screed
from app.services.projections.drywall import project_drywall
from app.services.projections.scaffolding import project_scaffolding
from app.services.projections.floor_finish import project_floor_finish
from app.services.projections.waterproofing import project_waterproofing


# ==================
# FIXTURES
# ==================

@pytest.fixture
def sample_extraction_result():
    """Sample extraction result for testing."""
    return {
        "extraction_id": "ext_test123",
        "total_area_m2": 500.0,
        "total_counted_m2": 480.0,
        "room_count": 10,
        "blueprint_style": "leiq",
        "rooms": [
            {
                "room_number": "B.01.1.001",
                "room_name": "Büro 1",
                "area_m2": 50.0,
                "counted_m2": 50.0,
                "perimeter_m": 28.5,
                "category": "office",
                "page": 1,
            },
            {
                "room_number": "B.01.1.002",
                "room_name": "Bad",
                "area_m2": 15.0,
                "counted_m2": 15.0,
                "perimeter_m": 16.0,
                "category": "sanitary",
                "page": 1,
            },
            {
                "room_number": "B.01.1.003",
                "room_name": "Flur",
                "area_m2": 25.0,
                "counted_m2": 25.0,
                "perimeter_m": 22.0,
                "category": "circulation",
                "page": 1,
            },
        ],
    }


@pytest.fixture
def screed_params():
    """Default screed parameters."""
    return TradeParams(
        trade_type=TradeType.SCREED,
        waste_factor=1.10,
        screed_type="ct",
        screed_thickness_mm=50,
    )


@pytest.fixture
def drywall_params():
    """Default drywall parameters."""
    return TradeParams(
        trade_type=TradeType.DRYWALL,
        waste_factor=1.10,
        wall_height_m=2.8,
        drywall_system="single",
        stud_spacing_mm=625,
    )


# ==================
# DATA MODEL TESTS
# ==================

class TestTradeParams:
    """Tests for TradeParams validation."""

    def test_valid_screed_params(self, screed_params):
        """Valid screed params should have no errors."""
        errors = screed_params.validate()
        assert len(errors) == 0

    def test_missing_required_param(self):
        """Missing required param should produce error."""
        params = TradeParams(
            trade_type=TradeType.DRYWALL,
            wall_height_m=None,  # Required for drywall
        )
        errors = params.validate()
        assert any("wall_height_m" in e for e in errors)

    def test_invalid_waste_factor(self):
        """Waste factor outside range should produce error."""
        params = TradeParams(
            trade_type=TradeType.SCREED,
            waste_factor=3.0,  # Too high
            screed_thickness_mm=50,
        )
        errors = params.validate()
        assert any("waste_factor" in e for e in errors)

    def test_to_dict(self, screed_params):
        """to_dict should include all fields."""
        data = screed_params.to_dict()
        assert data["trade_type"] == "screed"
        assert data["waste_factor"] == 1.10
        assert data["screed_type"] == "ct"
        assert data["screed_thickness_mm"] == 50


class TestGroundTruthMeasurement:
    """Tests for GroundTruthMeasurement."""

    def test_create_measurement(self):
        """Create measurement with all fields."""
        meas = create_ground_truth_measurement(
            source_field="total_area_m2",
            value=500.0,
            unit="m2",
            source_page=1,
        )
        assert meas.measurement_id.startswith("meas_")
        assert meas.value == 500.0
        assert meas.unit == "m2"

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        meas = create_ground_truth_measurement(
            source_field="perimeter_m",
            value=28.5,
            unit="m",
            source_room_id="B.01.1.001",
        )
        data = meas.to_dict()
        assert data["source_field"] == "perimeter_m"
        assert data["value"] == 28.5
        assert data["source_room_id"] == "B.01.1.001"


class TestAufmassItem:
    """Tests for AufmassItem."""

    def test_create_aufmass_item(self):
        """Create aufmass item with traceability."""
        meas = create_ground_truth_measurement(
            source_field="total_area_m2",
            value=500.0,
            unit="m2",
        )
        item = create_aufmass_item(
            position="03.01.001",
            description="Estrich CT 50mm",
            quantity=550.0,
            unit="m²",
            derived_from=[meas],
            formula="500.0 × 1.10",
        )
        assert item.item_id.startswith("auf_")
        assert item.quantity == 550.0
        assert len(item.derived_from) == 1

    def test_to_dict_includes_ground_truth_flag(self):
        """to_dict should include is_ground_truth=True."""
        item = create_aufmass_item(
            position="01.01",
            description="Test",
            quantity=100.0,
            unit="m²",
            derived_from=[],
            formula="test",
        )
        data = item.to_dict()
        assert data["is_ground_truth"] is True


class TestProjectedMaterial:
    """Tests for ProjectedMaterial."""

    def test_create_projected_material(self):
        """Create projected material with assumptions."""
        mat = create_projected_material(
            name="Gipskartonplatte 12.5mm",
            quantity=1100.0,
            unit="m²",
            confidence=0.75,
            assumptions=[
                "Both sides = ×2",
                "Waste factor: 10%",
            ],
        )
        assert mat.material_id.startswith("mat_")
        assert mat.quantity == 1100.0
        assert mat.method == ProjectionMethod.RULE_BASED
        assert len(mat.assumptions) == 2

    def test_effective_quantity_without_override(self):
        """effective_quantity should return quantity when no override."""
        mat = create_projected_material(
            name="Test",
            quantity=100.0,
            unit="m²",
            confidence=0.8,
            assumptions=[],
        )
        assert mat.effective_quantity == 100.0

    def test_effective_quantity_with_override(self):
        """effective_quantity should return override when set."""
        mat = create_projected_material(
            name="Test",
            quantity=100.0,
            unit="m²",
            confidence=0.8,
            assumptions=[],
        )
        mat.user_override = 120.0
        assert mat.effective_quantity == 120.0

    def test_confidence_level(self):
        """confidence_level should map correctly."""
        assert _get_confidence_level(0.9) == ConfidenceLevel.HIGH
        assert _get_confidence_level(0.7) == ConfidenceLevel.MEDIUM
        assert _get_confidence_level(0.4) == ConfidenceLevel.LOW

    def test_to_dict_includes_estimate_flag(self):
        """to_dict should include is_estimate=True."""
        mat = create_projected_material(
            name="Test",
            quantity=100.0,
            unit="m²",
            confidence=0.8,
            assumptions=[],
        )
        data = mat.to_dict()
        assert data["is_estimate"] is True


class TestMaterialProjectionResult:
    """Tests for MaterialProjectionResult."""

    def test_create_projection_result(self, screed_params):
        """Create projection result with items."""
        aufmass = create_aufmass_item(
            position="01.01",
            description="Test",
            quantity=100.0,
            unit="m²",
            derived_from=[],
            formula="test",
        )
        material = create_projected_material(
            name="Test Material",
            quantity=50.0,
            unit="kg",
            confidence=0.8,
            assumptions=["Test assumption"],
        )

        result = create_projection_result(
            trade_type=TradeType.SCREED,
            source_extraction_id="ext_123",
            params=screed_params,
            aufmass_items=[aufmass],
            projected_materials=[material],
        )

        assert result.projection_id.startswith("proj_")
        assert result.status == "ok"
        assert len(result.aufmass_items) == 1
        assert len(result.projected_materials) == 1
        assert result.disclaimer != ""

    def test_to_dict_structure(self, screed_params):
        """to_dict should have correct structure."""
        result = create_projection_result(
            trade_type=TradeType.SCREED,
            source_extraction_id="ext_123",
            params=screed_params,
            aufmass_items=[],
            projected_materials=[],
        )
        data = result.to_dict()

        assert "projection_id" in data
        assert "trade_type" in data
        assert "trade_name_de" in data
        assert "aufmass_items" in data
        assert "projected_materials" in data
        assert "disclaimer" in data
        assert "summary" in data


# ==================
# PROJECTION ENGINE TESTS
# ==================

class TestScreedProjection:
    """Tests for screed projection calculations."""

    def test_basic_calculation(self, sample_extraction_result, screed_params):
        """Basic screed projection should produce results."""
        result = project_screed(sample_extraction_result, screed_params)

        assert result.status == "ok"
        assert len(result.aufmass_items) >= 1
        assert len(result.projected_materials) >= 3  # Mix, PE foil, edge strips

    def test_aufmass_area_calculation(self, sample_extraction_result, screed_params):
        """Aufmass should calculate area with waste factor."""
        result = project_screed(sample_extraction_result, screed_params)

        # Find main area item
        area_item = next(
            (i for i in result.aufmass_items if "m²" in i.unit),
            None
        )
        assert area_item is not None

        # Should be total_area × waste_factor
        expected = sample_extraction_result["total_counted_m2"] * screed_params.waste_factor
        # Allow small floating point difference
        assert abs(area_item.quantity - expected) < 0.1

    def test_material_weight_calculation(self, sample_extraction_result, screed_params):
        """Screed material should be calculated from volume × density."""
        result = project_screed(sample_extraction_result, screed_params)

        # Find screed mix material
        mix = next(
            (m for m in result.projected_materials if "Fertigmischung" in m.name),
            None
        )
        assert mix is not None
        assert mix.unit == "t"
        assert mix.quantity > 0

    def test_traceability(self, sample_extraction_result, screed_params):
        """All aufmass items should have derived_from."""
        result = project_screed(sample_extraction_result, screed_params)

        for item in result.aufmass_items:
            assert len(item.derived_from) > 0 or "estimated" in item.formula.lower()

    def test_assumptions_required(self, sample_extraction_result, screed_params):
        """All projected materials should have assumptions."""
        result = project_screed(sample_extraction_result, screed_params)

        for mat in result.projected_materials:
            assert len(mat.assumptions) > 0


class TestDrywallProjection:
    """Tests for drywall projection calculations."""

    def test_basic_calculation(self, sample_extraction_result, drywall_params):
        """Basic drywall projection should produce results."""
        result = project_drywall(sample_extraction_result, drywall_params)

        assert result.status == "ok"
        assert len(result.aufmass_items) >= 1
        assert len(result.projected_materials) >= 4  # Boards, studs, tracks, screws

    def test_wall_area_calculation(self, sample_extraction_result, drywall_params):
        """Wall area should be perimeter × height."""
        result = project_drywall(sample_extraction_result, drywall_params)

        # Sum of room perimeters
        total_perimeter = sum(r.get("perimeter_m", 0) for r in sample_extraction_result["rooms"])
        expected_area = total_perimeter * drywall_params.wall_height_m * drywall_params.waste_factor

        # Find wall area item
        wall_item = next(
            (i for i in result.aufmass_items if "Trockenbau" in i.description),
            None
        )
        assert wall_item is not None
        assert abs(wall_item.quantity - expected_area) < 1.0

    def test_board_quantity_both_sides(self, sample_extraction_result, drywall_params):
        """Board quantity should account for both sides."""
        result = project_drywall(sample_extraction_result, drywall_params)

        # Find board material
        boards = next(
            (m for m in result.projected_materials if "Gipskarton" in m.name),
            None
        )
        assert boards is not None

        # Should include "Both sides" in assumptions
        assert any("both sides" in a.lower() for a in boards.assumptions)


class TestWaterproofingProjection:
    """Tests for waterproofing projection."""

    def test_identifies_wet_rooms(self, sample_extraction_result):
        """Should identify wet rooms by name."""
        params = TradeParams(
            trade_type=TradeType.WATERPROOFING,
            waterproofing_type="liquid",
        )
        result = project_waterproofing(sample_extraction_result, params)

        # Should find "Bad" room
        assert result.status == "ok"
        assert len(result.aufmass_items) >= 1

    def test_floor_and_wall_area(self, sample_extraction_result):
        """Should calculate both floor and wall area for wet rooms."""
        params = TradeParams(
            trade_type=TradeType.WATERPROOFING,
            waterproofing_type="liquid",
            waterproofing_wall_height_m=2.0,
        )
        result = project_waterproofing(sample_extraction_result, params)

        # Should have floor and wall aufmass items
        descriptions = [i.description for i in result.aufmass_items]
        assert any("Boden" in d for d in descriptions)
        assert any("Wand" in d for d in descriptions)


# ==================
# TRADE METADATA TESTS
# ==================

class TestTradeMetadata:
    """Tests for trade metadata."""

    def test_all_trades_have_metadata(self):
        """All TradeType values should have metadata."""
        for trade in TradeType:
            assert trade in TRADE_METADATA

    def test_metadata_structure(self):
        """Metadata should have required fields."""
        for trade, meta in TRADE_METADATA.items():
            assert "name_de" in meta
            assert "name_en" in meta
            assert "required_params" in meta
            assert "optional_params" in meta
            assert "uses_perimeter" in meta
            assert "uses_area" in meta
