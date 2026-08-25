"""Startup checks for the data files ETools cannot run without.

Three data assets are gitignored (``.gitignore`` lines 71 and 80), so a
fresh clone -- or a portable bundle copied without its data directory --
has none of them. Each is checked eagerly in a repository/catalog
constructor, and those constructors run at *page render* time, so a
missing file used to make every page load fail with the real cause
visible only in the log.

This module answers "what is missing and how do I get it?" before the
server ever starts. It is pure: no UI, no logging, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from etools.config import settings


@dataclass(frozen=True)
class DataFileStatus:
    name: str
    path: Path
    present: bool
    purpose: str
    build_hint: str


def required_data_files() -> list[DataFileStatus]:
    """Status of every data file the UI constructs eagerly at render time."""
    # Imported here, not at module scope: these modules pull in sqlite3 and
    # the casing domain, and preflight must stay importable even when they
    # are broken.
    from etools.core.casing_review.catalog import _CATALOG_PATH
    from etools.core.casing_review.grid_corners import _DB_PATH

    specs: list[tuple[str, Path, str, str]] = [
        (
            "Plat sections",
            Path(settings.plats_db),
            "PLSS section polygons - needed by the Casing Review, WCR and "
            "Plat Searcher tabs.",
            "Copy Board_DB_Plss_Sections.db into the data/ directory "
            "(~255 MB, not tracked in git).",
        ),
        (
            "Casing catalog",
            Path(_CATALOG_PATH),
            "Casing collapse/burst/tension strengths - needed to compute "
            "design factors.",
            "Build it with: python scripts/build_casing_catalog.py",
        ),
        (
            "Grid numbers",
            Path(_DB_PATH),
            "PLSS quarter-side geometry - needed for section bearing grids.",
            "Build it with: python scripts/build_grid_numbers_db.py",
        ),
    ]
    return [
        DataFileStatus(
            name=name,
            path=path,
            present=path.exists(),
            purpose=purpose,
            build_hint=hint,
        )
        for name, path, purpose, hint in specs
    ]


def missing_data_files() -> list[DataFileStatus]:
    return [s for s in required_data_files() if not s.present]


def format_preflight_report(missing: list[DataFileStatus]) -> str:
    """Human-readable console block. Empty string when nothing is missing."""
    if not missing:
        return ""
    rule = "=" * 72
    lines = [
        "",
        rule,
        f"[etools] {len(missing)} required data file(s) are missing.",
        "         The app will start, but the tabs that need them will show",
        "         an error panel instead of their content.",
        rule,
    ]
    for s in missing:
        lines += [
            "",
            f"  {s.name}",
            f"    expected at : {s.path}",
            f"    needed for  : {s.purpose}",
            f"    to fix      : {s.build_hint}",
        ]
    lines += ["", rule, ""]
    return "\n".join(lines)
