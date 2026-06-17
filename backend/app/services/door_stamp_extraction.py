"""
Door stamp (Türstempel) extraction.

Deterministic, text-only reader for the door stamps drawn on architectural
plans. Each door carries a small stamp clustered around its door number
(e.g. B.03.301.01) containing:

  - width over height, stacked just above the number   (e.g. 1.01 / 2.52  -> 1.01 m x 2.52 m)
  - construction type (Bauart), just above the number  (HT-2, GT-2, RR-2, ...)
  - fire rating, just below the number                 (T30, T30RS, T90 ...)
  - acoustic rating                                     (32dB, 42dB ...)

No computer vision: we read the words and their coordinates with PyMuPDF and
parse each stamp by the consistent position of its fields relative to the door
number. Every value comes straight from the PDF text — nothing is generated.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

import fitz  # PyMuPDF

# Door number on these plans: B.<floor>.<3-digit>.<2-digit>, e.g. B.03.301.01
# (distinct from room numbers B.<floor>.<1-digit>.<3-digit>, e.g. B.03.2.001).
DOOR_NUMBER_RE = re.compile(r"^[A-Z]\.\d+\.\d{3}\.\d{2}$")
FIRE_RE = re.compile(r"^T\s?30|^T\s?90", re.IGNORECASE)
CONSTRUCTION_RE = re.compile(r"^(HT|GT|HG|ST|RR|RT|GS)-?\d?$", re.IGNORECASE)
DB_RE = re.compile(r"^(\d{2})\s?dB", re.IGNORECASE)
NUM_RE = re.compile(r"^\d{1,2}[.,]\d{2,3}$")


@dataclass
class DoorStamp:
    door_number: str
    page_number: int
    fire_rating: str = "Standard"   # T30 / T30-RS / T90 / Standard ...
    door_type: Optional[str] = None  # construction code (HT-2, GT-2, ...)
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    acoustic_db: Optional[int] = None
    raw_tokens: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extraction_id": f"door_{self.door_number}",
            "door_number": self.door_number,
            "page_number": self.page_number,
            "fire_rating": self.fire_rating,
            "door_type": self.door_type,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "acoustic_db": self.acoustic_db,
            "confidence": 1.0,  # deterministic text read
            "extraction_method": "door_stamp_text",
            "assumptions": [],
            "warnings": [],
        }


def _num(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _normalize_fire(token: str, has_rs: bool) -> str:
    t = token.upper().replace(" ", "")
    base = "T90" if t.startswith("T90") else "T30"
    if "RS" in t or has_rs:
        return f"{base}-RS"
    return base


def _read_stamp(anchor, words, page_number: int, radius: float) -> DoorStamp:
    """Parse one door stamp from the words clustered around the door number."""
    ax0, ay0 = anchor[0], anchor[1]
    acx, acy = (anchor[0] + anchor[2]) / 2, (anchor[1] + anchor[3]) / 2

    # Collect (dx, dy, text) for words near the anchor.
    local = []
    for w in words:
        wcx, wcy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if abs(wcx - acx) < radius and abs(wcy - acy) < radius:
            local.append((w[0] - ax0, w[1] - ay0, w[4]))

    stamp = DoorStamp(door_number=anchor[4], page_number=page_number)
    stamp.raw_tokens = [t for _, _, t in local]

    # Fire rating: a T30/T90 token anywhere in the stamp; RS may be a separate token.
    has_rs = any(t.upper() == "RS" for _, _, t in local)
    fire_tok = next((t for _, _, t in local if FIRE_RE.match(t)), None)
    if fire_tok:
        stamp.fire_rating = _normalize_fire(fire_tok, has_rs)

    # Construction type (Bauart): code sitting just above the number (dy in [-20, 0]).
    for dx, dy, t in local:
        if CONSTRUCTION_RE.match(t) and -22 <= dy <= 4 and abs(dx) < 60:
            stamp.door_type = t.upper()
            break

    # Acoustic rating.
    for _, _, t in local:
        m = DB_RE.match(t)
        if m:
            stamp.acoustic_db = int(m.group(1))
            break

    # Dimensions: the stamp shows width stacked directly above height in the same
    # column. Door leaf/frame values are <= ~2.95 m (room LRH 3.17 m and areas/
    # perimeters like 11.x, 15.x are excluded by the range). Pair the UPPER number
    # (width) with the LOWER number (height) of any tight vertical pair, and keep
    # the pair closest to the door number. Generous range covers wide entrance
    # doors (e.g. 2.52 x 2.74).
    cand = [(dx, dy, _num(t)) for dx, dy, t in local
            if NUM_RE.match(t) and _num(t) is not None and 0.5 <= _num(t) <= 2.95 and abs(dx) < 95]
    best = None
    best_score = 1e9
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            ax_, ay_, av = cand[i]
            bx_, by_, bv = cand[j]
            dist = ((ax_ - bx_) ** 2 + (ay_ - by_) ** 2) ** 0.5
            hi, lo = max(av, bv), min(av, bv)
            # A width x height pair: two numbers close together (stacked OR side by
            # side) where the larger is a door height (>= 2.0 m). width = smaller,
            # height = larger (covers wide entrance doors too, e.g. 2.52 x 2.74).
            if dist <= 42 and hi >= 2.0:
                mx, my = (ax_ + bx_) / 2.0, (ay_ + by_) / 2.0
                score = (mx ** 2 + my ** 2) ** 0.5  # pair closest to the door number
                if score < best_score:
                    best_score = score
                    best = (round(lo, 3), round(hi, 3))
    if best:
        stamp.width_m, stamp.height_m = best
    return stamp


def extract_door_stamps(
    pdf_path,
    page_number: Optional[int] = None,
    cluster_fraction: float = 0.024,
) -> Dict[str, Any]:
    """Read all door stamps from a plan PDF.

    Args:
        pdf_path: path to the plan PDF.
        page_number: 1-indexed page to read, or None for all pages.
        cluster_fraction: stamp search radius as a fraction of the shorter page
            edge (scales across plan sizes).

    Returns a dict with the door list and summary statistics.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    doc = fitz.open(str(path))
    page_indices = [page_number - 1] if page_number else range(len(doc))

    doors: List[DoorStamp] = []
    processed_pages: List[int] = []
    for idx in page_indices:
        if idx < 0 or idx >= len(doc):
            continue
        page = doc[idx]
        words = page.get_text("words")
        if not words:
            continue
        radius = min(page.rect.width, page.rect.height) * cluster_fraction
        anchors = [w for w in words if DOOR_NUMBER_RE.match(w[4])]
        # De-duplicate door numbers (a number can appear twice); keep first.
        seen = set()
        for a in anchors:
            if a[4] in seen:
                continue
            seen.add(a[4])
            doors.append(_read_stamp(a, words, idx + 1, radius))
        processed_pages.append(idx + 1)

    page_count = len(doc)
    doc.close()

    # Summary
    by_fire: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_width: Dict[str, int] = {}
    widths = []
    for d in doors:
        by_fire[d.fire_rating] = by_fire.get(d.fire_rating, 0) + 1
        if d.door_type:
            by_type[d.door_type] = by_type.get(d.door_type, 0) + 1
        if d.width_m:
            key = f"{d.width_m:.2f}"
            by_width[key] = by_width.get(key, 0) + 1
            widths.append(d.width_m)
    avg_width = round(sum(widths) / len(widths), 3) if widths else None

    return {
        "total_doors": len(doors),
        "page_count": page_count,
        "processed_pages": processed_pages,
        "doors": [d.to_dict() for d in doors],
        "summary": {
            "total_doors": len(doors),
            "by_type": by_type,
            "by_fire_rating": by_fire,
            "by_width": by_width,
            "avg_width_m": avg_width,
        },
        "extraction_method": "door_stamp_text",
    }
