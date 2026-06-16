"""Ad-hoc stress harness — throws nasty inputs at the core logic and the
survey pipeline, reporting every uncaught exception. Not a pytest file;
run with `.venv/Scripts/python.exe scripts/stress_test.py`.
"""
from __future__ import annotations

import traceback

import numpy as np
import pandas as pd

PASS, FAIL = [], []


def check(name, fn, *, expect_raise=False):
    """Run fn(); record whether it raised. expect_raise=True means a raise is the PASS."""
    try:
        fn()
        if expect_raise:
            FAIL.append(f"{name}: expected an exception, got none")
        else:
            PASS.append(name)
    except Exception as e:  # noqa: BLE001
        if expect_raise:
            PASS.append(f"{name} (raised {type(e).__name__} as expected)")
        else:
            tb = traceback.format_exc().strip().splitlines()
            FAIL.append(f"{name}: {type(e).__name__}: {e}\n      " + "\n      ".join(tb[-3:]))


# ---------------------------------------------------------------- edits.py
def stress_edits():
    from etools.core.survey.edits import (
        delete_station,
        displayed_to_native_azimuth,
        insert_station,
        interpolate_raw_station,
        update_station,
    )

    def raw():
        return pd.DataFrame(
            {"MeasuredDepth": [0.0, 100.0, 200.0, 300.0],
             "Inclination": [0.0, 10.0, 30.0, 90.0],
             "Azimuth": [0.0, 350.0, 10.0, 20.0]}
        )

    one = pd.DataFrame({"MeasuredDepth": [0.0], "Inclination": [0.0], "Azimuth": [0.0]})
    empty = pd.DataFrame({"MeasuredDepth": [], "Inclination": [], "Azimuth": []})

    check("edits.interp empty raises", lambda: interpolate_raw_station(empty, 50), expect_raise=True)
    check("edits.interp single station", lambda: interpolate_raw_station(one, 50))
    check("edits.interp negative md", lambda: interpolate_raw_station(raw(), -100))
    check("edits.interp huge md", lambda: interpolate_raw_station(raw(), 1e9))
    check("edits.interp NaN md raises", lambda: interpolate_raw_station(raw(), float("nan")), expect_raise=True)
    check("edits.interp inf md raises", lambda: interpolate_raw_station(raw(), float("inf")), expect_raise=True)
    check("edits.insert NaN md raises", lambda: insert_station(raw(), float("nan")), expect_raise=True)
    check("edits.delete NaN md raises", lambda: delete_station(raw(), float("nan")), expect_raise=True)
    check("edits.update NaN old_md raises", lambda: update_station(raw(), float("nan"), inclination=5), expect_raise=True)

    check("edits.insert basic", lambda: insert_station(raw(), 150))
    check("edits.insert at existing replaces", lambda: insert_station(raw(), 200, inclination=45))
    check("edits.insert negative md", lambda: insert_station(raw(), -50, inclination=5))
    check("edits.insert azimuth wrap >360", lambda: insert_station(raw(), 150, azimuth=400))
    check("edits.insert azimuth negative", lambda: insert_station(raw(), 150, azimuth=-30))
    check("edits.insert into empty", lambda: insert_station(empty, 150, inclination=5, azimuth=10), expect_raise=True)

    check("edits.update inc+azi", lambda: update_station(raw(), 200, inclination=33.3, azimuth=361))
    check("edits.update md to existing collapses", lambda: update_station(raw(), 100, md=200))
    check("edits.update missing md raises", lambda: update_station(raw(), 12345, inclination=1), expect_raise=True)
    check("edits.update empty raises", lambda: update_station(empty, 0, inclination=1), expect_raise=True)

    check("edits.delete basic", lambda: delete_station(raw(), 100))
    check("edits.delete missing raises", lambda: delete_station(raw(), 123), expect_raise=True)
    check("edits.delete empty raises", lambda: delete_station(empty, 0), expect_raise=True)

    check("edits.azi true/true", lambda: displayed_to_native_azimuth(90, displayed_frame="true", native_ref="true", convergence=1.5))
    check("edits.azi grid native None", lambda: displayed_to_native_azimuth(90, displayed_frame="grid", native_ref=None, convergence=1.5))
    check("edits.azi magnetic", lambda: displayed_to_native_azimuth(90, displayed_frame="true", native_ref="magnetic", convergence=1.5, declination=10))
    check("edits.azi negative wrap", lambda: displayed_to_native_azimuth(-30, displayed_frame="true", native_ref="grid", convergence=1.5))

    # Behavioral assertions (not just "didn't crash")
    out = update_station(raw(), 100, md=200)
    if out["MeasuredDepth"].duplicated().any():
        FAIL.append("edits.update md collision: PRODUCED DUPLICATE MD ROW (data hazard) -> " + str(list(out["MeasuredDepth"])))
    elif out.loc[out["MeasuredDepth"] == 200.0, "Inclination"].iloc[0] != 10.0:
        FAIL.append("edits.update md collision: kept the wrong station's INC")
    else:
        PASS.append("edits.update md collision keeps edited station, no dup")


# ---------------------------------------------------------------- processor.py
def stress_processor():
    from etools.core.survey.processor import interpolate_at_md, process_survey

    LAT, LON, ELEV = 40.27, -110.35, 5200.0

    def proc(df, **kw):
        return process_survey(
            df, surface_lat=LAT, surface_lon=LON, surface_elevation_ft=ELEV,
            north_reference="true", citing_type="Drilled", api="4301312345",
            lateral="0000", **kw,
        )

    vertical = pd.DataFrame({"MeasuredDepth": [0, 1000, 2000], "Inclination": [0, 0, 0], "Azimuth": [0, 0, 0]})
    build = pd.DataFrame({
        "MeasuredDepth": [0, 1000, 2000, 3000, 4000, 5000],
        "Inclination": [0, 2, 30, 60, 88, 90],
        "Azimuth": [0, 45, 90, 90, 92, 91],
    })
    one = pd.DataFrame({"MeasuredDepth": [0.0], "Inclination": [0.0], "Azimuth": [0.0]})
    two = pd.DataFrame({"MeasuredDepth": [0, 5000], "Inclination": [0, 90], "Azimuth": [0, 90]})
    nonzero_start = pd.DataFrame({"MeasuredDepth": [500, 1000], "Inclination": [5, 10], "Azimuth": [90, 90]})
    dupes = pd.DataFrame({"MeasuredDepth": [0, 100, 100, 200], "Inclination": [0, 5, 6, 10], "Azimuth": [0, 1, 2, 3]})
    empty = pd.DataFrame({"MeasuredDepth": [], "Inclination": [], "Azimuth": []})
    wrap = pd.DataFrame({"MeasuredDepth": [0, 100, 200], "Inclination": [0, 80, 90], "Azimuth": [355, 5, 358]})

    check("proc.vertical", lambda: proc(vertical))
    check("proc.build", lambda: proc(build))
    check("proc.single station raises cleanly", lambda: proc(one), expect_raise=True)
    check("proc.two stations", lambda: proc(two))
    check("proc.nonzero start (inserts MD0)", lambda: proc(nonzero_start))
    check("proc.duplicate MDs", lambda: proc(dupes))
    check("proc.empty raises", lambda: proc(empty), expect_raise=True)
    check("proc.azimuth wraparound", lambda: proc(wrap))
    check("proc.convergence override", lambda: proc(build, convergence_override=2.5))
    check("proc.convergence override zero", lambda: proc(build, convergence_override=0.0))

    # TVD must be 0 at MD0 and monotonic-ish for vertical
    res = proc(build)
    from etools.models import SurveyFrame
    pts = res[SurveyFrame.TRUE].points
    if abs(float(pts.iloc[0]["tvd"])) > 0.01:
        FAIL.append(f"proc.tvd: MD0 tvd is {pts.iloc[0]['tvd']} (expected ~0)")
    else:
        PASS.append("proc.tvd zero at MD0")
    if float(pts.iloc[-1]["tvd"]) <= 0:
        FAIL.append(f"proc.tvd: final tvd {pts.iloc[-1]['tvd']} not positive")
    else:
        PASS.append("proc.tvd positive at TD")

    # convergence override actually applied
    r2 = proc(build, convergence_override=7.0)
    conv = r2[SurveyFrame.TRUE].convergence_angle
    if abs(conv - 7.0) > 1e-6:
        FAIL.append(f"proc.convergence override not applied: got {conv}")
    else:
        PASS.append("proc.convergence override applied")

    # grid vs true azimuth differ by convergence
    rg = proc(build, convergence_override=5.0)
    at = float(rg[SurveyFrame.TRUE].points.iloc[-1]["azimuth"])
    ag = float(rg[SurveyFrame.GRID].points.iloc[-1]["azimuth"])
    if abs(((at - ag) % 360) - 5.0) > 0.5 and abs(((ag - at) % 360) - 5.0) > 0.5:
        FAIL.append(f"proc.frames: true {at} grid {ag} don't differ by ~5 convergence")
    else:
        PASS.append("proc.frames differ by convergence")

    check("interp_at_md empty raises", lambda: interpolate_at_md(empty, 50), expect_raise=True)
    check("interp_at_md clamp high", lambda: interpolate_at_md(pts, 1e9))
    check("interp_at_md clamp low", lambda: interpolate_at_md(pts, -50))
    check("interp_at_md midpoint", lambda: interpolate_at_md(pts, 2500))


# ---------------------------------------------------------------- coordinates
def stress_coords():
    from etools.core.coordinates.converter import (
        dms_to_decimal,
        grid_convergence,
        latlon_to_utm,
        parse_coord_pair,
    )

    check("dms empty raises", lambda: dms_to_decimal(""), expect_raise=True)
    check("dms whitespace raises", lambda: dms_to_decimal("   "), expect_raise=True)
    check("dms no number raises", lambda: dms_to_decimal("north"), expect_raise=True)
    check("dms decimal", lambda: dms_to_decimal("40.27"))
    check("dms dms+suffix", lambda: dms_to_decimal("40 16 12 N"))
    check("dms negative+W", lambda: dms_to_decimal("-110 21 W"))

    check("pair latlon", lambda: parse_coord_pair("40.27, -110.35"))
    check("pair utm", lambda: parse_coord_pair("555200, 4458447"))
    check("pair dms", lambda: parse_coord_pair("40 16 12 N, 110 21 0 W"))
    check("pair semicolon", lambda: parse_coord_pair("40.27; -110.35"))
    check("pair None raises", lambda: parse_coord_pair(None), expect_raise=True)
    check("pair empty raises", lambda: parse_coord_pair(""), expect_raise=True)
    check("pair one value raises", lambda: parse_coord_pair("40.27"), expect_raise=True)
    check("pair three values raises", lambda: parse_coord_pair("1,2,3"), expect_raise=True)

    check("grid_conv utah", lambda: grid_convergence(40.27, -110.35))
    check("grid_conv origin (0,0)", lambda: grid_convergence(0, 0))
    check("grid_conv south pole", lambda: grid_convergence(-89, 10))
    check("latlon_to_utm utah", lambda: latlon_to_utm(40.27, -110.35))

    # behavioral: dms negative+W should be negative
    v = dms_to_decimal("-110 21 W")
    if v >= 0:
        FAIL.append(f"dms negative+W: got {v}, expected negative")
    else:
        PASS.append("dms negative+W is negative")
    # round trip latlon->utm
    e, n, zn, zl = latlon_to_utm(40.27, -110.35)
    PASS.append(f"latlon_to_utm zone {zn}{zl}")


# ---------------------------------------------------------------- wcr generator
def stress_wcr_generator(tmpdir):
    from pathlib import Path

    from etools.core.wcr import generate_wcr_excel
    from etools.models import WCRLocationRow

    # Build a minimal WellInfo-like — inspect what generate_wcr_excel needs.
    from etools.models import WCRWellInfo  # may differ; resolved below

    def row(name, md, tvd):
        return WCRLocationRow(
            name=name, measured_depth=md, tvd=tvd, easting=555200.0, northing=4458447.0,
            fnl=1000.0, fsl=4280.0, fel=2000.0, fwl=3280.0,
            section="14", township="2", township_dir="S", range="5", range_dir="W", baseline="U",
        )

    info = WCRWellInfo(
        api_well_no="4301312345", well_name="Stress Test 1H",
    ) if "api_well_no" in WCRWellInfo.model_fields else None

    rows = [row("SHL", 0, 0), row("Control_Point", 7800, 7700), row("Frac_Start", 9000, 8300), row("BHL", 19000, 8380)]

    out = Path(tmpdir) / "stress_wcr.xlsx"
    check("wcr.generate minimal", lambda: generate_wcr_excel(info=info, location_rows=rows, output_path=out))
    out2 = Path(tmpdir) / "stress_wcr_empty.xlsx"
    check("wcr.generate empty rows", lambda: generate_wcr_excel(info=info, location_rows=[], output_path=out2))
    out3 = Path(tmpdir) / "stress_wcr_perf.xlsx"
    check("wcr.generate with perf+casing", lambda: generate_wcr_excel(
        info=info, location_rows=rows, output_path=out3,
        perf_top_md=9000.0, perf_bottom_md=18000.0, perf_date="6/1/2026",
        casing=pd.DataFrame({"Feature": ["Surface", "Production"], "Top_MD": [0, 0], "Bottom_MD": [2000, 19000]}),
    ))


# ---------------------------------------------------------------- run
if __name__ == "__main__":
    import tempfile

    stress_edits()
    stress_processor()
    stress_coords()
    try:
        with tempfile.TemporaryDirectory() as td:
            stress_wcr_generator(td)
    except Exception as e:  # noqa: BLE001
        FAIL.append(f"wcr harness setup: {type(e).__name__}: {e}")

    print(f"\n{'='*70}\nSTRESS RESULTS: {len(PASS)} ok, {len(FAIL)} problems\n{'='*70}")
    if FAIL:
        print("\n--- PROBLEMS ---")
        for f in FAIL:
            print("  [X]", f)
    print("\n--- OK ---")
    for p in PASS:
        print("  [ok]", p)
