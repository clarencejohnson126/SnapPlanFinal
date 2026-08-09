"""
Schicht 1 adapter — existing extraction services onto the RawModel contract.

WHY AN ADAPTER RATHER THAN A REWRITE

The extraction services are 18.000 lines that work. Rewriting them to emit
RawModel directly would risk every regression they have already survived. This
module translates instead: it calls them as they are and maps their output onto
the contract. They stay untouched; the layer boundary still holds.

THE ONE THING THIS MODULE MUST GET RIGHT

`ExtractedRoom` carries three fields that look useful and are traps:

    area_m2     the measured floor area          → this is what we take
    counted_m2  area after the 50 % balcony rule → this is ALREADY Abrechnung
    factor      the rule that produced it        → also Abrechnung

Taking `counted_m2` would smuggle a billing rule into Schicht 1 and silently
halve outdoor areas for every trade, whether or not that trade's ATV says so.
So we take the raw area and pass the *classification* (`is_outdoor`) through.
Whether that means ×0.5, ×1.0, or exclusion is the ruleset's call.

The planner's own factor is kept in `attributes` for reference — visible to a
reviewer, invisible to the arithmetic.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from app.domain.evidence import CoordinateSpace, Evidence, ExtractionMethod, Geometry
from app.domain.quantities import (
    Opening,
    OpeningKind,
    RawModel,
    RoomSpace,
    ScaleInfo,
)
from app.services import door_stamp_extraction, unified_extraction
from app.services.scale_calibration import detect_scale_from_text

logger = logging.getLogger(__name__)


def build_raw_model(
    pdf_path: Union[str, Path],
    document_id: Optional[str] = None,
    style: Optional[str] = None,
    detect_openings: bool = False,
    elevation_pdfs: Optional[Sequence[Union[str, Path]]] = None,
) -> RawModel:
    """
    Run Schicht 1 over a PDF and return the trade-neutral model.

    Never raises on a difficult plan. A PDF that yields nothing comes back as an
    empty RawModel with warnings explaining why — the caller shows that to the
    user rather than a stack trace.

    `detect_openings` switches on geometric opening detection. It is off by
    default because it renders the page at 400 dpi and runs OpenCV over it —
    seconds per page, versus milliseconds for the text path. Turn it on when the
    plan carries no Türstempel and the trade needs deductions.
    """
    path = Path(pdf_path)
    doc_id = document_id or path.stem

    model = RawModel(document_id=doc_id, source_files=[path.name])

    if not path.exists():
        model.warnings.append(f"Datei nicht gefunden: {path.name}")
        return model

    _extract_rooms(path, doc_id, model, style)
    _extract_door_stamps(path, doc_id, model)
    _backfill_geometry(path, model)
    _detect_scale(path, model)

    if elevation_pdfs:
        attach_level_heights(elevation_pdfs, model)

    if detect_openings:
        attach_wall_openings(path, doc_id, model)

    _check_opening_assignment(model)

    return model


#: Room numbers carry their storey: R1.E-1.0.3 → E-1, F.E5.1.08.12 → E5
_ROOM_LEVEL = re.compile(r'^[A-Z]\d*\.(E-?\d+)\.')


def attach_level_heights(elevation_pdfs: Sequence[Union[str, Path]],
                         model: RawModel) -> None:
    """
    Fill in clear room heights from Ansichten or Schnitte.

    A Grundriss states areas but not heights, which is why wall-based trades
    produced almost nothing on the real plan corpus. The heights are on the
    elevation sheets as OKFFB/UKRD pairs, and room numbers carry their storey —
    so a height can be matched to a room rather than assumed for the building.

    Rooms whose storey cannot be identified are left without a height. The
    building's dominant height is deliberately *not* applied silently: a wrong
    height is a wrong wall area on every wall of that room.
    """
    from app.services.elevation_extraction import extract_level_heights

    merged: Dict[str, float] = {}
    sources: List[str] = []

    for pdf in elevation_pdfs:
        result = extract_level_heights(pdf)
        model.warnings.extend(result.warnings)

        for label, values in result.conflicts.items():
            model.warnings.append(
                f"Geschosshöhe {label} weicht zwischen den Ansichten ab: "
                f"{', '.join(f'{v:.2f} m' for v in values)}. Bitte prüfen."
            )

        for level in result.levels:
            if level.level_label:
                merged.setdefault(level.level_label, level.clear_height_m)
        if result.levels:
            sources.append(Path(pdf).name)

    if not merged:
        model.warnings.append(
            "Aus den Ansichten konnten keine Geschosshöhen einzelnen Ebenen "
            "zugeordnet werden."
        )
        return

    applied = 0
    unmatched = 0
    for room in model.rooms:
        if room.clear_height_m is not None:
            continue  # the Grundriss already stated one — it wins

        match = _ROOM_LEVEL.match(room.number or "")
        height = merged.get(match.group(1)) if match else None
        if height is None:
            unmatched += 1
            continue

        room.clear_height_m = height
        room.evidence.notes.append(
            f"Lichte Höhe {height:.2f} m aus Ansicht (Ebene {match.group(1)}, "
            f"OKFFB bis UKRD)"
        )
        applied += 1

    model.warnings.append(
        f"Lichte Höhen aus {', '.join(sources)} übernommen: {applied} Räume "
        f"zugeordnet, {unmatched} ohne passende Ebene."
        if applied else
        f"Keine Höhe konnte einem Raum zugeordnet werden "
        f"({unmatched} Räume geprüft)."
    )


# ----------------------------------------------------------------------- rooms

def _extract_rooms(path: Path, doc_id: str, model: RawModel,
                   style: Optional[str]) -> None:
    """
    Read the rooms, preferring the positional stamp reader.

    `unified_extraction` walks the text line by line and assumes a room's values
    follow its number. On the SPA sheets the number comes *after* its values, so
    every area was taken from the next room — B.02.1.105 reported 6,06 m² where
    the plan says 12,14. Nothing about that output looked wrong.

    So position wins: `room_stamp_extraction` assigns each value to the nearest
    room number. The line-based reader stays as a fallback for sheets whose
    number format it recognises and the positional one does not.
    """
    if _extract_rooms_positional(path, doc_id, model):
        return

    model.warnings.append(
        "Positionsbasierte Stempelerkennung lieferte keine Räume — es wurde auf "
        "die zeilenbasierte Extraktion zurückgegriffen. Werte bitte besonders "
        "sorgfältig prüfen."
    )
    _extract_rooms_linewise(path, doc_id, model, style)


def _extract_rooms_positional(path: Path, doc_id: str, model: RawModel) -> bool:
    """Map positionally-read Raumstempel onto RoomSpace. True if any were found."""
    from app.services.room_stamp_extraction import extract_room_stamps

    try:
        result = extract_room_stamps(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stempelerkennung fehlgeschlagen für %s: %s", path.name, exc)
        return False

    usable = [s for s in result.stamps if s.area_m2 is not None]
    if not usable:
        return False

    model.warnings.extend(result.warnings)

    without_values = len(result.stamps) - len(usable)
    if without_values:
        model.warnings.append(
            f"{without_values} Raumnummern ohne lesbare Flächenangabe gefunden — "
            f"diese Räume fehlen im Aufmaß und sollten im Plan geprüft werden."
        )

    for stamp in usable:
        model.rooms.append(RoomSpace(
            evidence=Evidence(
                method=ExtractionMethod.TEXT,
                file_id=doc_id,
                page_number=stamp.page_number,
                geometry=Geometry(
                    space=CoordinateSpace.PDF_POINTS,
                    bbox=(
                        stamp.bbox[0],
                        stamp.bbox[1],
                        stamp.bbox[2] - stamp.bbox[0],
                        stamp.bbox[3] - stamp.bbox[1],
                    ),
                ),
                raw_value=" | ".join(stamp.raw_lines[:4]),
                detector="room_stamp_extraction",
                confidence=1.0,
            ),
            number=stamp.number,
            name=stamp.name,
            floor_area_m2=stamp.area_m2,
            perimeter_m=stamp.perimeter_m,
            clear_height_m=stamp.clear_height_m,
            is_outdoor=unified_extraction.is_outdoor_room(stamp.name or ""),
            is_wet_room=_is_wet_room(stamp.name or ""),
            attributes={"source": "stamp_positional"},
        ))

    return True


def _extract_rooms_linewise(path: Path, doc_id: str, model: RawModel,
                            style: Optional[str]) -> None:
    """Fallback: map unified_extraction's rooms onto RoomSpace."""
    try:
        blueprint_style = (
            unified_extraction.BlueprintStyle(style) if style else None
        )
        result = unified_extraction.extract_room_areas(path, style=blueprint_style)
    except Exception as exc:  # noqa: BLE001 — a bad PDF must not crash the request
        logger.warning("Raumextraktion fehlgeschlagen für %s: %s", path.name, exc)
        model.warnings.append(f"Raumextraktion fehlgeschlagen: {exc}")
        return

    model.warnings.extend(result.warnings)

    for extracted in result.rooms:
        model.rooms.append(_to_room_space(extracted, doc_id, result.blueprint_style))

    if not result.rooms:
        model.warnings.append(
            "Keine Räume erkannt. Der Plan hat womöglich keine Textebene "
            "(reiner Scan) oder ein unbekanntes Stempelformat."
        )


def _to_room_space(extracted: Any, doc_id: str, blueprint_style: Any) -> RoomSpace:
    """
    One ExtractedRoom → one RoomSpace.

    Note what is *not* copied: counted_m2 and factor. See the module docstring.
    """
    detector = f"unified_extraction:{blueprint_style.value}"
    if extracted.extraction_pattern:
        detector = f"{detector}:{extracted.extraction_pattern}"

    evidence = Evidence(
        method=ExtractionMethod.TEXT,
        file_id=doc_id,
        # unified_extraction counts pages from 0; humans and the Prüfprotokoll
        # count from 1. Convert here, once, at the boundary.
        page_number=extracted.page + 1,
        geometry=_bbox_to_geometry(extracted.bbox),
        raw_value=extracted.source_text,
        detector=detector,
        confidence=1.0,  # read from the text layer, not interpreted
    )

    # The planner's own factor is reference material, never input to a rule.
    attributes: Dict[str, Any] = {
        "category": getattr(extracted.category, "value", None),
        "blueprint_style": blueprint_style.value,
    }
    if extracted.factor is not None and extracted.factor != 1.0:
        attributes["planer_factor"] = extracted.factor
        attributes["planer_counted_m2"] = extracted.counted_m2
        attributes["planer_factor_source"] = extracted.factor_source

    return RoomSpace(
        evidence=evidence,
        number=extracted.room_number or None,
        name=extracted.room_name or None,
        floor_area_m2=extracted.area_m2,
        perimeter_m=extracted.perimeter_m,
        clear_height_m=extracted.height_m,
        is_outdoor=unified_extraction.is_outdoor_room(extracted.room_name or ""),
        is_wet_room=_is_wet_room(extracted.room_name or ""),
        attributes=attributes,
    )


#: Room names implying a wet room. Drives Abdichtung/Fliesen decisions later.
_WET_ROOM_TOKENS = (
    "bad", "wc", "dusche", "sanitär", "sanitaer", "waschraum",
    "putzraum", "teeküche", "teekueche", "nassraum",
)


def _is_wet_room(room_name: str) -> bool:
    """Classification only — no trade decides anything here."""
    lowered = room_name.lower()
    return any(token in lowered for token in _WET_ROOM_TOKENS)


def _bbox_to_geometry(bbox: Any) -> Optional[Geometry]:
    """
    BoundingBox(x0, y0, x1, y1) → Geometry(x, y, w, h) in PDF points.

    unified_extraction works in PDF user space throughout, so no DPI conversion
    is involved. Getting this wrong puts the reviewer's highlight in the wrong
    place, which is why the space is stated explicitly rather than assumed.
    """
    if bbox is None:
        return None
    return Geometry(
        space=CoordinateSpace.PDF_POINTS,
        bbox=(bbox.x0, bbox.y0, bbox.x1 - bbox.x0, bbox.y1 - bbox.y0),
    )


def _backfill_geometry(path: Path, model: RawModel) -> None:
    """
    Find page positions for rooms that arrived without coordinates.

    unified_extraction works on plain text lines, so most rooms come back with
    no bbox at all. Without a position the reviewer cannot click a number and
    jump to its spot in the plan — and that Prüfpfad is the product's core
    promise, not a nicety.

    We search the page for the room number rather than the stamp text. Two
    reasons: the number is unique on the sheet, and the stamp text has already
    been normalised by the extractor ("NRF: 42,11" → "NRF: 42.11"), so it no
    longer matches what is actually in the document.
    """
    missing = [r for r in model.rooms if r.evidence.geometry is None]
    if not missing:
        return

    try:
        import fitz

        with fitz.open(str(path)) as doc:
            for room in missing:
                page_index = room.evidence.page_number - 1
                if not (0 <= page_index < len(doc)):
                    continue

                needle = room.number or room.evidence.raw_value
                if not needle:
                    continue

                hits = doc[page_index].search_for(needle)
                if not hits:
                    continue

                rect = hits[0]
                room.evidence.geometry = Geometry(
                    space=CoordinateSpace.PDF_POINTS,
                    bbox=(rect.x0, rect.y0, rect.width, rect.height),
                )
                room.evidence.notes.append(
                    f"Position über Raumnummer '{needle}' im Plan lokalisiert"
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Geometrie-Nachtrag fehlgeschlagen für %s: %s", path.name, exc)
        return

    still_missing = sum(1 for r in model.rooms if r.evidence.geometry is None)
    if still_missing:
        model.warnings.append(
            f"{still_missing} von {len(model.rooms)} Räumen konnten im Plan nicht "
            f"lokalisiert werden — für diese ist kein Sprung zur Fundstelle möglich."
        )


# ---------------------------------------------------------------------- doors

def _extract_door_stamps(path: Path, doc_id: str, model: RawModel) -> None:
    """
    Map Türstempel onto Opening.

    These arrive without geometry — the stamp reader returns dimensions and a
    page, not a position. They therefore land on the document rather than in a
    room, and `_check_opening_assignment` reports what that costs.
    """
    try:
        raw = door_stamp_extraction.extract_door_stamps(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Türstempel-Extraktion fehlgeschlagen für %s: %s", path.name, exc)
        model.warnings.append(f"Türstempel konnten nicht gelesen werden: {exc}")
        return

    for door in raw.get("doors", []):
        model.openings.append(_to_opening(door, doc_id))


def _to_opening(door: Dict[str, Any], doc_id: str) -> Opening:
    """One door stamp → one Opening."""
    evidence = Evidence(
        method=ExtractionMethod.TEXT,
        file_id=doc_id,
        page_number=door.get("page_number", 1),
        raw_value=" ".join(door.get("raw_tokens", [])) or None,
        detector="door_stamp_extraction",
        confidence=door.get("confidence", 1.0),
        notes=["Türstempel ohne Position im Plan — keine Wandzuordnung möglich"],
    )

    return Opening(
        kind=OpeningKind.DOOR,
        evidence=evidence,
        width_m=door.get("width_m"),
        height_m=door.get("height_m"),
        label=door.get("door_number"),
        attributes={
            "fire_rating": door.get("fire_rating"),
            "door_type": door.get("door_type"),
            "acoustic_db": door.get("acoustic_db"),
        },
    )


def attach_wall_openings(path: Path, doc_id: str, model: RawModel,
                         dpi: int = 400) -> None:
    """
    Detect openings from the plan geometry and add them to the model.

    Used when a plan has no Türstempel — the detector finds gaps in the wall
    mask instead of reading annotations.

    TWO THINGS THIS DELIBERATELY DOES NOT DO

    It does not invent a door height. `WallOpening` reports width only, and an
    opening without a height has no area, so `deduct_openings` will report it as
    unmeasurable rather than deduct a guess. A height can be supplied through
    `RuleParams.extras["default_opening_height_m"]`, where it is recorded as a
    user specification in the Rechenweg.

    It does not assign openings to rooms. Doing so needs room polygons, and the
    room data here comes from text stamps, which carry no outline. Until that is
    connected, these openings sit on the document and `_check_opening_
    assignment` says plainly what that costs.
    """
    if not model.scale.denominator:
        model.warnings.append(
            "Öffnungserkennung übersprungen: ohne bekannten Maßstab lassen sich "
            "aus der Geometrie keine Maße ableiten."
        )
        return

    try:
        from app.services.wall_opening_detector import detect_doors_from_wall_openings
    except Exception as exc:  # noqa: BLE001
        model.warnings.append(f"Öffnungserkennung nicht verfügbar: {exc}")
        return

    try:
        result = detect_doors_from_wall_openings(
            pdf_path=str(path),
            page_number=1,
            scale=model.scale.denominator,
            dpi=dpi,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Öffnungserkennung fehlgeschlagen für %s: %s", path.name, exc)
        model.warnings.append(f"Öffnungserkennung fehlgeschlagen: {exc}")
        return

    model.warnings.extend(result.warnings)

    for detected in result.doors:
        model.openings.append(_to_detected_opening(detected, doc_id, dpi))


def _to_detected_opening(detected: Any, doc_id: str, dpi: int) -> Opening:
    """
    One geometrically detected opening → one Opening.

    Coordinates arrive as pixels at render DPI, so the Geometry is tagged
    RENDER_PX with its dpi and normalises itself to PDF points on the way out.
    Marking the method CV is what forces the resulting position into review —
    this is a detection, not a reading.
    """
    half = detected.width_px / 2.0
    geometry = Geometry(
        space=CoordinateSpace.RENDER_PX,
        bbox=(
            detected.center_x - half,
            detected.center_y - half,
            detected.width_px,
            detected.width_px,
        ),
        dpi=dpi,
    )

    notes = ["Aus Plangeometrie erkannt, nicht aus einem Stempel gelesen"]
    if detected.detection_signals:
        notes.append("Signale: " + ", ".join(detected.detection_signals))

    return Opening(
        kind=OpeningKind.DOOR if detected.is_door else OpeningKind.PASSAGE,
        evidence=Evidence(
            method=ExtractionMethod.CV,
            file_id=doc_id,
            page_number=detected.page_number,
            geometry=geometry,
            detector="wall_opening_detector",
            confidence=detected.confidence,
            notes=notes,
        ),
        width_m=detected.width_m,
        height_m=None,  # not measurable from a floor plan — never guessed here
        label=detected.opening_id,
        attributes={"angle_degrees": detected.angle_degrees},
    )


def _check_opening_assignment(model: RawModel) -> None:
    """
    Report openings that could not be tied to a room.

    This matters more than it looks. A ruleset deducts openings per room via
    `room.all_openings()`. Openings sitting on the document are invisible to it,
    so every wall area comes out too large — silently, and in the customer's
    favour, which is the expensive direction to be wrong in.

    Saying so here turns a silent error into a visible warning that blocks
    export until a human has looked.
    """
    unassigned = [o for o in model.openings if o.room_id is None]
    if not unassigned:
        return

    model.warnings.append(
        f"{len(unassigned)} Öffnungen konnten keinem Raum zugeordnet werden "
        f"(Türstempel enthalten keine Position im Plan). Öffnungsabzüge sind "
        f"daher unvollständig — die Wandflächen fallen zu groß aus."
    )


# ---------------------------------------------------------------------- scale

def _detect_scale(path: Path, model: RawModel) -> None:
    """Read the Maßstab from the plan text. Never guessed."""
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            text = "".join(page.get_text() for page in doc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Maßstab-Erkennung fehlgeschlagen für %s: %s", path.name, exc)
        model.warnings.append("Maßstab konnte nicht gelesen werden.")
        return

    detected = detect_scale_from_text(text)
    if not detected:
        model.warnings.append(
            "Kein Maßstab im Plan gefunden. Für Messungen aus der Geometrie "
            "muss der Maßstab manuell bestätigt werden."
        )
        return

    scale_string, scale_factor, confidence = detected
    model.scale = ScaleInfo(
        denominator=int(scale_factor) if scale_factor else None,
        source=f"Plantext ({scale_string})",
        confidence=confidence,
        is_user_confirmed=False,
    )
