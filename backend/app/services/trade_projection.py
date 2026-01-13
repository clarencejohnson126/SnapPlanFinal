"""
Trade Material Projection - Core Data Models

This module defines the data structures for trade material projections.
Key principle: Clear separation between ground truth (measured) and projections (estimates).

Ground Truth (AufmassItem):
- Derived directly from extraction results
- 100% traceable to source measurements
- Formulas are deterministic

Projections (ProjectedMaterial):
- Estimates based on rules or LLM suggestions
- Always labeled as estimates
- Include assumptions and confidence scores
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from uuid import uuid4
from datetime import datetime


class TradeType(str, Enum):
    """Available construction trades for material projection."""
    SCAFFOLDING = "scaffolding"      # Gerüstbau
    DRYWALL = "drywall"              # Trockenbau
    SCREED = "screed"                # Estrich
    FLOOR_FINISH = "floor_finish"    # Oberbelag
    WATERPROOFING = "waterproofing"  # Abdichtung


class ProjectionMethod(str, Enum):
    """Method used to generate projection."""
    RULE_BASED = "rule_based"
    LLM_ASSISTED = "llm_assisted"


class ConfidenceLevel(str, Enum):
    """Confidence level categories."""
    HIGH = "high"      # 0.8-1.0 - Direct measurement-based
    MEDIUM = "medium"  # 0.5-0.8 - Standard formulas with assumptions
    LOW = "low"        # 0.0-0.5 - Estimates or LLM suggestions


# Trade metadata for UI and validation
TRADE_METADATA = {
    TradeType.SCAFFOLDING: {
        "name_de": "Gerüstbau",
        "name_en": "Scaffolding",
        "icon": "scaffold",
        "required_params": ["scaffold_height_m"],
        "optional_params": ["scaffold_type", "waste_factor"],
        "uses_perimeter": True,
        "uses_area": False,
    },
    TradeType.DRYWALL: {
        "name_de": "Trockenbau",
        "name_en": "Drywall",
        "icon": "wall",
        "required_params": ["wall_height_m"],
        "optional_params": ["drywall_system", "stud_spacing_mm", "waste_factor"],
        "uses_perimeter": True,
        "uses_area": False,
    },
    TradeType.SCREED: {
        "name_de": "Estrich",
        "name_en": "Screed",
        "icon": "layers",
        "required_params": ["screed_thickness_mm"],
        "optional_params": ["screed_type", "waste_factor"],
        "uses_perimeter": True,  # For edge strips
        "uses_area": True,
    },
    TradeType.FLOOR_FINISH: {
        "name_de": "Oberbelag",
        "name_en": "Floor Finish",
        "icon": "grid",
        "required_params": ["finish_type"],
        "optional_params": ["waste_factor"],
        "uses_perimeter": True,  # For skirting
        "uses_area": True,
    },
    TradeType.WATERPROOFING: {
        "name_de": "Abdichtung",
        "name_en": "Waterproofing",
        "icon": "droplet",
        "required_params": [],
        "optional_params": ["waterproofing_type", "wall_height_m", "waste_factor"],
        "uses_perimeter": True,
        "uses_area": True,
    },
}


def _generate_projection_id() -> str:
    """Generate a unique projection ID."""
    return f"proj_{uuid4().hex[:12]}"


def _generate_item_id(prefix: str = "item") -> str:
    """Generate a unique item ID with prefix."""
    return f"{prefix}_{uuid4().hex[:8]}"


def _get_confidence_level(confidence: float) -> ConfidenceLevel:
    """Map confidence score to level."""
    if confidence >= 0.8:
        return ConfidenceLevel.HIGH
    elif confidence >= 0.5:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


@dataclass
class GroundTruthMeasurement:
    """
    Reference to an extracted measurement (immutable ground truth).

    This links projections back to the original extraction results,
    ensuring full traceability.
    """
    measurement_id: str
    source_type: str          # "extraction_result" | "gewerk_result"
    source_field: str         # e.g., "total_area_m2", "rooms[].perimeter_m"
    value: float
    unit: str                 # "m2", "m", "count"
    source_page: Optional[int] = None
    source_room_id: Optional[str] = None
    source_text: Optional[str] = None  # Original text from PDF

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measurement_id": self.measurement_id,
            "source_type": self.source_type,
            "source_field": self.source_field,
            "value": round(self.value, 4),
            "unit": self.unit,
            "source_page": self.source_page,
            "source_room_id": self.source_room_id,
            "source_text": self.source_text,
        }


@dataclass
class AufmassItem:
    """
    Calculated item based on measured quantities (ground truth formulas).

    These are deterministic calculations derived from extraction results.
    Every item traces back to source measurements.
    """
    item_id: str
    position: str             # LV position number (e.g., "01.01")
    description: str
    quantity: float
    unit: str

    # Traceability - required
    derived_from: List[GroundTruthMeasurement] = field(default_factory=list)
    formula: str = ""         # e.g., "total_area_m2 * 1.10"
    formula_description: str = ""  # Human readable explanation

    # Optional pricing
    unit_price_eur: Optional[float] = None
    total_price_eur: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "position": self.position,
            "description": self.description,
            "quantity": round(self.quantity, 2),
            "unit": self.unit,
            "derived_from": [m.to_dict() for m in self.derived_from],
            "formula": self.formula,
            "formula_description": self.formula_description,
            "unit_price_eur": self.unit_price_eur,
            "total_price_eur": round(self.total_price_eur, 2) if self.total_price_eur else None,
            "is_ground_truth": True,  # Always true for AufmassItem
        }


@dataclass
class ProjectedMaterial:
    """
    Estimated material requirement (clearly labeled as projection).

    These are NOT ground truth - they are estimates based on rules or LLM.
    Always includes assumptions and confidence scores.
    """
    material_id: str
    name: str                 # e.g., "Estrich FE 50", "CW 75 Profile"
    quantity: float
    unit: str

    # Projection metadata - required
    method: ProjectionMethod
    confidence: float         # 0.0 - 1.0
    assumptions: List[str] = field(default_factory=list)

    # Source traceability
    derived_from_aufmass: Optional[str] = None  # Links to AufmassItem.item_id

    # Optional: LLM suggestion details (only if method == LLM_ASSISTED)
    llm_suggestion: Optional[Dict[str, Any]] = None

    # User can override the quantity
    user_override: Optional[float] = None
    user_override_reason: Optional[str] = None

    @property
    def effective_quantity(self) -> float:
        """Return user override if set, otherwise calculated quantity."""
        return self.user_override if self.user_override is not None else self.quantity

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level category."""
        return _get_confidence_level(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_id": self.material_id,
            "name": self.name,
            "quantity": round(self.quantity, 2),
            "effective_quantity": round(self.effective_quantity, 2),
            "unit": self.unit,
            "method": self.method.value,
            "confidence": round(self.confidence, 2),
            "confidence_level": self.confidence_level.value,
            "assumptions": self.assumptions,
            "derived_from_aufmass": self.derived_from_aufmass,
            "llm_suggestion": self.llm_suggestion,
            "user_override": self.user_override,
            "user_override_reason": self.user_override_reason,
            "is_estimate": True,  # Always true for ProjectedMaterial
        }


@dataclass
class TradeParams:
    """
    User-provided parameters for trade calculations.

    Different trades require different parameters.
    """
    trade_type: TradeType

    # Common params
    waste_factor: float = 1.10      # 10% default waste

    # Scaffolding specific
    scaffold_height_m: Optional[float] = None
    scaffold_type: str = "standard"  # "standard", "rollgeruest", "fassade"

    # Drywall specific
    wall_height_m: Optional[float] = None
    drywall_system: str = "single"   # "single", "double", "fire_rated"
    stud_spacing_mm: int = 625       # Standard spacing

    # Screed specific
    screed_type: str = "ct"          # "ct" (cement), "ca" (anhydrite), "ma" (mastic)
    screed_thickness_mm: int = 50

    # Floor finish specific
    finish_type: str = "laminate"    # "laminate", "parquet", "tile", "carpet"

    # Waterproofing specific
    waterproofing_type: str = "liquid"  # "liquid", "membrane", "bitumen"
    waterproofing_wall_height_m: float = 2.0  # Height to apply in wet areas

    def validate(self) -> List[str]:
        """Validate parameters for the trade type. Returns list of errors."""
        errors = []
        metadata = TRADE_METADATA.get(self.trade_type)

        if not metadata:
            errors.append(f"Unknown trade type: {self.trade_type}")
            return errors

        for param in metadata["required_params"]:
            value = getattr(self, param, None)
            if value is None:
                errors.append(f"Missing required parameter: {param}")
            elif isinstance(value, (int, float)) and value <= 0:
                errors.append(f"Parameter {param} must be positive")

        if self.waste_factor < 1.0 or self.waste_factor > 2.0:
            errors.append("waste_factor should be between 1.0 and 2.0")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_type": self.trade_type.value,
            "waste_factor": self.waste_factor,
            "scaffold_height_m": self.scaffold_height_m,
            "scaffold_type": self.scaffold_type,
            "wall_height_m": self.wall_height_m,
            "drywall_system": self.drywall_system,
            "stud_spacing_mm": self.stud_spacing_mm,
            "screed_type": self.screed_type,
            "screed_thickness_mm": self.screed_thickness_mm,
            "finish_type": self.finish_type,
            "waterproofing_type": self.waterproofing_type,
            "waterproofing_wall_height_m": self.waterproofing_wall_height_m,
        }


@dataclass
class MaterialProjectionResult:
    """
    Complete result for a trade material projection.

    Contains both ground truth (aufmass_items) and estimates (projected_materials).
    """
    projection_id: str
    trade_type: TradeType
    source_extraction_id: str
    processed_at: str
    status: str = "ok"  # "ok", "partial", "error"

    # Parameters used
    params: Optional[TradeParams] = None

    # Results
    aufmass_items: List[AufmassItem] = field(default_factory=list)
    projected_materials: List[ProjectedMaterial] = field(default_factory=list)

    # Totals
    total_aufmass_quantity: float = 0.0
    total_estimated_cost_eur: Optional[float] = None

    # Metadata
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Legal disclaimer - always included
    disclaimer: str = (
        "Projected materials are estimates based on standard formulas and assumptions. "
        "Actual quantities may vary based on site conditions, material specifications, "
        "and construction methods. These projections should be verified by a qualified professional."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "trade_type": self.trade_type.value,
            "trade_name_de": TRADE_METADATA[self.trade_type]["name_de"],
            "source_extraction_id": self.source_extraction_id,
            "processed_at": self.processed_at,
            "status": self.status,
            "params": self.params.to_dict() if self.params else None,
            "aufmass_items": [i.to_dict() for i in self.aufmass_items],
            "projected_materials": [m.to_dict() for m in self.projected_materials],
            "total_aufmass_quantity": round(self.total_aufmass_quantity, 2),
            "total_estimated_cost_eur": round(self.total_estimated_cost_eur, 2) if self.total_estimated_cost_eur else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "disclaimer": self.disclaimer,
            "summary": {
                "aufmass_count": len(self.aufmass_items),
                "materials_count": len(self.projected_materials),
                "has_errors": len(self.errors) > 0,
                "has_warnings": len(self.warnings) > 0,
            },
        }


# Helper functions for creating projection results

def create_ground_truth_measurement(
    source_field: str,
    value: float,
    unit: str,
    source_type: str = "extraction_result",
    source_page: Optional[int] = None,
    source_room_id: Optional[str] = None,
    source_text: Optional[str] = None,
) -> GroundTruthMeasurement:
    """Create a GroundTruthMeasurement with auto-generated ID."""
    return GroundTruthMeasurement(
        measurement_id=_generate_item_id("meas"),
        source_type=source_type,
        source_field=source_field,
        value=value,
        unit=unit,
        source_page=source_page,
        source_room_id=source_room_id,
        source_text=source_text,
    )


def create_aufmass_item(
    position: str,
    description: str,
    quantity: float,
    unit: str,
    derived_from: List[GroundTruthMeasurement],
    formula: str,
    formula_description: str = "",
) -> AufmassItem:
    """Create an AufmassItem with auto-generated ID."""
    return AufmassItem(
        item_id=_generate_item_id("auf"),
        position=position,
        description=description,
        quantity=quantity,
        unit=unit,
        derived_from=derived_from,
        formula=formula,
        formula_description=formula_description,
    )


def create_projected_material(
    name: str,
    quantity: float,
    unit: str,
    confidence: float,
    assumptions: List[str],
    method: ProjectionMethod = ProjectionMethod.RULE_BASED,
    derived_from_aufmass: Optional[str] = None,
) -> ProjectedMaterial:
    """Create a ProjectedMaterial with auto-generated ID."""
    return ProjectedMaterial(
        material_id=_generate_item_id("mat"),
        name=name,
        quantity=quantity,
        unit=unit,
        method=method,
        confidence=confidence,
        assumptions=assumptions,
        derived_from_aufmass=derived_from_aufmass,
    )


def create_projection_result(
    trade_type: TradeType,
    source_extraction_id: str,
    params: TradeParams,
    aufmass_items: List[AufmassItem],
    projected_materials: List[ProjectedMaterial],
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
) -> MaterialProjectionResult:
    """Create a MaterialProjectionResult with auto-generated ID and timestamp."""

    # Calculate total aufmass quantity (sum of primary unit)
    total_qty = sum(item.quantity for item in aufmass_items)

    return MaterialProjectionResult(
        projection_id=_generate_projection_id(),
        trade_type=trade_type,
        source_extraction_id=source_extraction_id,
        processed_at=datetime.utcnow().isoformat() + "Z",
        status="error" if errors else ("partial" if warnings else "ok"),
        params=params,
        aufmass_items=aufmass_items,
        projected_materials=projected_materials,
        total_aufmass_quantity=total_qty,
        warnings=warnings or [],
        errors=errors or [],
    )
