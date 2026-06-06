"""Promote APD-parsed data into the WellHeader/survey shape the rest of
the app (Survey / Map / Clearance tabs) expects.

The Load Well tab loads a well by hitting the DirectionalSurveyData table
and getting back a ``WellHeader`` plus per-citing survey dataframes. We
need to mint the same shape from an APD PDF + a directional survey (DB
lookup or PDF upload) so the same downstream tabs light up without any
database round-trip.
"""

from __future__ import annotations

import pandas as pd

from etools.models import APDPdfData, WellHeader, WCRPdfData


def well_header_from_apd(apd: APDPdfData, *, lateral: str = "0000") -> WellHeader:
    """Build a synthetic ``WellHeader`` from a parsed APD.

    The APD itself doesn't ship surface lat/lon. We derive it from the
    PLSS section centroid so downstream tabs (Survey / Map / Clearance)
    can process the well. Accurate to ~1 mile (a section is 5,280 ft on
    a side); the surface PDF survey, if uploaded, supplies the precise
    SHL coordinates and overrides this estimate.

    ``pkey`` is synthetic (hash of API) — only used by ``load_tab`` to
    de-duplicate other laterals in the dropdown, which is irrelevant
    when the well wasn't sourced from the DB.
    """
    api = (apd.api or "")[:10]
    pkey = abs(hash((api, lateral))) % (2**31)

    surface = next(
        (L for L in apd.locations if L.name.lower().startswith("location at surface")),
        None,
    )

    plss = None
    if surface is not None:
        ns = (
            f"{int(surface.fnl)} FNL" if surface.fnl
            else f"{int(surface.fsl)} FSL" if surface.fsl
            else None
        )
        ew = (
            f"{int(surface.fel)} FEL" if surface.fel
            else f"{int(surface.fwl)} FWL" if surface.fwl
            else None
        )
        twp = f"{surface.township}{surface.township_dir or ''}"
        rng = f"{surface.range}{surface.range_dir or ''}"
        plss = (
            f"{ns or ''} {ew or ''} {surface.qtr_qtr or ''} "
            f"Sec {surface.section or '?'} T{twp} R{rng} {surface.meridian or ''}"
        ).strip()

    # Derive surface lat/lon + UTM from the PLSS section centroid.
    surface_lat, surface_lon, surface_x, surface_y = _derive_surface_coords(surface)

    return WellHeader(
        pkey=pkey,
        api=api or "0000000000",
        lateral=lateral,
        well_name=apd.well_name,
        operator=apd.operator,
        citing_type="Planned",
        surface_elevation=apd.ground_elev_ft,
        elevation_reference="GR" if apd.ground_elev_ft else None,
        north_reference="grid",
        plss_location=plss,
        surface_lat=surface_lat,
        surface_lon=surface_lon,
        surface_x=surface_x,
        surface_y=surface_y,
        utm_zone="12N" if surface_x is not None else None,
        upload_filename=apd.source_pdf,
    )


def well_header_from_wcr(wcr: WCRPdfData, *, lateral: str = "0000") -> WellHeader:
    """Build a synthetic ``WellHeader`` from a parsed WCR (Form 8).

    Mirrors :func:`well_header_from_apd` but reads from ``wcr.positions``
    instead of ``apd.locations``. The WCR's "Surface" position carries
    UTM E/N directly (Section 27); when those are populated we trust
    them, otherwise we fall back to the PLSS section centroid like the
    APD path does.

    ``citing_type`` defaults to "AsDrilled" since WCR is a completion
    report — the survey it carries is the actual drilled geometry, not
    a planned trajectory.
    """
    api = (wcr.api or "")[:10]
    pkey = abs(hash((api, lateral))) % (2**31)

    surface = wcr.surface_position

    plss = None
    if surface is not None:
        ns = (
            f"{int(surface.fnl)} FNL" if surface.fnl
            else f"{int(surface.fsl)} FSL" if surface.fsl
            else None
        )
        ew = (
            f"{int(surface.fel)} FEL" if surface.fel
            else f"{int(surface.fwl)} FWL" if surface.fwl
            else None
        )
        twp = f"{surface.township}{surface.township_dir or ''}"
        rng = f"{surface.range}{surface.range_dir or ''}"
        plss = (
            f"{ns or ''} {ew or ''} {surface.qtr_qtr or ''} "
            f"Sec {surface.section or '?'} T{twp} R{rng} {surface.meridian or ''}"
        ).strip()

    surface_x = getattr(surface, "utm_easting", None) if surface else None
    surface_y = getattr(surface, "utm_northing", None) if surface else None
    if surface_x is not None and surface_y is not None:
        try:
            from etools.core.coordinates import utm_to_latlon
            surface_lat, surface_lon = utm_to_latlon(surface_x, surface_y, 12, "N")
        except Exception:
            surface_lat = surface_lon = None
    else:
        surface_lat, surface_lon, surface_x, surface_y = _derive_surface_coords(surface)

    elev_ft = wcr.elevation_ft if wcr.elevation_ft is not None else wcr.ground_elev_ft
    return WellHeader(
        pkey=pkey,
        api=api or "0000000000",
        lateral=lateral,
        well_name=wcr.well_name,
        operator=wcr.operator,
        citing_type="AsDrilled",
        surface_elevation=elev_ft,
        elevation_reference=("KB" if wcr.elevation_ft else ("GR" if wcr.ground_elev_ft else None)),
        north_reference="grid",
        plss_location=plss,
        surface_lat=surface_lat,
        surface_lon=surface_lon,
        surface_x=surface_x,
        surface_y=surface_y,
        utm_zone="12N" if surface_x is not None else None,
        upload_filename=wcr.source_pdf,
    )


def _derive_surface_coords(surface) -> tuple[float | None, float | None, float | None, float | None]:
    """Derive surface (lat, lon, easting, northing) from the APD footages.

    Places the surface at the precise FNL/FSL + FEL/FWL footage point inside
    the section's plat polygon (the same ``footages_to_xy`` the section
    sheets use). This matters: a section-centroid estimate is off by up to
    ~half a mile, which shifts the *entire* survey trajectory and makes the
    clearance step assign stations to the wrong PLSS sections — so the
    Casing Review section list comes out wrong. When the footages are
    missing we fall back to the section centroid (≈half-mile estimate);
    the user can still override by uploading a survey PDF with real SHL
    coordinates.

    Returns ``(None, None, None, None)`` if the plat DB doesn't contain the
    section or the surface PLSS components are missing.
    """
    if surface is None or not surface.section or not surface.township:
        return None, None, None, None
    try:
        conc = _build_conc(surface)
    except Exception:
        return None, None, None, None
    if conc is None:
        return None, None, None, None
    try:
        from etools.core.casing_review.footages import footages_to_xy
        from etools.core.coordinates import utm_to_latlon
        from etools.repositories import PlatRepository

        repo = PlatRepository()
        # Fetch the single section's corner points and assemble the polygon.
        df = repo._fetch_concs([conc])  # noqa: SLF001 — internal but exactly what we need
        if df.empty:
            return None, None, None, None
        gdf = repo._build_sections(df)  # noqa: SLF001
        if gdf.empty:
            return None, None, None, None
        row = gdf.iloc[0]

        # Prefer the exact footage point; fall back to the centroid.
        fnl = _coerce(getattr(surface, "fnl", None))
        fsl = _coerce(getattr(surface, "fsl", None))
        fel = _coerce(getattr(surface, "fel", None))
        fwl = _coerce(getattr(surface, "fwl", None))
        x = y = None
        if (fnl is not None or fsl is not None) and (fel is not None or fwl is not None):
            try:
                x, y = footages_to_xy(row.geometry, fnl=fnl, fsl=fsl, fel=fel, fwl=fwl)
            except Exception:
                x = y = None
        if x is None or y is None:
            x, y = float(row["centroid_x"]), float(row["centroid_y"])

        # Plat DB is UTM zone 12N (Utah).
        lat, lon = utm_to_latlon(x, y, 12, "N")
        return lat, lon, x, y
    except Exception:
        return None, None, None, None


def _coerce(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f  # drop NaN
    except (TypeError, ValueError):
        return None


def _build_conc(surface) -> str | None:
    """Build the 9-character ``Conc`` PLSS code used by the plat DB.

    Format: ``"SSTNTDRRRDB"`` (5+4) → e.g. ``"2303S02WU"`` for
    Sec 23 T3S R2W Uintah.
    """
    try:
        sec = int(surface.section)
        twp = int(surface.township)
        rng = int(surface.range)
    except (TypeError, ValueError):
        return None
    twp_dir = (surface.township_dir or "").upper()
    rng_dir = (surface.range_dir or "").upper()
    mer = (surface.meridian or "").upper()
    if twp_dir not in ("N", "S") or rng_dir not in ("E", "W") or not mer:
        return None
    return f"{sec:02d}{twp:02d}{twp_dir}{rng:02d}{rng_dir}{mer}"


def normalize_survey_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a survey DataFrame to the DB-shape SurveyService.process
    expects (``MeasuredDepth`` / ``Inclination`` / ``Azimuth``).

    Tolerates the DB-shape (already canonical), the parse_survey_pdf
    shape (``md`` / ``inc`` / ``azi``), and a few other common variants.
    """
    if df is None or df.empty:
        return df
    rename: dict[str, str] = {}
    for c in df.columns:
        cl = c.lower().strip()
        if cl in ("md", "md_ft", "measured_depth", "measured_depth_ft", "measureddepth"):
            rename[c] = "MeasuredDepth"
        elif cl in ("inc", "inclination", "inclination_deg"):
            rename[c] = "Inclination"
        elif cl in ("azi", "azimuth", "azimuth_deg"):
            rename[c] = "Azimuth"
    out = df.rename(columns=rename).copy()
    keep = [c for c in ("MeasuredDepth", "Inclination", "Azimuth") if c in out.columns]
    if len(keep) < 3:
        return out  # let downstream raise a clearer error
    return out[keep]
