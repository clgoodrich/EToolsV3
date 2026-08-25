# Failure-Path Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every failure in ETools either recoverable or loudly visible, so that no failure silently produces a plausible-looking regulatory workbook and no missing file takes the whole app down.

**Architecture:** Three mechanical changes carry most of the value: (1) an atomic write helper so a failed generation can never destroy the previous workbook, (2) per-tab render isolation plus a startup preflight so a missing data file degrades to one broken tab instead of a dead page, and (3) explicit guards where a numeric/geometric failure currently produces NaN or a plausible default instead of an error. The rest is surfacing: converting `log.warning` + `return` into a user-visible signal at the points where silence changes what goes in a submitted form.

**Tech Stack:** Python 3.11+, NiceGUI, openpyxl, shapely 2.0.5, GeoPandas, PyMuPDF (fitz), httpx, pytest.

**Spec:** `C:\Users\colto\.claude\plans\read-through-this-codebase-purring-dawn.md` section 7 ("Failure-path audit"). Section 7.I carries the severity ranking this plan follows. Sections 5 and 6 are earlier audit passes; 7.H lists the corrections to them.

## Global Constraints

- **No hot reload.** `etools/main.py` runs `ui.run(..., reload=False)`. Any manual UI verification requires `Stop ETools.bat` then `Launch ETools.bat`.
- **Never change the Excel output format.** Casing Review copies a template byte-for-byte then overwrites cells. Cell addresses, sheet names and the STRING 1-4 block layout are fixed. Fixes may change *when* a cell is written, never *where*.
- **Do not "fix" known-intentional behavior.** Per the audit decisions: engine defaults (9.0 ppg etc.) are intended; BOPE `'500'`/`'5000'`/`5584.5` stand-ins are accepted; the casing-override tag-vs-position defect is **WON'T FIX** by the user's decision; segment bearing overrides being ignored is won't-fix. Leave all of these alone.
- **`archive/` is dead code.** Never edit it.
- **Baseline (verified 2026-08-19, must stay green):** 132 tests pass.
  - Fast gate (~7 s): `tests/test_ddr_parser.py tests/test_grid_derivation.py tests/test_section_traversal.py tests/test_survey_edits.py tests/test_workspace.py tests/test_wcr_generator_blocks.py tests/test_tracking_service.py`
  - Slow gate (~11 min total): `tests/test_bope.py tests/test_writer_sections.py` (2:53) and `tests/test_wcr_south_moon.py` (7:01). These need SQL Server and the plat DB.
- **Python interpreter is `.venv/Scripts/python.exe`.** Always invoke pytest as `.venv/Scripts/python.exe -m pytest`.
- **Per `CLAUDE.md`:** each phase ends with a `CHANGELOG/YYYY-MM-DD-<slug>.md` entry copied from `CHANGELOG/TEMPLATE.md`, a one-line pointer at the top of the Index in `CHANGELOG/README.md`, then commit and `git push`.
- **Branch:** all work happens on `fix/failure-path-hardening`, branched from the current `chore/stress-test-artifacts`.

## Test Strategy

**The full suite runs after every task.** That is ~11 minutes per fix and roughly
3 hours across the plan; it is the chosen gate because `test_writer_sections`,
`test_bope` and `test_wcr_south_moon` are the only coverage over the writer,
BOPE and WCR paths several tasks touch, and a regression there is exactly the
kind this plan exists to prevent.

Each task therefore ends with:

1. Its own new test (fast, seconds).
2. The **fast gate** as a quick smoke check (~7 s):

```bash
.venv/Scripts/python.exe -m pytest tests/test_ddr_parser.py tests/test_grid_derivation.py tests/test_section_traversal.py tests/test_survey_edits.py tests/test_workspace.py tests/test_wcr_generator_blocks.py tests/test_tracking_service.py -q
```

3. The **full gate** before the commit (~11 min):

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

The full gate needs SQL Server (`CGDESKTOP\SQLEXPRESS`) reachable and all three
data files present. If it cannot run, stop and say so — do not commit on the
fast gate alone.

Expected counts as the plan progresses: baseline **132**, then +5 (Task 1),
+5 (Task 2), +6 (Task 3), +3 (Task 4), +7 (Task 5), +3 (Task 6), +2 (Task 7),
+2 (Task 8), +5 (Task 9), +3 (Task 10), +4 (Task 11), +5 (Task 12), +4 (Task 13),
+2 (Task 14), +5 (Task 15), +3 (Task 16), +2 (Task 17), +2 (Task 18), +3 (Task 19) = **201** at the end.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `etools/preflight.py` | **create** | Check the three required data files exist; return structured results. No UI, no side effects. |
| `etools/core/io_safety.py` | **create** | `atomic_output`, a context manager giving a temp path that is `os.replace`d into place only on success; plus `describe_write_error` for turning `OSError` into an actionable sentence. |
| `etools/ui/tab_guard.py` | **create** | `safe_tab_render`, which renders a tab and, on failure, substitutes an inline error panel and a no-op refresh callback. |
| `etools/ui/app.py` | modify | Wrap all seven tab renders in `safe_tab_render`; stage `post_load_orchestrate` writes so a mid-pipeline failure cannot leave two wells mixed. |
| `etools/main.py` | modify | Run preflight before `build_app()`; print an actionable console message. |
| `etools/core/casing_review/writer.py` | modify | Atomic write. |
| `etools/core/casing_review/generator.py` | modify | Atomic write. |
| `etools/core/wcr/generator.py` | modify | Atomic write. |
| `etools/services/tracking_service.py` | modify | Atomic write. |
| `etools/core/casing_review/footages.py` | modify | Reject non-finite polygon bounds instead of emitting NaN footages. |
| `etools/core/casing_review/sections.py` | modify | Reject a polygon that `buffer(0)` collapsed to empty. |
| `etools/core/coordinates/converter.py` | modify | Range-guard `utm_to_latlon` to match its siblings. |
| `etools/core/survey/kop.py` | modify | Guard `medfilt` window vs survey length; dedupe MD before `np.gradient`; log the `_kop_clustering` swallow. |
| `etools/core/plat/locator.py` | modify | Warn when the points frame carries no CRS to validate against. |
| `etools/core/llm/ollama_client.py` | modify | Guard `r.json()`; detect `done_reason == "length"` truncation. |
| `etools/services/wcr_pdf_service.py` | modify | Surface a DB-extras failure as a warning on the parsed data, not `log.info`. |
| `etools/ui/tabs/casing_review_tab.py` | modify | Actionable PermissionError message; mount-latch fix; DB-lookup notify; segment-override refresh notify. |
| `etools/ui/tabs/wcr_tab.py` | modify | Actionable PermissionError message; mount-latch fix. |
| `etools/ui/tabs/load_tab.py` | modify | DB-lookup notify. |
| `etools/core/pdf/*.py` | modify | Close PyMuPDF documents; clean up temp uploads. |
| `tests/test_preflight.py` | **create** | Preflight results for present/missing files. |
| `tests/test_io_safety.py` | **create** | Atomic write preserves the prior file on failure; error description. |
| `tests/test_geometry_guards.py` | **create** | Degenerate/empty polygon raises instead of returning NaN. |
| `tests/test_coordinate_guards.py` | **create** | `utm_to_latlon` range guard. |
| `tests/test_kop_guards.py` | **create** | Short-survey and duplicate-MD KOP behavior. |
| `tests/test_ollama_client_guards.py` | **create** | Non-JSON body and truncation detection. |

---

# Phase 1 — A missing data file must not kill the app

Spec: 7.A1. Ranked #1. All three data files are gitignored; `PlatRepository.__init__` and `CasingCatalog.__init__` raise `FileNotFoundError` eagerly; `CasingReviewService()` builds both at page-render time from `casing_review_tab.py:193`; and `app.py:553-575` renders the tabs outside any try/except. Result today: the process starts and binds the port, then every page load dies after six tabs are built, with the cause only in the log.

Two fixes: tell the user at startup (Task 1), and isolate the tab so the rest of the app survives (Task 2).

### Task 1: Startup preflight for required data files

**Files:**
- Create: `etools/preflight.py`
- Modify: `etools/main.py:21-35`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `settings.plats_db` from `etools/config.py`; the private module constants `etools.core.casing_review.catalog._CATALOG_PATH` and `etools.core.casing_review.grid_corners._DB_PATH` (imported inside the function so a broken import cannot break startup).
- Produces:
  - `DataFileStatus` — frozen dataclass with fields `name: str`, `path: Path`, `present: bool`, `purpose: str`, `build_hint: str`
  - `required_data_files() -> list[DataFileStatus]`
  - `missing_data_files() -> list[DataFileStatus]`
  - `format_preflight_report(missing: list[DataFileStatus]) -> str` — returns `""` when nothing is missing

  Task 2 consumes `required_data_files()` and `DataFileStatus.build_hint`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_preflight.py`:

```python
"""Startup preflight for the gitignored data files."""
from __future__ import annotations

from pathlib import Path

from etools import preflight


def test_required_data_files_lists_all_three():
    statuses = preflight.required_data_files()
    names = {s.name for s in statuses}
    assert names == {"Plat sections", "Casing catalog", "Grid numbers"}
    for s in statuses:
        assert s.build_hint, f"{s.name} must carry a build hint"
        assert s.purpose, f"{s.name} must explain what it is for"


def test_missing_data_files_is_empty_on_a_working_install():
    # This repo has all three present; the audit baseline depends on it.
    assert preflight.missing_data_files() == []


def test_missing_data_files_detects_an_absent_file(monkeypatch):
    monkeypatch.setattr(
        preflight.settings, "plats_db", Path("C:/nope/definitely_missing.db")
    )
    missing = preflight.missing_data_files()
    assert [s.name for s in missing] == ["Plat sections"]
    assert missing[0].present is False


def test_format_preflight_report_is_empty_when_nothing_missing():
    assert preflight.format_preflight_report([]) == ""


def test_format_preflight_report_names_file_and_hint(monkeypatch):
    monkeypatch.setattr(
        preflight.settings, "plats_db", Path("C:/nope/definitely_missing.db")
    )
    report = preflight.format_preflight_report(preflight.missing_data_files())
    assert "Plat sections" in report
    assert "definitely_missing.db" in report
    assert "Board_DB_Plss_Sections.db" in report  # the build hint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_preflight.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.preflight'`

- [ ] **Step 3: Write the implementation**

Create `etools/preflight.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_preflight.py -q`

Expected: PASS (5 passed)

- [ ] **Step 5: Wire preflight into startup**

In `etools/main.py`, add next to the existing imports:

```python
from etools.preflight import format_preflight_report, missing_data_files
```

Then in `run()`, insert between the `print(f"\n[etools] Persistent log: {log_file}\n")` line and the `build_app()` call:

```python
    missing = missing_data_files()
    if missing:
        print(format_preflight_report(missing))
        log.warning(
            "etools.preflight.missing_data_files",
            files=[s.name for s in missing],
            paths=[str(s.path) for s in missing],
        )
```

- [ ] **Step 6: Verify the startup path still imports cleanly**

Run:

```bash
.venv/Scripts/python.exe -c "import etools.main; from etools.preflight import missing_data_files; print('missing:', [s.name for s in missing_data_files()])"
```

Expected: `missing: []` and no traceback.

- [ ] **Step 7: Run the fast gate**

Run the fast gate command from the Test Strategy section.

Expected: 44 passed, unchanged.

- [ ] **Step 8: Commit**

```bash
git add etools/preflight.py etools/main.py tests/test_preflight.py
git commit -m "feat(preflight): report missing data files at startup instead of failing every page load"
```

### Task 2: Per-tab render isolation

**Files:**
- Create: `etools/ui/tab_guard.py`
- Modify: `etools/ui/app.py` — the import block, and the six non-Load `with ui.tab_panel(...)` bodies at `:553-575`
- Test: `tests/test_tab_guard.py`

**Interfaces:**
- Consumes: `required_data_files()` and `DataFileStatus.build_hint` / `.purpose` / `.path` from Task 1.
- Produces:
  - `describe_tab_failure(name: str, exc: Exception) -> str` — pure; the text shown in the panel
  - `safe_tab_render(name: str, render: Callable[[], Callable[[], None] | None], *, panel: Callable[[str, Exception], None] | None = None) -> Callable[[], None]` — always returns a callable, never raises

The `panel` parameter exists so tests can assert behavior without a NiceGUI page context. Production call sites omit it and get the default NiceGUI panel.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tab_guard.py`:

```python
"""Tab render isolation: one broken tab must not kill the page."""
from __future__ import annotations

from etools.ui.tab_guard import describe_tab_failure, safe_tab_render


def test_successful_render_returns_its_refresh_callback():
    calls = []
    cb = safe_tab_render("Demo", lambda: (lambda: calls.append("refreshed")))
    cb()
    assert calls == ["refreshed"]


def test_render_returning_none_still_yields_a_callable():
    cb = safe_tab_render("Demo", lambda: None)
    cb()  # must not raise


def test_failing_render_does_not_propagate_and_records_the_panel():
    seen = []

    def boom():
        raise RuntimeError("kaboom")

    cb = safe_tab_render("Demo", boom, panel=lambda n, e: seen.append((n, e)))
    cb()  # the substituted refresh must be a safe no-op
    assert len(seen) == 1
    assert seen[0][0] == "Demo"
    assert isinstance(seen[0][1], RuntimeError)


def test_describe_tab_failure_plain_exception_names_the_tab():
    msg = describe_tab_failure("Casing Review", RuntimeError("kaboom"))
    assert "Casing Review" in msg
    assert "kaboom" in msg


def test_describe_tab_failure_maps_a_missing_data_file_to_its_build_hint():
    exc = FileNotFoundError(
        "Plat database not found: C:/x/Board_DB_Plss_Sections.db"
    )
    msg = describe_tab_failure("Casing Review", exc)
    assert "Board_DB_Plss_Sections.db" in msg
    # The preflight hint must be surfaced, not just the raw error text.
    assert "data/" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tab_guard.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.ui.tab_guard'`

- [ ] **Step 3: Write the implementation**

Create `etools/ui/tab_guard.py`:

```python
"""Render one tab in isolation.

``root()`` builds seven tabs in sequence. Before this module, an exception
in any of them -- most realistically ``FileNotFoundError`` from a missing
gitignored data file, raised eagerly inside ``CasingReviewService()`` at
``casing_review_tab.py:193`` -- propagated out of ``root()`` and the whole
page failed to render, for every user, with the cause only in the log.

A broken tab now shows an inline explanation and the other six work.
"""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from etools.logging_setup import get_logger

log = get_logger(__name__)

RefreshCallback = Callable[[], None]


def describe_tab_failure(name: str, exc: Exception) -> str:
    """Explain a tab render failure in terms the user can act on."""
    base = f"The {name} tab could not be loaded."
    if isinstance(exc, FileNotFoundError):
        text = str(exc)
        # Match the failure against the known data files so we can print the
        # real build command rather than just echoing the exception.
        try:
            from etools.preflight import required_data_files

            for status in required_data_files():
                if status.path.name and status.path.name in text:
                    return (
                        f"{base}\n\n"
                        f"Missing data file: {status.name} "
                        f"(expected at {status.path}).\n"
                        f"Needed for: {status.purpose}\n"
                        f"To fix: {status.build_hint}"
                    )
        except Exception:  # pragma: no cover - preflight must never mask exc
            log.exception("tab_guard.preflight_lookup_failed")
        return f"{base}\n\nMissing file: {text}"
    return f"{base}\n\n{type(exc).__name__}: {exc}"


def _default_panel(name: str, exc: Exception) -> None:
    with ui.column().classes("p-6 gap-2 w-full"):
        ui.label(f"{name} unavailable").classes(
            "text-lg font-semibold text-red-700"
        )
        ui.label(describe_tab_failure(name, exc)).classes(
            "text-sm text-red-800 bg-red-50 p-3 rounded whitespace-pre-wrap"
        )
        ui.label(
            "The other tabs are unaffected. Restart ETools after fixing this."
        ).classes("text-xs text-gray-500")


def safe_tab_render(
    name: str,
    render: Callable[[], RefreshCallback | None],
    *,
    panel: Callable[[str, Exception], None] | None = None,
) -> RefreshCallback:
    """Render a tab, substituting an error panel if it raises.

    Always returns a callable, so ``refresh_callbacks`` stays uniform and
    ``fire_refresh`` never has to special-case a failed tab.
    """
    try:
        callback = render()
    except Exception as exc:
        log.exception("tab.render_failed", tab=name, error=str(exc))
        (panel or _default_panel)(name, exc)
        return lambda: None
    return callback if callable(callback) else (lambda: None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_tab_guard.py -q`

Expected: PASS (5 passed)

- [ ] **Step 5: Wire every tab render through the guard**

In `etools/ui/app.py`, add to the import block:

```python
from etools.ui.tab_guard import safe_tab_render
```

Then replace the six non-Load tab-panel bodies at `app.py:553-575`. Note `render_plat_tab()` takes no `state` argument, and the Map & Viz panel additionally assigns `state.viz_refresh`:

```python
            with ui.tab_panel(tab_survey):
                refresh_callbacks.append(
                    safe_tab_render("Survey", lambda: render_survey_tab(state))
                )
                _ts = _tlog("survey", _ts)

            with ui.tab_panel(tab_map):
                _viz_refresh = safe_tab_render(
                    "Map & Viz", lambda: render_viz_tab(state)
                )
                refresh_callbacks.append(_viz_refresh)
                state.viz_refresh = _viz_refresh
                _ts = _tlog("viz", _ts)
            with ui.tab_panel(tab_clearance):
                refresh_callbacks.append(
                    safe_tab_render(
                        "Clearance", lambda: render_clearance_tab(state)
                    )
                )
                _ts = _tlog("clearance", _ts)
            with ui.tab_panel(tab_wcr):
                refresh_callbacks.append(
                    safe_tab_render("WCR", lambda: render_wcr_tab(state))
                )
                _ts = _tlog("wcr", _ts)
            with ui.tab_panel(tab_casing):
                refresh_callbacks.append(
                    safe_tab_render(
                        "Casing Review", lambda: render_casing_review_tab(state)
                    )
                )
                _ts = _tlog("casing", _ts)
            with ui.tab_panel(tab_plat):
                refresh_callbacks.append(
                    safe_tab_render("Plat Searcher", render_plat_tab)
                )
                _ts = _tlog("plat", _ts)
```

Leave the Load Well panel as-is: it defines `load_handler` inline and constructs no services eagerly, so it cannot fail this way.

- [ ] **Step 6: Verify the guard catches the real A1 failure**

This reproduces A1 without deleting anyone's data file, by pointing the setting at a missing path in-process:

```bash
.venv/Scripts/python.exe -c "
from pathlib import Path
from etools.config import settings
settings.plats_db = Path('C:/nope/missing_plats.db')
from etools.ui.tab_guard import safe_tab_render, describe_tab_failure
from etools.services.casing_review_service import CasingReviewService
seen = []
cb = safe_tab_render('Casing Review', lambda: CasingReviewService(), panel=lambda n, e: seen.append((n, e)))
cb()
assert len(seen) == 1, seen
print('panel fired for:', seen[0][0])
print(describe_tab_failure(*seen[0]))
"
```

Expected: prints `panel fired for: Casing Review`, then a message naming `Board_DB_Plss_Sections.db` and the "Copy ... into the data/ directory" hint. No traceback, and `cb()` does not raise.

- [ ] **Step 7: Run the fast gate plus both new test files**

Run: `.venv/Scripts/python.exe -m pytest tests/test_preflight.py tests/test_tab_guard.py -q`, then the fast gate.

Expected: 10 passed, then 44 passed.

- [ ] **Step 8: Run the slow gate (end of Phase 1)**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`

Expected: 142 passed (132 baseline + 10 new). Takes ~11 minutes.

- [ ] **Step 9: Change log, commit and push**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-19-startup-resilience.md
```

Fill in every section, naming `etools/preflight.py`, `etools/ui/tab_guard.py`, the `main.run()` wiring and the six `app.py` call sites. Record the verification as the in-process `settings.plats_db` repro from Step 6 plus the full suite. Add a one-line pointer to the top of the Index in `CHANGELOG/README.md`.

```bash
git add etools/ui/tab_guard.py etools/ui/app.py tests/test_tab_guard.py \
        CHANGELOG/2026-08-19-startup-resilience.md CHANGELOG/README.md
git commit -m "feat(ui): isolate tab renders so a missing data file breaks one tab, not the page"
git push
```

# Phase 2 — A failed generation must not destroy the previous workbook

Spec: 7.A2 and 7.A3. Ranked #2. `writer.py:68` does `shutil.copyfile(template, output_path)` straight to the final path, then mutates and saves at `:157`. From the moment `copyfile` returns, the user's previous reviewed workbook is gone; if any of the mostly-unguarded `_write_*` helpers raises, what is left on disk is a blank template. The toast says "Generation failed" and is silent about the file having been replaced.

Compounding it: the output filename is deterministic (`casing_review_service.py:123-127`, no timestamp) and every success auto-opens the file in Excel (`casing_review_tab.py:586-589`), so the ordinary generate → tweak → generate loop targets a path Excel is holding.

### Task 3: Atomic workbook writes

**Files:**
- Create: `etools/core/io_safety.py`
- Modify: `etools/core/casing_review/writer.py:34-158`
- Modify: `etools/core/casing_review/generator.py:92-125`
- Modify: `etools/core/wcr/generator.py:117-159`
- Modify: `etools/services/tracking_service.py:42-114`
- Test: `tests/test_io_safety.py`

**Interfaces:**
- Produces:
  - `atomic_output(path: Path, *, keep_failed: bool = False) -> ContextManager[Path]` — yields a sibling temp path; `os.replace`s it onto `path` on clean exit; deletes it and leaves `path` untouched on any exception
  - `describe_write_error(path: str | Path, exc: BaseException) -> str` — actionable one-liner; Task 4 consumes this

The refactor pattern for each writer is a **rename plus a thin wrapper**, so no existing function body is re-indented or otherwise edited:

```python
def write_casing_review(design, output_path, **kwargs) -> Path:
    output_path = Path(output_path)
    with atomic_output(output_path) as work_path:
        _write_casing_review_to(design, work_path, **kwargs)
    return output_path


def _write_casing_review_to(design, output_path, *, template_path=None, ...):
    <the entire existing body, byte-for-byte unchanged>
```

Because the body only ever touches `output_path` at its `shutil.copyfile` and `wb.save` lines, redirecting it at the temp path is sufficient. Keep every keyword argument and the existing docstring on the public function.

**Important limitation to record in the change log:** on Windows, `os.replace` onto a file Excel holds open still raises `PermissionError`. Atomic write does not make the write succeed — it guarantees the **existing file survives** the failure. Task 4 supplies the message.

- [ ] **Step 1: Write the failing test**

Create `tests/test_io_safety.py`:

```python
"""Atomic output: a failed write must leave the previous file intact."""
from __future__ import annotations

from pathlib import Path

import pytest

from etools.core.io_safety import atomic_output, describe_write_error


def test_successful_write_replaces_the_target(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")
    with atomic_output(target) as work:
        assert work != target
        work.write_text("new", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "new"


def test_target_is_created_when_absent(tmp_path):
    target = tmp_path / "sub" / "out.txt"
    with atomic_output(target) as work:
        work.write_text("fresh", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "fresh"


def test_failed_write_leaves_the_previous_file_untouched(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("precious", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with atomic_output(target) as work:
            work.write_text("half written", encoding="utf-8")
            raise RuntimeError("boom")
    assert target.read_text(encoding="utf-8") == "precious"


def test_failed_write_removes_the_temp_file(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("precious", encoding="utf-8")
    seen = {}
    with pytest.raises(RuntimeError):
        with atomic_output(target) as work:
            work.write_text("half", encoding="utf-8")
            seen["work"] = work
            raise RuntimeError("boom")
    assert not seen["work"].exists()
    assert list(tmp_path.iterdir()) == [target]


def test_describe_write_error_calls_out_excel_for_permission_error(tmp_path):
    msg = describe_write_error(tmp_path / "Casing Review_x.xlsx", PermissionError(13, "denied"))
    assert "Casing Review_x.xlsx" in msg
    assert "Excel" in msg
    assert "Close it" in msg


def test_describe_write_error_falls_back_for_other_errors(tmp_path):
    msg = describe_write_error(tmp_path / "out.xlsx", ValueError("nope"))
    assert "out.xlsx" in msg
    assert "ValueError" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_io_safety.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.core.io_safety'`

- [ ] **Step 3: Write the implementation**

Create `etools/core/io_safety.py`:

```python
"""Write files without destroying the previous version on failure.

Every workbook writer in ETools used to write straight to its final path:
``shutil.copyfile(template, output_path)`` followed, ~90 lines later, by
``wb.save(output_path)``. Between those two calls the user's previously
generated workbook no longer existed, so any exception in between left a
blank template on disk while the UI reported only "Generation failed".

``atomic_output`` writes to a sibling temp file and ``os.replace``s it into
position only after the caller has finished cleanly. ``os.replace`` is
atomic within a single filesystem, which is why the temp file is a sibling
rather than something under the system temp directory.

Note for Windows: replacing a file that Excel holds open still raises
``PermissionError``. This module does not make that write succeed -- it
guarantees the existing file survives it.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from etools.logging_setup import get_logger

log = get_logger(__name__)


@contextmanager
def atomic_output(path: Path | str, *, keep_failed: bool = False) -> Iterator[Path]:
    """Yield a temp path to write to; swap it onto ``path`` on clean exit.

    On any exception the temp file is removed (unless ``keep_failed``) and
    ``path`` is left exactly as it was.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sibling temp file: os.replace is only atomic within one filesystem.
    # The PID keeps two concurrent generations of the same well apart.
    work = path.with_name(f".{path.stem}.{os.getpid()}.partial{path.suffix}")
    try:
        yield work
    except BaseException:
        if not keep_failed:
            try:
                work.unlink(missing_ok=True)
            except OSError as exc:
                log.warning(
                    "io_safety.temp_cleanup_failed", path=str(work), error=str(exc)
                )
        raise
    os.replace(work, path)


def describe_write_error(path: str | Path, exc: BaseException) -> str:
    """Turn a write failure into a sentence naming the cause and the fix."""
    name = Path(path).name
    if isinstance(exc, PermissionError):
        return (
            f"Can't write {name} - it is most likely open in Excel. "
            "Close it and try again. Your previous copy has not been changed."
        )
    if isinstance(exc, FileNotFoundError):
        return f"Can't write {name} - a required file is missing: {exc}"
    if isinstance(exc, OSError):
        detail = getattr(exc, "strerror", None) or str(exc)
        return f"Can't write {name} - {detail}"
    return f"Couldn't generate {name}: {type(exc).__name__}: {exc}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_io_safety.py -q`

Expected: PASS (6 passed)

- [ ] **Step 5: Apply the wrapper pattern to `writer.py`**

In `etools/core/casing_review/writer.py`, add the import:

```python
from etools.core.io_safety import atomic_output
```

Rename the existing `def write_casing_review(` (line 34) to `def _write_casing_review_to(` and leave its entire body untouched. Then add the public wrapper immediately above it, carrying the full keyword signature:

```python
def write_casing_review(
    design: CasingDesign,
    output_path: Path,
    *,
    template_path: Path | None = None,
    surface_location=None,
    producing_interval_location=None,
    td_location=None,
    intermediate_locations: list | None = None,
    section_locations: list | None = None,
    dx_survey_locations: list | None = None,
    dx_survey_footages: list | None = None,
    plat_repo=None,
    bope_system_psi: float | None = None,
    bope_overrides: BOPEOverrides | None = None,
    formations: list | None = None,
) -> Path:
    """Fill the Casing Review xlsx, atomically.

    The workbook is built at a sibling temp path and swapped into place only
    once it is complete, so a failure part-way through leaves any previously
    generated workbook at ``output_path`` untouched.
    """
    output_path = Path(output_path)
    with atomic_output(output_path) as work_path:
        _write_casing_review_to(
            design,
            work_path,
            template_path=template_path,
            surface_location=surface_location,
            producing_interval_location=producing_interval_location,
            td_location=td_location,
            intermediate_locations=intermediate_locations,
            section_locations=section_locations,
            dx_survey_locations=dx_survey_locations,
            dx_survey_footages=dx_survey_footages,
            plat_repo=plat_repo,
            bope_system_psi=bope_system_psi,
            bope_overrides=bope_overrides,
            formations=formations,
        )
    return output_path
```

- [ ] **Step 6: Apply the same pattern to the other three writers**

- `etools/core/casing_review/generator.py`: rename `generate_casing_review` to `_generate_casing_review_to`, add a wrapper with the same signature that opens `atomic_output(output_path)` and passes the temp path through.
- `etools/core/wcr/generator.py`: rename `generate_wcr_excel` to `_generate_wcr_excel_to`, wrapper as above.
- `etools/services/tracking_service.py`: rename `update_tracking_workbook` to `_update_tracking_workbook_to`, wrapper as above. Keep the existing docstring line "Raises PermissionError when the workbook is open in Excel." on the public wrapper — it is still true, and now the row file survives the failure.

Each wrapper returns the real `output_path`, never the temp path, because callers store and display it (`state.casing_last_output_path`, `_render_result`).

- [ ] **Step 7: Verify the guarantee against the real writer**

```bash
.venv/Scripts/python.exe -c "
import os
from pathlib import Path
from etools.core.casing_review.writer import write_casing_review
from etools.core.casing_review.domain import CasingDesign
sc = Path(os.environ['TEMP'])/'claude'/'atomic'; sc.mkdir(parents=True, exist_ok=True)
out = sc/'Casing Review_test.xlsx'
out.write_bytes(b'PRECIOUS-EXISTING-WORKBOOK')
try:
    write_casing_review(CasingDesign(), out, template_path=Path('does_not_exist.xlsx'))
except Exception as e:
    print('failed as expected:', type(e).__name__)
print('survived:', out.read_bytes()[:26])
print('no temp left:', [p.name for p in sc.iterdir()])
"
```

Expected: `failed as expected: FileNotFoundError`, then `survived: b'PRECIOUS-EXISTING-WORKBOOK'`, then a listing containing only the one xlsx. Before this task the file would have been a copied template or absent.

- [ ] **Step 8: Verify a real generation still produces a valid workbook**

```bash
.venv/Scripts/python.exe -c "
import os
from pathlib import Path
import openpyxl
from etools.core.casing_review.writer import write_casing_review
from etools.core.casing_review.domain import CasingDesign
sc = Path(os.environ['TEMP'])/'claude'/'atomic'
out = write_casing_review(CasingDesign(), sc/'real.xlsx')
wb = openpyxl.load_workbook(out)
print('sheets:', len(wb.sheetnames), 'path:', out.name)
assert 'Casing Review' in wb.sheetnames
print('OK')
"
```

Expected: 15 sheets, `path: real.xlsx`, `OK`.

- [ ] **Step 9: Fast gate, then full gate**

Run the fast gate, then `.venv/Scripts/python.exe -m pytest tests/ -q`.

Expected: 44 passed; then 148 passed (142 + 6). `test_writer_sections`, `test_bope` and `test_wcr_south_moon` all exercise these writers, so a signature mistake in the wrapper shows up here.

- [ ] **Step 10: Commit**

```bash
git add etools/core/io_safety.py etools/core/casing_review/writer.py \
        etools/core/casing_review/generator.py etools/core/wcr/generator.py \
        etools/services/tracking_service.py tests/test_io_safety.py
git commit -m "fix(io): write workbooks atomically so a failed generation can't destroy the previous one"
```

### Task 4: Say why a write failed

**Files:**
- Modify: `etools/ui/tabs/casing_review_tab.py:571-579` (the `generate()` handler)
- Modify: `etools/ui/tabs/wcr_tab.py:336-341` (`generate_from_pdf`) and the save-edited-Excel handler in the same file
- Test: `tests/test_io_safety.py` (extend — the message logic lives in `describe_write_error`, already unit-tested; this task adds the two call sites and one regression test for the wiring)

**Interfaces:**
- Consumes: `describe_write_error` from Task 3.

Today every write failure renders as `f"Generation failed: {exc}"` — identical text for a missing template, a full disk, and the overwhelmingly common case of the file being open in Excel. `wcr_tab.py:608-612` already does this properly for the tracking workbook; this task brings the other two up to that standard.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_io_safety.py`:

```python
def test_permission_error_message_is_reused_by_the_ui_layer():
    # The Casing Review tab must not hand-roll its own wording; it must use
    # the shared helper so every write path says the same actionable thing.
    import inspect

    from etools.ui.tabs import casing_review_tab

    src = inspect.getsource(casing_review_tab)
    assert "describe_write_error" in src, (
        "casing_review_tab must surface write failures via describe_write_error"
    )


def test_wcr_tab_also_uses_the_shared_write_error_message():
    import inspect

    from etools.ui.tabs import wcr_tab

    assert "describe_write_error" in inspect.getsource(wcr_tab)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_io_safety.py -q`

Expected: FAIL — both new tests fail on the missing `describe_write_error` reference.

- [ ] **Step 3: Wire the Casing Review handler**

In `etools/ui/tabs/casing_review_tab.py`, add to the imports:

```python
from etools.core.io_safety import describe_write_error
```

Replace the `except Exception as exc:` block inside `generate()` (currently `:573-577`) with:

```python
        except Exception as exc:
            log.exception("casing_review.generate_failed")
            if isinstance(exc, OSError):
                msg = describe_write_error(
                    svc.output_dir / svc._default_filename(data), exc
                )
            else:
                msg = f"Generation failed: {exc}"
            ui.notify(msg, type="negative")
            cache["gen_status"].text = msg
            return
```

Keep the existing `finally:` block that removes the button's loading state — it is already correct.

- [ ] **Step 4: Wire the WCR handler**

In `etools/ui/tabs/wcr_tab.py`, add the same import, then in `generate_from_pdf`'s `except Exception as exc:` block (`:338-341`) apply the same `isinstance(exc, OSError)` branch, using the path from `_default_output_path(pdf_data)` where available and the well name otherwise. Apply it to the save-edited-Excel handler in the same file as well.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_io_safety.py -q`

Expected: PASS (8 passed)

- [ ] **Step 6: Verify the message end to end**

```bash
.venv/Scripts/python.exe -c "
import msvcrt, os, shutil
from pathlib import Path
from etools.core.io_safety import describe_write_error
from etools.core.casing_review.writer import write_casing_review
from etools.core.casing_review.domain import CasingDesign
from etools.core.casing_review.generator import CASING_REVIEW_TEMPLATE
sc = Path(os.environ['TEMP'])/'claude'/'lock2'; sc.mkdir(parents=True, exist_ok=True)
out = sc/'Casing Review_locked.xlsx'
shutil.copyfile(CASING_REVIEW_TEMPLATE, out)
fh = open(out, 'r+b'); msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
try:
    write_casing_review(CasingDesign(), out)
except Exception as e:
    print(describe_write_error(out, e))
finally:
    fh.close()
"
```

Expected: `Can't write Casing Review_locked.xlsx - it is most likely open in Excel. Close it and try again. Your previous copy has not been changed.`

- [ ] **Step 7: Fast gate, then full gate**

Expected: 44 passed; then 150 passed (148 + 2).

- [ ] **Step 8: Change log, commit and push (end of Phase 2)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-atomic-workbook-writes.md
```

Record: the four writers now build at a sibling temp path and `os.replace` into position; a failed generation leaves the previous workbook byte-identical; write failures name Excel as the likely cause. Note the Windows limitation explicitly — atomic write does not defeat an Excel lock, it protects the existing file from one. Add the `CHANGELOG/README.md` pointer.

```bash
git add etools/ui/tabs/casing_review_tab.py etools/ui/tabs/wcr_tab.py \
        tests/test_io_safety.py CHANGELOG/2026-08-25-atomic-workbook-writes.md \
        CHANGELOG/README.md
git commit -m "fix(ui): name Excel as the cause when a workbook write is blocked"
git push
```

---

# Phase 3 — Degenerate geometry must raise, not return NaN

Spec: 7.A4, which **corrects** earlier finding #30. Verified on shapely 2.0.5: `Polygon().bounds` returns `(nan, nan, nan, nan)` and unpacks cleanly, so nothing raises. Traced end to end:

```
polygon_footages(empty, (100, 200))      -> SectionFootages(fnl=nan, fsl=nan, fel=nan, fwl=nan)
footages_to_xy(empty, fnl=100, fwl=200)  -> (nan, nan)
```

The trigger is `sections.py:669-672`, where `buffer(0)` "repairs" a self-intersecting or zero-length-segment ring by collapsing it to an empty polygon. NaN footages then flow into the section sheets. A crash would have stopped the user; NaN does not.

### Task 5: Guard the polygon and the footage math

**Files:**
- Modify: `etools/core/casing_review/sections.py:669-672` (`resolve_polygon`) and `:693-695` (`_bbox_corners`)
- Modify: `etools/core/casing_review/footages.py:47-62` (`polygon_footages`) and `:66-89` (`footages_to_xy`)
- Test: `tests/test_geometry_guards.py`

**Interfaces:**
- Produces: `etools.core.casing_review.footages.DegenerateGeometryError` (subclasses `ValueError`, so every existing `except ValueError` caller — `sections.py:316`, `writer.py:473`, `build_section_definitions:941` — keeps working and skips the bad section rather than shipping NaN).

Subclassing `ValueError` is deliberate: those three call sites already catch `ValueError` and degrade to skipping a section, which is the behavior we want. Raising a bare new exception type would turn a silent-NaN bug into a hard crash.

- [ ] **Step 1: Write the failing test**

Create `tests/test_geometry_guards.py`:

```python
"""Degenerate geometry must raise rather than emit NaN footages."""
from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from etools.core.casing_review.footages import (
    DegenerateGeometryError,
    footages_to_xy,
    polygon_footages,
)


def _empty_polygon() -> Polygon:
    # This is exactly what sections.resolve_polygon's buffer(0) repair
    # produces from a zero-length ring.
    collapsed = Polygon([(0, 0), (0, 0), (0, 0)]).buffer(0)
    assert collapsed.is_empty
    return collapsed


def test_shapely_still_returns_nan_bounds_for_an_empty_polygon():
    # Pins the upstream behavior this guard exists for. If shapely ever
    # starts raising here, this test tells us the guard can be simplified.
    assert all(math.isnan(v) for v in _empty_polygon().bounds)


def test_polygon_footages_rejects_an_empty_polygon():
    with pytest.raises(DegenerateGeometryError):
        polygon_footages(_empty_polygon(), (100.0, 200.0))


def test_footages_to_xy_rejects_an_empty_polygon():
    with pytest.raises(DegenerateGeometryError):
        footages_to_xy(_empty_polygon(), fnl=100.0, fwl=200.0)


def test_degenerate_error_is_a_value_error():
    # Existing callers catch ValueError and skip the section; that must keep
    # working rather than becoming a hard crash.
    assert issubclass(DegenerateGeometryError, ValueError)


def test_zero_area_polygon_is_rejected():
    flat = Polygon([(0, 0), (10, 0), (20, 0), (0, 0)])
    with pytest.raises(DegenerateGeometryError):
        polygon_footages(flat, (5.0, 0.0))


def test_a_normal_polygon_still_works():
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    f = polygon_footages(square, (250.0, 750.0))
    assert all(math.isfinite(v) for v in (f.fnl, f.fsl, f.fel, f.fwl))
    assert f.fsl > f.fnl  # the point sits in the northern half


def test_footages_round_trip_on_a_normal_polygon():
    square = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    f = polygon_footages(square, (250.0, 750.0))
    x, y = footages_to_xy(square, fnl=f.fnl, fwl=f.fwl)
    assert x == pytest.approx(250.0)
    assert y == pytest.approx(750.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geometry_guards.py -q`

Expected: FAIL — `ImportError: cannot import name 'DegenerateGeometryError'`

- [ ] **Step 3: Write the implementation**

In `etools/core/casing_review/footages.py`, add near the top after the imports:

```python
class DegenerateGeometryError(ValueError):
    """A section polygon has no usable extent.

    Subclasses ``ValueError`` on purpose: ``sections.py``, ``writer.py`` and
    ``build_section_definitions`` already catch ``ValueError`` and skip the
    offending section, which is the behavior we want. Shapely returns
    ``(nan, nan, nan, nan)`` from ``.bounds`` on an empty geometry and that
    unpacks without complaint, so without this guard the NaN flows straight
    into the section-sheet footages.
    """


def _checked_bounds(polygon: BaseGeometry) -> tuple[float, float, float, float]:
    if polygon is None:
        raise DegenerateGeometryError("No polygon supplied.")
    if getattr(polygon, "is_empty", False):
        raise DegenerateGeometryError(
            "Section polygon is empty - it most likely collapsed during "
            "geometry repair. Check the section's segment overrides."
        )
    minx, miny, maxx, maxy = polygon.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise DegenerateGeometryError(
            f"Section polygon has non-finite bounds: "
            f"{(minx, miny, maxx, maxy)!r}"
        )
    if maxx <= minx or maxy <= miny:
        raise DegenerateGeometryError(
            f"Section polygon has zero extent: width={maxx - minx}, "
            f"height={maxy - miny}"
        )
    return minx, miny, maxx, maxy
```

Add `import math` to the module imports if absent. Then in `polygon_footages` replace:

```python
    minx, miny, maxx, maxy = polygon.bounds
```

with:

```python
    minx, miny, maxx, maxy = _checked_bounds(polygon)
```

and make the identical substitution in `footages_to_xy` (its `minx, miny, maxx, maxy = polygon.bounds` line, which sits after the two existing "exactly one of" argument checks — leave those where they are).

- [ ] **Step 4: Guard the collapse at its source**

In `etools/core/casing_review/sections.py`, `resolve_polygon` currently ends:

```python
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly
```

Replace with:

```python
        poly = Polygon(ring)
        if not poly.is_valid:
            repaired = poly.buffer(0)
            # buffer(0) is a repair trick, not a guarantee: on a
            # self-intersecting or zero-length ring it returns an empty
            # geometry whose .bounds is (nan, nan, nan, nan). Letting that
            # through produced NaN footages in the section sheets with no
            # error anywhere.
            if repaired.is_empty:
                raise DegenerateGeometryError(
                    "Section geometry collapsed while being repaired - the "
                    "segment overrides do not describe a closed section."
                )
            log.warning(
                "section.polygon_repaired",
                conc=getattr(self, "conc", None),
                area_before=poly.area,
                area_after=repaired.area,
            )
            poly = repaired
        return poly
```

Add the import at the top of `sections.py`:

```python
from etools.core.casing_review.footages import DegenerateGeometryError
```

Check for an import cycle first — `footages.py` must not import `sections.py`. Confirm with:

```bash
grep -n "^from\|^import" etools/core/casing_review/footages.py
```

Expected: no `sections` import, so the direction is safe.

Also harden `_bbox_corners` (`:693-695`), which today takes `.bounds` directly after only a `None` check:

```python
        if self.plat_polygon is None:
            raise ValueError("No plat_polygon to derive corners from")
        minx, miny, maxx, maxy = _checked_bounds(self.plat_polygon)
```

importing `_checked_bounds` alongside `DegenerateGeometryError`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geometry_guards.py -q`

Expected: PASS (7 passed)

- [ ] **Step 6: Verify the NaN path is actually closed**

```bash
.venv/Scripts/python.exe -c "
from shapely.geometry import Polygon
from etools.core.casing_review.footages import polygon_footages, footages_to_xy, DegenerateGeometryError
z = Polygon([(0,0),(0,0),(0,0)]).buffer(0)
for fn, kw in ((polygon_footages, {}), (footages_to_xy, dict(fnl=100.0, fwl=200.0))):
    try:
        r = fn(z, (100.0,200.0)) if not kw else fn(z, **kw)
        print('LEAK - returned', r)
    except DegenerateGeometryError as e:
        print('guarded:', str(e)[:60])
"
```

Expected: two `guarded:` lines. Before this task both printed NaN results.

- [ ] **Step 7: Fast gate, then full gate**

Expected: 44 passed; then 157 passed (150 + 7). `test_section_traversal`, `test_grid_derivation` and `test_writer_sections` all build real polygons — if any legitimate section has zero extent this is where it surfaces, and that would be a genuine data finding worth reporting rather than relaxing the guard.

- [ ] **Step 8: Change log, commit and push (end of Phase 3)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-degenerate-geometry-guards.md
```

Record that this also corrects audit finding #30 (predicted a `ValueError` crash; the real behavior was silent NaN).

```bash
git add etools/core/casing_review/footages.py etools/core/casing_review/sections.py \
        tests/test_geometry_guards.py CHANGELOG/2026-08-25-degenerate-geometry-guards.md \
        CHANGELOG/README.md
git commit -m "fix(geometry): reject degenerate section polygons instead of emitting NaN footages"
git push
```

---

# Phase 4 — Silence that changes a regulatory workbook

Spec: 7.B1 and 7.B3, ranked #4. Two paths degrade quietly in ways that alter what gets submitted.

### Task 6: A DB blip must not silently strip the casing table out of a WCR

`wcr_pdf_service.py:309-328` returns `(None, None)` on any exception at `log.info` level. The generated Form 8 then omits the entire casing table and the perf date, and the same button pressed a minute later produces a different workbook with nothing in the UI to distinguish them.

**Files:**
- Modify: `etools/services/wcr_pdf_service.py:309-328` (`_db_extras`), and its two call sites at `:190` and `:270`
- Test: `tests/test_wcr_db_extras.py`

**Interfaces:**
- Produces: `_db_extras(api: str | None, *, warnings: list[str] | None = None) -> tuple[pd.DataFrame | None, str | None]` — appends one sentence to `warnings` when the DB could not be reached. `WCRPdfData.warnings` already exists (`etools/models/wcr.py:311`) and is already rendered by the WCR tab, so nothing new is needed downstream.

- [ ] **Step 1: Write the failing test**

Create `tests/test_wcr_db_extras.py`:

```python
"""A DB failure while fetching WCR extras must be visible, not silent."""
from __future__ import annotations

import pytest

from etools.services import wcr_pdf_service


def test_db_extras_returns_none_pair_without_an_api():
    assert wcr_pdf_service._db_extras(None) == (None, None)


def test_db_extras_warns_when_the_database_is_unreachable(monkeypatch):
    class Boom:
        def __init__(self):
            raise RuntimeError("SQL Server unreachable")

    monkeypatch.setattr(
        "etools.repositories.WCRRepository", Boom, raising=True
    )
    warnings: list[str] = []
    casing, perf = wcr_pdf_service._db_extras("4301354722", warnings=warnings)
    assert (casing, perf) == (None, None)
    assert len(warnings) == 1
    assert "casing" in warnings[0].lower()
    assert "database" in warnings[0].lower()


def test_db_extras_without_a_warnings_sink_still_degrades(monkeypatch):
    class Boom:
        def __init__(self):
            raise RuntimeError("SQL Server unreachable")

    monkeypatch.setattr("etools.repositories.WCRRepository", Boom, raising=True)
    assert wcr_pdf_service._db_extras("4301354722") == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wcr_db_extras.py -q`

Expected: FAIL — `TypeError: _db_extras() got an unexpected keyword argument 'warnings'`

- [ ] **Step 3: Write the implementation**

Replace `_db_extras` in `etools/services/wcr_pdf_service.py`:

```python
def _db_extras(
    api: str | None, *, warnings: list[str] | None = None
) -> tuple[pd.DataFrame | None, str | None]:
    """Casing table + latest perf date from the DB, when reachable.

    The PDF pipeline must keep working without SQL Server, so any failure
    here degrades to (None, None) -- but it is NOT invisible. Omitting the
    casing table changes what gets submitted, and the same button pressed
    twice must not quietly produce two different workbooks.
    """
    if not api:
        return None, None
    try:
        from etools.repositories import WCRRepository
        from etools.services.wcr_service import _perf_summary

        bundle = WCRRepository().get_bundle(api[:10])
    except Exception as exc:
        log.warning("wcr_pdf_service.db_extras.unavailable", api=api, error=str(exc))
        if warnings is not None:
            warnings.append(
                "Could not reach the database, so the casing table and "
                "perforation date were left out of this workbook. Fix the "
                "connection and generate again if you need them."
            )
        return None, None
    casing = bundle.casing if bundle.casing is not None and not bundle.casing.empty else None
    _, _, perf_date = _perf_summary(bundle.perforations)
    return casing, perf_date
```

- [ ] **Step 4: Pass the warnings sink at both call sites**

At `wcr_pdf_service.py:270` inside `rewrite_excel`, and at `:190` inside `generate`, change:

```python
    casing_df, perf_date = _db_extras(pdf_data.api)
```

to:

```python
    casing_df, perf_date = _db_extras(pdf_data.api, warnings=pdf_data.warnings)
```

`WCRPdfData.warnings` is a plain mutable list on the Pydantic model, so appending in place is enough — the WCR tab already renders it.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wcr_db_extras.py -q`

Expected: PASS (3 passed)

- [ ] **Step 6: Fast gate, then full gate**

Expected: 44 passed; then 160 passed (157 + 3). `test_wcr_south_moon` exercises the real generate path — confirm no duplicate warnings accumulate when it regenerates.

- [ ] **Step 7: Commit**

```bash
git add etools/services/wcr_pdf_service.py tests/test_wcr_db_extras.py
git commit -m "fix(wcr): warn when a DB failure strips the casing table from a generated workbook"
```

### Task 7: A failed survey lookup must not look like "no survey exists"

`load_tab.py:286-291`, `casing_review_tab.py:445-451` and `wcr_tab.py:202-203` all `log.warning` then `return`. The user cannot tell a DB outage from a well that genuinely has no survey — and the difference decides whether every casing TVD comes from a real trajectory or from the synthetic vertical welltrack.

**Files:**
- Modify: `etools/ui/tabs/casing_review_tab.py:444-451` (`_try_db_survey_for_apd`)
- Modify: `etools/ui/tabs/load_tab.py:284-302` and `:404-418` (the two DB survey helpers)
- Test: `tests/test_db_lookup_notifies.py`

**Interfaces:**
- Consumes nothing new. Produces no new public API — this is a behavior change at three call sites, asserted structurally.

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_lookup_notifies.py`:

```python
"""A DB survey lookup failure must reach the user, not just the log."""
from __future__ import annotations

import inspect

import pytest

MODULES = [
    "etools.ui.tabs.casing_review_tab",
    "etools.ui.tabs.load_tab",
]


@pytest.mark.parametrize("modname", MODULES)
def test_db_lookup_failure_notifies_the_user(modname):
    mod = __import__(modname, fromlist=["*"])
    src = inspect.getsource(mod)
    # Every handler that logs a db lookup failure must also notify.
    for marker in ("db_lookup_failed", "db_survey_failed"):
        if marker not in src:
            continue
        idx = src.index(marker)
        window = src[idx : idx + 600]
        assert "ui.notify" in window, (
            f"{modname}: '{marker}' is logged but never surfaced to the user"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_db_lookup_notifies.py -q`

Expected: FAIL on `etools.ui.tabs.casing_review_tab` — the handler logs and returns with no notify.

- [ ] **Step 3: Write the implementation**

In `etools/ui/tabs/casing_review_tab.py`, replace the `except` block inside `_try_db_survey_for_apd` (`:447-451`):

```python
        except Exception as exc:
            log.warning("casing_review.db_lookup_failed", error=str(exc))
            ui.notify(
                "Couldn't reach the database to look up this well's survey. "
                "Casing TVDs will fall back to a straight-hole estimate "
                "unless you load a survey PDF.",
                type="warning",
            )
            return
```

Apply the same treatment in `etools/ui/tabs/load_tab.py` to both `_try_db_survey_for_apd` and `_try_db_survey_for_wcr`, wording the second for the WCR context.

Leave the "query succeeded but returned nothing" branches (`chosen is None`) silent — that is a real, ordinary answer, not a failure.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_db_lookup_notifies.py -q`

Expected: PASS (2 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 162 passed (160 + 2).

- [ ] **Step 6: Change log, commit and push (end of Phase 4)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-surface-silent-degradation.md
git add etools/ui/tabs/casing_review_tab.py etools/ui/tabs/load_tab.py \
        tests/test_db_lookup_notifies.py CHANGELOG/2026-08-25-surface-silent-degradation.md \
        CHANGELOG/README.md
git commit -m "fix(ui): tell the user when a DB lookup failed instead of looking like no data"
git push
```

---

# Phase 5 — Latches, KOP guards and CRS

Spec: 7.B2, 7.B4, 7.B5, 7.B6.

### Task 8: The static-file mount must not latch on failure

`casing_review_tab.py:2575-2586` and the identical block in `wcr_tab.py:1200` set `_mounted = True` unconditionally after a `try/except Exception: pass` around `app.mount(...)`. One failed mount and every "Open folder" link 404s for the rest of the process lifetime.

**Files:**
- Modify: `etools/ui/tabs/casing_review_tab.py:2573-2586` and `etools/ui/tabs/wcr_tab.py` (same helper)
- Test: `tests/test_output_mount.py`

**Interfaces:**
- Produces: `etools/ui/output_mount.py` with `serve_output_file(path: Path) -> str`, replacing the duplicated private helper in both tabs. Single implementation, single latch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_output_mount.py`:

```python
"""The output static-mount must retry after a failure, not latch."""
from __future__ import annotations

from pathlib import Path

from etools.ui import output_mount


def test_url_is_derived_from_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    calls = []
    monkeypatch.setattr(output_mount, "_do_mount", lambda d: calls.append(d))
    url = output_mount.serve_output_file(tmp_path / "Casing Review_x.xlsx")
    assert url == "/output/Casing Review_x.xlsx"
    assert len(calls) == 1


def test_a_failed_mount_is_retried_on_the_next_call(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    attempts = []

    def flaky(directory):
        attempts.append(directory)
        if len(attempts) == 1:
            raise RuntimeError("mount failed")

    monkeypatch.setattr(output_mount, "_do_mount", flaky)
    output_mount.serve_output_file(tmp_path / "a.xlsx")
    output_mount.serve_output_file(tmp_path / "b.xlsx")
    assert len(attempts) == 2, "a failed mount must be retried"


def test_a_successful_mount_is_not_repeated(tmp_path, monkeypatch):
    monkeypatch.setattr(output_mount, "_mounted", False, raising=False)
    attempts = []
    monkeypatch.setattr(output_mount, "_do_mount", lambda d: attempts.append(d))
    output_mount.serve_output_file(tmp_path / "a.xlsx")
    output_mount.serve_output_file(tmp_path / "b.xlsx")
    assert len(attempts) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_output_mount.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.ui.output_mount'`

- [ ] **Step 3: Write the implementation**

Create `etools/ui/output_mount.py`:

```python
"""Serve generated workbooks over /output.

Previously duplicated in casing_review_tab and wcr_tab, both of which set
their "already mounted" flag unconditionally after a bare
``except Exception: pass`` -- so a single failed mount disabled every
Open-folder link for the rest of the process lifetime.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app

from etools.config import settings
from etools.logging_setup import get_logger

log = get_logger(__name__)

MOUNT_PATH = "/output"
_mounted = False


def _do_mount(directory: str) -> None:
    from starlette.staticfiles import StaticFiles

    app.mount(
        MOUNT_PATH, StaticFiles(directory=directory), name="etools_output"
    )


def serve_output_file(path: Path | str) -> str:
    """Return the browser URL for a generated file, mounting /output once."""
    global _mounted
    if not _mounted:
        out_dir = Path(settings.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            _do_mount(str(out_dir))
        except Exception as exc:
            # Deliberately do NOT latch: the usual cause is a transient
            # missing directory, and latching made the failure permanent.
            log.warning(
                "output_mount.failed", directory=str(out_dir), error=str(exc)
            )
            return f"{MOUNT_PATH}/{Path(path).name}"
        _mounted = True
    return f"{MOUNT_PATH}/{Path(path).name}"
```

- [ ] **Step 4: Replace both duplicated helpers**

In `etools/ui/tabs/casing_review_tab.py`, delete the private `_serve_output_file` function (`:2573-2586`) and import the shared one:

```python
from etools.ui.output_mount import serve_output_file as _serve_output_file
```

Do the same in `etools/ui/tabs/wcr_tab.py`. The alias keeps every existing call site unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_output_mount.py -q`

Expected: PASS (3 passed)

- [ ] **Step 6: Fast gate, then full gate**

Expected: 44 passed; then 165 passed (162 + 3).

- [ ] **Step 7: Commit**

```bash
git add etools/ui/output_mount.py etools/ui/tabs/casing_review_tab.py \
        etools/ui/tabs/wcr_tab.py tests/test_output_mount.py
git commit -m "fix(ui): retry the /output mount instead of latching on the first failure"
```

### Task 9: KOP detection on short and duplicate-MD surveys

Spec 7.B4. Three separate silent degradations in `kop.py`:
- `:65` `medfilt(inc, kernel_size=max(3, window | 1))` zero-pads (with a `UserWarning`) when the survey is shorter than the kernel. `detect_kop` checks only `survey.empty` at `:57`. This also **softens earlier finding #26**, which predicted a hard `ValueError`.
- `:66` `np.gradient(smoothed, md, edge_order=2)` divides by zero on duplicate MDs and emits NaN; `nan > threshold` is `False`, so candidates vanish silently.
- `:390-402` `_kop_clustering` swallows every exception with no log, dropping one of five consensus voters invisibly.

**Files:**
- Modify: `etools/core/survey/kop.py:56-70` and `:390-402`
- Test: `tests/test_kop_guards.py`

**Interfaces:**
- `detect_kop` keeps its signature and its `KOPResult` return type. On an input too short to analyse it returns `KOPResult(md=None, confidence=0.0, method="insufficient_data", candidates={})` rather than garbage.

- [ ] **Step 1: Write the failing test**

Create `tests/test_kop_guards.py`:

```python
"""KOP detection must degrade honestly on thin or malformed surveys."""
from __future__ import annotations

import warnings

import pandas as pd

from etools.core.survey.kop import detect_kop


def _survey(mds, incs):
    return pd.DataFrame(
        {"measured_depth": mds, "inclination": incs, "azimuth": [0.0] * len(mds)}
    )


def test_empty_survey_reports_none():
    r = detect_kop(_survey([], []))
    assert r.md is None
    assert r.method == "none"


def test_three_station_survey_does_not_emit_a_scipy_padding_warning():
    thin = _survey([0.0, 100.0, 200.0], [0.0, 1.0, 2.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        r = detect_kop(thin)  # must not raise a zero-padding UserWarning
    assert r.md is None or isinstance(r.md, float)


def test_survey_shorter_than_the_kernel_reports_insufficient_data():
    r = detect_kop(_survey([0.0, 50.0], [0.0, 0.5]))
    assert r.md is None
    assert r.method == "insufficient_data"
    assert r.confidence == 0.0


def test_duplicate_measured_depths_do_not_produce_nan_gradients():
    mds = [0.0, 100.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    incs = [0.0, 0.5, 0.6, 1.0, 12.0, 30.0, 55.0, 80.0]
    r = detect_kop(_survey(mds, incs))
    # With duplicate MDs np.gradient divides by zero and every candidate
    # silently drops out; after the dedupe a real KOP is found.
    assert r.md is not None
    assert r.confidence > 0.0


def test_a_normal_survey_still_finds_a_kop():
    mds = [float(x) for x in range(0, 3000, 100)]
    incs = [0.0] * 10 + [float(i * 6) for i in range(1, 21)]
    r = detect_kop(_survey(mds, incs))
    assert r.md is not None
    assert 500.0 <= r.md <= 2000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_kop_guards.py -q`

Expected: FAIL — the short-survey tests fail (no `insufficient_data` path, and scipy's padding `UserWarning` is raised as an error).

- [ ] **Step 3: Write the implementation**

In `etools/core/survey/kop.py`, replace the head of `detect_kop` (currently `:57-66`):

```python
    if survey.empty:
        return KOPResult(md=None, confidence=0.0, method="none", candidates={})

    df = survey.sort_values(md_col).reset_index(drop=True)
    # Duplicate MDs make np.gradient divide by zero and emit NaN for those
    # stations. Every candidate test is a `> threshold` comparison, and
    # `nan > x` is False, so the candidates vanished silently instead of
    # anyone learning the survey had duplicate depths.
    before = len(df)
    df = df.drop_duplicates(subset=md_col, keep="first").reset_index(drop=True)
    if len(df) < before:
        log.warning(
            "kop.duplicate_md_dropped", dropped=before - len(df), kept=len(df)
        )

    # medfilt zero-pads (with a UserWarning) when the kernel exceeds the
    # signal length, which silently produces garbage rather than raising.
    kernel = max(3, window | 1)
    if len(df) < kernel:
        log.warning(
            "kop.survey_too_short", stations=len(df), kernel=kernel
        )
        return KOPResult(
            md=None, confidence=0.0, method="insufficient_data", candidates={}
        )

    inc = df[inc_col].to_numpy(dtype=float)
    md = df[md_col].to_numpy(dtype=float)

    # Median-filter to suppress single-point noise spikes; rolling stats for ROC.
    smoothed = medfilt(inc, kernel_size=kernel)
    grad = np.gradient(smoothed, md, edge_order=2)
```

Confirm `log` is already bound in this module; if not, add `from etools.logging_setup import get_logger` and `log = get_logger(__name__)`.

Then give `_kop_clustering` (`:390-402`) a log line so a dropped voter is traceable:

```python
    except Exception as exc:
        log.warning("kop.clustering_failed", error=str(exc))
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_kop_guards.py -q`

Expected: PASS (5 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 170 passed (165 + 5). Watch `test_wcr_south_moon` and `test_survey_edits` closely — the dedupe changes station indices for any real survey that carries duplicate MDs, and a shifted KOP there is a genuine result worth reporting, not a test to relax.

- [ ] **Step 6: Commit**

```bash
git add etools/core/survey/kop.py tests/test_kop_guards.py
git commit -m "fix(kop): reject too-short surveys and dedupe MDs instead of returning silent garbage"
```

### Task 10: Say when a spatial join has no CRS to validate

Spec 7.B5. `locator.py:38` forcibly assigns `sections.crs` to the points frame instead of reprojecting. A gross mismatch yields all-NaN `Conc` (visible); a subtle one silently mis-locates points into the wrong section.

A real reprojection is out of scope — the callers genuinely do supply UTM 12N eastings and the assignment is correct in practice. What is missing is any record that the assumption was never checked.

**Files:**
- Modify: `etools/core/plat/locator.py:36-47`
- Test: `tests/test_locator_crs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_locator_crs.py`:

```python
"""The spatial join must record that it assumed a CRS rather than checking."""
from __future__ import annotations

import inspect

from etools.core.plat import locator


def test_crs_assumption_is_documented_at_the_assignment():
    src = inspect.getsource(locator.locate_points)
    assert "crs=sections.crs" in src
    lowered = src.lower()
    assert "assum" in lowered or "not reprojected" in lowered, (
        "the forced CRS assignment must carry an explicit comment"
    )


def test_locator_logs_the_match_rate():
    src = inspect.getsource(locator.locate_points)
    assert "matched" in src or "match_rate" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_locator_crs.py -q`

Expected: FAIL on the comment assertion.

- [ ] **Step 3: Write the implementation**

In `etools/core/plat/locator.py`, replace the GeoDataFrame construction with:

```python
    # NOTE: this ASSIGNS the sections' CRS to the points, it does not
    # reproject them. Callers are expected to pass UTM zone 12N eastings
    # and northings, which is what the plat sections use. A gross mismatch
    # (feet vs metres) shows up as an all-NaN Conc and is caught by the
    # match-rate warning below; a subtle one (NAD83 vs NAD27) would not be
    # caught at all, which is why the rate is logged on every call.
    pts_gdf = gpd.GeoDataFrame(points.copy(), geometry=geom, crs=sections.crs)
```

Then, after the existing `joined` assignment and duplicate-drop, add:

```python
    matched = int(joined["Conc"].notna().sum())
    total = len(joined)
    if total and matched == 0:
        log.warning(
            "plat.locate_points.no_matches",
            points=total,
            sections_crs=str(sections.crs),
            hint="every point fell outside every section - check the input CRS",
        )
    elif total and matched < total:
        log.info("plat.locate_points.partial", matched=matched, total=total)
```

If a match-rate log already exists at that spot, extend it rather than duplicating.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_locator_crs.py -q`

Expected: PASS (2 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 172 passed (170 + 2).

- [ ] **Step 6: Change log, commit and push (end of Phase 5)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-latches-kop-crs.md
git add etools/core/plat/locator.py tests/test_locator_crs.py \
        CHANGELOG/2026-08-25-latches-kop-crs.md CHANGELOG/README.md
git commit -m "fix(plat): log the spatial-join match rate and document the CRS assumption"
git push
```

---

# Phase 6 — Coordinates and the network layer

Spec: 7.C2, 7.C3, 7.C5.

### Task 11: Range-guard `utm_to_latlon`

Spec 7.C2. `converter.py:58-60` calls `utm.to_latlon` with no validation, unlike `_validate_latlon`, `dms_to_decimal` and `parse_coord_pair`, which all raise clean `ValueError`s. The escaping `utm.OutOfRangeError` is **not** a `ValueError`, which is the precise mechanism behind break case §6/E2: the Survey tab's `except ValueError` at `survey_tab.py:351-355` misses it, so swapping lat and lon makes "Reprocess with new SHL" do nothing at all — no dialog, no notification.

**Files:**
- Modify: `etools/core/coordinates/converter.py:55-60`
- Modify: `etools/ui/tabs/survey_tab.py:347-365` (widen the handler's except to cover the call)
- Test: `tests/test_coordinate_guards.py`

**Interfaces:**
- `utm_to_latlon(easting, northing, zone_number, zone_letter)` keeps its signature and raises `ValueError` (never `utm.OutOfRangeError`) for out-of-range input.

- [ ] **Step 1: Write the failing test**

Create `tests/test_coordinate_guards.py`:

```python
"""utm_to_latlon must raise ValueError like its sibling converters."""
from __future__ import annotations

import math

import pytest

from etools.core.coordinates.converter import utm_to_latlon


def test_a_valid_utm_pair_round_trips():
    lat, lon = utm_to_latlon(555247.77, 4457938.89, 12, "N")
    assert 40.0 < lat < 40.5
    assert -111.0 < lon < -110.0


def test_swapped_lat_lon_raises_value_error():
    # This is the real break case: the user typed longitude into the
    # easting box. utm.OutOfRangeError is NOT a ValueError, so the Survey
    # tab's except ValueError used to miss it entirely.
    with pytest.raises(ValueError):
        utm_to_latlon(-110.3502, 40.2701, 12, "N")


def test_non_finite_input_raises_value_error():
    with pytest.raises(ValueError):
        utm_to_latlon(float("nan"), 4457938.89, 12, "N")
    with pytest.raises(ValueError):
        utm_to_latlon(555247.77, float("inf"), 12, "N")


def test_bad_zone_raises_value_error():
    with pytest.raises(ValueError):
        utm_to_latlon(555247.77, 4457938.89, 99, "N")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_coordinate_guards.py -q`

Expected: FAIL — `utm.error.OutOfRangeError` is raised instead of `ValueError`, so `pytest.raises(ValueError)` does not match.

- [ ] **Step 3: Write the implementation**

In `etools/core/coordinates/converter.py`, replace `utm_to_latlon`:

```python
def utm_to_latlon(
    easting: float, northing: float, zone_number: int, zone_letter: str
) -> tuple[float, float]:
    """Project a UTM coordinate back to WGS84 lat/lon.

    Raises ``ValueError`` on anything unusable. The ``utm`` package raises
    its own ``OutOfRangeError``, which is NOT a ``ValueError`` -- callers
    that guard with ``except ValueError`` (survey_tab's "Reprocess with new
    SHL" among them) were silently missing it, so a swapped lat/lon pair
    made the button do nothing at all.
    """
    try:
        e = float(easting)
        n = float(northing)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"UTM easting/northing must be numbers; got {easting!r}, {northing!r}"
        ) from exc
    if not math.isfinite(e) or not math.isfinite(n):
        raise ValueError(
            f"UTM easting/northing must be finite; got {easting!r}, {northing!r}"
        )
    try:
        lat, lon = utm.to_latlon(e, n, zone_number, zone_letter)
    except Exception as exc:
        # utm raises OutOfRangeError (not a ValueError) for a bad easting,
        # northing or zone. Normalise so every converter in this module
        # fails the same way.
        raise ValueError(
            f"Not a valid UTM coordinate: easting={e}, northing={n}, "
            f"zone={zone_number}{zone_letter} ({exc})"
        ) from exc
    return float(lat), float(lon)
```

Ensure `import math` is present at the top of the module.

- [ ] **Step 4: Widen the Survey tab handler**

In `etools/ui/tabs/survey_tab.py`, `reprocess_shl` currently wraps only `dms_to_decimal` in `try/except ValueError` at `:351-355`, leaving the `utm_to_latlon` call at `:361` outside it. Extend the existing `try` block to enclose the conversion call too, so the existing `except ValueError` branch handles it and the user gets the notification that was previously missing.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_coordinate_guards.py -q`

Expected: PASS (4 passed)

- [ ] **Step 6: Verify break case E2 is closed**

```bash
.venv/Scripts/python.exe -c "
from etools.core.coordinates.converter import utm_to_latlon
try:
    utm_to_latlon(-110.3502, 40.2701, 12, 'N')
except ValueError as e:
    print('now a ValueError:', str(e)[:80])
except Exception as e:
    print('STILL LEAKING', type(e).__name__)
"
```

Expected: `now a ValueError: ...`.

- [ ] **Step 7: Fast gate, then full gate**

Expected: 44 passed; then 176 passed (172 + 4).

- [ ] **Step 8: Commit**

```bash
git add etools/core/coordinates/converter.py etools/ui/tabs/survey_tab.py \
        tests/test_coordinate_guards.py
git commit -m "fix(coords): raise ValueError from utm_to_latlon so callers actually catch it"
```

### Task 12: Ollama response handling

Spec 7.C3 and 7.C5. Two gaps in `ollama_client.py`:
- `:189` and `:95` call `r.json()` unguarded. A 200 with a non-JSON body raises `json.JSONDecodeError` — a `ValueError`, so `has_model`'s `except (httpx.HTTPError, KeyError)` misses it — and it surfaces several frames up mis-attributed as "LLM extraction failed".
- Truncation by `num_predict: 2048` is never detected. Ollama reports `done_reason == "length"`; the code never reads it, so a truncated response is indistinguishable from any other malformed one.

Retries are deliberately **not** added — `ddr_llm.py:485-499`'s chunk-splitting is the one retry that exists and it is a smarter response than blind repetition.

**Files:**
- Modify: `etools/core/llm/ollama_client.py:91-98` (`has_model`) and `:184-206` (`chat_json`)
- Test: `tests/test_ollama_client_guards.py`

**Interfaces:**
- `chat_json` raises `OllamaUnavailableError` (existing type, already handled by every caller) for a non-JSON body and for a truncated response. `has_model` returns `False` for a non-JSON body instead of raising.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ollama_client_guards.py`:

```python
"""Ollama transport guards: bad bodies and truncated responses."""
from __future__ import annotations

import json

import pytest

from etools.core.llm.ollama_client import OllamaClient, OllamaUnavailableError


class _Resp:
    def __init__(self, status=200, payload=None, text="", raise_json=False):
        self.status_code = status
        self._payload = payload
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise json.JSONDecodeError("Expecting value", "<html>", 0)
        return self._payload

    def raise_for_status(self):
        return None


def test_non_json_body_becomes_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _Resp(raise_json=True, text="<html>bad gateway</html>"),
    )
    with pytest.raises(OllamaUnavailableError) as ei:
        OllamaClient().chat_json("hi")
    assert "json" in str(ei.value).lower()


def test_truncated_response_is_detected(monkeypatch):
    payload = {
        "message": {"content": '{"partial": tru'},
        "done_reason": "length",
        "eval_count": 2048,
    }
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(payload=payload))
    with pytest.raises(OllamaUnavailableError) as ei:
        OllamaClient().chat_json("hi")
    assert "truncat" in str(ei.value).lower()


def test_a_complete_response_is_returned(monkeypatch):
    payload = {
        "message": {"content": '{"ok": true}'},
        "done_reason": "stop",
        "eval_count": 12,
    }
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(payload=payload))
    assert OllamaClient().chat_json("hi") == '{"ok": true}'


def test_has_model_returns_false_on_a_non_json_body(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(raise_json=True))
    assert OllamaClient().has_model("anything") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ollama_client_guards.py -q`

Expected: FAIL — the JSONDecodeError propagates raw from both `chat_json` and `has_model`, and the truncated response is returned as if valid.

- [ ] **Step 3: Write the implementation**

In `etools/core/llm/ollama_client.py`, replace the body of `has_model` after `raise_for_status()`:

```python
    def has_model(self, model: str | None = None) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=4.0)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
        except (httpx.HTTPError, KeyError, ValueError):
            # ValueError covers json.JSONDecodeError -- a proxy returning an
            # HTML error page used to escape here and get mis-reported
            # several frames up as "LLM extraction failed".
            return False
        return (model or self.model) in names
```

Then in `chat_json`, replace the block from `data = r.json()` (`:189`) through the `content` assignment:

```python
        try:
            data = r.json()
        except ValueError as exc:  # json.JSONDecodeError
            raise OllamaUnavailableError(
                f"Ollama returned a non-JSON body ({len(r.text)} chars): "
                f"{r.text[:200]}"
            ) from exc

        if data.get("done_reason") == "length":
            # num_predict cut the model off mid-object. Without this check a
            # truncated response was indistinguishable from any other
            # malformed one, and the caller reported an empty field.
            log.warning(
                "llm.response_truncated",
                num_predict=body["options"]["num_predict"],
                eval_count=data.get("eval_count"),
            )
            raise OllamaUnavailableError(
                "Ollama response was truncated at the num_predict limit "
                f"({body['options']['num_predict']} tokens); the extraction "
                "for this layer was skipped."
            )

        content = data.get("message", {}).get("content", "")
```

Every caller already wraps these in a broad `except Exception` that appends a warning, so this degrades to a named warning instead of a mystery empty field.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ollama_client_guards.py -q`

Expected: PASS (4 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 180 passed (176 + 4). No test in the suite requires a live Ollama, so this must not change any existing result.

- [ ] **Step 6: Change log, commit and push (end of Phase 6)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-coords-and-llm-transport.md
git add etools/core/llm/ollama_client.py tests/test_ollama_client_guards.py \
        CHANGELOG/2026-08-25-coords-and-llm-transport.md CHANGELOG/README.md
git commit -m "fix(llm): detect truncated and non-JSON Ollama responses instead of mis-reporting them"
git push
```

---

# Phase 7 — Half-updated state

Spec: 7.D1, 7.D2, 7.D3. Ranked #5. This is the same shape as §6's dominant pattern: some fields advance to the new well, neighbouring ones do not, and nothing on screen says the display is a mixture.

### Task 13: Stage `post_load_orchestrate`'s writes

`app.py:172-352` writes `state.processed` (:178), `state.clearances` (:238) and `state.section_definitions` (:286) in sequence with no rollback. A step-2 failure leaves the new well's survey next to the old well's clearances.

**Files:**
- Modify: `etools/ui/app.py:142-352` (`post_load_orchestrate`)
- Test: `tests/test_post_load_staging.py`

**Interfaces:**
- Produces: `etools/ui/state_staging.py` with `staged_well_fields(state) -> ContextManager[dict]` — collects the new values and commits them to `state` in one step on clean exit; on failure clears all of them together so the app shows one consistent empty well rather than two mixed ones.

Clearing rather than restoring is deliberate: the previous values belong to a different well and restoring them would recreate the very mixture this fixes. An empty, obviously-unloaded state is honest.

> **DEVIATION (applied 2026-08-25).** The staging-dict design below was
> abandoned during implementation. `post_load_orchestrate` *reads*
> `state.processed`, `state.clearances` and `state.section_definitions` at a
> dozen points between the writes (`app.py:194-291`), so redirecting the
> writes to a dict would have required rewriting every one of those reads —
> a large, risky diff for a defensive fix. The same user-visible guarantee
> (never show two wells mixed) is achieved by keeping the direct writes and
> clearing the whole group on failure. See `clear_group_on_failure`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_post_load_staging.py`:

```python
"""A failed orchestration must not leave two wells' data side by side."""
from __future__ import annotations

import pytest

from etools.ui.state import AppState
from etools.ui.state_staging import staged_well_fields

FIELDS = ("processed", "clearances", "section_definitions")


def _loaded_state():
    s = AppState()
    s.processed = {"AsDrilled": "OLD-processed"}
    s.clearances = {"AsDrilled": "OLD-clearances"}
    s.section_definitions = {"2303S02WU": "OLD-sections"}
    return s


def test_successful_staging_commits_every_field():
    s = _loaded_state()
    with staged_well_fields(s, FIELDS) as staged:
        staged["processed"] = {"AsDrilled": "NEW-processed"}
        staged["clearances"] = {"AsDrilled": "NEW-clearances"}
        staged["section_definitions"] = {"x": "NEW-sections"}
    assert s.processed == {"AsDrilled": "NEW-processed"}
    assert s.clearances == {"AsDrilled": "NEW-clearances"}
    assert s.section_definitions == {"x": "NEW-sections"}


def test_nothing_is_committed_until_the_block_exits():
    s = _loaded_state()
    with staged_well_fields(s, FIELDS) as staged:
        staged["processed"] = {"AsDrilled": "NEW-processed"}
        # Mid-block, state must still hold the old well untouched.
        assert s.processed == {"AsDrilled": "OLD-processed"}


def test_a_failure_clears_every_staged_field_rather_than_mixing():
    s = _loaded_state()
    with pytest.raises(RuntimeError):
        with staged_well_fields(s, FIELDS) as staged:
            staged["processed"] = {"AsDrilled": "NEW-processed"}
            raise RuntimeError("clearances blew up")
    # The new well's survey must NOT be left sitting next to the old
    # well's clearances.
    assert not s.processed
    assert not s.clearances
    assert not s.section_definitions


def test_partial_staging_commits_only_what_was_set():
    s = _loaded_state()
    with staged_well_fields(s, FIELDS) as staged:
        staged["processed"] = {"AsDrilled": "NEW"}
    # Unset fields keep their previous value on the success path.
    assert s.processed == {"AsDrilled": "NEW"}
    assert s.clearances == {"AsDrilled": "OLD-clearances"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_post_load_staging.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.ui.state_staging'`

- [ ] **Step 3: Write the implementation**

Create `etools/ui/state_staging.py`:

```python
"""Commit a group of per-well AppState fields together, or not at all.

``post_load_orchestrate`` writes ``state.processed``, ``state.clearances``
and ``state.section_definitions`` in sequence. A failure part-way through
used to leave the new well's survey sitting next to the previous well's
clearances, with nothing on screen saying the display was a mixture.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from etools.logging_setup import get_logger

log = get_logger(__name__)


@contextmanager
def staged_well_fields(state: Any, fields: Sequence[str]) -> Iterator[dict]:
    """Yield a staging dict; assign it onto ``state`` only on clean exit.

    On failure every named field is reset to an empty dict instead of being
    restored. The previous values describe a *different* well, so restoring
    them would recreate the mixture this exists to prevent -- an obviously
    unloaded state is the honest outcome.
    """
    staged: dict[str, Any] = {}
    try:
        yield staged
    except BaseException:
        log.warning(
            "state.staged_commit_aborted",
            fields=list(fields),
            staged=sorted(staged),
        )
        for name in fields:
            setattr(state, name, {})
        raise
    for name, value in staged.items():
        setattr(state, name, value)
```

- [ ] **Step 4: Wire it into `post_load_orchestrate`**

In `etools/ui/app.py`, add the import:

```python
from etools.ui.state_staging import staged_well_fields
```

Then wrap the three assignments. The existing structure keeps its inner `try/except ... raise` blocks and its outer `except Exception` / `finally: busy_dialog.close()`; only the assignment targets change:

- `state.processed = await loop.run_in_executor(...)` becomes `staged["processed"] = await loop.run_in_executor(...)`
- `state.clearances = await loop.run_in_executor(None, _calc)` becomes `staged["clearances"] = ...`
- the section-definitions assignment at `:286` becomes `staged["section_definitions"] = ...`

with the whole sequence inside:

```python
        with staged_well_fields(
            state, ("processed", "clearances", "section_definitions")
        ) as staged:
            ...
```

Two details to preserve:
- Step 2b's handler currently swallows rather than re-raising (`log.exception("post_load.section_defs.failed")` with no `raise`). Keep that — it is intentional — but have it write `staged["section_definitions"] = {}` explicitly so a failed seed clears the previous well's sections instead of silently keeping them (spec 7.D2).
- Any code between the staged assignments that *reads* `state.processed` must read `staged["processed"]` instead, since the commit has not happened yet. Check the `upsert_active_document` call and the clearance step's inputs before finishing.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_post_load_staging.py -q`

Expected: PASS (4 passed)

- [ ] **Step 6: Manual verification (requires a restart)**

`Stop ETools.bat`, then `Launch ETools.bat`. Load a well, run Calculate Clearances, then load a *different* well whose clearance calculation fails (or temporarily stop SQL Server after the survey step). Confirm the tabs come up empty rather than showing the new survey beside the old clearances, and that the error toast still appears.

- [ ] **Step 7: Fast gate, then full gate**

Expected: 44 passed; then 184 passed (180 + 4).

- [ ] **Step 8: Commit**

```bash
git add etools/ui/state_staging.py etools/ui/app.py tests/test_post_load_staging.py
git commit -m "fix(ui): commit post-load state as a unit so a failure can't mix two wells"
```

### Task 14: A saved segment override whose refresh failed must say so

Spec 7.D3. `casing_review_tab.py:1945-1972` mutates `sd.segment_overrides` first, then calls `_fire_viz_refresh()`, whose two callbacks are each `except Exception: log.warning(...)` with no notify. The override is persisted and feeds the Excel generator, but the plat SVG and map do not repaint — so the user sees no change, assumes the edit did not take, and edits again.

**Files:**
- Modify: `etools/ui/tabs/casing_review_tab.py:1932-1943` (`_fire_viz_refresh`)
- Test: `tests/test_segment_override_feedback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_segment_override_feedback.py`:

```python
"""A failed post-edit refresh must be visible, not log-only."""
from __future__ import annotations

import inspect

from etools.ui.tabs import casing_review_tab


def test_fire_viz_refresh_notifies_on_failure():
    src = inspect.getsource(casing_review_tab)
    idx = src.index("def _fire_viz_refresh")
    body = src[idx : idx + 1200]
    assert "ui.notify" in body, (
        "_fire_viz_refresh swallows refresh failures; the user must be told "
        "the edit was saved but the view did not repaint"
    )


def test_the_notify_explains_the_edit_was_still_saved():
    src = inspect.getsource(casing_review_tab)
    idx = src.index("def _fire_viz_refresh")
    body = src[idx : idx + 1200]
    assert "saved" in body.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_segment_override_feedback.py -q`

Expected: FAIL — no `ui.notify` in `_fire_viz_refresh`.

- [ ] **Step 3: Write the implementation**

Replace `_fire_viz_refresh` in `etools/ui/tabs/casing_review_tab.py`:

```python
    def _fire_viz_refresh() -> None:
        """Repaint the map and plat SVG after a geometry edit.

        The override has already been written to ``sd`` by the time we get
        here, so a failure means the data changed but the screen did not --
        which reads to the user as "my edit did nothing" and invites them to
        make the same edit twice.
        """
        failed = []
        for name, cb in (
            ("map", getattr(state, "viz_refresh", None)),
            ("plat", on_geometry_change),
        ):
            if cb is None:
                continue
            try:
                cb()
            except Exception as exc:
                log.warning(
                    "casing_review.viz_refresh_failed", target=name, error=str(exc)
                )
                failed.append(name)
        if failed:
            ui.notify(
                "Your edit was saved, but the "
                f"{' and '.join(failed)} view could not be redrawn. "
                "Switch tabs and back to refresh it.",
                type="warning",
            )
```

Match the existing callback names in the current implementation — if `on_geometry_change` is not in scope under that name, use whatever the current body calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_segment_override_feedback.py -q`

Expected: PASS (2 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 186 passed (184 + 2).

- [ ] **Step 6: Change log, commit and push (end of Phase 7)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-half-updated-state.md
git add etools/ui/tabs/casing_review_tab.py tests/test_segment_override_feedback.py \
        CHANGELOG/2026-08-25-half-updated-state.md CHANGELOG/README.md
git commit -m "fix(ui): tell the user when a geometry edit saved but the view failed to repaint"
git push
```

---

# Phase 8 — Resource leaks

Spec: 7.E. Lowest severity in the ranking, and the one place where doing less is defensible — but both leaks are unbounded and trivially fixable.

### Task 15: Close PyMuPDF documents

No `doc.close()` exists in `parser.py`, `apd_parser.py`, `wcr_parser.py` or `ddr_parser.py`. The single exception is `wcr_parser._slice_pdf`, which closes both handles. Every parse leaks a file handle until GC — and on Windows an unclosed handle keeps the temp PDF locked, which interacts badly with Task 16.

**Files:**
- Modify: `etools/core/pdf/parser.py:731`, `:824`, `:845`
- Modify: `etools/core/pdf/apd_parser.py:176`
- Modify: `etools/core/pdf/wcr_parser.py:435`, `:456`
- Modify: `etools/core/pdf/ddr_parser.py:71`
- Test: `tests/test_pdf_handles.py`

**Interfaces:** no signature changes. Each `fitz.open(...)` becomes a `with` block, or gains a `try/finally: doc.close()` where the document outlives a single expression.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pdf_handles.py`:

```python
"""Every PyMuPDF document must be closed, including on the error path."""
from __future__ import annotations

import inspect

import pytest

MODULES = [
    "etools.core.pdf.parser",
    "etools.core.pdf.apd_parser",
    "etools.core.pdf.wcr_parser",
    "etools.core.pdf.ddr_parser",
]


@pytest.mark.parametrize("modname", MODULES)
def test_every_fitz_open_is_closed(modname):
    mod = __import__(modname, fromlist=["*"])
    src = inspect.getsource(mod)
    opens = src.count("fitz.open(")
    closes = src.count(".close()") + src.count("with fitz.open(")
    assert closes >= opens, (
        f"{modname}: {opens} fitz.open() call(s) but only {closes} "
        "close()/with statement(s)"
    )


def test_a_parsed_pdf_releases_its_file_lock(tmp_path):
    # On Windows an unclosed fitz handle keeps the file locked, which is
    # what makes temp-file cleanup (Task 16) fail.
    import shutil

    from etools.core.pdf.apd_parser import parse_apd_pdf

    src = next(iter(tmp_path.parent.glob("**/*.pdf")), None)
    if src is None:
        pytest.skip("no sample PDF available")
    work = tmp_path / "sample.pdf"
    shutil.copyfile(src, work)
    try:
        parse_apd_pdf(work, mode="rules")
    except Exception:
        pass  # parsing may legitimately fail; the lock is what matters
    work.unlink()  # raises PermissionError if a handle is still open
    assert not work.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pdf_handles.py -q`

Expected: FAIL — every module reports more `fitz.open(` calls than closes.

- [ ] **Step 3: Write the implementation**

Convert each site. The common shape in `_extract_text` becomes:

```python
    with fitz.open(str(path)) as doc:
        parts = []
        for i in range(len(doc)):
            try:
                parts.append(doc[i].get_text())
            except Exception as exc:
                log.warning("apd_pdf.page_failed", page=i, error=str(exc))
        return "\n".join(parts)
```

PyMuPDF `Document` supports the context-manager protocol, so this is a direct substitution. Apply the same at `parser.py:731` (`vision_transcribe_page`), `:824` (`_pymupdf_extract_text` — keep its existing `except Exception` around the open, moving the `with` inside the `try`), `:845` (`_render_pages_to_png`), `wcr_parser.py:435` and `:456`, and `ddr_parser.py:71`.

Where the open is already inside a `try` that returns `""` on failure, keep that behavior — only the closing changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pdf_handles.py -q`

Expected: PASS (5 passed, or 4 passed + 1 skipped if no sample PDF is discoverable)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 191 passed (186 + 5). `test_wcr_south_moon` parses a real PDF end to end, so a mis-converted `with` block shows up there.

- [ ] **Step 6: Commit**

```bash
git add etools/core/pdf/parser.py etools/core/pdf/apd_parser.py \
        etools/core/pdf/wcr_parser.py etools/core/pdf/ddr_parser.py \
        tests/test_pdf_handles.py
git commit -m "fix(pdf): close PyMuPDF documents so parses stop leaking file handles"
```

### Task 16: Clean up uploaded temp files

All four `_save_upload` copies use `NamedTemporaryFile(delete=False)`, and there is no `unlink` anywhere in `etools/`. Every uploaded PDF stays in the OS temp directory permanently.

**Files:**
- Create: `etools/ui/upload_temp.py`
- Modify: `etools/ui/tabs/load_tab.py:436-454`, `etools/ui/tabs/casing_review_tab.py:2553`, `etools/ui/tabs/pdf_tab.py:667`, `etools/ui/tabs/wcr_tab.py:1180`
- Test: `tests/test_upload_temp.py`

**Interfaces:**
- Produces:
  - `save_upload(upload, name: str) -> str` (async) — the shared implementation the four copies collapse into
  - `sweep_stale_uploads(max_age_hours: float = 24.0) -> int` — deletes this app's leftovers, returns the count

Files are swept by age rather than deleted immediately after parsing, because `state.apd_pdf_path` is retained and re-read on regeneration — deleting on parse would break the "generate again without re-uploading" flow.

- [ ] **Step 1: Write the failing test**

Create `tests/test_upload_temp.py`:

```python
"""Uploaded PDFs must not accumulate in the temp directory forever."""
from __future__ import annotations

import os
import time
from pathlib import Path

from etools.ui import upload_temp


def test_prefix_is_distinctive_enough_to_sweep_safely():
    assert upload_temp.UPLOAD_PREFIX.startswith("etools-upload-")


def test_sweep_removes_only_old_etools_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_temp, "_temp_dir", lambda: tmp_path)
    old = tmp_path / f"{upload_temp.UPLOAD_PREFIX}old.pdf"
    new = tmp_path / f"{upload_temp.UPLOAD_PREFIX}new.pdf"
    other = tmp_path / "someone-elses-file.pdf"
    for p in (old, new, other):
        p.write_bytes(b"x")
    stale = time.time() - (48 * 3600)
    os.utime(old, (stale, stale))

    removed = upload_temp.sweep_stale_uploads(max_age_hours=24.0)

    assert removed == 1
    assert not old.exists()
    assert new.exists()
    assert other.exists(), "the sweep must never touch files it did not create"


def test_sweep_survives_a_locked_file(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_temp, "_temp_dir", lambda: tmp_path)
    locked = tmp_path / f"{upload_temp.UPLOAD_PREFIX}locked.pdf"
    locked.write_bytes(b"x")
    stale = time.time() - (48 * 3600)
    os.utime(locked, (stale, stale))
    fh = open(locked, "r+b")
    try:
        # Must not raise even though the file cannot be removed on Windows.
        upload_temp.sweep_stale_uploads(max_age_hours=24.0)
    finally:
        fh.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_upload_temp.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etools.ui.upload_temp'`

- [ ] **Step 3: Write the implementation**

Create `etools/ui/upload_temp.py`:

```python
"""Temp storage for uploaded PDFs, with an age-based sweep.

Four tabs each had their own ``_save_upload`` using
``NamedTemporaryFile(delete=False)``, and nothing in the package ever
deleted the result -- so every upload leaked a PDF into the OS temp
directory for the life of the machine.

Files are swept by age rather than removed right after parsing because
``state.apd_pdf_path`` is kept and re-read when the user regenerates
without re-uploading.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from etools.logging_setup import get_logger

log = get_logger(__name__)

UPLOAD_PREFIX = "etools-upload-"


def _temp_dir() -> Path:
    return Path(tempfile.gettempdir())


async def save_upload(upload, name: str) -> str:
    """Persist an uploaded file to a sweepable temp path."""
    suffix = Path(name).suffix or ".pdf"
    fh = tempfile.NamedTemporaryFile(
        delete=False, prefix=UPLOAD_PREFIX, suffix=suffix
    )
    tmp_path = fh.name
    fh.close()
    if upload is not None and hasattr(upload, "save"):
        await upload.save(tmp_path)
    elif upload is not None and hasattr(upload, "read"):
        read_result = upload.read()
        data = await read_result if hasattr(read_result, "__await__") else read_result
        Path(tmp_path).write_bytes(
            data if isinstance(data, bytes) else bytes(data)
        )
    else:
        raise RuntimeError(
            f"Don't know how to read upload object: {type(upload).__name__}"
        )
    return tmp_path


def sweep_stale_uploads(max_age_hours: float = 24.0) -> int:
    """Delete this app's leftover uploads. Returns how many were removed."""
    cutoff = time.time() - (max_age_hours * 3600.0)
    removed = 0
    try:
        candidates = list(_temp_dir().glob(f"{UPLOAD_PREFIX}*"))
    except OSError as exc:
        log.warning("upload_temp.sweep_listing_failed", error=str(exc))
        return 0
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            # Locked (still open in a viewer) or already gone. Never fatal.
            log.debug("upload_temp.sweep_skipped", path=str(path), error=str(exc))
    if removed:
        log.info("upload_temp.swept", removed=removed)
    return removed
```

- [ ] **Step 4: Collapse the four copies and call the sweep at startup**

In each of `load_tab.py`, `casing_review_tab.py`, `pdf_tab.py` and `wcr_tab.py`, delete the private `_save_upload` and import the shared one:

```python
from etools.ui.upload_temp import save_upload as _save_upload
```

The alias keeps every existing `await _save_upload(upload, name)` call site unchanged.

Then in `etools/main.py`'s `run()`, next to the preflight block from Task 1:

```python
    swept = sweep_stale_uploads()
    if swept:
        log.info("etools.startup.swept_uploads", removed=swept)
```

with `from etools.ui.upload_temp import sweep_stale_uploads` added to the imports.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_upload_temp.py -q`

Expected: PASS (3 passed)

- [ ] **Step 6: Fast gate, then full gate**

Expected: 44 passed; then 194 passed (191 + 3).

- [ ] **Step 7: Change log, commit and push (end of Phase 8)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-resource-leaks.md
git add etools/ui/upload_temp.py etools/ui/tabs/load_tab.py \
        etools/ui/tabs/casing_review_tab.py etools/ui/tabs/pdf_tab.py \
        etools/ui/tabs/wcr_tab.py etools/main.py tests/test_upload_temp.py \
        CHANGELOG/2026-08-25-resource-leaks.md CHANGELOG/README.md
git commit -m "fix(uploads): share one temp-file helper and sweep stale uploads at startup"
git push
```

---

# Phase 9 — Gaps found in self-review

These three come straight from the spec but did not fall naturally into an earlier phase. **7.C4 is ranked #6 in 7.I** and is the most consequential item in this phase.

### Task 17: Get the Load Well DB call off the event loop

Spec 7.C4. `app.py:521-530` calls `bundle = service.load(lookup)` synchronously inside an async page handler. Every *other* DB call site in the UI already uses `asyncio.to_thread` (`load_tab.py:286`, `casing_review_tab.py:445`, `wcr_tab.py:202`). With SQL Server unreachable, the blocking `pyodbc` connect freezes the whole NiceGUI server thread for the full ODBC timeout — the UI is dead for every connected client — and only then does the error toast appear.

**Files:**
- Modify: `etools/ui/app.py:519-543` (`load_handler`)
- Test: `tests/test_load_handler_offloads.py`

**Interfaces:** no signature change. `load_handler` stays `async`; only the call becomes `await asyncio.to_thread(service.load, lookup)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_load_handler_offloads.py`:

```python
"""The Load Well handler must not block the event loop on a DB call."""
from __future__ import annotations

import inspect

from etools.ui import app as app_module


def _load_handler_source() -> str:
    src = inspect.getsource(app_module)
    start = src.index("async def load_handler")
    return src[start : start + 1500]


def test_service_load_is_offloaded_to_a_thread():
    body = _load_handler_source()
    assert "service.load(lookup)" not in body, (
        "service.load is a blocking pyodbc call; it must not run on the loop"
    )
    assert "to_thread" in body or "run_in_executor" in body


def test_well_not_found_is_still_handled_separately():
    # The typed empty-state error must keep its friendly warning toast
    # rather than collapsing into the generic failure branch.
    body = _load_handler_source()
    assert "WellNotFoundError" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_load_handler_offloads.py -q`

Expected: FAIL — `service.load(lookup)` appears directly in the handler body.

- [ ] **Step 3: Write the implementation**

In `etools/ui/app.py`, confirm `import asyncio` is present at module scope (it is used by `fire_refresh`). Then change the call inside `load_handler`:

```python
                    try:
                        bundle = await asyncio.to_thread(service.load, lookup)
                    except WellNotFoundError as exc:
                        ui.notify(str(exc), type="warning")
                        return
                    except Exception as exc:  # pragma: no cover - bubble up to user
                        log.exception("well.load.failed", error=str(exc))
                        ui.notify(f"Load failed: {exc}", type="negative")
                        return
```

Both `except` branches are unchanged — only the call is offloaded. `WellNotFoundError` propagates out of `to_thread` intact, so the friendly empty-state toast still works.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_load_handler_offloads.py -q`

Expected: PASS (2 passed)

- [ ] **Step 5: Manual verification (requires a restart)**

`Stop ETools.bat`, `Launch ETools.bat`. Point `ETOOLS_DB__SERVER` at an unreachable host (or stop the SQL Server service), then click Load Well. The spinner must stay responsive and other tabs must remain clickable during the connect timeout, with the red toast arriving at the end. Before this change the whole page froze.

- [ ] **Step 6: Fast gate, then full gate**

Expected: 44 passed; then 196 passed (194 + 2).

- [ ] **Step 7: Commit**

```bash
git add etools/ui/app.py tests/test_load_handler_offloads.py
git commit -m "fix(ui): offload the Load Well DB call so an outage can't freeze the server"
```

### Task 18: Update the WCR grid before swapping the data model

Spec 7.D4. `wcr_tab.py:406-450` assigns `result.location_rows = new_rows` at `:424`, then updates the on-screen labels in a loop whose per-row handler is `except Exception: log.debug(...)`. Stale widgets leave the visible grid showing old values while the exported Excel already uses the new ones — a data/display divergence with no signal.

**Files:**
- Modify: `etools/ui/tabs/wcr_tab.py:406-450` (`recalculate_edits`)
- Test: `tests/test_wcr_recalculate_feedback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_wcr_recalculate_feedback.py`:

```python
"""A partially-repainted WCR grid must not silently diverge from the data."""
from __future__ import annotations

import inspect

from etools.ui.tabs import wcr_tab


def _recalc_source() -> str:
    src = inspect.getsource(wcr_tab)
    start = src.index("def recalculate_edits")
    return src[start : start + 2000]


def test_row_repaint_failures_are_counted_and_surfaced():
    body = _recalc_source()
    assert "ui.notify" in body, (
        "recalculate_edits must tell the user when rows failed to repaint"
    )


def test_repaint_failures_are_not_only_debug_logged():
    body = _recalc_source()
    # A bare log.debug swallow is what allowed the divergence.
    assert body.count("log.debug") <= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wcr_recalculate_feedback.py -q`

Expected: FAIL — no `ui.notify` inside `recalculate_edits`.

- [ ] **Step 3: Write the implementation**

In `etools/ui/tabs/wcr_tab.py`, keep the assignment where it is (the data model *should* advance — the recompute succeeded), but count the repaint failures and tell the user. Replace the label-update loop's exception handling so it accumulates:

```python
        result.location_rows = new_rows
        stale = 0
        for i, row in enumerate(new_rows):
            try:
                <existing per-row label updates, unchanged>
            except Exception as exc:
                stale += 1
                log.debug("wcr.row_repaint_failed", row=i, error=str(exc))
        if stale:
            log.warning("wcr.rows_not_repainted", rows=stale, total=len(new_rows))
            ui.notify(
                f"{stale} of {len(new_rows)} rows could not be redrawn. The "
                "recalculated values are saved and will be used in the "
                "export - switch tabs and back to see them.",
                type="warning",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wcr_recalculate_feedback.py -q`

Expected: PASS (2 passed)

- [ ] **Step 5: Fast gate, then full gate**

Expected: 44 passed; then 198 passed (196 + 2).

- [ ] **Step 6: Commit**

```bash
git add etools/ui/tabs/wcr_tab.py tests/test_wcr_recalculate_feedback.py
git commit -m "fix(wcr): report rows that failed to repaint after a recalculation"
```

### Task 19: A zero-length boundary must not report a confident 0 degrees

Spec 7.B6. `grid_corners.py:119-127` computes `atan2(d_east, d_north)`. When a boundary is genuinely zero-length both deltas are zero, `atan2(0, 0)` returns exactly `0.0`, and the result is emitted as a real bearing due north rather than "no boundary data".

**Files:**
- Modify: `etools/core/casing_review/grid_corners.py:115-130`
- Test: `tests/test_grid_bearing_guards.py`

**Interfaces:** `_bearing_to_dms_alignment` returns `None` instead of a bearing when the boundary has no length. Its callers must already tolerate `None` — verify before changing, and if they do not, return `None` and have the caller skip that side.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grid_bearing_guards.py`:

```python
"""A zero-length section boundary has no bearing, not a bearing of zero."""
from __future__ import annotations

from etools.core.casing_review.grid_corners import _bearing_to_dms_alignment


def test_a_real_boundary_yields_a_bearing():
    assert _bearing_to_dms_alignment(0.0, 0.0, 1000.0, 0.0) is not None


def test_a_zero_length_boundary_yields_none():
    # atan2(0, 0) is exactly 0.0, which used to be emitted as a confident
    # due-north bearing for a boundary that does not exist.
    assert _bearing_to_dms_alignment(500.0, 500.0, 500.0, 500.0) is None


def test_a_sub_millimetre_boundary_yields_none():
    assert _bearing_to_dms_alignment(0.0, 0.0, 1e-9, 1e-9) is None
```

Adjust the call signature in this test to match the real one before running — check it with:

```bash
grep -n "_bearing_to_dms_alignment" etools/core/casing_review/grid_corners.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_grid_bearing_guards.py -q`

Expected: FAIL — the zero-length case returns a bearing rather than `None`.

- [ ] **Step 3: Write the implementation**

In `etools/core/casing_review/grid_corners.py`, guard before the `atan2`:

```python
    d_east = x2 - x1
    d_north = y2 - y1
    # atan2(0, 0) returns exactly 0.0, so a boundary with no length used to
    # be reported as a confident bearing due north instead of "no data".
    if math.hypot(d_east, d_north) < _MIN_BOUNDARY_LEN_M:
        log.warning(
            "grid_corners.zero_length_boundary", d_east=d_east, d_north=d_north
        )
        return None
```

with a module constant near the other constants:

```python
# Below this the two corners are the same point to within survey precision.
_MIN_BOUNDARY_LEN_M = 1e-6
```

Match the real parameter names in the function; the snippet above assumes `x1, y1, x2, y2`.

- [ ] **Step 4: Confirm callers tolerate `None`**

```bash
grep -n "_bearing_to_dms_alignment" -A6 etools/core/casing_review/grid_corners.py
```

If any caller unpacks the result directly, add a `None` check that skips that side rather than writing a bearing. Do not invent a fallback bearing — the whole point is that there isn't one.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_grid_bearing_guards.py -q`

Expected: PASS (3 passed)

- [ ] **Step 6: Fast gate, then full gate**

Expected: 44 passed; then 201 passed (198 + 3). `test_grid_derivation` covers this module directly — a change in any real section's derived bearings shows up there and would be a genuine finding, not a test to relax.

- [ ] **Step 7: Change log, commit and push (end of Phase 9)**

```bash
cp CHANGELOG/TEMPLATE.md CHANGELOG/2026-08-25-event-loop-and-bearing-guards.md
git add etools/core/casing_review/grid_corners.py tests/test_grid_bearing_guards.py \
        CHANGELOG/2026-08-25-event-loop-and-bearing-guards.md CHANGELOG/README.md
git commit -m "fix(grid): return None for a zero-length boundary instead of a due-north bearing"
git push
```

---

# Closing out

- [ ] **Refresh the portable bundle** (required by `CLAUDE.md` once behavior changed):

```bash
robocopy C:\Users\colto\Documents\GitHub\EToolsV3\etools \
         C:\Users\colto\Documents\ETools_Portable\app\etools /MIR /XD __pycache__ /XF *.pyc
```

- [ ] **Manual smoke test.** `Stop ETools.bat`, `Launch ETools.bat`, then: load a well from the DB, parse an APD, generate a Casing Review, generate it a second time while the first is still open in Excel (expect the actionable "open in Excel" message and an intact previous file), and open every tab once.

- [ ] **Confirm the final suite state.** `.venv/Scripts/python.exe -m pytest tests/ -q` — expected 201 passed.

## Explicitly out of scope

Recorded so a later reader does not mistake these for oversights:

- **Casing override tag-vs-position** (audit #1) — confirmed defect, **WON'T FIX** by the user's decision on Excel-format continuity.
- **Engine defaults** (audit #3, 9.0 ppg etc.) — intended behavior.
- **BOPE stand-ins** `'500'`/`'5000'`/`5584.5` — accepted as-is.
- **Segment bearing overrides having no effect** (audit #22) — won't fix.
- **Inconsistent PDF-parser failure modes** (spec 7.C1) — `parse_apd_pdf` and
  `parse_wcr_pdf` raise on a corrupt file while `parse_survey_pdf` survives with
  warnings. Verified that both raising paths are caught and shown to the user
  (`load_tab.py:243-248` and `:377-380`), so this is an asymmetry worth knowing
  about, not a live defect. Task 15 touches these files for handle-closing only.
- **LLM retries** — not added; `ddr_llm.py`'s chunk-splitting is a better answer than blind repetition.
- **Reprojection in `locator.py`** — the CRS assignment is correct for real inputs; Task 10 documents and monitors it rather than changing the projection behavior.
- **Stale template literals** (audit #4) and the other items in §4 of the audit — those have their own agreed specs and are a separate effort from this failure-path work.
