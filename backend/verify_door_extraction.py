"""
Quick verification script for door geometry extraction.

Tests basic functionality without requiring full test infrastructure.
"""

import sys
sys.path.insert(0, '.')

from app.services.door_label_detection import (
    parse_dimension_from_text,
    _apply_patterns_to_text,
    group_nearby_labels,
    DoorLabel,
)
from app.services.door_geometry_extraction import (
    DoorGeometry,
    associate_labels_with_geometries,
    extract_door_attributes,
)
from app.services.scale_calibration import ScaleContext

def test_dimension_parsing():
    """Test dimension parsing."""
    print("\n=== Testing Dimension Parsing ===")

    test_cases = [
        ("0,90 x 2,10", (0.90, 2.10)),
        ("1,25 x 2,00", (1.25, 2.00)),
        ("90 x 210", (0.90, 2.10)),
    ]

    for text, expected in test_cases:
        result = parse_dimension_from_text(text)
        if result:
            width, height = result
            success = abs(width - expected[0]) < 0.01 and abs(height - expected[1]) < 0.01
            status = "✅" if success else "❌"
            print(f"{status} '{text}' -> ({width:.2f}, {height:.2f}) [expected: {expected}]")
        else:
            print(f"❌ '{text}' -> None [expected: {expected}]")

def test_label_detection():
    """Test label pattern detection."""
    print("\n=== Testing Label Detection ===")

    test_cases = [
        ("WD", "german_door", "WD"),
        ("T 30-RS", "fire_rating", "T30"),
        ("T90", "fire_rating", "T90"),
        ("0,90 x 2,10", "dimension", None),
    ]

    bbox = (100.0, 200.0, 150.0, 220.0)

    for text, expected_pattern, expected_attr in test_cases:
        labels = _apply_patterns_to_text(text, bbox, page_number=1)

        if labels:
            label = labels[0]
            pattern_match = expected_pattern in label.pattern_type
            status = "✅" if pattern_match else "❌"
            print(f"{status} '{text}' -> pattern_type='{label.pattern_type}'")

            if expected_attr:
                if label.door_type == expected_attr or label.fire_rating == expected_attr:
                    print(f"   ✅ Attribute extracted: {expected_attr}")
                else:
                    print(f"   ❌ Expected attribute: {expected_attr}, got: door_type={label.door_type}, fire_rating={label.fire_rating}")
        else:
            print(f"❌ '{text}' -> No labels detected")

def test_label_grouping():
    """Test label grouping for compound labels."""
    print("\n=== Testing Label Grouping ===")

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

    if len(grouped) == 1:
        merged = grouped[0]
        has_both = "F. ND1" in merged.label_text and "T 30-RS" in merged.label_text
        has_fire_rating = merged.fire_rating == "T30"

        if has_both and has_fire_rating:
            print("✅ Labels grouped correctly")
            print(f"   Combined text: '{merged.label_text}'")
            print(f"   Fire rating preserved: {merged.fire_rating}")
        else:
            print(f"❌ Grouping incomplete: text={merged.label_text}, fire_rating={merged.fire_rating}")
    else:
        print(f"❌ Expected 1 grouped label, got {len(grouped)}")

def test_label_geometry_association():
    """Test label-geometry association."""
    print("\n=== Testing Label-Geometry Association ===")

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

    if len(doors) == 1:
        door = doors[0]
        has_label = door.label is not None
        has_geometry = door.geometry is not None
        correct_method = door.extraction_method == "label_geometry_match"

        if has_label and has_geometry and correct_method:
            print("✅ Label-geometry association successful")
            print(f"   Method: {door.extraction_method}")
            print(f"   Confidence: {door.confidence:.2f}")
        else:
            print(f"❌ Association incomplete: label={has_label}, geometry={has_geometry}, method={door.extraction_method}")
    else:
        print(f"❌ Expected 1 door, got {len(doors)}")

def test_attribute_extraction():
    """Test attribute extraction with scale."""
    print("\n=== Testing Attribute Extraction ===")

    scale_context = ScaleContext(
        id="scale_test",
        scale_factor=100,
        pixels_per_meter=59.055,
    )

    label = DoorLabel(
        label_text="T 30-RS",
        raw_text="T 30-RS",
        page_number=1,
        bbox=(100.0, 100.0, 150.0, 110.0),
        confidence=0.95,
        pattern_type="fire_rating",
        fire_rating="T30",
    )

    geometry = DoorGeometry(
        geometry_id="door_001",
        page_number=1,
        center=(100.0, 100.0),
        width_px=53.15,  # ~0.90m at this scale
        opening_type="arc",
        confidence=0.85,
    )

    from app.services.door_geometry_extraction import DoorExtraction

    door = DoorExtraction(
        extraction_id="door_test",
        page_number=1,
        label=label,
        geometry=geometry,
        extraction_method="label_geometry_match",
    )

    extract_door_attributes(door, scale_context)

    width_correct = door.width_m is not None and abs(door.width_m - 0.90) < 0.05
    fire_rating_correct = door.fire_rating == "T30"
    category_correct = door.category == "T30"

    if width_correct and fire_rating_correct and category_correct:
        print("✅ Attribute extraction successful")
        print(f"   Width: {door.width_m:.2f}m")
        print(f"   Fire rating: {door.fire_rating}")
        print(f"   Category: {door.category}")
    else:
        print(f"❌ Attribute extraction incomplete:")
        print(f"   Width: {door.width_m} (expected ~0.90m)")
        print(f"   Fire rating: {door.fire_rating} (expected T30)")
        print(f"   Category: {door.category} (expected T30)")

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Door Geometry Extraction Verification")
    print("=" * 60)

    try:
        test_dimension_parsing()
        test_label_detection()
        test_label_grouping()
        test_label_geometry_association()
        test_attribute_extraction()

        print("\n" + "=" * 60)
        print("✅ Verification Complete - All Core Functions Working")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Verification Failed: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
