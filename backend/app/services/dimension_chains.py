"""
Maßketten — the dimension chains a plan is actually built from.

WHY THIS IS THE FOUNDATION

A Raumstempel states an area. That is a *result*, and only for rooms someone
bothered to stamp. The Maßkette states the building itself: every wall segment,
opening and offset, in order, along one line. From it you can compute lengths,
widths and areas that no stamp mentions — which is what Massenermittlung is.

    2,355 · 1,135 · 1,375 · 1,135 · 3,115 · 1,135 · … = 37,40 m

SELF-VALIDATION IS BUILT IN

Plans carry nested chains: a fine chain of individual segments, and beside it a
coarser one grouping them. They must add up. When a fine chain sums to its
parent, the reading is confirmed — no external ground truth needed. When it
does not, something was misread, and `ChainSet.validations` says so rather than
letting a wrong length through.

WHAT THIS MODULE DOES NOT DO

It does not guess units, and it does not accept a lone number as a dimension.
A plan is dense with room numbers, door codes and reference marks that look
like measurements. Only values sharing an axis, in sequence, count as a chain.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import re

logger = logging.getLogger(__name__)

#: A dimension in metres: 1,135 / 2,36 / 12,5. Two or three decimals, because
#: German plans write millimetre precision as 1,135 and centimetre as 1,14.
_METRE = re.compile(r'^(\d{1,3}),(\d{2,3})$')

#: Values outside this range are wall-thickness labels, fragments or page
#: numbers rather than chain segments.
_MIN_SEGMENT_M = 0.05
_MAX_SEGMENT_M = 120.0

#: Points of tolerance for "on the same line". Dimension text sits on a thin
#: leader line and is typeset consistently, so this can be tight.
_AXIS_TOLERANCE = 3.0

#: A chain needs at least this many segments. Two numbers that happen to align
#: are a coincidence; four in a row on one axis are a Maßkette.
_MIN_CHAIN_LENGTH = 4

#: How closely a sub-chain must match its parent to count as confirmed. 1 cm
#: absorbs rounding in the plan itself without hiding a real misread.
_VALIDATION_TOLERANCE_M = 0.01


@dataclass
class DimensionChain:
    """One run of dimensions along a single axis."""

    orientation: str                 # "horizontal" | "vertical"
    values_m: List[float]
    position: float                  # y for horizontal chains, x for vertical
    start: float                     # first segment's leading edge, in points
    end: float                       # last segment's trailing edge
    page_number: int

    @property
    def total_m(self) -> float:
        """Sum of the chain — the overall dimension it describes."""
        return round(sum(self.values_m), 3)

    @property
    def segment_count(self) -> int:
        return len(self.values_m)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orientation": self.orientation,
            "values_m": self.values_m,
            "total_m": self.total_m,
            "segment_count": self.segment_count,
            "position": self.position,
            "start": self.start,
            "end": self.end,
            "page_number": self.page_number,
        }


@dataclass
class ChainValidation:
    """A cross-check between two chains describing the same span."""

    fine_total_m: float
    coarse_total_m: float
    difference_m: float
    orientation: str
    confirmed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fine_total_m": self.fine_total_m,
            "coarse_total_m": self.coarse_total_m,
            "difference_m": self.difference_m,
            "orientation": self.orientation,
            "confirmed": self.confirmed,
        }


@dataclass
class ChainSet:
    """Every Maßkette found on a sheet, plus what they say about each other."""

    document_id: str
    chains: List[DimensionChain] = field(default_factory=list)
    validations: List[ChainValidation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def by_orientation(self, orientation: str) -> List[DimensionChain]:
        return [c for c in self.chains if c.orientation == orientation]

    def overall_extent_m(self, orientation: str) -> Optional[float]:
        """
        The building's extent along one axis.

        Taken as the longest chain in that direction — a full-width Maßkette
        spans the structure, shorter ones describe parts of it.
        """
        candidates = self.by_orientation(orientation)
        if not candidates:
            return None
        return max(c.total_m for c in candidates)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for v in self.validations if v.confirmed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chains": [c.to_dict() for c in self.chains],
            "chain_count": len(self.chains),
            "validations": [v.to_dict() for v in self.validations],
            "confirmed_count": self.confirmed_count,
            "overall_width_m": self.overall_extent_m("horizontal"),
            "overall_height_m": self.overall_extent_m("vertical"),
            "warnings": self.warnings,
        }


def points_per_metre(scale_denominator: int) -> float:
    """
    PDF points that represent one real metre at a given scale.

    1 pt = 1/72 inch = 0,0254/72 m on paper. At 1:50, one real metre is 0,02 m
    on paper, so 0,02 / (0,0254/72) ≈ 56,7 pt.
    """
    return 72.0 / (0.0254 * scale_denominator)


def _is_geometrically_consistent(ordered: List[Tuple[float, float, float]],
                                 run_index: int, pt_per_m: float) -> bool:
    """
    Whether these values behave like a real Maßkette on the sheet.

    In a chain, each number is centred over the span it measures. So the
    distance between two neighbouring labels must equal half of one span plus
    half of the next — scaled. Numbers that merely share a y coordinate do not
    satisfy that, which is exactly how a Maßkette can be told from a row of
    unrelated figures that happen to line up.

    This is also why the check is worth its cost: without it the extractor
    reported 1.054 "chains" of which only 10 % could confirm each other.
    """
    if len(ordered) < 3 or pt_per_m <= 0:
        return False

    matches = 0
    comparisons = 0
    for current, following in zip(ordered, ordered[1:]):
        expected_pt = (current[0] + following[0]) / 2.0 * pt_per_m
        actual_pt = abs(following[run_index] - current[run_index])
        if expected_pt <= 0:
            continue
        comparisons += 1
        # 25 % tolerance: label text is centred by the CAD system but nudged to
        # avoid collisions, and short spans get their number offset entirely.
        if abs(actual_pt - expected_pt) / expected_pt <= 0.25:
            matches += 1

    if comparisons == 0:
        return False
    return matches / comparisons >= 0.6


def extract_dimension_chains(pdf_path: Union[str, Path],
                             page_number: int = 1,
                             scale_denominator: Optional[int] = None) -> ChainSet:
    """
    Find the Maßketten on one page.

    Never raises. A sheet without chains comes back empty with a warning, which
    is a legitimate outcome — a Detailplan or a Schnitt may carry none.
    """
    path = Path(pdf_path)
    result = ChainSet(document_id=path.stem)

    if not path.exists():
        result.warnings.append(f"Datei nicht gefunden: {path.name}")
        return result

    try:
        import fitz

        with fitz.open(str(path)) as doc:
            if not (1 <= page_number <= len(doc)):
                result.warnings.append(
                    f"Seite {page_number} existiert nicht "
                    f"(Dokument hat {len(doc)} Seiten)."
                )
                return result
            words = doc[page_number - 1].get_text("words")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Maßkettenextraktion fehlgeschlagen für %s: %s", path.name, exc)
        result.warnings.append(f"Maßketten konnten nicht gelesen werden: {exc}")
        return result

    measurements = _collect_measurements(words)
    if not measurements:
        result.warnings.append(
            "Keine Maßangaben im Format X,XX gefunden — der Plan enthält "
            "womöglich keine bemaßten Ketten."
        )
        return result

    # Without a scale the geometric check cannot run, so every aligned group is
    # kept and the caller is told the readings are unverified.
    pt_per_m = points_per_metre(scale_denominator) if scale_denominator else 0.0
    if not pt_per_m:
        result.warnings.append(
            "Ohne Maßstab konnten die Ketten nicht geometrisch geprüft werden — "
            "ausgerichtete Zahlengruppen wurden ungeprüft übernommen."
        )

    result.chains.extend(
        _chains_along(measurements, "horizontal", page_number, pt_per_m))
    result.chains.extend(
        _chains_along(measurements, "vertical", page_number, pt_per_m))

    if not result.chains:
        result.warnings.append(
            f"{len(measurements)} Maßangaben gefunden, aber keine zusammen"
            f"hängende Kette — die Maße stehen nicht auf gemeinsamen Achsen."
        )
        return result

    result.validations.extend(_cross_validate(result.chains))

    unconfirmed = [v for v in result.validations if not v.confirmed]
    for validation in unconfirmed[:5]:
        result.warnings.append(
            f"Maßkette ({validation.orientation}) summiert auf "
            f"{validation.fine_total_m:.3f} m, die übergeordnete Kette nennt "
            f"{validation.coarse_total_m:.3f} m — Abweichung "
            f"{validation.difference_m:.3f} m. Bitte prüfen."
        )

    return result


def _collect_measurements(
    words: List[Tuple],
) -> List[Tuple[float, float, float]]:
    """
    Every plausible metre dimension, as (value, cx, cy).

    Values outside a sane segment range are dropped here rather than in the
    chain builder, so a stray page number cannot anchor a chain.
    """
    found = []
    for word in words:
        if not _METRE.match(word[4]):
            continue
        value = float(word[4].replace(",", "."))
        if not (_MIN_SEGMENT_M <= value <= _MAX_SEGMENT_M):
            continue
        found.append((
            value,
            (word[0] + word[2]) / 2.0,
            (word[1] + word[3]) / 2.0,
        ))
    return found


def _chains_along(measurements: List[Tuple[float, float, float]],
                  orientation: str, page_number: int,
                  pt_per_m: float = 0.0) -> List[DimensionChain]:
    """
    Group measurements that share an axis into chains.

    Horizontal chains share a y and run along x; vertical chains the reverse.
    Ordering is by position on the running axis, because a Maßkette's meaning
    depends on its sequence — the values are consecutive spans, not a set.
    """
    axis_index = 2 if orientation == "horizontal" else 1   # cy or cx
    run_index = 1 if orientation == "horizontal" else 2

    buckets: Dict[float, List[Tuple[float, float, float]]] = {}
    for item in measurements:
        key = round(item[axis_index] / _AXIS_TOLERANCE) * _AXIS_TOLERANCE
        buckets.setdefault(key, []).append(item)

    chains: List[DimensionChain] = []
    for axis_position, items in buckets.items():
        if len(items) < _MIN_CHAIN_LENGTH:
            continue
        ordered = _drop_outliers(sorted(items, key=lambda i: i[run_index]))
        if len(ordered) < _MIN_CHAIN_LENGTH:
            continue
        if pt_per_m and not _is_geometrically_consistent(ordered, run_index, pt_per_m):
            continue
        chains.append(DimensionChain(
            orientation=orientation,
            values_m=[i[0] for i in ordered],
            position=axis_position,
            start=ordered[0][run_index],
            end=ordered[-1][run_index],
            page_number=page_number,
        ))

    return chains


def _drop_outliers(
    ordered: List[Tuple[float, float, float]],
) -> List[Tuple[float, float, float]]:
    """
    Remove values that sit on the chain's axis but are not part of it.

    Observed on real sheets: a chain of 2–3 m wall segments containing a lone
    97,5 — a level kote or a reference number that happens to share the y of the
    dimension line. Summed in, it turned a 13 m building into a 111 m one.

    A segment more than eight times the chain's median is not a wall span. The
    factor is deliberately loose: a Maßkette legitimately mixes a 0,24 m pier
    with a 12 m hall bay, and rejecting that would be worse than the disease.
    """
    if len(ordered) < 3:
        return ordered

    values = sorted(item[0] for item in ordered)
    median = values[len(values) // 2]
    if median <= 0:
        return ordered

    return [item for item in ordered if item[0] <= median * 8.0]


def _cross_validate(chains: List[DimensionChain]) -> List[ChainValidation]:
    """
    Check chains against each other.

    Plans nest their dimensioning: a fine chain of individual segments sits
    beside a coarser one covering the same span. Equal totals confirm both
    readings; unequal totals mean one was misread. This is the closest thing to
    ground truth a plan offers about itself, and it costs nothing to use.
    """
    validations: List[ChainValidation] = []

    for orientation in ("horizontal", "vertical"):
        group = [c for c in chains if c.orientation == orientation]

        for index, reference in enumerate(group):
            for other in group[index + 1:]:
                if not _spans_same_range(reference, other):
                    continue
                difference = round(abs(reference.total_m - other.total_m), 3)
                validations.append(ChainValidation(
                    fine_total_m=min(reference.total_m, other.total_m),
                    coarse_total_m=max(reference.total_m, other.total_m),
                    difference_m=difference,
                    orientation=orientation,
                    confirmed=difference <= _VALIDATION_TOLERANCE_M,
                ))

    return validations


def _spans_same_range(first: DimensionChain, second: DimensionChain) -> bool:
    """
    Whether two chains describe the same physical span.

    This is the whole basis of the cross-check, and it has to be geometric.
    Comparing totals would be circular — two chains agreeing on 37,55 m proves
    nothing if they cover different parts of the building, and two chains over
    the same span disagreeing is exactly the error worth catching.

    So the test is where they start and end on the sheet, not what they sum to.
    """
    span = max(first.end - first.start, second.end - second.start)
    if span <= 0:
        return False

    # Both ends must line up within a tenth of the span. Nested Maßketten are
    # drawn one above the other and share their extremities closely.
    tolerance = span * 0.10
    return (
        abs(first.start - second.start) <= tolerance
        and abs(first.end - second.end) <= tolerance
    )
