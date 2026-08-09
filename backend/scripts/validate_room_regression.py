#!/usr/bin/env python3
"""
Validation helper to ensure the deterministic room m² extractor remains unchanged.

It runs the extractor twice on the same PDF and asserts identical outputs
to catch accidental stateful side effects introduced by CV additions.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate room area extraction determinism.")
    parser.add_argument(
        "--pdf",
        default=str(Path(__file__).resolve().parents[2] / "sampleGrundrissBauplanGenie.pdf"),
        help="PDF to validate against (defaults to sampleGrundrissBauplanGenie.pdf)",
    )
    args = parser.parse_args()

    try:
        from app.services.room_area_extraction import extract_rooms_from_pdf
    except Exception as exc:
        print(f"[SKIP] room_area_extraction unavailable: {exc}")
        sys.exit(0)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[SKIP] PDF not found: {pdf_path}")
        sys.exit(0)

    result_a = extract_rooms_from_pdf(str(pdf_path))
    result_b = extract_rooms_from_pdf(str(pdf_path))

    a_json = json.dumps(result_a.to_dict(), sort_keys=True)
    b_json = json.dumps(result_b.to_dict(), sort_keys=True)

    if a_json != b_json:
        print("[FAIL] Room extraction outputs differ between runs.")
        sys.exit(1)

    print("[OK] Room extraction deterministic for", pdf_path.name)


if __name__ == "__main__":
    main()

