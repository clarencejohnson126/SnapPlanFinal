"""
The measuring grid a plan is drawn on, reconstructed from its Maßketten.

WHAT PROBLEM THIS SOLVES

A Raumstempel states a room's area — when someone bothered to stamp it. Most
rooms on most plans have no area at all, and reading only stamps means SnapPlan
can report what a planner already calculated but cannot measure anything itself.

A Maßkette states the building. Cumulate one chain and you have the positions of
every wall along a line; take a second chain at right angles and those positions
intersect into a grid of cells with known dimensions. A room's stamp sits in one
of those cells — so its size follows from the plan's own dimensioning, whether
or not an area was ever written down.

    horizontal:  0,00   5,00   8,50   12,70
    vertical:    0,00   4,00   10,00

    → cell (0,0) is 5,00 × 4,00 = 20,00 m²

THE SELF-CHECK THAT MAKES THIS TRUSTWORTHY

Each dimension label is centred over the span it measures. So the label's
position on the sheet, in points, must match its cumulated position in metres,
scaled. Fitting one against the other yields points-per-metre — which can then
be compared against the scale printed in the Plankopf.

Agreement proves three things at once: the chain was read in the right order, no
value was misparsed, and the stated scale is real. Disagreement means something
is wrong, and `PlanGrid.scale_confirmed` says so rather than letting a wrong
dimension through. The check costs nothing and needs no ground truth from
outside the document.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging

from app.services.dimension_chains import ChainSet, DimensionChain

logger = logging.getLogger(__name__)

#: How far a label may sit from where its cumulated position predicts, in
#: metres, before the chain counts as inconsistent. Dimension text is nudged to
#: avoid collisions, so this tolerates centimetres, not decimetres.
_MAX_RESIDUAL_M = 0.35

#: How far the fitted scale may deviate from the one printed in the Plankopf.
#: Beyond this the two disagree about what the drawing means.
_SCALE_TOLERANCE = 0.06

#: A grid axis needs at least this many lines to bound any cell.
_MIN_LINES = 3


@dataclass
class GridLine:
    """One wall or axis position, in both worlds."""

    position_m: float     # cumulated distance from the chain's origin
    position_pt: float    # where that lands on the sheet

    def to_dict(self) -> Dict[str, float]:
        return {"position_m": round(self.position_m, 4),
                "position_pt": round(self.position_pt, 2)}


@dataclass
class GridAxis:
    """The lines of one direction, ordered along the sheet."""

    orientation: str                     # "horizontal" | "vertical"
    lines: List[GridLine] = field(default_factory=list)
    #: Points per metre as fitted from this axis. Signed: on the vertical axis
    #: PDF y grows downward, so a chain running upward fits a negative slope.
    fitted_pt_per_m: float = 0.0
    #: Largest deviation between a label's actual and predicted position.
    residual_m: float = 0.0

    @property
    def extent_m(self) -> float:
        if len(self.lines) < 2:
            return 0.0
        return abs(self.lines[-1].position_m - self.lines[0].position_m)

    @property
    def is_consistent(self) -> bool:
        return bool(self.lines) and self.residual_m <= _MAX_RESIDUAL_M

    def span_between(self, first_pt: float, second_pt: float) -> Optional[float]:
        """
        Real distance in metres between two points on the sheet.

        Uses this axis's own fitted scale rather than a global one, because a
        sheet may carry details drawn at a different scale than the main plan.
        """
        if not self.fitted_pt_per_m:
            return None
        return abs(second_pt - first_pt) / abs(self.fitted_pt_per_m)

    def bracketing_lines(self, position_pt: float) -> Optional[Tuple[GridLine, GridLine]]:
        """The two lines a point lies between, or None if it lies outside."""
        ordered = sorted(self.lines, key=lambda line: line.position_pt)
        for lower, upper in zip(ordered, ordered[1:]):
            if lower.position_pt <= position_pt <= upper.position_pt:
                return lower, upper
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orientation": self.orientation,
            "line_count": len(self.lines),
            "extent_m": round(self.extent_m, 3),
            "fitted_pt_per_m": round(self.fitted_pt_per_m, 3),
            "residual_m": round(self.residual_m, 4),
            "is_consistent": self.is_consistent,
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass
class GridCell:
    """One field of the grid — a candidate room, measured by the plan itself."""

    width_m: float
    height_m: float
    x_range_pt: Tuple[float, float]
    y_range_pt: Tuple[float, float]

    @property
    def area_m2(self) -> float:
        return round(self.width_m * self.height_m, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width_m": round(self.width_m, 3),
            "height_m": round(self.height_m, 3),
            "area_m2": self.area_m2,
            "x_range_pt": [round(v, 2) for v in self.x_range_pt],
            "y_range_pt": [round(v, 2) for v in self.y_range_pt],
        }


@dataclass
class PlanGrid:
    """Both axes plus what they say about the drawing's scale."""

    horizontal: Optional[GridAxis] = None
    vertical: Optional[GridAxis] = None
    #: Scale from the Plankopf, for comparison. None when the plan states none.
    stated_scale: Optional[int] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """Whether both directions are present and internally consistent."""
        return bool(
            self.horizontal and self.vertical
            and self.horizontal.is_consistent and self.vertical.is_consistent
        )

    @property
    def fitted_scale(self) -> Optional[float]:
        """
        The scale denominator implied by the chains themselves.

        Averaged across both axes — they measure the same drawing, so a large
        difference between them is itself a signal that one was misread.
        """
        slopes = [
            abs(axis.fitted_pt_per_m)
            for axis in (self.horizontal, self.vertical)
            if axis and axis.fitted_pt_per_m
        ]
        if not slopes:
            return None
        mean_slope = sum(slopes) / len(slopes)
        if mean_slope <= 0:
            return None
        # points_per_metre(s) = 72 / (0.0254 · s)  →  s = 72 / (0.0254 · ppm)
        return 72.0 / (0.0254 * mean_slope)

    @property
    def scale_confirmed(self) -> bool:
        """True when the chains and the Plankopf agree about the scale."""
        fitted = self.fitted_scale
        if fitted is None or not self.stated_scale:
            return False
        return abs(fitted - self.stated_scale) / self.stated_scale <= _SCALE_TOLERANCE

    def cell_at(self, x_pt: float, y_pt: float) -> Optional[GridCell]:
        """
        The cell containing a point on the sheet.

        This is how a room stamp becomes a measurement: the stamp's coordinates
        are known, and the cell around it carries the dimensions the plan gives.
        """
        if not (self.horizontal and self.vertical):
            return None

        horizontal_pair = self.horizontal.bracketing_lines(x_pt)
        vertical_pair = self.vertical.bracketing_lines(y_pt)
        if not horizontal_pair or not vertical_pair:
            return None

        left, right = horizontal_pair
        top, bottom = vertical_pair
        return GridCell(
            width_m=abs(right.position_m - left.position_m),
            height_m=abs(bottom.position_m - top.position_m),
            x_range_pt=(left.position_pt, right.position_pt),
            y_range_pt=(top.position_pt, bottom.position_pt),
        )

    def area_between(self, x1_pt: float, y1_pt: float,
                     x2_pt: float, y2_pt: float) -> Optional[float]:
        """
        Real area of a rectangle drawn on the sheet, in m².

        This answers "zieh mir von hier bis dort die Bodenfläche": the span is
        converted through each axis's own fitted scale, so the result comes from
        the plan's dimensioning rather than from a pixel estimate.
        """
        if not (self.horizontal and self.vertical):
            return None
        width = self.horizontal.span_between(x1_pt, x2_pt)
        height = self.vertical.span_between(y1_pt, y2_pt)
        if width is None or height is None:
            return None
        return round(width * height, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_usable": self.is_usable,
            "stated_scale": self.stated_scale,
            "fitted_scale": round(self.fitted_scale, 1) if self.fitted_scale else None,
            "scale_confirmed": self.scale_confirmed,
            "horizontal": self.horizontal.to_dict() if self.horizontal else None,
            "vertical": self.vertical.to_dict() if self.vertical else None,
            "warnings": self.warnings,
        }


def build_grid(chains: ChainSet, stated_scale: Optional[int] = None) -> PlanGrid:
    """
    Turn the Maßketten of a sheet into a measuring grid.

    Picks the longest consistent chain per direction: a full-width Maßkette
    spans the structure, while shorter ones describe parts of it and would
    produce a grid covering only a corner of the plan.
    """
    grid = PlanGrid(stated_scale=stated_scale)

    for orientation in ("horizontal", "vertical"):
        axis = _best_axis(chains.by_orientation(orientation), orientation)
        if axis is None:
            grid.warnings.append(
                f"Keine belastbare Maßkette in {orientation}er Richtung — ohne "
                f"sie lässt sich in dieser Achse nichts berechnen."
            )
            continue

        setattr(grid, orientation, axis)
        if not axis.is_consistent:
            grid.warnings.append(
                f"Maßkette ({orientation}) weicht um bis zu {axis.residual_m:.2f} m "
                f"von ihrer eigenen Bemaßung ab — vermutlich wurde ein Maß falsch "
                f"gelesen. Nicht für Berechnungen verwenden."
            )

    fitted = grid.fitted_scale
    if fitted and stated_scale and not grid.scale_confirmed:
        grid.warnings.append(
            f"Der aus den Maßketten abgeleitete Maßstab (1:{fitted:.0f}) weicht vom "
            f"angegebenen (1:{stated_scale}) ab. Solange das nicht geklärt ist, sind "
            f"daraus berechnete Mengen nicht belastbar."
        )
    elif grid.scale_confirmed:
        logger.info("Maßstab 1:%s durch die Maßketten bestätigt.", stated_scale)

    return grid


#: Two grid lines closer than this on the sheet describe the same wall and are
#: merged. At 1:50 this is about 4 cm in reality — finer than any wall position
#: a plan distinguishes, coarse enough to absorb rounding between chains.
_MERGE_TOLERANCE_PT = 2.0


def _best_axis(candidates: List[DimensionChain],
               orientation: str) -> Optional[GridAxis]:
    """
    Merge every consistent chain of one direction into a single set of lines.

    Taking only the longest chain was wrong and wrong in a way that looked
    plausible: a plan's outermost Maßkette gives overall dimensions in a handful
    of spans, so the grid came out with seven columns for a building with
    thirty-eight rooms. Cells spanned whole apartments — a 5 m² room measured
    37 m², and nothing about the number looked broken.

    Plans dimension in layers: an overall chain, a coarse one below it, a fine
    one against the walls. Every one of them marks real wall positions, and only
    their union is the grid the building was drawn on. Because each chain is
    fitted to the sheet independently, their lines already share one coordinate
    system — the page — so merging is just deduplication.
    """
    built = [_axis_from_chain(chain, orientation) for chain in candidates]
    usable = [axis for axis in built if axis and axis.is_consistent]

    if not usable:
        # Nothing consistent — return the longest anyway so the caller can
        # report *why* it is unusable rather than merely finding nothing.
        fallback = [axis for axis in built if axis and len(axis.lines) >= _MIN_LINES]
        return max(fallback, key=lambda axis: axis.extent_m) if fallback else None

    # The scale is a property of the drawing, not of one chain. Take it from the
    # chain that spans the most, where a fitting error weighs least.
    reference = max(usable, key=lambda axis: axis.extent_m)
    slope = reference.fitted_pt_per_m

    merged_pt: List[float] = []
    for axis in usable:
        for line in axis.lines:
            if not any(abs(line.position_pt - kept) <= _MERGE_TOLERANCE_PT
                       for kept in merged_pt):
                merged_pt.append(line.position_pt)

    if len(merged_pt) < _MIN_LINES:
        return reference

    merged_pt.sort()
    origin_pt = merged_pt[0] if slope > 0 else merged_pt[-1]

    return GridAxis(
        orientation=orientation,
        lines=[
            GridLine(position_m=abs(position - origin_pt) / abs(slope),
                     position_pt=position)
            for position in merged_pt
        ],
        fitted_pt_per_m=slope,
        # The merged axis inherits the reference chain's quality: the individual
        # fits were already checked, and merging cannot make them worse.
        residual_m=max(axis.residual_m for axis in usable),
    )


def _axis_from_chain(chain: DimensionChain,
                     orientation: str) -> Optional[GridAxis]:
    """
    Cumulate one chain into grid lines and fit it against the sheet.

    The fit is the point of this function. Cumulating alone produces
    plausible-looking metres from any row of numbers; checking them against
    where their labels actually sit is what distinguishes a real Maßkette from
    a coincidence.
    """
    values = chain.values_m
    labels_pt = chain.positions_pt
    if len(values) < 2 or len(labels_pt) != len(values):
        return None

    # Cumulated edges, and the midpoint of each span — where its label belongs.
    edges_m: List[float] = [0.0]
    for value in values:
        edges_m.append(edges_m[-1] + value)
    midpoints_m = [(edges_m[i] + edges_m[i + 1]) / 2.0 for i in range(len(values))]

    slope, intercept = _fit_line(midpoints_m, labels_pt)
    if slope is None or abs(slope) < 1e-6:
        return None

    residual_pt = max(
        abs(actual - (slope * expected + intercept))
        for expected, actual in zip(midpoints_m, labels_pt)
    )

    return GridAxis(
        orientation=orientation,
        lines=[
            GridLine(position_m=edge, position_pt=slope * edge + intercept)
            for edge in edges_m
        ],
        fitted_pt_per_m=slope,
        residual_m=residual_pt / abs(slope),
    )


def _fit_line(xs: List[float], ys: List[float]) -> Tuple[Optional[float], float]:
    """Least-squares fit of ys = slope · xs + intercept."""
    count = len(xs)
    if count < 2:
        return None, 0.0

    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    variance = sum((x - mean_x) ** 2 for x in xs)
    if variance == 0:
        return None, 0.0

    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / variance
    return slope, mean_y - slope * mean_x
