"""
Floor Finish (Oberbelag) Material Projection

Formulas vary by finish type:
- Laminate/Parquet: Area × waste factor + underlay + skirting
- Tile: Area × waste factor + adhesive + grout
- Carpet: Area × waste factor + adhesive/tape

Types:
- laminate: Click-lock laminate flooring
- parquet: Engineered or solid wood parquet
- tile: Ceramic or porcelain tiles
- carpet: Wall-to-wall carpet
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


# Floor finish type specifications
FLOOR_FINISH_TYPES = {
    "laminate": {
        "name_de": "Laminat",
        "waste_factor": 1.10,  # 10% for click-lock
        "needs_underlay": True,
        "underlay_type": "PE-Schaum 2mm",
        "needs_skirting": True,
        "adhesive_per_m2": 0,  # Floating installation
    },
    "parquet": {
        "name_de": "Parkett",
        "waste_factor": 1.12,  # 12% for pattern matching
        "needs_underlay": True,
        "underlay_type": "Trittschalldämmung 3mm",
        "needs_skirting": True,
        "adhesive_per_m2": 0,  # Can be floating or glued
        "needs_oil": True,
    },
    "tile": {
        "name_de": "Fliesen",
        "waste_factor": 1.15,  # 15% for cuts and breakage
        "needs_underlay": False,
        "needs_skirting": False,  # Often uses cove base tiles
        "adhesive_kg_per_m2": 4.5,
        "grout_kg_per_m2": 0.5,
    },
    "carpet": {
        "name_de": "Teppichboden",
        "waste_factor": 1.05,  # 5% less waste
        "needs_underlay": False,
        "needs_skirting": True,
        "adhesive_per_m2": 0.3,  # kg of carpet adhesive
    },
}


def _extract_floor_data(extraction_result: Dict[str, Any]) -> tuple[float, float, List[GroundTruthMeasurement]]:
    """
    Extract floor area and perimeter for finish calculations.
    Returns (area_m2, perimeter_m, measurements).
    """
    measurements = []

    # Get floor area
    floor_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)
    if floor_area > 0:
        measurements.append(create_ground_truth_measurement(
            source_field="total_counted_m2" if "total_counted_m2" in extraction_result else "total_area_m2",
            value=floor_area,
            unit="m2",
            source_type="extraction_result",
        ))

    # Get perimeter from rooms
    total_perimeter = 0.0
    rooms = extraction_result.get("rooms", [])
    for room in rooms:
        perimeter = room.get("perimeter_m") or 0
        if perimeter and perimeter > 0:
            total_perimeter += perimeter

    if total_perimeter > 0:
        measurements.append(create_ground_truth_measurement(
            source_field="sum(perimeter_m)",
            value=total_perimeter,
            unit="m",
            source_type="extraction_result",
        ))
    elif floor_area > 0:
        # Estimate perimeter from area
        total_perimeter = 4 * (floor_area ** 0.5)
        measurements.append(create_ground_truth_measurement(
            source_field="estimated_from_area",
            value=total_perimeter,
            unit="m",
            source_type="calculation",
        ))

    return floor_area, total_perimeter, measurements


def project_floor_finish(
    extraction_result: Dict[str, Any],
    params: TradeParams,
) -> MaterialProjectionResult:
    """
    Calculate floor finish material projection.

    Aufmass items (ground truth):
    - Floor finish area (m²)
    - Skirting length (m)

    Projected materials (estimates) - varies by type:
    - Flooring material (m²)
    - Underlay (m²) - laminate/parquet
    - Skirting boards (m)
    - Adhesive (kg) - tile/carpet
    - Grout (kg) - tile
    - Oil/finish (L) - parquet

    Args:
        extraction_result: Extraction result with rooms and areas
        params: Trade parameters (finish_type, waste_factor)

    Returns:
        MaterialProjectionResult with aufmass items and projected materials
    """
    warnings = []
    errors = []

    # Validate params
    param_errors = params.validate()
    if param_errors:
        errors.extend(param_errors)

    # Get finish type specs
    finish_type = params.finish_type.lower()
    if finish_type not in FLOOR_FINISH_TYPES:
        warnings.append(f"Unknown finish type '{finish_type}', using 'laminate'")
        finish_type = "laminate"

    spec = FLOOR_FINISH_TYPES[finish_type]

    # Extract measurements
    floor_area, total_perimeter, measurements = _extract_floor_data(extraction_result)

    if floor_area <= 0:
        errors.append("No floor area found in extraction result")
        return create_projection_result(
            trade_type=TradeType.FLOOR_FINISH,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    # Use spec waste factor or override from params
    waste_factor = params.waste_factor if params.waste_factor != 1.10 else spec["waste_factor"]

    # ==================
    # AUFMASS ITEMS (Ground Truth)
    # ==================
    aufmass_items = []

    # Floor area with waste
    floor_area_with_waste = floor_area * waste_factor
    aufmass_items.append(create_aufmass_item(
        position="04.01.001",
        description=f"Bodenbelag {spec['name_de']}",
        quantity=floor_area_with_waste,
        unit="m²",
        derived_from=measurements[:1],  # Area measurement
        formula=f"floor_area × waste_factor = {floor_area:.2f} × {waste_factor}",
        formula_description="Total floor area with waste factor for cuts",
    ))

    # Skirting length (if applicable)
    if spec.get("needs_skirting", False):
        skirting_length = total_perimeter * 1.05  # 5% waste for corners
        aufmass_items.append(create_aufmass_item(
            position="04.01.002",
            description="Sockelleisten",
            quantity=skirting_length,
            unit="m",
            derived_from=measurements[1:] if len(measurements) > 1 else [],
            formula=f"perimeter × 1.05 = {total_perimeter:.2f} × 1.05",
            formula_description="Room perimeter with 5% waste for corners",
        ))

    # ==================
    # PROJECTED MATERIALS (Estimates)
    # ==================
    projected_materials = []

    # 1. Main flooring material
    projected_materials.append(create_projected_material(
        name=f"{spec['name_de']} Bodenbelag",
        quantity=floor_area_with_waste,
        unit="m²",
        confidence=0.80,
        assumptions=[
            f"Finish type: {spec['name_de']}",
            f"Waste factor: {waste_factor:.0%}",
            "Standard plank/tile sizes",
        ],
        derived_from_aufmass=aufmass_items[0].item_id,
    ))

    # 2. Underlay (laminate/parquet)
    if spec.get("needs_underlay", False):
        underlay_area = floor_area * 1.05  # 5% overlap
        projected_materials.append(create_projected_material(
            name=spec.get("underlay_type", "Trittschalldämmung"),
            quantity=underlay_area,
            unit="m²",
            confidence=0.85,
            assumptions=[
                "5% overlap at joints",
                "Standard roll width (1m)",
                "Required for floating installation",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    # 3. Skirting boards
    if spec.get("needs_skirting", False):
        skirting_length = total_perimeter * 1.10  # 10% for cuts/waste
        projected_materials.append(create_projected_material(
            name="Sockelleiste MDF 60mm",
            quantity=skirting_length,
            unit="m",
            confidence=0.75,
            assumptions=[
                "10% waste for mitre cuts",
                "Standard 2.4m lengths",
                "Does not include inside corners/caps",
            ],
        ))

        # Skirting clips/adhesive
        clips_per_m = 3  # ~3 clips per meter
        projected_materials.append(create_projected_material(
            name="Sockelleisten-Clips",
            quantity=total_perimeter * clips_per_m,
            unit="Stk",
            confidence=0.70,
            assumptions=[
                f"~{clips_per_m} clips per meter",
                "Alternative: adhesive mounting",
            ],
        ))

    # 4. Tile-specific materials
    if finish_type == "tile":
        # Adhesive
        adhesive_kg = floor_area * spec.get("adhesive_kg_per_m2", 4.5) * waste_factor
        projected_materials.append(create_projected_material(
            name="Fliesenkleber Flexkleber",
            quantity=adhesive_kg,
            unit="kg",
            confidence=0.75,
            assumptions=[
                f"~{spec.get('adhesive_kg_per_m2', 4.5)} kg/m²",
                "Medium-bed application",
                "Varies with tile size and substrate",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Grout
        grout_kg = floor_area * spec.get("grout_kg_per_m2", 0.5)
        projected_materials.append(create_projected_material(
            name="Fugenmörtel",
            quantity=grout_kg,
            unit="kg",
            confidence=0.70,
            assumptions=[
                f"~{spec.get('grout_kg_per_m2', 0.5)} kg/m²",
                "Standard 3mm joint width",
                "Varies with tile size",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Tile spacers
        spacers = floor_area * 10  # ~10 spacers per m²
        projected_materials.append(create_projected_material(
            name="Fliesenkreuze 3mm",
            quantity=spacers,
            unit="Stk",
            confidence=0.60,
            assumptions=[
                "~10 spacers per m²",
                "Based on 30×30cm tiles",
                "Larger tiles need fewer",
            ],
        ))

    # 5. Carpet-specific materials
    if finish_type == "carpet":
        adhesive_kg = floor_area * spec.get("adhesive_per_m2", 0.3)
        projected_materials.append(create_projected_material(
            name="Teppichkleber",
            quantity=adhesive_kg,
            unit="kg",
            confidence=0.70,
            assumptions=[
                f"~{spec.get('adhesive_per_m2', 0.3)} kg/m²",
                "Full-spread adhesive method",
                "Alternative: double-sided tape",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Seaming tape
        seam_length = floor_area * 0.2  # Estimate ~0.2m seam per m² for rolls
        projected_materials.append(create_projected_material(
            name="Nahtband",
            quantity=seam_length,
            unit="m",
            confidence=0.55,
            assumptions=[
                "Estimated from typical roll widths (4m)",
                "Actual amount depends on room layout",
                "May be less for small rooms",
            ],
        ))

    # 6. Parquet-specific materials
    if finish_type == "parquet" and spec.get("needs_oil", False):
        # Oil/finish for parquet
        oil_liters = floor_area * 0.1  # ~0.1 L/m² for 2 coats
        projected_materials.append(create_projected_material(
            name="Parkettöl / Versiegelung",
            quantity=oil_liters,
            unit="L",
            confidence=0.65,
            assumptions=[
                "~0.1 L/m² for 2 coats",
                "Oil-based finish",
                "Alternative: lacquer finish",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    # 7. Common accessories
    # Transition strips (estimated: 1 per room)
    room_count = len(extraction_result.get("rooms", []))
    if room_count > 0:
        projected_materials.append(create_projected_material(
            name="Übergangsprofile",
            quantity=max(room_count - 1, 1),  # Between rooms
            unit="Stk",
            confidence=0.55,
            assumptions=[
                "One profile per room transition",
                "May vary based on room layout",
                "Different profiles for different height changes",
            ],
        ))

    # Create result
    return create_projection_result(
        trade_type=TradeType.FLOOR_FINISH,
        source_extraction_id=extraction_result.get("extraction_id", "unknown"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        warnings=warnings,
        errors=errors,
    )
