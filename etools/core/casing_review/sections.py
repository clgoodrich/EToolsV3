"""SectionDefinition — middleware between the raw plat DB and consumers.

A ``SectionDefinition`` carries everything we know about one PLSS section:
the 16 boundary segments (default values from ``grid_numbers.sqlite`` +
per-segment override slots), 8 corner overrides (NW/NE/SW/SE section corners
and N/S/E/W quarter corners), the anchor UTM point, the raw plat polygon
for fallback, and a north-reference choice.

Two consumers read this:
    * Casing Review SHL/BHL section sub-tabs render the 3x3 segment grid
      and edit overrides in place.
    * Map & Viz reads ``resolve_polygon()`` so user edits in the section
      tabs reshape the polygons drawn on the 2D map.

The segment-walk geometry honors overrides; with no overrides set,
``resolve_polygon()`` short-circuits and returns the raw plat polygon
verbatim (same shape that ``PlatRepository._build_sections`` produces).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from etools.core.casing_review.footages import (
    DegenerateGeometryError,
    _checked_bounds,
)
from etools.logging_setup import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# PLSS key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PLSSKey:
    """The 6-tuple that uniquely identifies a PLSS section in our DBs.

    ``township_dir``/``range_dir`` use the int codes from the Grid Numbers
    schema (1=N or 1=E; 2=S or 2=W). ``baseline`` 1=Salt Lake, 2=Uintah.
    """

    section: int
    township: int
    township_dir: int
    range_: int
    range_dir: int
    baseline: int

    @property
    def conc(self) -> str:
        """9-char Conc code used by PlatRepository (``"2303S02WU"``)."""
        twpd = "N" if self.township_dir == 1 else "S"
        rngd = "E" if self.range_dir == 1 else "W"
        mer = "S" if self.baseline == 1 else "U"
        return f"{self.section:02d}{self.township:02d}{twpd}{self.range_:02d}{rngd}{mer}"

    @classmethod
    def from_conc(cls, conc: str) -> "PLSSKey":
        if not isinstance(conc, str) or len(conc) < 9:
            raise ValueError(f"Bad Conc code: {conc!r}")
        return cls(
            section=int(conc[0:2]),
            township=int(conc[2:4]),
            township_dir=1 if conc[4].upper() == "N" else 2,
            range_=int(conc[5:7]),
            range_dir=1 if conc[7].upper() == "E" else 2,
            baseline=1 if conc[8].upper() == "S" else 2,
        )

    @classmethod
    def from_location(cls, location) -> "PLSSKey | None":
        """Build from an APDLocationRow-shaped object (.section/.township/.range/.*_dir/.meridian)."""
        try:
            sec = int(location.section)
            twp = int(location.township)
            rng = int(location.range)
        except (TypeError, ValueError, AttributeError):
            return None
        twpd = (location.township_dir or "").upper()
        rngd = (location.range_dir or "").upper()
        mer = (location.meridian or "").upper()
        if twpd not in ("N", "S") or rngd not in ("E", "W") or mer not in ("S", "U"):
            return None
        return cls(
            section=sec,
            township=twp,
            township_dir=1 if twpd == "N" else 2,
            range_=rng,
            range_dir=1 if rngd == "E" else 2,
            baseline=1 if mer == "S" else 2,
        )


# ---------------------------------------------------------------------------
# Section traversal — the ordered list of PLSS sections the wellbore crosses
# ---------------------------------------------------------------------------
@dataclass
class SectionCrossing:
    """One PLSS section the wellbore passes through, in MD order.

    ``label`` is the human label used by both the on-screen section
    sub-tab title and the Excel sheet's logical name. ``apd_name`` is the
    original APD location-row name when this section matched one (Surface
    / producing zone / TD), else ``None`` for an auto-detected
    intermediate crossing.
    """

    conc: str
    fnl: float | None = None
    fsl: float | None = None
    fel: float | None = None
    fwl: float | None = None
    label: str = ""
    apd_name: str | None = None

    def to_location_row(self):
        """Build a writer-ready ``APDLocationRow`` from this crossing.

        Lets the Excel generator drive a BHL Section sheet straight from
        the traversal — same PLSS + footages the section sub-tab shows.
        """
        from etools.models import APDLocationRow

        key = PLSSKey.from_conc(self.conc)
        return APDLocationRow(
            name=self.apd_name or self.label or f"Section {self.conc}",
            fnl=self.fnl,
            fsl=self.fsl,
            fel=self.fel,
            fwl=self.fwl,
            section=str(key.section),
            township=str(key.township),
            township_dir="N" if key.township_dir == 1 else "S",
            range=str(key.range_),
            range_dir="E" if key.range_dir == 1 else "W",
            meridian="S" if key.baseline == 1 else "U",
        )


def _coerce_float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def quarter_quarter(fnl, fsl, fel, fwl) -> "str | None":
    """The PLSS quarter-quarter call (e.g. ``"SESW"``) for a point given its
    distances to all four section lines.

    A section is a 4×4 grid of quarter-quarters. The call is
    ``<inner><outer>`` — the finer 1/16 cell first, then the 1/4 it sits in
    (e.g. ``"SESW"`` = the SE quarter-quarter of the SW quarter). We need all
    four footages to know the section's extent (height = FNL+FSL, width =
    FEL+FWL); returns ``None`` if any axis is incomplete.
    """
    if None in (fnl, fsl, fel, fwl):
        return None
    height = float(fnl) + float(fsl)
    width = float(fel) + float(fwl)
    if height <= 0 or width <= 0:
        return None
    half_h, half_w = height / 2.0, width / 2.0
    # Outer quarter: which half of the whole section (N/S from the top, E/W
    # from the east since FEL is distance from the east line).
    outer_ns = "N" if fnl < half_h else "S"
    outer_ew = "E" if fel < half_w else "W"
    # Inner quarter-quarter: which half *within* that quarter.
    inner_ns = "N" if (float(fnl) % half_h) < (half_h / 2.0) else "S"
    inner_ew = "E" if (float(fel) % half_w) < (half_w / 2.0) else "W"
    return f"{inner_ns}{inner_ew}{outer_ns}{outer_ew}"


def survey_kop_footages(points, kop_md) -> "tuple[str, dict] | None":
    """Computed-KOP contingency: the K.O. Point footages taken straight from
    the survey path when the APD doesn't print a "Location At Kickoff Point".

    The clearance points carry a ``Conc`` and all four section-line footages
    per station, so we read the station nearest ``kop_md`` and return the same
    ``(conc, {fnl,fsl,fel,fwl,qq})`` shape :func:`apd_summary_footages`
    produces. Returns ``None`` when there's no usable survey/MD.
    """
    if points is None or getattr(points, "empty", True) or kop_md is None:
        return None
    if "measured_depth" not in points or "Conc" not in points:
        return None
    try:
        idx = (points["measured_depth"] - float(kop_md)).abs().idxmin()
    except (TypeError, ValueError):
        return None
    row = points.loc[idx]
    conc = row.get("Conc")
    if not isinstance(conc, str) or len(conc) < 9:
        return None
    fnl = _coerce_float(row.get("FNL"))
    fsl = _coerce_float(row.get("FSL"))
    fel = _coerce_float(row.get("FEL"))
    fwl = _coerce_float(row.get("FWL"))
    pair = _nearest_footage_pair(fnl, fsl, fel, fwl)
    if all(v is None for v in pair.values()):
        return None
    pair["qq"] = quarter_quarter(fnl, fsl, fel, fwl)
    return (conc, pair)


def _nearest_footage_pair(fnl, fsl, fel, fwl) -> dict:
    """Collapse all-four footages to one N/S + one E/W (the PLSS convention).

    Clearance data carries the distance from *every* section line for each
    point (FNL and FSL and FEL and FWL all populated), but a PLSS call —
    and ``footages_to_xy`` — references exactly one north/south line and
    one east/west line. Pick the nearer of each (smaller distance), which
    is how a surveyor states the location and keeps the point closest to
    its reference line for irregular sections.
    """
    out = {"fnl": None, "fsl": None, "fel": None, "fwl": None}
    if fnl is not None and fsl is not None:
        out["fnl" if fnl <= fsl else "fsl"] = fnl if fnl <= fsl else fsl
    elif fnl is not None:
        out["fnl"] = fnl
    elif fsl is not None:
        out["fsl"] = fsl
    if fel is not None and fwl is not None:
        out["fel" if fel <= fwl else "fwl"] = fel if fel <= fwl else fwl
    elif fel is not None:
        out["fel"] = fel
    elif fwl is not None:
        out["fwl"] = fwl
    return out


# APD location-row name → friendly label for the three named sections.
_APD_SECTION_LABELS = {
    "location at surface": "Surface (SHL)",
    "top of uppermost producing zone": "Top of Producing Zone",
    "at total depth": "Total Depth",
}


def build_section_traversal(locations, clearance_points=None) -> "list[SectionCrossing]":
    """Ordered PLSS sections the wellbore crosses — one source of truth.

    Shared by the Casing Review SHL/BHL section sub-tabs **and** the Excel
    generator so the on-screen *BHL Section N* always matches the *BHL
    Section N* sheet in the output workbook.

    Order of preference:

    1. ``clearance_points`` — the processed-survey DataFrame carrying a
       ``Conc`` per station (plus FNL/FSL/FEL/FWL). First occurrence of
       each Conc gives the section-entry footages, in MD order. This is
       authoritative for a horizontal lateral that crosses several
       sections.
    2. Fallback to the APD's ``locations`` rows when no clearance data is
       available (well not yet promoted / no geometry).

    For any section that *also* has an APD location row (surface,
    producing zone, TD), the APD footages win — they're the regulator's
    stated values — and the row keeps its familiar label. Auto-detected
    intermediate sections are labelled ``"Intermediate — <conc>"``.

    ``locations`` is ``APDPdfData.locations``; ``clearance_points`` is a
    ``ClearanceResult.points`` DataFrame (or ``None``). Imported lazily by
    callers to avoid a hard dependency on pandas here.
    """
    from etools.core.casing_review.footages import location_footages

    # conc → (apd_row, label) for any section the APD names directly.
    # ``setdefault`` keeps the FIRST row for a section — the APD lists
    # Surface before Producing/TD, so when several share one section (a
    # short lateral) the section keeps its Surface identity instead of
    # being relabelled by a later row.
    apd_by_conc: dict[str, tuple[object, str]] = {}
    for L in locations or []:
        key = PLSSKey.from_location(L)
        if key is None:
            continue
        label = _APD_SECTION_LABELS.get((L.name or "").lower(), L.name or "")
        apd_by_conc.setdefault(key.conc, (L, label))

    # First-occurrence-per-Conc traversal, ordered by the measured depth at
    # which the wellbore ENTERS each section. Sorting by MD first makes the
    # order strictly sequential down the hole (surface section first, TD
    # section last) and immune to however the points DataFrame is ordered.
    traversal: list[tuple[str, dict]] = []
    seen: set[str] = set()
    if (
        clearance_points is not None
        and not clearance_points.empty
        and "Conc" in clearance_points
    ):
        ordered = clearance_points
        for cand in ("measured_depth", "MeasuredDepth", "MD", "md"):
            if cand in clearance_points:
                ordered = clearance_points.sort_values(cand, kind="stable")
                break

        # One sheet per UNIQUE section the wellbore passes through, in
        # first-entry (MD) order — exactly the legacy ``Conc.unique()``
        # behaviour. Every distinct section gets a sheet (including a
        # short detour into a neighbouring township-line section, e.g.
        # 5 -> 32 -> 5 -> 8 yields 5, 32, 8); only *re-entries* of an
        # already-seen section are skipped, never a new section.
        for _, row in ordered.iterrows():
            conc = row.get("Conc")
            # Skip blanks, dups, and anything that isn't a well-formed
            # 9-char Conc — a malformed value would later blow up
            # ``to_location_row`` (PLSSKey.from_conc) and abort generation.
            if not isinstance(conc, str) or len(conc) < 9 or conc in seen:
                continue
            try:
                PLSSKey.from_conc(conc)
            except (ValueError, IndexError):
                continue
            seen.add(conc)
            # Clearance carries all four footages per point; collapse to the
            # nearest N/S + E/W so footages_to_xy (which wants exactly one
            # of each) can place the point. Without this, every
            # clearance-sourced intermediate section fails UTM and the sheet
            # comes up empty.
            traversal.append(
                (
                    conc,
                    _nearest_footage_pair(
                        _coerce_float(row.get("FNL")),
                        _coerce_float(row.get("FSL")),
                        _coerce_float(row.get("FEL")),
                        _coerce_float(row.get("FWL")),
                    ),
                )
            )

    if not traversal:  # fallback: APD location rows
        for L in locations or []:
            key = PLSSKey.from_location(L)
            if key is None or key.conc in seen:
                continue
            seen.add(key.conc)
            fnl, fsl, fel, fwl = location_footages(L)
            traversal.append(
                (key.conc, {"fnl": fnl, "fsl": fsl, "fel": fel, "fwl": fwl})
            )

    crossings: list[SectionCrossing] = []
    for conc, fps in traversal:
        if conc in apd_by_conc:
            L, label = apd_by_conc[conc]
            fnl, fsl, fel, fwl = location_footages(L)
            crossings.append(
                SectionCrossing(
                    conc=conc,
                    fnl=fnl,
                    fsl=fsl,
                    fel=fel,
                    fwl=fwl,
                    label=f"{label} — {conc}" if label else f"Section {conc}",
                    apd_name=getattr(L, "name", None),
                )
            )
        else:
            crossings.append(
                SectionCrossing(conc=conc, label=f"Intermediate — {conc}", **fps)
            )
    return crossings


def dx_survey_path_offsets(
    points, *, kop_md=None, landing_md=None, td_md=None
) -> "list[tuple[float | None, float | None, float | None]]":
    """Return the (md, n_offset, e_offset) rows DxSurvey 8-10 need.

    The Casing Review template walks the wellbore through PLSS sections
    using three reference stations — K.O. Point, Prod. Interval, Total
    Depth — stored in ``DxSurvey`` rows 8/9/10. Each is the survey's
    north/east offset (feet; N+/S-, E+/W-) at that measured depth, which is
    what the BHL Section sheets' section-detection reads. Without these the
    detection runs on zeros and the BHL bearing grids come up blank.

    ``points`` is a processed-survey / clearance DataFrame carrying
    ``measured_depth``, ``n_offset`` and ``e_offset``. ``td_md`` defaults
    to the deepest station. Any station whose MD is unknown yields ``None``
    (the writer skips it, leaving the template default).
    """
    if points is None or getattr(points, "empty", True):
        return []
    md_col = "measured_depth"
    if md_col not in points or "n_offset" not in points or "e_offset" not in points:
        return []
    if td_md is None:
        td_md = float(points[md_col].iloc[-1])

    def _at(md):
        if md is None:
            return None
        try:
            idx = (points[md_col] - float(md)).abs().idxmin()
        except (TypeError, ValueError):
            return None
        row = points.loc[idx]
        return (
            _coerce_float(row.get(md_col)),
            _coerce_float(row.get("n_offset")),
            _coerce_float(row.get("e_offset")),
        )

    return [_at(kop_md), _at(landing_md), _at(td_md)]


def apd_summary_footages(locations) -> "list[tuple[str, dict] | None]":
    """Return ``(conc, {fnl,fsl,fel,fwl})`` for the KOP / Prod-Interval / TD rows.

    The section sheets' "Section Line Footages" (I/K columns of the
    KOP/Prod-Interval/Total-Depth rows) are natively computed by a survey-path
    walk against the PLSS boundaries — the SAME unreliable detection that
    blanks out the **final (Total Depth) footages** on cross-township wells.

    The legacy Casing Reviews instead show the regulator's STATED footages
    straight off the APD (Form 3, Section 20): the producing-zone row carries
    "Top of Uppermost Producing Zone" and the Total-Depth row carries "At
    Total Depth". Those are authoritative (the well was permitted to them) and
    don't drift with whichever survey revision is on hand, so the final
    footages match the originals. We return them keyed by ``conc`` so the
    writer can place each on the matching section sheet (and the SHL summary).

    KOP has no APD-stated footage, so it stays ``None`` (template default).
    Returns ``[]`` when no usable APD locations are present.
    """
    from etools.core.casing_review.footages import location_footages

    by_name: dict[str, object] = {}
    for L in locations or []:
        by_name.setdefault((getattr(L, "name", "") or "").lower(), L)
    if not by_name:
        return []

    def _mk(name: str):
        L = by_name.get(name)
        if L is None:
            return None
        key = PLSSKey.from_location(L)
        if key is None:
            return None
        fnl, fsl, fel, fwl = location_footages(L)
        if (fnl is None and fsl is None) and (fel is None and fwl is None):
            return None
        return (
            key.conc,
            {
                "fnl": fnl,
                "fsl": fsl,
                "fel": fel,
                "fwl": fwl,
                # The APD prints the quarter-quarter directly — authoritative.
                "qq": getattr(L, "qtr_qtr", None),
            },
        )

    return [
        # KOP — the APD prints a "Location At Kickoff Point" row (with its own
        # footages) on directional permits; older forms omit it, leaving the
        # template default.
        _mk("location at kickoff point"),
        _mk("top of uppermost producing zone"),
        _mk("at total depth"),
    ]


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

# Canonical clockwise traversal starting at NW corner. Each segment is one
# quarter-side of the section (~1320 ft on a regular section), so 16 of them
# trace the full mile-square boundary.
SIDE_ORDER: tuple[str, ...] = (
    # North boundary — NW corner east to NE corner
    "North-Left2",
    "North-Left1",
    "North-Right1",
    "North-Right2",
    # East boundary — NE corner south to SE corner
    "East-Up2",
    "East-Up1",
    "East-Down1",
    "East-Down2",
    # South boundary — SE corner west to SW corner
    "South-Right2",
    "South-Right1",
    "South-Left1",
    "South-Left2",
    # West boundary — SW corner north to NW corner
    "West-Down2",
    "West-Down1",
    "West-Up1",
    "West-Up2",
)

# Side -> outward-pointing cardinal bearing (deg, clockwise from north) for
# the *travel* direction along that segment. Used as the "natural" bearing
# the Grid Numbers DMS reading should resolve to in absence of alignment
# corrections — i.e. North-* segments travel east (90°), East-* segments
# travel south (180°), etc.
_TRAVEL_BEARING_DEG: dict[str, float] = {
    "North-Left2": 90.0,
    "North-Left1": 90.0,
    "North-Right1": 90.0,
    "North-Right2": 90.0,
    "East-Up2": 180.0,
    "East-Up1": 180.0,
    "East-Down1": 180.0,
    "East-Down2": 180.0,
    "South-Right2": 270.0,
    "South-Right1": 270.0,
    "South-Left1": 270.0,
    "South-Left2": 270.0,
    "West-Down2": 0.0,
    "West-Down1": 0.0,
    "West-Up1": 0.0,
    "West-Up2": 0.0,
}


# Outer corner names (the 4 section corners + 4 quarter-corner midpoints).
CORNER_NAMES: tuple[str, ...] = (
    "NW_SC",  # Section Corner
    "N_QC",   # Quarter Corner (midpoint of N boundary)
    "NE_SC",
    "E_QC",
    "SE_SC",
    "S_QC",
    "SW_SC",
    "W_QC",
)


@dataclass
class SegmentData:
    """One row of the Grid Numbers DB — a single quarter-side of a section."""

    length_ft: float | None = None
    degrees: int | None = None
    minutes: int | None = None
    seconds: int | None = None
    alignment: int | None = None
    north_ref: str | None = None  # "T"=True, "G"=Grid

    @property
    def bearing_dms_deg(self) -> float | None:
        """Bearing as a decimal-degree value of the raw DMS reading.

        This is *not* the travel direction along the segment — alignment
        and the side's natural orientation determine that. This is just
        the (deg + min/60 + sec/3600) magnitude.
        """
        if self.degrees is None:
            return None
        return self.degrees + (self.minutes or 0) / 60.0 + (self.seconds or 0) / 3600.0

    def is_blank(self) -> bool:
        return all(
            v is None or v == 0
            for v in (self.length_ft, self.degrees, self.minutes, self.seconds)
        )


# ---------------------------------------------------------------------------
# SectionDefinition
# ---------------------------------------------------------------------------


@dataclass
class SectionDefinition:
    """Authoritative model for one PLSS section.

    ``segments`` carries the default per-segment data sourced from
    ``grid_numbers.sqlite`` (16 entries, keyed by the names in
    :data:`SIDE_ORDER`). ``segment_overrides`` holds user-entered values
    that win when present.

    ``corner_overrides`` allows direct edits to the 8 named corner points
    (UTM Easting/Northing) — used when the user knows the surveyed corner
    coordinates and wants to override the polygon shape directly without
    going through the segment-walk math.

    ``plat_polygon`` is the raw polygon from ``PlatRepository`` used as a
    no-override fallback (and as the source of ``anchor_utm``).

    ``north_ref_choice`` selects the survey north reference for any
    bearing math the consumer does ("T" / "G" / "M").

    Use :meth:`effective_segment` and :meth:`resolve_polygon` to read.
    """

    plss: PLSSKey
    segments: dict[str, SegmentData] = field(default_factory=dict)
    segment_overrides: dict[str, SegmentData] = field(default_factory=dict)
    corner_overrides: dict[str, tuple[float, float] | None] = field(
        default_factory=lambda: {name: None for name in CORNER_NAMES}
    )
    anchor_utm: tuple[float, float] | None = None
    plat_polygon: BaseGeometry | None = None
    north_ref_choice: str = "T"
    convergence_deg: float | None = None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def effective_segment(self, key: str) -> SegmentData:
        """Return the override if present and non-blank, otherwise the default."""
        ov = self.segment_overrides.get(key)
        if ov is not None and not ov.is_blank():
            return ov
        return self.segments.get(key, SegmentData())

    def has_overrides(self) -> bool:
        if any(
            ov is not None and not ov.is_blank()
            for ov in self.segment_overrides.values()
        ):
            return True
        if any(v is not None for v in self.corner_overrides.values()):
            return True
        return False

    def resolve_corners(self) -> dict[str, tuple[float, float]]:
        """Return UTM coordinates for each of the 8 named corners.

        With no overrides set we read corner points off ``plat_polygon``'s
        bounds (cardinally aligned approximation). With segment overrides
        in play we walk the boundary from ``anchor_utm`` to derive the
        4 section corners + 4 quarter corners.

        ``corner_overrides`` always wins, applied last.
        """
        corners = (
            self._walk_corners()
            if self._needs_walk()
            else self._bbox_corners()
        )
        for name, override in self.corner_overrides.items():
            if override is not None:
                corners[name] = override
        return corners

    def resolve_polygon(self) -> Polygon:
        """Return the section polygon, honoring overrides.

        Closes back to NW corner so the returned ring is valid.
        """
        if not self.has_overrides() and self.plat_polygon is not None:
            return self.plat_polygon
        corners = self.resolve_corners()
        ring = [
            corners["NW_SC"],
            corners["N_QC"],
            corners["NE_SC"],
            corners["E_QC"],
            corners["SE_SC"],
            corners["S_QC"],
            corners["SW_SC"],
            corners["W_QC"],
            corners["NW_SC"],
        ]
        poly = Polygon(ring)
        if not poly.is_valid:
            repaired = poly.buffer(0)
            # buffer(0) is a repair trick, not a guarantee: on a
            # self-intersecting or zero-length ring it returns an EMPTY
            # geometry whose .bounds is (nan, nan, nan, nan). That unpacks
            # without complaint, so letting it through produced NaN footages
            # in the section sheets with no error raised anywhere.
            if repaired.is_empty:
                raise DegenerateGeometryError(
                    "Section geometry collapsed while being repaired - the "
                    "segment overrides do not describe a closed section."
                )
            log.warning(
                "section.polygon_repaired",
                area_before=poly.area,
                area_after=repaired.area,
            )
            poly = repaired
        return poly

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _needs_walk(self) -> bool:
        """Walk only when we have segment overrides (corner overrides are
        applied on top of the bbox result so they don't need a walk)."""
        return any(
            ov is not None and not ov.is_blank()
            for ov in self.segment_overrides.values()
        )

    def _bbox_corners(self) -> dict[str, tuple[float, float]]:
        """Cardinally-aligned corner derivation from the plat polygon's bbox.

        Exact for regular sections (~95% of Utah). Sections with meander
        corrections will have a residual error here that the segment-walk
        path can correct once overrides flow in.
        """
        if self.plat_polygon is None:
            raise ValueError("No plat_polygon to derive corners from")
        minx, miny, maxx, maxy = _checked_bounds(self.plat_polygon)
        midx = (minx + maxx) / 2.0
        midy = (miny + maxy) / 2.0
        return {
            "NW_SC": (minx, maxy),
            "N_QC": (midx, maxy),
            "NE_SC": (maxx, maxy),
            "E_QC": (maxx, midy),
            "SE_SC": (maxx, miny),
            "S_QC": (midx, miny),
            "SW_SC": (minx, miny),
            "W_QC": (minx, midy),
        }

    def walk_segment_endpoints(self) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
        """Walk the 16 boundary segments from the anchor (NW corner) in
        clockwise order, returning ``(segment_key, start_xy, end_xy)`` for
        each. The final segment's end_xy is the walked closure point — it
        will equal the start anchor only if the segment lengths happen to
        close. Use this in renderers that want to *show* open polygons
        when the user breaks closure with overrides.
        """
        anchor = self._bbox_corners()["NW_SC"] if self.anchor_utm is None else self.anchor_utm
        x, y = anchor
        out: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
        ft_to_m = 0.3048
        for key in SIDE_ORDER:
            seg = self.effective_segment(key)
            length_m = (seg.length_ft or 0.0) * ft_to_m
            travel_rad = math.radians(_TRAVEL_BEARING_DEG[key])
            dx = math.sin(travel_rad) * length_m
            dy = math.cos(travel_rad) * length_m
            nx, ny = x + dx, y + dy
            out.append((key, (x, y), (nx, ny)))
            x, y = nx, ny
        return out

    def _walk_corners(self) -> dict[str, tuple[float, float]]:
        """Segment-walk corner derivation. Starts at NW corner taken from
        the bbox approximation and walks clockwise through all 16 segments.

        The four segment lengths along each cardinal side are summed and
        applied along the side's nominal cardinal bearing (north sides
        travel east at 90°, etc.). DMS bearings from the Grid Numbers DB
        are used as small perpendicular corrections — meander offsets —
        rather than full direction overrides. This keeps the walk stable
        even when one segment has a partial override applied.
        """
        anchor = self._bbox_corners()["NW_SC"] if self.anchor_utm is None else self.anchor_utm
        x, y = anchor
        corners: dict[str, tuple[float, float]] = {"NW_SC": (x, y)}

        # Group the 16 sides into the 4 cardinal boundaries (clockwise).
        sides_by_boundary = [
            ("N", SIDE_ORDER[0:4],   "N_QC", "NE_SC"),
            ("E", SIDE_ORDER[4:8],   "E_QC", "SE_SC"),
            ("S", SIDE_ORDER[8:12],  "S_QC", "SW_SC"),
            ("W", SIDE_ORDER[12:16], "W_QC", "NW_SC"),
        ]

        for direction, side_keys, qc_name, end_corner_name in sides_by_boundary:
            # Sum the 4 segment lengths along this boundary, and capture
            # the quarter-corner position after the first 2 segments.
            segment_lengths = [self.effective_segment(k).length_ft or 0.0 for k in side_keys]
            # Travel bearing (degrees clockwise from north) for this boundary.
            travel_deg = _TRAVEL_BEARING_DEG[side_keys[0]]
            travel_rad = math.radians(travel_deg)
            dx_unit = math.sin(travel_rad)
            dy_unit = math.cos(travel_rad)
            # Convert length_ft → meters for UTM (1 ft = 0.3048 m).
            ft_to_m = 0.3048
            # Quarter corner is at segments 1+2.
            half_length_m = (segment_lengths[0] + segment_lengths[1]) * ft_to_m
            full_length_m = sum(segment_lengths) * ft_to_m
            corners[qc_name] = (x + dx_unit * half_length_m, y + dy_unit * half_length_m)
            x = x + dx_unit * full_length_m
            y = y + dy_unit * full_length_m
            if end_corner_name != "NW_SC":  # already set
                corners[end_corner_name] = (x, y)

        return corners

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls, plss: PLSSKey) -> "SectionDefinition":
        return cls(
            plss=plss,
            segments={key: SegmentData() for key in SIDE_ORDER},
            segment_overrides={},
            corner_overrides={name: None for name in CORNER_NAMES},
        )

    # ------------------------------------------------------------------
    # Coordinate sync helpers — keep footages / UTM / lat-lon in lockstep
    # ------------------------------------------------------------------

    def footages_to_latlon(
        self,
        *,
        fnl: float | None = None,
        fsl: float | None = None,
        fel: float | None = None,
        fwl: float | None = None,
    ) -> "CoordSyncResult":
        """Resolve a location given footages → full (utm, latlon) triple."""
        from etools.core.casing_review.footages import (
            footages_to_xy,
            polygon_footages,
        )
        from etools.core.coordinates import utm_to_latlon

        polygon = self.resolve_polygon()
        x, y = footages_to_xy(polygon, fnl=fnl, fsl=fsl, fel=fel, fwl=fwl)
        lat, lon = utm_to_latlon(x, y, 12, "N")
        rt = polygon_footages(polygon, (x, y))
        return CoordSyncResult(
            fnl=rt.fnl, fsl=rt.fsl, fel=rt.fel, fwl=rt.fwl,
            utm_easting=x, utm_northing=y, utm_zone=12, utm_letter="N",
            lat=lat, lon=lon,
        )

    def latlon_to_footages(self, lat: float, lon: float) -> "CoordSyncResult":
        """Resolve a location given lat/lon → full coord triple."""
        from etools.core.casing_review.footages import polygon_footages
        from etools.core.coordinates import latlon_to_utm

        polygon = self.resolve_polygon()
        x, y, zone, letter = latlon_to_utm(lat, lon)
        rt = polygon_footages(polygon, (x, y))
        return CoordSyncResult(
            fnl=rt.fnl, fsl=rt.fsl, fel=rt.fel, fwl=rt.fwl,
            utm_easting=x, utm_northing=y, utm_zone=zone, utm_letter=letter,
            lat=lat, lon=lon,
        )

    def utm_to_footages(
        self, easting: float, northing: float, *, zone: int = 12, letter: str = "N",
    ) -> "CoordSyncResult":
        """Resolve a location given UTM E/N → full coord triple."""
        from etools.core.casing_review.footages import polygon_footages
        from etools.core.coordinates import utm_to_latlon

        polygon = self.resolve_polygon()
        rt = polygon_footages(polygon, (easting, northing))
        lat, lon = utm_to_latlon(easting, northing, zone, letter)
        return CoordSyncResult(
            fnl=rt.fnl, fsl=rt.fsl, fel=rt.fel, fwl=rt.fwl,
            utm_easting=easting, utm_northing=northing, utm_zone=zone, utm_letter=letter,
            lat=lat, lon=lon,
        )


@dataclass
class CoordSyncResult:
    """A single point expressed in all three coordinate frames.

    Footages are full-bbox values (both FNL and FSL populated, both FEL
    and FWL populated) so a UI can show whichever direction the user
    selected via radio button.
    """

    fnl: float
    fsl: float
    fel: float
    fwl: float
    utm_easting: float
    utm_northing: float
    utm_zone: int
    utm_letter: str
    lat: float
    lon: float


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def build_section_definition(
    *,
    plss: PLSSKey,
    catalog,
    plat_polygon: BaseGeometry | None = None,
) -> SectionDefinition:
    """Construct a SectionDefinition for ``plss`` from the Grid Numbers DB.

    Pass a :class:`GridCornerCatalog` and (optionally) the raw plat polygon
    sourced via :class:`PlatRepository` — the polygon is held as the
    no-override fallback and as the anchor source. If the plat polygon is
    omitted, ``anchor_utm`` is left as ``None`` and a segment-walk will
    fail until the caller supplies an anchor.

    Sections not present in the Grid Numbers DB get an empty SectionDefinition
    (16 blank segments) that consumers can still write overrides into.
    """
    section_def = SectionDefinition.empty(plss)
    if plat_polygon is not None:
        section_def.plat_polygon = plat_polygon
        minx, _, _, maxy = plat_polygon.bounds
        section_def.anchor_utm = (minx, maxy)  # NW corner anchor

    rows = catalog.section_corners(
        section=plss.section,
        township=plss.township,
        township_dir=plss.township_dir,
        range_=plss.range_,
        range_dir=plss.range_dir,
        baseline=plss.baseline,
    )
    for row in rows:
        if row.side not in section_def.segments:
            continue
        section_def.segments[row.side] = SegmentData(
            length_ft=row.length_ft,
            degrees=row.degrees,
            minutes=row.minutes,
            seconds=row.seconds,
            alignment=row.alignment,
            north_ref=row.north_ref,
        )
    return section_def


def build_section_definitions(
    *,
    concs: Iterable[str],
    catalog,
    plat_repo,
) -> dict[str, SectionDefinition]:
    """Bulk-build SectionDefinitions for ``concs`` from the plat + Grid Numbers DBs."""
    conc_list = list(concs)
    if not conc_list:
        return {}
    base_df = plat_repo._fetch_concs(conc_list)  # noqa: SLF001 — direct lookup
    sections_gdf = plat_repo._build_sections(base_df) if not base_df.empty else None  # noqa: SLF001
    polygon_by_conc: dict[str, BaseGeometry] = {}
    if sections_gdf is not None and not sections_gdf.empty:
        for _, row in sections_gdf.iterrows():
            polygon_by_conc[row["Conc"]] = row["geometry"]

    out: dict[str, SectionDefinition] = {}
    for conc in conc_list:
        try:
            plss = PLSSKey.from_conc(conc)
        except ValueError:
            continue
        out[conc] = build_section_definition(
            plss=plss,
            catalog=catalog,
            plat_polygon=polygon_by_conc.get(conc),
        )
    return out
