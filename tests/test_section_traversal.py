"""Section-traversal tests — guards the BHL Section 2 regression.

The on-screen SHL/BHL section sub-tabs and the Excel generator must agree
on which PLSS section maps to which sheet. Both now derive that mapping
from :func:`build_section_traversal`; these tests lock the ordering, the
APD-vs-clearance footage precedence, and the PLSS round-trip the writer
relies on.
"""

from __future__ import annotations

import pandas as pd

from etools.core.casing_review.sections import (
    PLSSKey,
    _nearest_footage_pair,
    build_section_traversal,
)
from etools.models import APDLocationRow


def _loc(name: str, sec: str, **foot) -> APDLocationRow:
    return APDLocationRow(
        name=name,
        section=sec,
        township="3",
        township_dir="S",
        range="2",
        range_dir="W",
        meridian="U",
        **foot,
    )


def _apd_three() -> list[APDLocationRow]:
    return [
        _loc("Location at Surface", "23", fnl=660, fel=1980),
        _loc("Top of Uppermost Producing Zone", "26", fnl=300, fel=900),
        _loc("At Total Depth", "35", fsl=250, fel=800),
    ]


def test_clearance_traversal_orders_sheets_by_md_and_fills_intermediate() -> None:
    """A lateral crossing an un-named section still yields a BHL sheet."""
    pts = pd.DataFrame(
        [
            {"Conc": "2303S02WU", "FNL": 660, "FSL": None, "FEL": 1980, "FWL": None},
            {"Conc": "2303S02WU", "FNL": 700, "FSL": None, "FEL": 2000, "FWL": None},
            {"Conc": "2403S02WU", "FNL": 1320, "FSL": None, "FEL": 50, "FWL": None},
            {"Conc": "2603S02WU", "FNL": 300, "FSL": None, "FEL": 900, "FWL": None},
            {"Conc": "3503S02WU", "FNL": None, "FSL": 250, "FEL": 800, "FWL": None},
        ]
    )
    crossings = build_section_traversal(_apd_three(), pts)

    # 4 sections crossed → SHL + BHL 1/2/3.
    assert [c.conc for c in crossings] == [
        "2303S02WU",
        "2403S02WU",
        "2603S02WU",
        "3503S02WU",
    ]
    # The previously-blank BHL Section 2 (index 2) is the producing zone.
    bhl2 = crossings[2]
    assert "Producing" in bhl2.label
    assert (bhl2.fnl, bhl2.fel) == (300, 900)  # APD footages win
    # The auto-detected intermediate (index 1) carries clearance footages.
    intermediate = crossings[1]
    assert intermediate.label.startswith("Intermediate")
    assert (intermediate.fnl, intermediate.fel) == (1320, 50)


def test_dup_conc_collapses_to_first_occurrence() -> None:
    pts = pd.DataFrame(
        [
            {"Conc": "2303S02WU", "FNL": 660, "FSL": None, "FEL": 1980, "FWL": None},
            {"Conc": "2303S02WU", "FNL": 700, "FSL": None, "FEL": 2000, "FWL": None},
        ]
    )
    crossings = build_section_traversal(_apd_three(), pts)
    assert len(crossings) == 1
    assert crossings[0].conc == "2303S02WU"


def test_fallback_to_apd_locations_without_clearance() -> None:
    crossings = build_section_traversal(_apd_three(), None)
    assert [c.conc for c in crossings] == ["2303S02WU", "2603S02WU", "3503S02WU"]
    assert all(c.apd_name for c in crossings)  # every one is an APD-named row


def test_to_location_row_round_trips_plss_and_footages() -> None:
    pts = pd.DataFrame(
        [{"Conc": "2403S02WU", "FNL": 1320, "FSL": None, "FEL": 50, "FWL": None}]
    )
    (crossing,) = build_section_traversal([], pts)
    row = crossing.to_location_row()
    assert PLSSKey.from_location(row).conc == "2403S02WU"
    assert row.fnl == 1320 and row.fel == 50
    # PLSS string components the writer reads off the row.
    assert row.section == "24" and row.township == "3"
    assert row.township_dir == "S" and row.range_dir == "W" and row.meridian == "U"


def test_empty_inputs_yield_no_crossings() -> None:
    assert build_section_traversal([], None) == []
    assert build_section_traversal(None, pd.DataFrame()) == []


def test_surface_and_producing_in_one_section_keeps_surface_identity() -> None:
    """Short lateral: surface + producing share a section. The SHL slot must
    keep the Surface label and Surface footages, not be relabelled by the
    later producing-zone row."""
    locs = [
        _loc("Location at Surface", "5", fnl=564, fwl=1032),
        _loc("Top of Uppermost Producing Zone", "5", fnl=330, fwl=2282),
        _loc("At Total Depth", "8", fsl=330, fwl=2630),
    ]
    # _loc builds T3S R2W U, so the matching Concs are S02W.
    pts = pd.DataFrame(
        [
            {"Conc": "0503S02WU", "FNL": 566, "FSL": None, "FEL": None, "FWL": 1034},
            {"Conc": "0803S02WU", "FNL": None, "FSL": 29, "FEL": None, "FWL": 2714},
        ]
    )
    crossings = build_section_traversal(locs, pts)
    shl = crossings[0]
    assert shl.conc == "0503S02WU"
    assert "Surface" in shl.label
    assert (shl.fnl, shl.fwl) == (564, 1032)  # surface, not producing (330/2282)


def test_nearest_footage_pair_collapses_all_four() -> None:
    """Clearance gives all four footages; we keep the nearer N/S and E/W."""
    # FNL closer than FSL; FWL closer than FEL.
    out = _nearest_footage_pair(fnl=200, fsl=5080, fel=4000, fwl=1280)
    assert out == {"fnl": 200, "fsl": None, "fel": None, "fwl": 1280}
    # FSL closer than FNL; FEL closer than FWL.
    out = _nearest_footage_pair(fnl=5000, fsl=300, fel=900, fwl=4380)
    assert out == {"fnl": None, "fsl": 300, "fel": 900, "fwl": None}
    # Partial input is preserved as-is.
    assert _nearest_footage_pair(660, None, None, 1980) == {
        "fnl": 660, "fsl": None, "fel": None, "fwl": 1980
    }


def test_intermediate_crossing_has_exactly_one_ns_and_ew() -> None:
    """An intermediate section sourced from clearance must end up with one
    N/S and one E/W footage so footages_to_xy can place it (regression for
    'Supply exactly one of fnl / fsl')."""
    pts = pd.DataFrame(
        [
            # All four populated, as clearance always emits.
            {"Conc": "1703S02WU", "FNL": 200, "FSL": 5080, "FEL": 4000, "FWL": 1280},
        ]
    )
    (crossing,) = build_section_traversal([], pts)
    ns = [v for v in (crossing.fnl, crossing.fsl) if v is not None]
    ew = [v for v in (crossing.fel, crossing.fwl) if v is not None]
    assert len(ns) == 1 and len(ew) == 1
    assert crossing.fnl == 200 and crossing.fwl == 1280  # the nearer lines


def test_malformed_clearance_conc_is_skipped() -> None:
    pts = pd.DataFrame(
        [
            {"Conc": "0503S01EU", "FNL": 1, "FSL": None, "FEL": None, "FWL": 2},
            {"Conc": "BOGUS", "FNL": 1, "FSL": None, "FEL": None, "FWL": 2},
            {"Conc": None, "FNL": 1, "FSL": None, "FEL": None, "FWL": 2},
        ]
    )
    crossings = build_section_traversal([], pts)
    assert [c.conc for c in crossings] == ["0503S01EU"]
    # And every survivor round-trips (no crash building writer rows).
    assert all(c.to_location_row() is not None for c in crossings)
