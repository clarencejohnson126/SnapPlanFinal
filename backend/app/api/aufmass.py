"""
Aufmaß API — the layered pipeline exposed over HTTP.

    POST /aufmass/analyze                          Plan + Gewerk → Positionen
    GET  /aufmass/trades                           available Regelwerke
    GET  /aufmass/{job_id}                         retrieve a result
    POST /aufmass/{job_id}/positions/{id}/review   sign off / correct
    POST /aufmass/{job_id}/review-all              bulk sign-off
    GET  /aufmass/{job_id}/export                  xlsx | csv | protokoll

WHY THE ENDPOINTS ARE `def` AND NOT `async def`

Extraction is blocking work — PyMuPDF, OpenCV, page rendering. A plain `def`
endpoint runs in FastAPI's threadpool, which keeps one slow plan from stalling
the event loop. An `async def` here would freeze every other request for the
duration. Same reasoning as commit 3ead892.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.adapters import build_raw_model
from app.domain.position import PositionSet
from app.domain.trades import parse_trade
from app.export import ExportBlockedError, build_csv, build_excel, build_protocol
from app.rules import RuleParams, ruleset_catalog, run_ruleset
from app.rules.thresholds import unverified_thresholds
from app.services.dimension_chains import extract_dimension_chains, points_per_metre

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aufmass", tags=["Aufmaß"])


# ----------------------------------------------------------------------- store

@dataclass
class _Job:
    """A result plus the plan it came from — the review screen needs both."""

    positions: PositionSet
    pdf_path: Path
    #: Kept alongside because chain extraction and the measuring tool both need
    #: it, and re-reading the plan text just to find it again would be wasteful.
    scale_denominator: Optional[int] = None


#: Jobs by id.
#:
#: TRANSITIONAL. Process-local: results vanish on restart and are not shared
#: between workers. Enough to build the review screen against, and it must move
#: to Supabase before more than one backend process runs. The interface below is
#: deliberately narrow so that swap touches only this block.
_JOBS: Dict[str, _Job] = {}

#: Uploaded plans are kept for the lifetime of the process so the review screen
#: can render pages from them. Cleared by the OS when the process ends.
_UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="snapplan_plans_"))


def _store(position_set: PositionSet, pdf_path: Path,
           scale_denominator: Optional[int] = None) -> str:
    job_id = f"job_{len(_JOBS) + 1}_{position_set.document_id[:24]}"
    _JOBS[job_id] = _Job(
        positions=position_set,
        pdf_path=pdf_path,
        scale_denominator=scale_denominator,
    )
    return job_id


def _job(job_id: str) -> _Job:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aufmaß '{job_id}' nicht gefunden. Ergebnisse gehen bei einem "
                   f"Neustart des Servers verloren — bitte neu analysieren.",
        )
    return job


def _load(job_id: str) -> PositionSet:
    return _job(job_id).positions


# --------------------------------------------------------------------- schemas

class ReviewRequest(BaseModel):
    """Sign off on one position, optionally correcting its quantity."""

    reviewed_by: str = Field(..., description="Wer die Freigabe erteilt")
    corrected_quantity: Optional[float] = Field(
        None,
        description="Korrigierte Menge. Weglassen, um die berechnete zu bestätigen.",
    )


class ReviewAllRequest(BaseModel):
    """Sign off on every position that is still open."""

    reviewed_by: str
    only_without_warnings: bool = Field(
        True,
        description="Nur Positionen ohne Hinweise freigeben. Standard ist an, damit "
                    "eine Sammelfreigabe keine Warnungen überfährt.",
    )


# ------------------------------------------------------------------- endpoints

@router.get("/trades")
def list_trades() -> Dict[str, Any]:
    """
    Which trades can actually be calculated, and on what basis.

    Also reports thresholds not yet checked against the printed VOB/C. The UI
    should surface that — a trade with unverified norms is usable for a preview,
    not for an invoice.
    """
    pending = unverified_thresholds()
    return {
        "trades": ruleset_catalog(),
        "unverified_thresholds": [
            {
                "key": t.key,
                "value": t.value,
                "unit": t.unit,
                "atv": t.atv,
                "description": t.description,
                "note": t.source_note,
            }
            for t in pending.values()
        ],
        "all_thresholds_verified": not pending,
    }


@router.post("/analyze")
def analyze(
    file: UploadFile = File(..., description="Plan als PDF"),
    trade: str = Form(..., description="Gewerk, z. B. 'trockenbau'"),
    wall_height_m: Optional[float] = Form(
        None, description="Raumhöhe, falls der Plan keine enthält"
    ),
    opening_height_m: Optional[float] = Form(
        None, description="Höhe für Öffnungen ohne Maßangabe"
    ),
    include_ceiling: bool = Form(False, description="Deckenflächen mitrechnen"),
    detect_openings: bool = Form(
        False,
        description="Öffnungen aus der Plangeometrie erkennen. Deutlich langsamer; "
                    "nur nötig, wenn der Plan keine Türstempel hat.",
    ),
) -> Dict[str, Any]:
    """
    Run the full chain: plan → raw model → VOB-conformant positions.

    Returns positions that are all unreviewed, and therefore none exportable.
    That is intended — the review step is the product, not a formality.
    """
    parsed_trade = parse_trade(trade)
    if parsed_trade is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekanntes Gewerk '{trade}'. Verfügbar: "
                   f"{[t['trade'] for t in ruleset_catalog()]}",
        )

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Es werden nur PDF-Dateien unterstützt.")

    # Kept on disk rather than streamed: the extraction services take a path,
    # and the review screen renders pages from the same file afterwards.
    stem = Path(file.filename).stem
    pdf_path = _UPLOAD_DIR / f"{len(_JOBS) + 1}_{stem[:40]}.pdf"
    pdf_path.write_bytes(file.file.read())

    model = build_raw_model(
        pdf_path,
        document_id=stem,
        detect_openings=detect_openings,
    )

    params = RuleParams(
        wall_height_m=wall_height_m,
        extras={
            "include_ceiling": include_ceiling,
            "default_opening_height_m": opening_height_m,
        },
    )
    position_set = run_ruleset(model, parsed_trade, params)

    job_id = _store(position_set, pdf_path, model.scale.denominator)
    payload = position_set.to_dict()
    payload["job_id"] = job_id
    payload["raw_model"] = model.to_dict()

    # Everything the measuring tool needs to turn two clicks into metres.
    payload["measurement"] = {
        "scale_denominator": model.scale.denominator,
        "points_per_metre": (
            points_per_metre(model.scale.denominator)
            if model.scale.denominator else None
        ),
        "is_scale_confirmed": model.scale.is_user_confirmed,
    }
    return payload


@router.get("/{job_id}")
def get_result(job_id: str) -> Dict[str, Any]:
    """Retrieve a stored result, e.g. after reloading the review screen."""
    payload = _load(job_id).to_dict()
    payload["job_id"] = job_id
    return payload


@router.post("/{job_id}/positions/{position_id}/review")
def review_position(job_id: str, position_id: str, request: ReviewRequest) -> Dict[str, Any]:
    """
    Sign off on one position, or correct it.

    This is the moment responsibility moves from machine to human, so the
    reviewer's name and the original value are both recorded.
    """
    position_set = _load(job_id)

    position = next(
        (p for p in position_set.positions if p.position_id == position_id), None
    )
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position '{position_id}' nicht gefunden.")

    position.mark_reviewed(request.reviewed_by, request.corrected_quantity)

    return {
        "position": position.to_dict(),
        "exportable_count": position_set.exportable_count,
        "review_pending_count": position_set.review_pending_count,
        "is_release_ready": position_set.is_release_ready,
    }


@router.post("/{job_id}/review-all")
def review_all(job_id: str, request: ReviewAllRequest) -> Dict[str, Any]:
    """
    Bulk sign-off.

    Skips positions carrying warnings by default. A warning means the system
    found something it could not resolve — waving a hundred of those through
    with one click is exactly the habit this product exists to prevent.
    """
    position_set = _load(job_id)

    approved: List[str] = []
    skipped: List[str] = []

    for position in position_set.positions:
        if position.is_exportable:
            continue
        if request.only_without_warnings and position.warnings:
            skipped.append(position.position_id)
            continue
        position.mark_reviewed(request.reviewed_by)
        approved.append(position.position_id)

    return {
        "approved": len(approved),
        "skipped_with_warnings": len(skipped),
        "exportable_count": position_set.exportable_count,
        "review_pending_count": position_set.review_pending_count,
        "is_release_ready": position_set.is_release_ready,
    }


@router.get("/{job_id}/page/{page_number}")
def render_page(job_id: str, page_number: int, max_px: int = 2400):
    """
    Render one plan page as PNG for the review screen.

    Resolution is derived from `max_px`, not fixed as DPI. Construction plans
    are A0 and larger: a 5.386 × 4.691 pt sheet at 110 dpi is 8.229 px wide and
    lands at roughly 12 MB, which no browser handles gracefully. Capping the
    long edge instead keeps every sheet size in a sane range.

    Also returns the page's PDF-point dimensions in headers. The frontend needs
    them to place highlight boxes: evidence geometry is in PDF points, the image
    is in pixels, and the ratio between them is the only thing that makes a
    highlight land on the right room instead of somewhere near it.
    """
    job = _job(job_id)

    try:
        import fitz

        with fitz.open(str(job.pdf_path)) as doc:
            if not (1 <= page_number <= len(doc)):
                raise HTTPException(
                    status_code=404,
                    detail=f"Seite {page_number} existiert nicht "
                           f"(Dokument hat {len(doc)} Seiten).",
                )

            page = doc[page_number - 1]
            longest_edge_points = max(page.rect.width, page.rect.height)
            dpi = max(24, min(150, int(72.0 * max_px / longest_edge_points)))

            pixmap = page.get_pixmap(dpi=dpi)
            png = pixmap.tobytes("png")

            return Response(
                content=png,
                media_type="image/png",
                headers={
                    "X-Page-Width-Points": str(page.rect.width),
                    "X-Page-Height-Points": str(page.rect.height),
                    "X-Image-Width-Px": str(pixmap.width),
                    "X-Image-Height-Px": str(pixmap.height),
                    "X-Page-Count": str(len(doc)),
                    "Access-Control-Expose-Headers":
                        "X-Page-Width-Points, X-Page-Height-Points, "
                        "X-Image-Width-Px, X-Image-Height-Px, X-Page-Count",
                    "Cache-Control": "private, max-age=3600",
                },
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Seitenrendering fehlgeschlagen (%s, S.%s): %s",
                       job_id, page_number, exc)
        raise HTTPException(
            status_code=500, detail=f"Seite konnte nicht gerendert werden: {exc}"
        ) from exc


@router.get("/{job_id}/chains")
def get_dimension_chains(job_id: str, page_number: int = 1) -> Dict[str, Any]:
    """
    The Maßketten on a page — the dimensions the building is drawn from.

    Separate from /analyze because chain extraction is only worth running when
    someone is actually looking at them, and because it answers a different
    question: not "what does this room measure" but "what does this plan say
    about the structure".
    """
    job = _job(job_id)
    chains = extract_dimension_chains(
        job.pdf_path,
        page_number=page_number,
        scale_denominator=job.scale_denominator,
    )
    return chains.to_dict()


@router.get("/{job_id}/export")
def export(job_id: str, format: str = "xlsx"):
    """
    Download the Aufmaß. Only signed-off positions are included.

    A request with nothing signed off returns 409 rather than an empty file — an
    empty spreadsheet looks like a bug, a clear refusal explains itself.
    """
    position_set = _load(job_id)
    stem = position_set.document_id

    try:
        if format == "xlsx":
            return Response(
                content=build_excel(position_set),
                media_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                headers={
                    "Content-Disposition": f'attachment; filename="{stem}_aufmass.xlsx"'
                },
            )
        if format == "csv":
            return Response(
                content=build_csv(position_set).encode("utf-8-sig"),  # BOM für Excel/DE
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{stem}_aufmass.csv"'
                },
            )
        if format in ("protokoll", "protocol"):
            return PlainTextResponse(
                content=build_protocol(position_set),
                headers={
                    "Content-Disposition": f'attachment; filename="{stem}_protokoll.txt"'
                },
            )
    except ExportBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    raise HTTPException(
        status_code=400,
        detail=f"Unbekanntes Format '{format}'. Verfügbar: xlsx, csv, protokoll.",
    )
