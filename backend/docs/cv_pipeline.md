# CV Symbol Pipeline (Phase: geometry-first)

Purpose: detect doors, windows, walls, toilets, wash basins, conduits, room boundaries, and dimension annotations on plans that have no usable room text. The deterministic m² extractor is untouched and still primary.

## How to run
- Local one-off (single page): `python -m app.scripts.run_cv_pipeline --pdf /path/to/plan.pdf --page 1 --targets doors,windows,walls,conduits`
- Multi-page: add `--pages 1 2 3`
- Debug overlays: add `--debug` (writes into `$TMPDIR/snapplan_cv_debug`)
- Output: JSON matching `backend/docs/examples/cv_output_sample.json`

## Feature flags / env
- `SNAPGRID_CV_SYMBOL_PIPELINE_ENABLED=true` (default)
- `SNAPGRID_CV_CLASSICAL_ENABLED=true` to keep OpenCV detectors on
- `SNAPGRID_CV_DEBUG_OVERLAYS=true` to render overlays
- `SNAPGRID_YOLO_MODEL_PATH=/path/to/weights.pt` to enable YOLO detections
- `SNAPGRID_ROBOFLOW_API_KEY=<your key>` (optional; see `ROBOFLOW_TRAINING_GUIDE.md`)

## Adding new object classes
- Map YOLO class → `ObjectType` in `cv_pipeline._map_yolo_class_to_object_type`.
- Map `ObjectType` → `CVElementType` in `cv_analysis_pipeline._object_type_to_element_type`.
- Add classical detector (if deterministic geometry is possible) in `cv_analysis_pipeline._run_classical_detectors`.
- Update sample JSON if schema changes.

## Training / models
- Preferred: train a compact YOLOv8/12 model on plan symbols. See `ROBOFLOW_TRAINING_GUIDE.md` for dataset setup.
- Roboflow can be used for dataset/versioning; keep it optional and gated by env vars.

## Safety & determinism
- Confidence floor: `SNAPGRID_CV_CONFIDENCE_FLOOR` (default 0.35) → below this, results are marked `needs_review`.
- No scale? Derived measurements return `"unknown"` and `needs_review=true`.
- Validation script `backend/scripts/validate_room_regression.py` checks the text-based m² extractor remains unchanged.

## Debugging
- Set `--debug` or `SNAPGRID_CV_DEBUG_OVERLAYS=true` to emit overlay PNGs.
- Inspect per-page warnings in the returned JSON; they explain which detectors were skipped (missing deps, missing scale, etc.).

