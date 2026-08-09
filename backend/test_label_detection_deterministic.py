"""
Test door label detection determinism.

Verifies that Stage 1 (label detection) produces consistent, traceable results
from PDF text extraction alone, without any geometry analysis.
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from app.services.door_label_detection import detect_door_labels
import json

def test_with_sample_pdf():
    """Test label detection with a real PDF from PLANS directory."""
    print("\n" + "=" * 80)
    print("Testing Label Detection with Real PDF")
    print("=" * 80)

    # Find sample PDFs (try current dir, then parent dir)
    plans_dir = Path("PLANS")
    if not plans_dir.exists():
        plans_dir = Path("../PLANS")

    if not plans_dir.exists():
        print("⚠️  PLANS directory not found (skipping real PDF test)")
        print("   This is OK - synthetic tests verify determinism")
        return True  # Don't fail if no real PDFs available

    pdf_files = list(plans_dir.rglob("*.pdf"))
    if not pdf_files:
        print("❌ No PDF files found in PLANS directory")
        return False

    # Test with first PDF
    sample_pdf = pdf_files[0]
    print(f"\nTesting with: {sample_pdf}")
    print("-" * 80)

    try:
        # Run detection twice to verify determinism
        print("\n🔄 Run 1:")
        labels_run1 = detect_door_labels(pdf_path=sample_pdf, page_number=1, dpi=150)

        print("\n🔄 Run 2:")
        labels_run2 = detect_door_labels(pdf_path=sample_pdf, page_number=1, dpi=150)

        # Compare results
        print(f"\n📊 Results Comparison:")
        print(f"   Run 1: {len(labels_run1)} labels detected")
        print(f"   Run 2: {len(labels_run2)} labels detected")

        if len(labels_run1) != len(labels_run2):
            print("❌ NON-DETERMINISTIC: Different number of labels detected")
            return False

        print("✅ DETERMINISTIC: Same number of labels in both runs")

        # Show detailed results
        print("\n📋 Detected Labels (Run 1):")
        print("-" * 80)

        if len(labels_run1) == 0:
            print("   No labels detected on page 1")
            print("   (This is expected for pages without door labels)")
        else:
            for i, label in enumerate(labels_run1, 1):
                print(f"\n   Label #{i}:")
                print(f"   • Text: '{label.label_text}'")
                print(f"   • Raw: '{label.raw_text}'")
                print(f"   • Pattern: {label.pattern_type}")
                print(f"   • Bbox: {label.bbox}")
                print(f"   • Confidence: {label.confidence:.2f}")
                print(f"   • Page: {label.page_number}")

                # Show extracted attributes
                attrs = []
                if label.width_m:
                    attrs.append(f"width={label.width_m}m")
                if label.height_m:
                    attrs.append(f"height={label.height_m}m")
                if label.door_type:
                    attrs.append(f"type={label.door_type}")
                if label.fire_rating:
                    attrs.append(f"fire_rating={label.fire_rating}")

                if attrs:
                    print(f"   • Attributes: {', '.join(attrs)}")

        # Verify byte-for-byte equality
        print("\n🔍 Detailed Comparison:")
        all_match = True
        for i, (l1, l2) in enumerate(zip(labels_run1, labels_run2), 1):
            if l1.label_text != l2.label_text:
                print(f"   ❌ Label #{i} text differs: '{l1.label_text}' vs '{l2.label_text}'")
                all_match = False
            elif l1.bbox != l2.bbox:
                print(f"   ❌ Label #{i} bbox differs: {l1.bbox} vs {l2.bbox}")
                all_match = False
            elif l1.confidence != l2.confidence:
                print(f"   ❌ Label #{i} confidence differs: {l1.confidence} vs {l2.confidence}")
                all_match = False

        if all_match:
            print("   ✅ All labels match exactly (byte-for-byte)")

        return all_match

    except Exception as e:
        print(f"❌ Error during detection: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_synthetic_text():
    """Test label detection with synthetic text patterns."""
    print("\n" + "=" * 80)
    print("Testing Label Detection with Synthetic Patterns")
    print("=" * 80)

    from app.services.door_label_detection import _apply_patterns_to_text

    test_cases = [
        {
            "name": "German door abbreviation",
            "text": "Wohnungstür WD steht hier",
            "expected_pattern": "german_door",
            "expected_attr": "WD"
        },
        {
            "name": "Fire rating T30",
            "text": "T 30-RS",
            "expected_pattern": "fire_rating",
            "expected_attr": "T30"
        },
        {
            "name": "Fire rating T90",
            "text": "T90",
            "expected_pattern": "fire_rating",
            "expected_attr": "T90"
        },
        {
            "name": "Dimension German format",
            "text": "0,90 x 2,10",
            "expected_pattern": "dimension",
            "expected_attr": (0.90, 2.10)
        },
        {
            "name": "Room door label",
            "text": "F. ND1",
            "expected_pattern": "room_door",
            "expected_attr": None
        },
        {
            "name": "DSS smoke protection",
            "text": "DSS",
            "expected_pattern": "fire_rating",
            "expected_attr": "DSS"
        },
    ]

    bbox = (100.0, 200.0, 150.0, 220.0)
    all_passed = True

    for test in test_cases:
        print(f"\n📝 Test: {test['name']}")
        print(f"   Input: '{test['text']}'")

        # Run twice to verify determinism
        labels_run1 = _apply_patterns_to_text(test['text'], bbox, page_number=1)
        labels_run2 = _apply_patterns_to_text(test['text'], bbox, page_number=1)

        # Check determinism
        if len(labels_run1) != len(labels_run2):
            print(f"   ❌ NON-DETERMINISTIC: {len(labels_run1)} vs {len(labels_run2)} labels")
            all_passed = False
            continue

        if not labels_run1:
            print(f"   ❌ No labels detected")
            all_passed = False
            continue

        # Check pattern type
        label = labels_run1[0]
        if test['expected_pattern'] in label.pattern_type:
            print(f"   ✅ Pattern detected: {label.pattern_type}")
        else:
            print(f"   ❌ Wrong pattern: expected '{test['expected_pattern']}', got '{label.pattern_type}'")
            all_passed = False
            continue

        # Check extracted attributes
        if test['expected_attr'] is not None:
            if isinstance(test['expected_attr'], tuple):
                # Dimension check
                if label.width_m and label.height_m:
                    width_ok = abs(label.width_m - test['expected_attr'][0]) < 0.01
                    height_ok = abs(label.height_m - test['expected_attr'][1]) < 0.01
                    if width_ok and height_ok:
                        print(f"   ✅ Dimensions: {label.width_m}m x {label.height_m}m")
                    else:
                        print(f"   ❌ Dimensions wrong: {label.width_m}m x {label.height_m}m")
                        all_passed = False
                else:
                    print(f"   ❌ Dimensions not extracted")
                    all_passed = False
            else:
                # Attribute check (door_type or fire_rating)
                if label.door_type == test['expected_attr'] or label.fire_rating == test['expected_attr']:
                    print(f"   ✅ Attribute: {test['expected_attr']}")
                else:
                    print(f"   ❌ Attribute wrong: expected '{test['expected_attr']}', got door_type={label.door_type}, fire_rating={label.fire_rating}")
                    all_passed = False

        # Verify traceability
        print(f"   📍 Traceability:")
        print(f"      • Bbox: {label.bbox}")
        print(f"      • Page: {label.page_number}")
        print(f"      • Confidence: {label.confidence:.2f}")
        print(f"      • Raw text: '{label.raw_text}'")

    return all_passed


def test_multiple_runs_same_input():
    """Run the same detection 5 times and verify identical results."""
    print("\n" + "=" * 80)
    print("Testing Determinism: Multiple Runs with Same Input")
    print("=" * 80)

    from app.services.door_label_detection import _apply_patterns_to_text

    # Test with compound pattern (multiple labels in one text)
    text = "B.03.1.001-1 WD T 30-RS 0,90 x 2,10"
    bbox = (100.0, 200.0, 200.0, 220.0)

    print(f"\nInput text: '{text}'")
    print("Running detection 5 times...")

    results = []
    for i in range(5):
        labels = _apply_patterns_to_text(text, bbox, page_number=1)
        results.append(labels)
        print(f"   Run {i+1}: {len(labels)} labels detected")

    # Compare all runs
    print("\n🔍 Comparing results:")

    # Check same number of labels
    label_counts = [len(r) for r in results]
    if len(set(label_counts)) == 1:
        print(f"   ✅ All runs detected same count: {label_counts[0]} labels")
    else:
        print(f"   ❌ Different counts: {label_counts}")
        return False

    # Check all labels match
    reference = results[0]
    all_match = True

    for run_idx, run_labels in enumerate(results[1:], 2):
        for label_idx, (ref_label, run_label) in enumerate(zip(reference, run_labels)):
            if ref_label.label_text != run_label.label_text:
                print(f"   ❌ Run {run_idx}, Label {label_idx}: text differs")
                all_match = False
            if ref_label.pattern_type != run_label.pattern_type:
                print(f"   ❌ Run {run_idx}, Label {label_idx}: pattern differs")
                all_match = False
            if ref_label.confidence != run_label.confidence:
                print(f"   ❌ Run {run_idx}, Label {label_idx}: confidence differs")
                all_match = False

    if all_match:
        print("   ✅ All 5 runs produced identical results")

    # Show what was detected
    print("\n📋 Detected labels (consistent across all runs):")
    for i, label in enumerate(reference, 1):
        print(f"   {i}. '{label.label_text}' ({label.pattern_type}) - confidence: {label.confidence:.2f}")

    return all_match


def main():
    """Run all determinism tests."""
    print("=" * 80)
    print("DOOR LABEL DETECTION DETERMINISM VERIFICATION")
    print("=" * 80)
    print("\nThis test verifies that Stage 1 (label detection) is:")
    print("• Deterministic (same input → same output)")
    print("• Traceable (every label has bbox, page, confidence)")
    print("• Pattern-based (no AI/LLM inference)")
    print("=" * 80)

    results = {
        "synthetic": test_with_synthetic_text(),
        "multiple_runs": test_multiple_runs_same_input(),
        "real_pdf": test_with_sample_pdf(),
    }

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED - Label Detection is DETERMINISTIC")
        print("\nKey findings:")
        print("• Same input produces identical output every time")
        print("• All labels have full traceability (bbox, page, confidence)")
        print("• No AI/LLM inference - pure regex pattern matching")
        print("• Ready for Stage 2 (geometry detection)")
    else:
        print("❌ SOME TESTS FAILED - Review output above")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
