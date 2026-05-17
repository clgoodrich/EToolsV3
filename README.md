# ETools

Local web app for the Utah Division of Oil, Gas & Mining (DOGM): load directional
surveys (from the state SQL Server **or** an operator-submitted PDF), recompute
the trajectory, locate it inside Utah's PLSS sections, calculate FNL/FSL/FEL/FWL
footages, and emit a Well Completion Report (WCR) Excel file.

```
                ┌────────────────────────────┐
                │         Browser            │
                │  http://localhost:8080/    │
                └────────────┬───────────────┘
                             │
                ┌────────────▼───────────────┐
                │  NiceGUI + FastAPI (local) │
                │  • Load Well   • Survey    │
                │  • Map & Viz   • Clearance │
                │  • WCR         • PDF Import│
                │  • Plat Searcher           │
                └────────────┬───────────────┘
                             │
                ┌────────────▼───────────────┐
                │     services + core        │
                │  welleng · pygeomag (WMM)  │
                │  Docling · Ollama (qwen3.5)│
                │  shapely · geopandas       │
                └────────────┬───────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   SQL Server         SQLite (PLSS)         Ollama (LLM)
   UTRBDMSNET        Board_DB_Plss…       :11434 / qwen3.5:9b
```

## Quick start

### Daily use

Double-click **`Launch ETools.bat`** (or **`Launch ETools (Silent).vbs`**) from
this folder, or use the desktop shortcut after running
`Install Desktop Shortcut.ps1`.

The browser opens to `http://localhost:8080/` automatically.

### One-time setup

1. **Python 3.12** + a venv at `.venv/`:

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

2. **SQL Server**: a local SQL Express instance on `CGDESKTOP\SQLEXPRESS`
   serving the `UTRBDMSNET` database via Windows Authentication. Adjust
   `.env` (copy from `.env.example`) if your server is named differently.

3. **PLSS plat databases** (≈250 MB each, gitignored): drop these files in
   `data/`:
   - `Board_DB_Plss_Sections.db`
   - `location_data.db`

4. **Ollama** (optional but recommended) for LLM PDF extraction:

   ```powershell
   # 1. Install from https://ollama.com/download/windows
   # 2. Pull the model used for PDF extraction
   ollama pull qwen3.5:9b
   ```

   Without Ollama the app still runs; the PDF parser falls back to a
   rules-only mode that handles clean text-based PDFs.

## Project layout

```
EToolsV3/
├── etools/                         # main package — all current code
│   ├── main.py                     # entry point: `python -m etools.main`
│   ├── config.py                   # pydantic-settings, .env handling
│   ├── logging_setup.py
│   ├── core/                       # business logic (no DB / UI dependency)
│   │   ├── coordinates/            # lat/lon ↔ UTM, grid convergence
│   │   ├── survey/                 # min-curvature, KOP, magnetic field
│   │   ├── plat/                   # spatial-join points → sections
│   │   ├── clearance/              # FNL/FSL/FEL/FWL footages
│   │   ├── wcr/                    # Excel generator
│   │   ├── pdf/                    # Docling + LLM-backed PDF parser
│   │   └── llm/                    # Ollama JSON-schema client
│   ├── data/db/                    # SQLAlchemy engine factories
│   ├── models/                     # Pydantic DTOs
│   ├── repositories/               # parameterized SQL access
│   ├── services/                   # workflow orchestration
│   └── ui/                         # NiceGUI tabs + state
│
├── data/                           # SQLite reference DBs (PLSS, casing)
├── output/                         # generated WCR .xlsx files
├── tests/                          # pytest, current package only
├── logs/
│
├── archive/                        # deprecated code, kept for reference only
│   ├── legacy_pyqt/                # original PyQt5 stack (~14k LOC)
│   ├── legacy_refactor/            # half-done rewrite's package directories
│   ├── docs/                       # superseded README / DEPLOYMENT
│   └── misc/                       # screenshots, old WCRs, legacy requirements
│
├── pyproject.toml                  # build + deps
├── .env.example
├── README.md                       # this file
│
├── Launch ETools.bat               # ← double-click launchers
├── Launch ETools (Silent).vbs
├── Stop ETools.bat
├── Install Desktop Shortcut.ps1
├── WCR_Empty.xlsm                  # legacy WCR template (referenced by code)
└── application_*.pdf               # operator drilling-permit PDFs (gitignored)
```

## Workflow at a glance

| Step | Path A — well already in DB | Path B — only have a PDF |
|---|---|---|
| Load | API + lateral → **Load Well** | **PDF Import** → drop PDF → wait ~50–90 s → **Use this survey** |
| Process | **Survey** tab → **Process Survey** | same |
| Footages | **Clearance** → **Calculate Clearances** | same |
| Visualize | **Map & Viz** → 2D / 3D sub-tabs | same |
| WCR | **WCR** → **Generate WCR Excel** → file lands in `output/` | same |

## PDF parsing pipeline

```
PDF → Docling (markdown + table-aware OCR if needed)
        ↓
      rules     (regex/heuristic — fast)
        ↓
      LLM text  (Ollama qwen3.5:9b — when rules incomplete or "Always run LLM" checked)
        ↓
      LLM vision (rendered page images — for scanned PDFs)
```

Each layer fills in fields the previous layer missed; the UI shows which
layers actually ran (`docling → rules` for clean PDFs, `docling → rules →
llm-text` when the LLM contributed).

## Configuration

Copy `.env.example` to `.env` and adjust if needed. Common knobs:

```env
ETOOLS_DB__SERVER=CGDESKTOP\SQLEXPRESS    # SQL Server host
ETOOLS_DB__DATABASE=UTRBDMSNET
ETOOLS_DB__TRUSTED=true                    # Windows Auth

ETOOLS_LLM__ENABLED=true                   # set false to skip Ollama entirely
ETOOLS_LLM__MODEL=qwen3.5:9b
ETOOLS_LLM__VISION_MODEL=qwen3.5:9b        # qwen3.5 is multimodal — same model

ETOOLS_PORT=8080
ETOOLS_LOG_LEVEL=INFO
```

## Running tests

```powershell
.venv\Scripts\activate
pytest tests/ -v
```

The new test suite is intentionally small. Legacy tests for the old refactor
live under `archive/legacy_refactor/tests/` and are not maintained.
