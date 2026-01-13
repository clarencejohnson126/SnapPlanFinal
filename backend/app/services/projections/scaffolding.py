"""
Scaffolding (Gerüstbau) Material Projection

Formulas:
- Facade scaffolding area = Building Perimeter × Scaffold Height
- Mobile scaffold count = ceil(Working Area / 100m²)
- Safety net = Perimeter × Height × 1.15

Types:
- standard: Standard facade scaffolding (Fassadengerüst)
- rollgeruest: Mobile scaffold towers (Rollgerüst)
- fassade: Heavy-duty facade scaffolding with protective screens
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


# Scaffolding type specifications
SCAFFOLD_TYPES = {
    "standard": {
        "name_de": "Fassadengerüst Standard",
        "rental_per_m2_week_eur": 8.50,
        "setup_per_m2_eur": 12.00,
        "dismount_per_m2_eur": 8.00,
        "max_height_m": 24,
        "bay_width_m": 2.5,
        "lift_height_m": 2.0,
    },
    "rollgeruest": {
        "name_de": "Rollgerüst / Fahrgerüst",
        "rental_per_unit_week_eur": 120.00,
        "coverage_m2_per_unit": 100,
        "platform_size_m2": 2.0,
        "max_height_m": 12,
    },
    "fassade": {
        "name_de": "Fassadengerüst mit Schutzplane",
        "rental_per_m2_week_eur": 10.50,
        "setup_per_m2_eur": 15.00,
        "dismount_per_m2_eur": 10.00,
        "net_factor": 1.15,  # Safety net coverage factor
        "max_height_m": 50,
    },
}


def _extract_building_perimeter(extraction_result: Dict[str, Any]) -> tuple[float, List[GroundTruthMeasurement]]:
    """
    Extract building perimeter for facade scaffolding.
    For scaffolding, we need the OUTER perimeter, not individual room perimeters.
    If not available, estimate from total area.
    """
    measurements = []

    # Try to get building perimeter (if stored)
    building_perimeter = extraction_result.get("building_perimeter_m") or 0

    if building_perimeter and building_perimeter > 0:
        measurements.append(create_ground_truth_measurement(
            source_field="building_perimeter_m",
            value=building_perimeter,
            unit="m",
            source_type="extraction_result",
        ))
        return building_perimeter, measurements

    # Estimate from total floor area
    # Assumption: roughly rectangular building, perimeter ≈ 4 × sqrt(area)
    total_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)

    if total_area > 0:
        # Estimate building perimeter (exterior walls)
        # Using factor 4.5 instead of 4 to account for non-square shapes
        estimated_perimeter = 4.5 * (total_area ** 0.5)
        measurements.append(create_ground_truth_measurement(
            source_field="estimated_from_total_area",
            value=estimated_perimeter,
            unit="m",
            source_type="calculation",
        ))
        return estimated_perimeter, measurements

    return 0, measurements


def _extract_working_area(extraction_result: Dict[str, Any]) -> tuple[float, List[GroundTruthMeasurement]]:
    """Extract total working area for mobile scaffold calculation."""
    measurements = []

    total_area = extraction_result.get("total_counted_m2") or extraction_result.get("total_area_m2", 0)

    if total_area > 0:
        measurements.append(create_ground_truth_measurement(
            source_field="total_counted_m2" if "total_counted_m2" in extraction_result else "total_area_m2",
            value=total_area,
            unit="m2",
            source_type="extraction_result",
        ))

    return total_area, measurements


def project_scaffolding(
    extraction_result: Dict[str, Any],
    params: TradeParams,
) -> MaterialProjectionResult:
    """
    Calculate scaffolding material projection.

    Aufmass items (ground truth):
    - Scaffold facade area (m²) - for standard/fassade
    - Working area (m²) - for rollgeruest

    Projected materials (estimates):
    - Scaffold rental (m² or units)
    - Setup/dismount labor
    - Safety nets (m²)
    - Protective screens (m²)

    Args:
        extraction_result: Extraction result with building data
        params: Trade parameters (scaffold_height_m, scaffold_type)

    Returns:
        MaterialProjectionResult with aufmass items and projected materials
    """
    warnings = []
    errors = []

    # Validate params
    param_errors = params.validate()
    if param_errors:
        errors.extend(param_errors)

    scaffold_height = params.scaffold_height_m
    if not scaffold_height or scaffold_height <= 0:
        errors.append("scaffold_height_m is required for scaffolding projection")
        return create_projection_result(
            trade_type=TradeType.SCAFFOLDING,
            source_extraction_id=extraction_result.get("extraction_id", "unknown"),
            params=params,
            aufmass_items=[],
            projected_materials=[],
            errors=errors,
            warnings=warnings,
        )

    # Get scaffold type specs
    scaffold_type = params.scaffold_type.lower()
    if scaffold_type not in SCAFFOLD_TYPES:
        warnings.append(f"Unknown scaffold type '{scaffold_type}', using 'standard'")
        scaffold_type = "standard"

    spec = SCAFFOLD_TYPES[scaffold_type]

    # Check height limits
    max_height = spec.get("max_height_m", 50)
    if scaffold_height > max_height:
        warnings.append(f"Height {scaffold_height}m exceeds typical max {max_height}m for {spec['name_de']}")

    waste_factor = params.waste_factor

    # ==================
    # AUFMASS & PROJECTIONS by type
    # ==================
    aufmass_items = []
    projected_materials = []

    if scaffold_type == "rollgeruest":
        # Mobile scaffold - based on working area
        working_area, area_measurements = _extract_working_area(extraction_result)

        if working_area <= 0:
            errors.append("No floor area available for mobile scaffold calculation")
            return create_projection_result(
                trade_type=TradeType.SCAFFOLDING,
                source_extraction_id=extraction_result.get("extraction_id", "unknown"),
                params=params,
                aufmass_items=[],
                projected_materials=[],
                errors=errors,
                warnings=warnings,
            )

        # Aufmass: working area
        aufmass_items.append(create_aufmass_item(
            position="01.01.001",
            description="Arbeitsfläche für Rollgerüst",
            quantity=working_area,
            unit="m²",
            derived_from=area_measurements,
            formula="total_area_m2",
            formula_description="Total floor area to be covered by mobile scaffolds",
        ))

        # Projected: number of mobile scaffold units
        coverage_per_unit = spec.get("coverage_m2_per_unit", 100)
        unit_count = math.ceil(working_area / coverage_per_unit)

        projected_materials.append(create_projected_material(
            name=spec["name_de"],
            quantity=unit_count,
            unit="Stk",
            confidence=0.70,
            assumptions=[
                f"One unit covers ~{coverage_per_unit}m² working area",
                f"Platform height: {scaffold_height}m",
                "Includes wheels, platforms, and safety rails",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

    else:
        # Facade scaffolding - based on building perimeter
        building_perimeter, perimeter_measurements = _extract_building_perimeter(extraction_result)

        if building_perimeter <= 0:
            errors.append("Cannot determine building perimeter for facade scaffolding")
            return create_projection_result(
                trade_type=TradeType.SCAFFOLDING,
                source_extraction_id=extraction_result.get("extraction_id", "unknown"),
                params=params,
                aufmass_items=[],
                projected_materials=[],
                errors=errors,
                warnings=warnings,
            )

        # Calculate facade area
        facade_area = building_perimeter * scaffold_height
        facade_area_with_waste = facade_area * waste_factor

        # Aufmass: facade area
        aufmass_items.append(create_aufmass_item(
            position="01.01.001",
            description=f"Gerüstfläche {spec['name_de']}",
            quantity=facade_area_with_waste,
            unit="m²",
            derived_from=perimeter_measurements,
            formula=f"perimeter × height × waste = {building_perimeter:.2f} × {scaffold_height:.2f} × {waste_factor}",
            formula_description="Building perimeter times scaffold height",
        ))

        # Projected: scaffold rental
        projected_materials.append(create_projected_material(
            name=f"{spec['name_de']} Miete",
            quantity=facade_area_with_waste,
            unit="m²",
            confidence=0.75,
            assumptions=[
                f"Scaffold height: {scaffold_height}m",
                f"Building perimeter: {building_perimeter:.1f}m (estimated from floor area)",
                f"Waste factor: {waste_factor:.0%}",
                "Rental typically per week",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Projected: setup labor
        projected_materials.append(create_projected_material(
            name="Gerüststellung (Aufbau)",
            quantity=facade_area_with_waste,
            unit="m²",
            confidence=0.80,
            assumptions=[
                "Standard setup labor per m² facade",
                "Includes ground preparation and anchoring",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Projected: dismount labor
        projected_materials.append(create_projected_material(
            name="Gerüstabbau",
            quantity=facade_area_with_waste,
            unit="m²",
            confidence=0.80,
            assumptions=[
                "Standard dismount labor per m² facade",
                "Includes cleanup and removal",
            ],
            derived_from_aufmass=aufmass_items[0].item_id,
        ))

        # Safety nets (for fassade type)
        if scaffold_type == "fassade":
            net_factor = spec.get("net_factor", 1.15)
            net_area = facade_area * net_factor

            projected_materials.append(create_projected_material(
                name="Schutznetz",
                quantity=net_area,
                unit="m²",
                confidence=0.70,
                assumptions=[
                    f"Coverage factor: {net_factor:.0%} (overlap at edges)",
                    "Required for facade work with debris risk",
                    "Mesh size per local regulations",
                ],
                derived_from_aufmass=aufmass_items[0].item_id,
            ))

            # Protective screen/tarp
            projected_materials.append(create_projected_material(
                name="Schutzplane / Staubschutz",
                quantity=facade_area,
                unit="m²",
                confidence=0.65,
                assumptions=[
                    "Full coverage for dust/weather protection",
                    "May not be needed for all projects",
                    "Required for work in occupied buildings",
                ],
                derived_from_aufmass=aufmass_items[0].item_id,
            ))

    # Create result
    return create_projection_result(
        trade_type=TradeType.SCAFFOLDING,
        source_extraction_id=extraction_result.get("extraction_id", "unknown"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        warnings=warnings,
        errors=errors,
    )
