#!/usr/bin/env python3
"""
Debug script for room extraction - see what's being detected
"""
import sys
import fitz
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.unified_extraction import (
    detect_blueprint_style,
    extract_rooms_from_pdf,
    BlueprintStyle
)

def main():
    pdf_path = "/Users/clarence/Desktop/SnapPlan/GRUNDRISSE BTB 2/HMA-ARC-5-UP-WP-00-B0-0001-07-v-Bauteil B - šbersichtsplan Grundriss Erdgeschoss.pdf"

    print(f"\n{'='*80}")
    print(f"Testing room extraction: {Path(pdf_path).name}")
    print(f"{'='*80}\n")

    # Open PDF and extract text for style detection
    doc = fitz.open(pdf_path)
    page = doc[0]  # First page
    text = page.get_text()

    # Detect style
    style = detect_blueprint_style(text)
    print(f"Detected style: {style}")
    print()

    # Show first 3000 chars of text to see what we're working with
    print("First 3000 characters of extracted text:")
    print("-" * 80)
    print(text[:3000])
    print("-" * 80)
    print()

    # Count key patterns
    import re
    nrf_count = len(re.findall(r'\bNRF:\s*\d', text, re.IGNORECASE))
    f_count = len(re.findall(r'\bF:\s*\d', text))
    b_pattern_count = len(re.findall(r'\bB\.\d+\.\d+\.\d+\b', text))

    print(f"Pattern counts in text:")
    print(f"  NRF: patterns: {nrf_count}")
    print(f"  F: patterns: {f_count}")
    print(f"  B.XX.X.XXX patterns: {b_pattern_count}")
    print()

    doc.close()

    # Now try the full extraction
    print("Running full extraction...")
    try:
        result = extract_rooms_from_pdf(pdf_path, pages=[0])
        print(f"\nExtraction Result:")
        print(f"  Total rooms found: {len(result.rooms)}")
        print(f"  Warnings: {result.warnings}")
        print(f"  Errors: {result.errors}")

        if result.rooms:
            print(f"\nFirst 5 rooms:")
            for room in result.rooms[:5]:
                print(f"  - {room.room_number}: {room.room_name} = {room.area_m2:.2f} m²")
        else:
            print("\n⚠️  NO ROOMS EXTRACTED")

            # Debug: Try to see what lines are being processed
            print("\nShowing first 50 lines of text for debugging:")
            lines = text.split('\n')
            for i, line in enumerate(lines[:50]):
                print(f"  {i:3d}: '{line.strip()}'")

    except Exception as e:
        print(f"\n❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
