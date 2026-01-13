"""
Waterproofing (Abdichtung) Material Projection

Formulas:
- Wet room floor area = Sum of areas for rooms containing "Bad", "WC", "Dusche"
- Wall area for wet rooms = Wet room perimeter × Wall height (typically 2.0m)
- Total waterproofing area = Floor + Wall area
- Material quantities based on 2-coat application

Types:
- liquid: Liquid-applied membrane (Flüssigabdichtung)
- membrane: Sheet membrane (Bahnenabdichtung)
- bitumen: Bituminous waterproofing (for below-grade)
"""

from typing import Dict, Any, List, Optional
from app.services.trade_projection import (
    TradeType,
    TradeParams,
    ProjectionMethod,
    MaterialProjectionResult,
    GroundTruthMeasurement,
    AufmassItem,
    ProjectedMaterial,
    create_ground_truth_measurement,
    create_aufmass_item,
    create_projected_material,
    create_projection_result,
)


# Keywords indicating wet rooms (German)
WET_ROOM_KEYWORDS = [
    "bad", "wc", "dusche", "sanitär", "nassraum", "nassbereich",
    "bathroom", "toilet", "shower", "wet room",
]

# Waterproofing type specifications
WATERPROOFING_TYPES = {
    "liquid": {
        "name_de": "Flüssigabdichtung",
        "coverage_kg_per_m2": 1.5,  # 2 coats
        "primer_kg_per_m2": 0.2,
        "cure_hours": 24,
        "coats": 2,
    },
    "membrane": {
        "name_de": "Bahnenabdichtung",
        "overlap_factor": 1.15,  # 15% for overlaps
        "adhesive_kg_per_m2": 1.0,
        "primer_kg_per_m2": 0.15,
    },
    "bitumen": {
        "name_de": "Bitumenabdichtung",
        "coverage_kg_per_m2": 3.0,  # Thicker application
        "primer_kg_per_m2": 0.3,
        "layers": 2,
    },
}


def _identify_wet_rooms(extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter rooms that need waterproofing based on name/category.
    Returns list of room dicts.
    """
    wet_rooms = []

    for room in extraction_result.get("rooms", []):
        room_name = room.get("room_name", "").lower()
        room_category = room.get("category", "").lower()

        # Check if any keyword matches
        is_wet = any(kw in room_name or kw in room_category for kw in WET_ROOM_KEYWORDS)

        if is_wet:
            wet_rooms.append(room)

    return wet_rooms


def _calculate_wet_room_areas(
    wet_rooms: List[Dict[str, Any]],
    wall_height_m: float,
) -> tuple[float, float, float, List[GroundTruthMeasurement]]:
    """
    Calculate floor area, wall area, and perimeter for wet rooms.
    Returns (floor_area, wall_area, perimeter, measurements).
    """
    measurements = []
    total_floor_area = 0.0
    total_perimeter = 0.0

    for room in wet_rooms:
        # Floor area
        area = room.get("counted_m2") or room.get("area_m2", 0)
        if area > 0:
            total_floor_area += area
            measurements.append(create_ground_truth_measurement(
                source_field="area_m2",
                value=area,
                unit="m2",
                source_type="extraction_result",
                source_room_id=room.get("room_number"),
                source_page=room.get("page"),
            ))

        # Perimeter
        perimeter = room.get("perimeter_m") or 0
        if perimeter and perimeter > 0:
            total_perimeter += perimeter
        elif area > 0:
            # Estimate perimeter from area (assuming roughly square)
            perimeter = 4 * (area ** 0.5)
            total_perimeter += perimeter

    # Calculate wall area
    total_wall_area = total_perimeter * wall_height_m

    return total_floor_area, total_wall_area, total_perimeter, measurements


def project_waterproofing(
    extraction_result: Dict[str, Any],
    params: TradeParams,
) -> MaterialProjectionResult:
    """
    Calculate waterproofing material projection.

    Aufmass items (ground truth):
    - Wet room floor area (m²)
    - Wet room wall area (m²)

    Projected materials (estimates):
    - Waterproofing membrane/liquid (m² or kg)
    - Primer (kg or L)
    - Sealing tape for corners (m)
    - Sealing collars for fixtures (Stk)
    - Reinforcement tape for joints (m)

    Args:
        extraction_result: Extraction result with rooms
        params: Trade parameters (waterproofing_type, wall_height_m)

    Returns:
        MaterialProjectionResult with aufmass items and projected materials
    """
    warnings = []
    errors = []

    # Validate params
    param_errors = params.validate()
    if param_errors:
        errors.extend(param_errors)

    # Get waterproofing type specs
    wp_type = params.waterproofing_type.lower()
    if wp_type not in WATERPROOFING_TYPES:
        warnings.append(f"Unknown waterproofing type '{wp_type}', using 'liquid'")
        wp_type = "liquid"

    spec = WATERPROOFING_TYPES[wp_type]

    # Wall height for wet areas
    wall_height = params.waterproofing_wall_height_m or 2.0

    # Identify wet rooms
    wet_rooms = _identify_wet_rooms(extraction_result)

    if not wet_rooms:
        warnings.append("No wet rooms identified (Bad, WC, Dusche). Using entire floor area.")
        # Use entire floor area if no wet rooms identified
        total_floor_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)
        if total_floor_area <= 0:
            errors.append("No floor area available and no wet rooms identified")
            return create_projection_result(
                trade_type=TradeType.WATERPROOFING,
                source_extraction_id=extraction_result.get("extraction_id", "unknown"),
                params=params,
                aufmass_items=[],
                projected_materials=[],
                errors=errors,
                warnings=warnings,
            )

        # Estimate for entire area (likely a wet area building)
        total_perimeter = 4 * (total_floor_area ** 0.5)
        total_wall_area = total_perimeter * wall_height
        measurements = [create_ground_truth_measurement(
            source_field="total_area_m2",
            value=total_floor_area,
            unit="m2",
            source_type="extraction_result",
        )]
    else:
        # Calculate from identified wet rooms
        total_floor_area, total_wall_area, total_perimeter, measurements = _calculate_wet_room_areas(
            wet_rooms, wall_height
        )

    if total_floor_area <= 0:
        errors.append("No wet room floor area found")
        return create_projection_result(
            trade_type=TradeType.WATERPROOFING,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    waste_factor = params.waste_factor
    total_waterproofing_area = (total_floor_area + total_wall_area) * waste_factor

    # Count wet rooms for fixture estimates
    wet_room_count = len(wet_rooms) if wet_rooms else 1

    # ==================
    # AUFMASS ITEMS (Ground Truth)
    # ==================
    aufmass_items = []

    # Wet room floor area
    aufmass_items.append(create_aufmass_item(
        position="05.01.001",
        description=f"Abdichtung Bodenfläche Nassräume",
        quantity=total_floor_area * waste_factor,
        unit="m²",
        derived_from=measurements,
        formula=f"sum(wet_room_areas) × waste = {total_floor_area:.2f} × {waste_factor}",
        formula_description=f"Total floor area of {wet_room_count} wet room(s)",
    ))

    # Wet room wall area
    aufmass_items.append(create_aufmass_item(
        position="05.01.002",
        description=f"Abdichtung Wandfläche bis {wall_height:.1f}m Höhe",
        quantity=total_wall_area * waste_factor,
        unit="m²",
        derived_from=[],
        formula=f"perimeter × height × waste = {total_perimeter:.2f} × {wall_height:.2f} × {waste_factor}",
        formula_description="Wall area up to specified height in wet rooms",
    ))

    # ==================
    # PROJECTED MATERIALS (Estimates)
    # ==================
    projected_materials = []

    # Materials vary by type
    if wp_type == "liquid":
        # 1. Liquid membrane
        membrane_kg = total_waterproofing_area * spec["coverage_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name=f"{spec['name_de']} (2-Komponenten)",
            quantity=membrane_kg,
            unit="kg",
            confidence=0.75,
            assumptions=[
                f"Coverage: {spec['coverage_kg_per_m2']} kg/m² for {spec['coats']} coats",
                f"Wall height: {wall_height}m",
                f"Waste factor: {waste_factor:.0%}",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # 2. Primer
        primer_kg = total_waterproofing_area * spec["primer_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name="Grundierung / Haftgrund",
            quantity=primer_kg,
            unit="kg",
            confidence=0.80,
            assumptions=[
                f"Coverage: {spec['primer_kg_per_m2']} kg/m²",
                "Single coat application",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    elif wp_type == "membrane":
        # 1. Sheet membrane
        membrane_area = total_waterproofing_area * spec["overlap_factor"]
        projected_materials.append(create_projected_material(
            name=f"{spec['name_de']}",
            quantity=membrane_area,
            unit="m²",
            confidence=0.75,
            assumptions=[
                f"Overlap factor: {spec['overlap_factor']:.0%}",
                "Standard roll width (1m)",
                f"Wall height: {wall_height}m",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # 2. Adhesive
        adhesive_kg = total_waterproofing_area * spec["adhesive_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name="Dichtkleber",
            quantity=adhesive_kg,
            unit="kg",
            confidence=0.70,
            assumptions=[
                f"Coverage: {spec['adhesive_kg_per_m2']} kg/m²",
                "Full-spread application",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # 3. Primer
        primer_kg = total_waterproofing_area * spec["primer_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name="Voranstrich",
            quantity=primer_kg,
            unit="kg",
            confidence=0.80,
            assumptions=[
                f"Coverage: {spec['primer_kg_per_m2']} kg/m²",
            ],
        ))

    elif wp_type == "bitumen":
        # 1. Bitumen membrane
        membrane_kg = total_waterproofing_area * spec["coverage_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name=f"{spec['name_de']}",
            quantity=membrane_kg,
            unit="kg",
            confidence=0.70,
            assumptions=[
                f"Coverage: {spec['coverage_kg_per_m2']} kg/m² for {spec['layers']} layers",
                "Hot or cold application",
                "Suitable for below-grade waterproofing",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # 2. Primer
        primer_kg = total_waterproofing_area * spec["primer_kg_per_m2"]
        projected_materials.append(create_projected_material(
            name="Bitumenvoranstrich",
            quantity=primer_kg,
            unit="kg",
            confidence=0.75,
            assumptions=[
                f"Coverage: {spec['primer_kg_per_m2']} kg/m²",
            ],
        ))

    # Common accessories for all types

    # 3. Sealing tape for corners/edges
    # Estimate: ~2m per m² of floor area (internal corners, wall-floor junctions)
    corner_length = total_perimeter + (total_floor_area * 0.5)
    projected_materials.append(create_projected_material(
        name="Dichtband / Fugenband 120mm",
        quantity=corner_length,
        unit="m",
        confidence=0.65,
        assumptions=[
            "For wall-floor junctions",
            "Internal corners",
            "Around penetrations",
            "~2m tape per m² floor area (estimated)",
        ],
    ))

    # 4. Sealing collars for fixtures
    # Estimate: 3-5 penetrations per wet room (drain, toilet, pipes)
    fixture_count = wet_room_count * 4  # Average 4 penetrations per wet room
    projected_materials.append(create_projected_material(
        name="Dichtmanschetten (Rohrdurchführung)",
        quantity=fixture_count,
        unit="Stk",
        confidence=0.60,
        assumptions=[
            f"~4 penetrations per wet room",
            f"{wet_room_count} wet room(s) identified",
            "Includes: drain, toilet, supply pipes",
        ],
    ))

    # 5. Floor drain collars
    drain_count = wet_room_count  # 1 floor drain per wet room
    projected_materials.append(create_projected_material(
        name="Bodenablauf-Dichtmanschette",
        quantity=drain_count,
        unit="Stk",
        confidence=0.70,
        assumptions=[
            "1 floor drain per wet room",
            "May need more for large shower areas",
        ],
    ))

    # 6. Reinforcement fabric (for liquid membrane)
    if wp_type == "liquid":
        # For corners and critical areas - estimate 20% of total area
        fabric_area = total_waterproofing_area * 0.20
        projected_materials.append(create_projected_material(
            name="Armierungsgewebe",
            quantity=fabric_area,
            unit="m²",
            confidence=0.55,
            assumptions=[
                "For corners, joints, and stress points",
                "~20% of total waterproofing area",
                "May vary based on substrate condition",
            ],
        ))

    # Create result
    return create_projection_result(
        trade_type=TradeType.WATERPROOFING,
        source_extraction_id=extraction_result.get("extraction_id", "unknown"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        warnings=warnings,
        errors=errors,
    )
