# ETools — Session Context for Resume

Saved 2026-05-07. Pick this up after a reboot — it covers everything needed
to continue without re-deriving anything.

---

## TL;DR — what this project is

A local NiceGUI web app rebuilt from the ground up to replace a legacy
~14k-LOC PyQt5 application used by Utah DOGM analysts. Loads directional
surveys (from local SQL Server **or** operator-submitted PDFs), processes the
trajectory with welleng + WMM-2025, locates it inside Utah's PLSS section
plats, calculates FNL/FSL/FEL/FWL footages, and emits a Well Completion
Report Excel file.

Launchers are at the repo root: double-click **`Launch ETools.bat`** (visible
console) or **`Launch ETools (Silent).vbs`**. Browser opens at
`http://localhost:8080/`.

---

## Where we are right now

**All seven phases shipped.** Last user action before save: clicked through
the new "LLM only (skip rules)" checkbox in the PDF Import tab; not yet
test-driven.

### Phase progression — all complete

| Phase | What | Status |
|---|---|---|
| 1 | NiceGUI shell, config, DB session, Pydantic DTOs, well repo, smoke test | ✅ |
| 2 | Coordinates, magnetic field (WMM-2025), survey processor (welleng), KOP detector | ✅ |
| 3 | PLSS plat repo (SQLite `BaseData` → polygons), spatial-join locator, boundary segmenter, FNL/FSL/FEL/FWL clearance | ✅ |
| 4 | Map & Viz tab (Leaflet 2D + Plotly 3D) | ✅ |
| 5 | WCR repository, openpyxl Excel generator, WCR tab UI | ✅ |
| 6 | PDF parser (initial pdfplumber), PDF Import tab, Plat Searcher | ✅ |
| 7 | LLM augmentation: Docling, Ollama qwen3.5:9b, layered pipeline, lock dialog, cancel button, provenance badges, change-log | ✅ |

### Last UX work (Phase 7.7 + a follow-up)

1. **Modal lock dialog** prevents tab-switching / button-clicks during a parse.
2. **Cancel button** in that dialog (calls `task.cancel()`).
3. **Per-field provenance badges** in the metadata grid (`rules`, `llm-text`, `llm-vision`, `… (manual)`).
4. **Change-log dialog** after manual LLM re-run shows agreed/changed/filled counts.
5. **"LLM only (skip rules)" checkbox** — the most recent change, not yet tested by the user.

### Known caveats (not bugs to fix unless requested)

- **Cancel during Docling** unlocks the UI immediately but the worker thread keeps running ~50s in the background until Docling itself returns. Python threads can't be killed mid-execution. Forceful cancel would require running each parse in a subprocess (~10s startup tax per parse).
- **Locked PDF at root** — `application_4304756010.pdf` may sometimes be held by Windows Defender or the indexer; harmless duplicate may exist if it ever ended up in `samples/`. Now `application_*.pdf` is gitignored.
- **Plat coverage** is statewide via the SQLite DB in `data/`, but if a well's UTM falls outside any section in `BaseData`, `clearance` will be NaN for those points. Real wells in Utah are always covered.

---

## Tech stack pinned

| Component | Version / source | Notes |
|---|---|---|
| Python | 3.12 | venv at `.venv/` |
| NiceGUI | 3.11.1 | **Note**: `e.file` API for upload (not `e.content`) |
| FastAPI | (NiceGUI's bundled) | served on `:8080` |
| SQLAlchemy | 2.x | parameterized queries everywhere |
| pyodbc | 5.x | SQL Server connection |
| welleng | 0.8+ | minimum-curvature trajectory |
| pygeomag | 1.1.0 | **Must use `wmm/WMM_2025.COF`** (default `WMM.COF` is the expired 2020 model) |
| shapely / geopandas | 2.x / 1.x | spatial joins, plat polygons |
| pyproj | 3.6+ | grid convergence, aeqd projection |
| Docling | latest | PDF → markdown w/ table awareness, OCR optional |
| Ollama | 0.23.1 | running as Windows service on `:11434` |
| qwen3.5:9b | Q4_K_M (5.2 GB) | multimodal: completion + vision + tools + thinking |
| pdfplumber, pdfminer.six | latest | legacy fallback only — pdfminer chokes on operator PDF fonts |
| PyMuPDF (fitz) | latest | used to render PDF pages → PNG for vision LLM |
| openpyxl | 3.x | WCR Excel writer |

`pyproject.toml` is the source of truth for deps. Install with:

```
pip install -e .
```

---

## File layout

```
EToolsV3/
├── etools/                       # the only source-of-truth package
│   ├── main.py                   # entry: `python -m etools.main`
│   ├── config.py                 # pydantic-settings + LLMConfig
│   ├── logging_setup.py          # structlog (UTF-8 stdout wrapper for Windows)
│   ├── core/
│   │   ├── coordinates/converter.py
│   │   ├── survey/{processor,magnetic,kop}.py
│   │   ├── plat/locator.py
│   │   ├── clearance/{boundary_segmenter,calculator}.py
│   │   ├── wcr/generator.py
│   │   ├── pdf/{parser,docling_extractor,llm_extractor}.py
│   │   └── llm/ollama_client.py
│   ├── data/db/session.py        # SQLAlchemy engines (SQL Server + SQLite)
│   ├── models/                   # Pydantic DTOs (well, survey, plat, clearance, wcr)
│   ├── repositories/             # parameterized SQL access (well, survey, plat, wcr)
│   ├── services/                 # workflow orchestration
│   └── ui/
│       ├── app.py · state.py
│       └── tabs/{load_tab,survey_tab,viz_tab,clearance_tab,wcr_tab,pdf_tab,plat_tab}.py
│
├── data/                         # SQLite plat DBs (~250 MB each, gitignored)
│   ├── Board_DB_Plss_Sections.db # `BaseData`, `Adjacent`, `section_plat_data`, …
│   └── location_data.db
├── output/                       # generated WCR Excel files
├── tests/                        # fresh pytest stub
├── logs/
│
├── archive/                      # deprecated code, kept for reference
│   ├── README.md                 # what's archived and why
│   ├── legacy_pyqt/              # 17 PyQt5 source files
│   ├── legacy_refactor/          # half-done rewrite (core/, services/, ui/, …)
│   ├── docs/                     # superseded README/DEPLOYMENT
│   └── misc/                     # screenshots, old reqs, legacy WCRs
│
├── README.md
├── pyproject.toml
├── .env.example                  # config template
├── .gitignore                    # data/*.db, application_*.pdf, etc.
│
├── Launch ETools.bat             # ← double-click launchers
├── Launch ETools (Silent).vbs
├── Stop ETools.bat
├── Install Desktop Shortcut.ps1
├── WCR_Empty.xlsm                # legacy WCR template
│
└── application_*.pdf             # operator drilling-permit PDFs (gitignored)
```

---

## Key configuration

`.env` (copy from `.env.example`):

```env
# SQL Server (Windows Auth, local default)
ETOOLS_DB__SERVER=CGDESKTOP\SQLEXPRESS
ETOOLS_DB__DATABASE=UTRBDMSNET
ETOOLS_DB__TRUSTED=true

# LLM (Ollama)
ETOOLS_LLM__ENABLED=true
ETOOLS_LLM__BASE_URL=http://localhost:11434
ETOOLS_LLM__MODEL=qwen3.5:9b
ETOOLS_LLM__VISION_MODEL=qwen3.5:9b   # qwen3.5:9b is multimodal — same model
ETOOLS_LLM__TIMEOUT_S=600              # 10 min — qwen3.5:9b is slow on CPU

ETOOLS_PORT=8080
ETOOLS_LOG_LEVEL=INFO
```

Test well used throughout: **API `4301354722` lateral `0000`** — Reay
16-29-30-B4-2H by Javelin Energy. 222 drilled survey points, KOP at 765 ft,
landing at 10,495 ft. SHL is 14 ft from west boundary of Section 28-T2S-R4W
in the Uintah meridian. BHL in Section 30, having crossed sections 28→29→30.

---

## Runtime quirks I've fixed (and you should know about)

These tripped me up; documenting so they don't trip up resume-Claude:

1. **NiceGUI 3.x changed `ui.upload`'s event API.**
   - Old (2.x): `e.name`, `e.content.read()`
   - New (3.x): `e.file.name`, `await e.file.save(path)` or `await e.file.read()`
   - The handler in `pdf_tab.py` supports both via `getattr(e, "file", None) or getattr(e, "content", None)` for forward-compat safety.

2. **NiceGUI's `run.io_bound` swallows `CancelledError`** and returns `None` instead of propagating. That broke our cancel handler. We bypass it with a local `_io()` helper that calls `loop.run_in_executor(None, ...)` directly.

3. **NiceGUI slot context doesn't propagate into `asyncio.create_task` children.** UI rendering (`ui.label`, `ui.code`) raises *"slot stack is empty"* if called from a child task. Fix: child task only computes + returns, parent coroutine renders.

4. **pygeomag's bundled `WMM.COF` points at the expired 2020 model.** Must explicitly load `wmm/WMM_2025.COF`. The path is *relative to the pygeomag package directory* — the loader prepends its base path, so passing absolute paths fails.

5. **MS SQL Server PLSS_QQ stores geometry as proprietary spatial UDT in an `image` column.** `CAST(... AS varbinary(max)) AS geometry).STAsBinary()` converts to standard WKB at the database edge. (Note: we don't actually use this anymore — the SQLite plat DB has full state coverage; the SQL Server PLSS data only covers SW Utah.)

6. **Windows console encoding (cp1252) crashes on Unicode** from PDFs/LLM output. `etools/logging_setup.py` wraps stdout/stderr in a UTF-8 `TextIOWrapper` with `errors="replace"`.

7. **Docling with OCR enabled is ~8 minutes per PDF.** With OCR off (default in `pdf_to_markdown(with_ocr=False)`) it's ~50 seconds. We auto-retry with OCR only if `looks_scanned` heuristic triggers.

8. **`qwen3.5:9b` cold-load on CPU is ~60 s** the first time after Ollama starts. Subsequent calls are ~30 s for typical extraction prompts. Default timeout is 600 s.

---

## How to run / test

### Resume after reboot

1. Open this folder, double-click **`Launch ETools.bat`**.
2. Wait ~5 s for browser to open.
3. Default test API `4301354722` is pre-filled in the Load Well tab — click **Load Well** to confirm SQL Server is up and data flows.
4. To test PDF parsing: PDF Import tab → drop one of `application_*.pdf` (4 samples in repo root) → wait ~50–90 s.

### If Ollama isn't running

The PDF tab shows *"LLM: Ollama not running (rules-only mode)"* in gray text under the upload area. To start it:

```powershell
ollama serve     # if it's not auto-started
# or just run any ollama command — Windows starts the service
```

The model is at `~/.ollama/models/` (Ollama default). Verify with:

```powershell
ollama list      # should show qwen3.5:9b @ 6.6 GB
```

### Workflow paths

| Path | Steps |
|---|---|
| **DB-loaded well** | Load Well → Survey: Process Survey → Clearance: Calculate Clearances → Map & Viz → WCR: Generate WCR Excel |
| **PDF-loaded well** | PDF Import: drop PDF → wait → Use this survey → Survey: Process Survey → (rest same as above) |

---

## PDF parser pipeline (current)

```
PDF
 ↓
Layer 1: Docling → markdown (no OCR by default; auto-retry with OCR if looks_scanned)
 ↓
Layer 2: rules-extract       (skipped if "LLM only" checkbox is checked)
 ↓
Layer 3: text LLM            (runs if force_llm OR is_incomplete OR llm_only)
 ↓
Layer 4: vision LLM          (runs if force_vision OR surveys still empty)
 ↓
ParsedSurvey (with field_sources dict for provenance)
```

Three checkboxes on the PDF Import tab control behavior:
- **Always run LLM extraction** — runs LLM even if rules succeeded
- **LLM only (skip rules)** — Docling → LLM directly, skipping rules entirely
- **Force vision LLM (for scanned PDFs)** — vision-LLM on rendered page images

---

## Architecture decisions worth remembering

1. **Local-only by design.** No cloud APIs anywhere. Ollama for LLM, Docling
   for OCR, all data stays on the local network or this machine.
2. **NiceGUI over PyQt5** — modern, web-native, way less code, runs as a
   local web app the user opens in their browser.
3. **Service layer doesn't talk to UI** — services return DTOs/dataframes,
   UI orchestrates. Clean cancellation + testability.
4. **Repositories are parameterized** — no f-string SQL anywhere in the new
   code. Legacy stuff in `archive/legacy_pyqt/` still has it; not maintained.
5. **Plat data lives in SQLite** (`data/Board_DB_Plss_Sections.db`) because
   the SQL Server `PLSS_QQ` table only has SW Utah coverage and uses MS SQL
   spatial UDT format that requires conversion. SQLite is faster + statewide.
6. **PDF metadata extraction is layered** — cheap rules first, LLM only when
   they fail. `_trim_to_survey_region()` cuts the markdown to ~20 KB before
   sending to LLM so CPU inference stays under timeout.

---

## Open / queued items (not done; resume here if asked)

- **Editable metadata fields** in the PDF Import tab — currently the user
  can't correct an LLM mis-extraction before clicking "Use this survey".
  Mentioned as a "Future enhancement" in the README's workflow section.
- **Forceful cancellation** — currently cancel pops UI lock but worker
  keeps running. Would require subprocess-based parsing.
- **Test coverage for the math** — `tests/` is mostly stub. Real KOP / clearance fixtures would catch regressions.
- **WCR template integration** — current generator writes a fresh xlsx
  matching the legacy layout but doesn't use `WCR_Empty.xlsm` (the macro
  template). Could be wired up if the user wants the macros preserved.
- **Plat polygon caching** — every clearance run rebuilds polygons from
  `BaseData` (~1 s for ~30 sections). A cached statewide GeoDataFrame would
  make it instant.

---

## Resume checklist

When you (or future-Claude) come back:

1. Read this file.
2. `git status` and `git log --oneline -20` to see anything I/you/the user
   committed.
3. Look at `tests/` and confirm what's there is stub vs real.
4. The most recent open thread: user just shipped the **"LLM only (skip
   rules)" checkbox** but hadn't confirmed it works end-to-end yet. Ask if
   they tested it. The change-log dialog after a manual re-run also hasn't
   been visually confirmed.
5. If the user says "what was I in the middle of?" — answer: testing PDF
   parsing UX (lock dialog, cancel, provenance badges, LLM-only). The math
   layers (Phases 1–5) are stable; UX polish is what's been changing.

---

*This document is the canonical handoff. Edit it as more sessions accumulate.*
