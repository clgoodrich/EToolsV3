# Archive

Everything in this folder is **deprecated and unmaintained**. It's preserved
because the original implementations contain context (database schemas,
domain logic, hand-tuned heuristics) that was useful while building the
current `etools/` package, and because nothing here is reachable from the
current code path — it's safe to keep around without risk of accidental
imports.

## Contents

### `legacy_pyqt/`

The original PyQt5 desktop application — what `mainProject.py` actually ran
before the rewrite. ~14k LOC across ~17 files.

- `mainProject.py` — `ETools(QMainWindow)` glue, inline DB connectors
- `EToolsLimited.py` — pyuic5-generated UI (tabs: DX Survey, Well Viz,
  WCR, Plat Searcher)
- `main_project_*.py` — business logic modules: clearance, drawer,
  dx_survey, import_surveys, locations, survey_process, wcr, writer,
  detect_kop, relative_calc
- `WCR.py`, `DXClearance.py`, `DXSurveys2.py`, `SQLQueries.py`,
  `ModuleAgnostic.py` — earlier monolithic versions that
  `main_project_*.py` partially replaced

### `legacy_refactor/`

The half-done rewrite that was sitting next to the legacy code at the repo
root: a clean-architecture attempt with `core/`, `services/`, `data/`,
`config/`, `utils/`, `ui/` packages plus `main.py` / `mainProject_new.py`
entry points. Imports were broken (`main.py` referenced `MainWindow` from
the wrong module) and the UI controller never wired up to real widget
names. The current `etools/` package is the spiritual successor.

The matching tests live under `legacy_refactor/tests/` and import from
`data.repositories.*` etc. — those modules live inside this folder, so
you'd need to add the folder to `PYTHONPATH` to run them.

### `docs/`

Superseded `README.md` and `DEPLOYMENT.md` from the legacy/half-refactor era.

### `misc/`

Random artifacts: old `requirements.txt` files, the legacy
`logininfo.txt` credentials format, a debugging screenshot
(`problem_upload.jpg`), an old design doc (`modular-wandering-blossom.md`),
a sample legacy WCR output (`Reay_*_WCR.xlsx`), and a tracking sheet
(`TrackingWCR.xlsx`).

## When can this be deleted?

Once the new app has been used in production for a few release cycles and
no one has needed to look at the legacy implementations, the entire
`archive/` directory can be removed in one commit. Until then, keeping it
costs ~~about 1 MB of source~~ near-zero (gitignored binaries excepted).
