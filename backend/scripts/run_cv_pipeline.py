#!/usr/bin/env python3
"""
CLI runner for the geometry/symbol CV pipeline.

Usage:
  python -m app.scripts.run_cv_pipeline --pdf /path/to/plan.pdf --page 1 --targets doors,windows,walls
"""

import argparse
import json
from typing import List

from app.services.cv_analysis_pipeline import (
    run_cv_document_analysis,
    DetectionTarget,
    CVAnalysisConfig,
)
from app.core.config import get_settings


def parse_targets(raw: str) -> List[DetectionTarget]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [DetectionTarget(p) for p in parts]


def main():
    parser = argparse.ArgumentParser(description="Run CV symbol pipeline on a PDF.")
    parser.add_argument("--pdf", required=True, help="Path to PDF blueprint")
    parser.add_argument("--page", type=int, default=1, help="Single page to analyze")
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        help="Optional list of pages (overrides --page when provided)",
    )
    parser.add_argument(
        "--targets",
        default="doors,windows,walls,conduits,dimensions",
        help="Comma-separated detection targets",
    )
    parser.add_argument("--debug", action="store_true", help="Save debug overlays")
    parser.add_argument("--dpi", type=int, default=None, help="Override render DPI")

    args = parser.parse_args()
    settings = get_settings()

    pages = args.pages if args.pages else [args.page]
    targets = parse_targets(args.targets)

    config = CVAnalysisConfig(
        dpi=args.dpi or settings.cv_default_dpi,
        debug=args.debug,
        use_yolo=settings.cv_pipeline_enabled,
        use_classical=settings.cv_classical_enabled,
        confidence_threshold=settings.yolo_confidence_threshold,
        needs_review_threshold=settings.cv_needs_review_threshold,
    )

    result = run_cv_document_analysis(
        pdf_path=args.pdf,
        pages=pages,
        detection_targets=targets,
        scale_context=None,
        settings=settings,
        config=config,
    )

    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()

