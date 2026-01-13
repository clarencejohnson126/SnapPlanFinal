"""
Drywall (Trockenbau) Material Projection

Formulas:
- Wall area = Total Perimeter × Wall Height
- Board quantity = Wall Area × Waste Factor × Layers × 2 (both sides)
- Stud count = ceil(Perimeter / Stud Spacing) + door_frames
- Screws = Wall Area × 25 per m² per layer

Systems:
- single: Single layer, CW 50 profiles
- double: Double layer, CW 75 profiles
- fire_rated: Double layer GKF, CW 100 profiles
"""

import math
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


# Drywall system specifications
DRYWALL_SYSTEMS = {
    "single": {
        "name_de": "Einfachbeplankung",
        "layers": 1,
        "profile_type": "CW 50",
        "track_type": "UW 50",
        "board_thickness_mm": 12.5,
        "board_type": "GKB",  # Standard gypsum board
        "fire_rating": None,
    },
    "double": {
        "name_de": "Doppelbeplankung",
        "layers": 2,
        "profile_type": "CW 75",
        "track_type": "UW 75",
        "board_thickness_mm": 12.5,
        "board_type": "GKB",
        "fire_rating": "F30",
    },
    "fire_rated": {
        "name_de": "Brandschutz F90",
        "layers": 2,
        "profile_type": "CW 100",
        "track_type": "UW 100",
        "board_thickness_mm": 12.5,
        "board_type": "GKF",  # Fire-rated gypsum board
        "fire_rating": "F90",
    },
}


def _extract_perimeter_and_height(
    extraction_result: Dict[str, Any],
    wall_height_m: float,
) -> tuple[float, float, List[GroundTruthMeasurement]]:
    """
    Extract total perimeter and calculate wall area.
    Returns (perimeter_m, wall_area_m2, measurements).
    """
    measurements = []
    total_perimeter = 0.0

    rooms = extraction_result.get("rooms", [])
    for room in rooms:
        perimeter = room.get("perimeter_m") or 0
        if perimeter and perimeter > 0:
            total_perimeter += perimeter
            measurements.append(create_ground_truth_measurement(
                source_field="perimeter_m",
                value=perimeter,
                unit="m",
                source_type="extraction_result",
                source_room_id=room.get("room_number"),
                source_page=room.get("page"),
            ))

    # If no perimeter data, estimate from area
    if total_perimeter <= 0:
        total_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)
        if total_area > 0:
            # Rough estimate: perimeter ≈ 4 × sqrt(area)
            total_perimeter = 4 * (total_area ** 0.5)
            measurements.append(create_ground_truth_measurement(
                source_field="estimated_from_area",
                value=total_perimeter,
                unit="m",
                source_type="calculation",
            ))

    wall_area = total_perimeter * wall_height_m

    return total_perimeter, wall_area, measurements


def project_drywall(
    extraction_result: Dict[str, Any],
    params: TradeParams,
) -> MaterialProjectionResult:
    """
    Calculate drywall material projection.

    Aufmass items (ground truth):
    - Drywall wall area (m²)
    - Wall length (m)

    Projected materials (estimates):
    - Gypsum boards (m²)
    - CW profiles / studs (Stk)
    - UW profiles / tracks (m)
    - Screws (Stk)
    - Joint tape (m)
    - Joint compound (kg)
    - Insulation (m²) - if double layer

    Args:
        extraction_result: Extraction result with rooms and perimeters
        params: Trade parameters (wall_height_m, drywall_system, stud_spacing_mm)

    Returns:
        MaterialProjectionResult with aufmass items and projected materials
    """
    warnings = []
    errors = []

    # Validate params
    param_errors = params.validate()
    if param_errors:
        errors.extend(param_errors)

    wall_height = params.wall_height_m
    if not wall_height or wall_height <= 0:
        errors.append("wall_height_m is required for drywall projection")
        return create_projection_result(
            trade_type=TradeType.DRYWALL,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    # Get system specs
    system_type = params.drywall_system.lower()
    if system_type not in DRYWALL_SYSTEMS:
        warnings.append(f"Unknown system '{system_type}', using 'single'")
        system_type = "single"

    system = DRYWALL_SYSTEMS[system_type]

    # Extract measurements
    total_perimeter, wall_area, measurements = _extract_perimeter_and_height(
        extraction_result, wall_height
    )

    if total_perimeter <= 0:
        errors.append("No perimeter data available in extraction result")
        return create_projection_result(
            trade_type=TradeType.DRYWALL,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    # Calculation factors
    waste_factor = params.waste_factor
    stud_spacing_m = params.stud_spacing_mm / 1000
    layers = system["layers"]

    # ==================
    # AUFMASS ITEMS (Ground Truth)
    # ==================
    aufmass_items = []

    # Wall area
    wall_area_with_waste = wall_area * waste_factor
    aufmass_items.append(create_aufmass_item(
        position="02.01.001",
        description=f"Trockenbau {system['profile_type']} {system['name_de']}",
        quantity=wall_area_with_waste,
        unit="m²",
        derived_from=measurements,
        formula=f"perimeter × height × waste = {total_perimeter:.2f} × {wall_height:.2f} × {waste_factor}",
        formula_description="Total wall area from room perimeters times wall height",
    ))

    # Wall length (for reference)
    aufmass_items.append(create_aufmass_item(
        position="02.01.002",
        description="Wandlänge (Referenz)",
        quantity=total_perimeter,
        unit="m",
        derived_from=measurements,
        formula="sum(room.perimeter_m)",
        formula_description="Total perimeter of all rooms",
    ))

    # ==================
    # PROJECTED MATERIALS (Estimates)
    # ==================
    projected_materials = []

    # 1. Gypsum boards (both sides)
    board_area = wall_area * waste_factor * layers * 2
    projected_materials.append(create_projected_material(
        name=f"Gipskartonplatte {system['board_type']} {system['board_thickness_mm']}mm",
        quantity=board_area,
        unit="m²",
        confidence=0.75,
        assumptions=[
            f"System: {system['name_de']} ({layers} layer(s))",
            f"Both sides of wall = ×2",
            f"Waste factor: {waste_factor:.0%}",
            f"Standard board size: 2500×1250mm",
        ],
        derived_from_aufmass=aufmass_items[0].item_id,
    ))

    # 2. CW Profiles (studs)
    stud_count = math.ceil(total_perimeter / stud_spacing_m)
    # Add extra for door frames (estimate: 1 door per 10m perimeter)
    estimated_doors = max(1, int(total_perimeter / 10))
    stud_count += estimated_doors * 2  # 2 extra studs per door frame

    projected_materials.append(create_projected_material(
        name=f"{system['profile_type']} Ständerprofil 2600mm",
        quantity=stud_count,
        unit="Stk",
        confidence=0.70,
        assumptions=[
            f"Stud spacing: {params.stud_spacing_mm}mm (standard)",
            f"Profile height: 2600mm (standard)",
            f"Estimated {estimated_doors} door frames (+2 studs each)",
            "May need cutting for exact wall height",
        ],
        derived_from_aufmass=aufmass_items[1].item_id,
    ))

    # 3. UW Profiles (tracks) - top and bottom
    track_length = total_perimeter * 2 * waste_factor  # Top + bottom
    projected_materials.append(create_projected_material(
        name=f"{system['track_type']} Anschlussprofil",
        quantity=track_length,
        unit="m",
        confidence=0.80,
        assumptions=[
            "Top and bottom tracks (×2)",
            f"Waste factor: {waste_factor:.0%}",
            "Standard 4m profile lengths",
        ],
        derived_from_aufmass=aufmass_items[1].item_id,
    ))

    # 4. Screws
    screws_per_m2 = 25  # Standard: ~25 screws per m² per layer
    total_screws = wall_area * screws_per_m2 * layers * 2  # Both sides
    projected_materials.append(create_projected_material(
        name="Schnellbauschrauben 3.9×25mm",
        quantity=total_screws,
        unit="Stk",
        confidence=0.65,
        assumptions=[
            f"~{screws_per_m2} screws per m² per layer",
            f"{layers} layer(s), both sides",
            "Screw spacing: ~250mm board edge, ~300mm field",
        ],
        derived_from_aufmass=aufmass_items[0].item_id,
    ))

    # 5. Joint tape
    # Estimate: vertical joints every 1.25m + horizontal at floor/ceiling
    vertical_joints = math.ceil(total_perimeter * 2 / 1.25)  # Both sides
    horizontal_joints = total_perimeter * 2 * 2  # Top + bottom, both sides
    total_joint_length = (vertical_joints * wall_height) + horizontal_joints
    total_joint_length *= waste_factor

    projected_materials.append(create_projected_material(
        name="Fugenband Papier 50mm",
        quantity=total_joint_length,
        unit="m",
        confidence=0.60,
        assumptions=[
            "Vertical joints every 1.25m (board width)",
            "Horizontal joints at floor and ceiling",
            "Both sides of wall",
            f"Waste factor: {waste_factor:.0%}",
        ],
    ))

    # 6. Joint compound
    compound_per_m_joint = 0.3  # ~0.3 kg per meter of joint
    total_compound = total_joint_length * compound_per_m_joint
    projected_materials.append(create_projected_material(
        name="Fugenspachtel (Fertigmischung)",
        quantity=total_compound,
        unit="kg",
        confidence=0.55,
        assumptions=[
            "~0.3 kg per meter of joint",
            "Includes 3 coats (fill, tape, finish)",
            "May vary with joint quality requirements",
        ],
    ))

    # 7. Insulation (for double/fire-rated systems)
    if layers >= 2:
        insulation_area = wall_area * waste_factor
        projected_materials.append(create_projected_material(
            name="Mineralwolle Dämmung 60mm",
            quantity=insulation_area,
            unit="m²",
            confidence=0.70,
            assumptions=[
                "Required for double-layer systems",
                "60mm thickness for CW 75/100 profiles",
                f"Waste factor: {waste_factor:.0%}",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    # Create result
    return create_projection_result(
        trade_type=TradeType.DRYWALL,
        source_extraction_id=extraction_result.get("extraction_id", "unknown"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        warnings=warnings,
        errors=errors,
    )
