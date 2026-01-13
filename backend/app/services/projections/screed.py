"""
Screed (Estrich) Material Projection

Formulas:
- Screed volume = Floor Area × Thickness
- Material weight = Volume × Density × Waste Factor
- Edge strips = Total Perimeter × 1.05

Material types:
- CT (Zementestrich): Cement screed, 28-day cure, 2100 kg/m³
- CA (Anhydritestrich): Anhydrite/gypsum screed, 7-day cure, 2100 kg/m³
- MA (Gussasphaltestrich): Mastic asphalt, 1-day cure, 2400 kg/m³
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


# Screed type specifications
SCREED_TYPES = {
    "ct": {
        "name_de": "Zementestrich CT",
        "name_en": "Cement Screed",
        "density_kg_m3": 2100,
        "cure_days": 28,
        "min_thickness_mm": 45,
        "typical_thickness_mm": 65,
    },
    "ca": {
        "name_de": "Anhydritestrich CA",
        "name_en": "Anhydrite Screed",
        "density_kg_m3": 2100,
        "cure_days": 7,
        "min_thickness_mm": 35,
        "typical_thickness_mm": 50,
    },
    "ma": {
        "name_de": "Gussasphaltestrich MA",
        "name_en": "Mastic Asphalt",
        "density_kg_m3": 2400,
        "cure_days": 1,
        "min_thickness_mm": 25,
        "typical_thickness_mm": 35,
    },
}


def _extract_floor_area(extraction_result: Dict[str, Any]) -> tuple[float, List[GroundTruthMeasurement]]:
    """
    Extract total floor area from extraction result.
    Returns (area_m2, list of source measurements).
    """
    measurements = []

    # Primary: use total_area_m2 or total_counted_m2
    total_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)

    if total_area > 0:
        measurements.append(create_ground_truth_measurement(
            source_field="total_counted_m2" if "total_counted_m2" in extraction_result else "total_area_m2",
            value=total_area,
            unit="m2",
            source_type="extraction_result",
        ))

    return total_area, measurements


def _extract_total_perimeter(extraction_result: Dict[str, Any]) -> tuple[float, List[GroundTruthMeasurement]]:
    """
    Extract total perimeter from extraction result rooms.
    Returns (perimeter_m, list of source measurements).
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

    return total_perimeter, measurements


def project_screed(
    extraction_result: Dict[str, Any],
    params: TradeParams,
) -> MaterialProjectionResult:
    """
    Calculate screed material projection.

    Aufmass items (ground truth):
    - Estrich area (m²)

    Projected materials (estimates):
    - Screed mix (tonnes)
    - PE vapor barrier (m²)
    - Edge strips (m)
    - Optional: reinforcement mesh (m²)

    Args:
        extraction_result: Extraction result with rooms and areas
        params: Trade parameters (screed_type, screed_thickness_mm, waste_factor)

    Returns:
        MaterialProjectionResult with aufmass items and projected materials
    """
    warnings = []
    errors = []

    # Validate params
    param_errors = params.validate()
    if param_errors:
        errors.extend(param_errors)

    # Get screed type specs
    screed_type = params.screed_type.lower()
    if screed_type not in SCREED_TYPES:
        errors.append(f"Unknown screed type: {screed_type}. Valid types: {list(SCREED_TYPES.keys())}")
        screed_type = "ct"  # Default fallback

    screed_spec = SCREED_TYPES[screed_type]

    # Validate thickness
    thickness_mm = params.screed_thickness_mm
    if thickness_mm < screed_spec["min_thickness_mm"]:
        warnings.append(
            f"Thickness {thickness_mm}mm is below minimum {screed_spec['min_thickness_mm']}mm for {screed_spec['name_de']}"
        )

    # Extract measurements
    floor_area, area_measurements = _extract_floor_area(extraction_result)
    total_perimeter, perimeter_measurements = _extract_total_perimeter(extraction_result)

    if floor_area <= 0:
        errors.append("No floor area found in extraction result")
        return create_projection_result(
            trade_type=TradeType.SCREED,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    if total_perimeter <= 0:
        warnings.append("No perimeter data found - edge strip quantity estimated from area")
        # Estimate perimeter from area (assuming roughly square rooms)
        estimated_perimeter = 4 * (floor_area ** 0.5)
        total_perimeter = estimated_perimeter
        perimeter_measurements = [create_ground_truth_measurement(
            source_field="estimated_from_area",
            value=estimated_perimeter,
            unit="m",
            source_type="calculation",
        )]

    # Calculate quantities
    waste_factor = params.waste_factor
    thickness_m = thickness_mm / 1000
    volume_m3 = floor_area * thickness_m
    density = screed_spec["density_kg_m3"]

    # ==================
    # AUFMASS ITEMS (Ground Truth)
    # ==================
    aufmass_items = []

    # Main screed area
    screed_area_with_waste = floor_area * waste_factor
    aufmass_items.append(create_aufmass_item(
        position="03.01.001",
        description=f"{screed_spec['name_de']} d={thickness_mm}mm",
        quantity=screed_area_with_waste,
        unit="m²",
        derived_from=area_measurements,
        formula=f"floor_area × waste_factor = {floor_area:.2f} × {waste_factor}",
        formula_description="Total floor area with waste factor for cuts and overlaps",
    ))

    # ==================
    # PROJECTED MATERIALS (Estimates)
    # ==================
    projected_materials = []

    # 1. Screed mix (tonnes)
    screed_weight_kg = volume_m3 * density * waste_factor
    screed_weight_tonnes = screed_weight_kg / 1000
    projected_materials.append(create_projected_material(
        name=f"{screed_spec['name_de']} Fertigmischung",
        quantity=screed_weight_tonnes,
        unit="t",
        confidence=0.80,
        assumptions=[
            f"Screed type: {screed_spec['name_de']}",
            f"Thickness: {thickness_mm}mm",
            f"Density: {density} kg/m³",
            f"Waste factor: {waste_factor:.0%}",
            f"Volume: {volume_m3:.2f} m³",
        ],
        derived_from_aufmass=aufmass_items[0].item_id,
    ))

    # 2. PE vapor barrier (0.2mm film)
    pe_area = floor_area * 1.15  # 15% overlap allowance
    projected_materials.append(create_projected_material(
        name="PE-Folie 0.2mm (Dampfsperre)",
        quantity=pe_area,
        unit="m²",
        confidence=0.85,
        assumptions=[
            "15% overlap allowance for joints",
            "Single layer application",
            "Standard residential/commercial use",
        ],
        derived_from_aufmass=aufmass_items[0].item_id,
    ))

    # 3. Edge strips (Randstreifen)
    edge_strip_length = total_perimeter * 1.05  # 5% waste for corners
    projected_materials.append(create_projected_material(
        name="Randstreifen PE 100mm",
        quantity=edge_strip_length,
        unit="m",
        confidence=0.90,
        assumptions=[
            "5% waste allowance for corners",
            "Standard 100mm height",
            "One continuous strip around perimeter",
        ],
    ))

    # 4. Reinforcement mesh (optional, for larger areas or CT screed)
    if screed_type == "ct" and floor_area > 50:
        mesh_area = floor_area * 1.10  # 10% overlap
        projected_materials.append(create_projected_material(
            name="Bewehrungsmatte Q188",
            quantity=mesh_area,
            unit="m²",
            confidence=0.60,
            assumptions=[
                "Recommended for cement screed CT",
                "10% overlap at joints",
                "Required for areas > 50m² or heavy loads",
                "May not be needed - verify with structural requirements",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    # 5. Adhesive tape for PE joints
    # Estimate: ~1m tape per 2m² of PE foil (for 1m wide rolls with overlaps)
    tape_length = floor_area * 0.5
    projected_materials.append(create_projected_material(
        name="PE-Klebeband 50mm",
        quantity=tape_length,
        unit="m",
        confidence=0.65,
        assumptions=[
            "Based on standard 1m roll width",
            "~0.5m tape per m² for joint sealing",
            "Actual amount depends on room layout",
        ],
    ))

    # Create result
    return create_projection_result(
        trade_type=TradeType.SCREED,
        source_extraction_id=extraction_result.get("extraction_id", "unknown"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        warnings=warnings,
        errors=errors,
    )
