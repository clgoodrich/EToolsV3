# Change Log

This folder records every **major change** to ETools — one Markdown file per change.
It is the human-readable history of *what was done and why*, complementing the terse
git commit log.

## When to add an entry

Add a file here whenever you complete a **major change**: a new feature, a removed
feature, a parser/algorithm rewrite, a schema or template change, or anything that
alters app behavior or output. Skip trivial edits (typos, formatting, one-line tweaks).

## How to add an entry

1. Copy `TEMPLATE.md` to a new file named `YYYY-MM-DD-short-slug.md`
   (e.g. `2026-08-13-formations-tab.md`). Use the real date; if several land on one
   day, keep the slug distinct.
2. Fill in every section. Be concrete — name the files, functions, and behavior that
   changed, and note how the change was verified.
3. Add a one-line pointer to the top of the **Index** below (newest first).
4. Commit, then **push** — see the workflow policy in `../CLAUDE.md`.

## Index

<!-- newest first: - [YYYY-MM-DD Title](file.md) — one-line hook -->
- [2026-10-26 Bug sweep 2](2026-10-26-bug-sweep-2.md) - 31 reproduced bugs fixed: Casing TVDs from PDF surveys (were straight-hole), WCR formation tops (294/294 now parse), APD side-column tops, magnetic altitude units, DataPrint sheet, liner ordering, per-well UI state, two-tab refresh.
- [2026-10-26 Type / paste survey](2026-10-26-type-paste-survey.md) - WCR and Casing Review take a survey typed or pasted from Excel into a table (True/Grid choice, validated); identical workbook to the same survey from a file.
- [2026-10-26 No SQL Server](2026-10-26-pdf-only-no-sql-server.md) - Surveys, casing, perf date and sundry now read from the PDFs (checked against the DB first: surveys 25/25 exact, casing 264/277); SQL Server code, Legacy flow and pyodbc removed.
- [2026-10-26 WCR operations viewer](2026-10-26-wcr-operations-viewer.md) - Operations log grouped by day in a clean layout (wording unchanged) beside the PDF; click a day/entry to scroll to and highlight that row.
- [2026-10-26 Help tab](2026-10-26-help-tab-guide.md) - In-app Help tab: plain-language guide with six flow charts, tab-by-tab tables, file locations, troubleshooting and glossary (`etools/docs/app_guide.md`).
- [2026-10-26 3-D trajectory sections](2026-10-26-3d-trajectory-sections.md) - The 3-D trajectory outlines the crossed PLSS sections at the surface, labelled, in the same frame as the wellbore.
- [2026-10-26 PDF field extraction](2026-10-26-pdf-field-extraction.md) - APD slant from the ticked radio, formation tops by position, frac gradient from the permit (not "4 1/2"), STC/LTC collars, WCR blank-TVD, survey lat/lon, vision crash.
- [2026-10-26 WCR tab stale survey + blocking](2026-10-26-wcr-tab-stale-survey-and-blocking.md) - A new WCR no longer reuses the previous well's survey; the legacy DB bundle loads off the event loop; tracking logs the WCR on screen.
- [2026-10-26 Casing Review template parity](2026-10-26-casing-review-template-parity.md) - Burst load, buoyed tension/DF, neutral point, cement height/TOC and liner TOL now equal the template formulas they overwrite.
- [2026-10-26 Survey true-north lat/lon](2026-10-26-survey-true-north-latlon.md) - Station lat/lon/UTM/footages were rotated about the SHL by the grid convergence (up to ~140 ft); WCR/promote now use the survey's own north reference.
- [2026-10-26 DB survey correctness](2026-10-26-survey-db-correctness.md) - ASDRILLED/PLANNED spellings, re-uploaded headers interleaving, drilled primary header, TrackingWCR sundry date join.
- [2026-10-26 Per-well state reset](2026-10-26-per-well-state-reset.md) - Loading/parsing a new well, Clear All, Process Survey and Calculate Clearances no longer leave the previous well's APD/WCR/casing/survey data mixed into the new one.
- [2026-08-28 Well path hover readout](2026-08-28-wellpath-hover-readout.md) - Hovering the trajectory on a section panel reports that station's MD/TVD/inc/azi and its FNL/FSL/FEL/FWL.
- [2026-08-25 Event loop, WCR repaint, bearings](2026-08-25-event-loop-and-bearing-guards.md) - A DB outage froze the whole server on Load Well; a half-repainted WCR grid diverged from the export; zero-length boundaries reported a fake due-north bearing (25 real sections affected).
- [2026-08-25 Resource leaks](2026-08-25-resource-leaks.md) - Every PDF parse leaked a file handle (and kept the file locked on Windows); uploaded PDFs accumulated in temp forever. Both fixed, with a startup sweep.
- [2026-08-25 Half-updated state](2026-08-25-half-updated-state.md) - A failed load left the new well's survey beside the old well's clearances; the well-state group is now all-or-nothing, and a saved edit that fails to repaint says so.
- [2026-08-25 Coordinate guards and LLM transport](2026-08-25-coords-and-llm-transport.md) - Swapping lat/lon made Reprocess SHL silently do nothing; Ollama non-JSON bodies and num_predict truncation were reported as the wrong failure.
- [2026-08-25 Mount latch, KOP guards, CRS](2026-08-25-latches-kop-crs.md) - A failed /output mount latched and killed every download link; KOP analysed zero-padded garbage on short surveys; an all-miss spatial join only logged at info.
- [2026-08-25 Surface silent degradation](2026-08-25-surface-silent-degradation.md) - A DB blip silently dropped the casing table from a WCR and made a failed survey lookup look like a well with no survey; both now tell you.
- [2026-08-25 Degenerate geometry guards](2026-08-25-degenerate-geometry-guards.md) - A collapsed section polygon silently produced NaN footages in the section sheets; it now raises and the section is skipped. Corrects audit finding #30.
- [2026-08-25 Atomic workbook writes](2026-08-25-atomic-workbook-writes.md) - A failed generation used to leave a blank template where your reviewed workbook was; writes are now atomic and blocked saves name Excel as the cause.
- [2026-08-25 Startup resilience](2026-08-25-startup-resilience.md) - A missing gitignored data file used to blank every page load; startup now names what is missing and each tab renders in isolation.
- [2026-08-13 Casing Review output correctness](2026-08-13-casing-review-output-correctness.md) — Every workbook shipped the template well's formation tops; production liners landed in STRING 3 instead of STRING 4; Formations tab is now editable with a bounded Top MD.
- [2026-08-13 Formations tab, extraction rewrite & Load-Well cleanup](2026-08-13-formations-and-load-tab.md) — Casing Review gets a Formations tab, APD formation extraction rewritten to 3 parsers + quality gate, "From Database" on-ramp removed, portable bundle refreshed.
