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
- [2026-08-25 Half-updated state](2026-08-25-half-updated-state.md) - A failed load left the new well's survey beside the old well's clearances; the well-state group is now all-or-nothing, and a saved edit that fails to repaint says so.
- [2026-08-25 Coordinate guards and LLM transport](2026-08-25-coords-and-llm-transport.md) - Swapping lat/lon made Reprocess SHL silently do nothing; Ollama non-JSON bodies and num_predict truncation were reported as the wrong failure.
- [2026-08-25 Mount latch, KOP guards, CRS](2026-08-25-latches-kop-crs.md) - A failed /output mount latched and killed every download link; KOP analysed zero-padded garbage on short surveys; an all-miss spatial join only logged at info.
- [2026-08-25 Surface silent degradation](2026-08-25-surface-silent-degradation.md) - A DB blip silently dropped the casing table from a WCR and made a failed survey lookup look like a well with no survey; both now tell you.
- [2026-08-25 Degenerate geometry guards](2026-08-25-degenerate-geometry-guards.md) - A collapsed section polygon silently produced NaN footages in the section sheets; it now raises and the section is skipped. Corrects audit finding #30.
- [2026-08-25 Atomic workbook writes](2026-08-25-atomic-workbook-writes.md) - A failed generation used to leave a blank template where your reviewed workbook was; writes are now atomic and blocked saves name Excel as the cause.
- [2026-08-25 Startup resilience](2026-08-25-startup-resilience.md) - A missing gitignored data file used to blank every page load; startup now names what is missing and each tab renders in isolation.
- [2026-08-13 Casing Review output correctness](2026-08-13-casing-review-output-correctness.md) — Every workbook shipped the template well's formation tops; production liners landed in STRING 3 instead of STRING 4; Formations tab is now editable with a bounded Top MD.
- [2026-08-13 Formations tab, extraction rewrite & Load-Well cleanup](2026-08-13-formations-and-load-tab.md) — Casing Review gets a Formations tab, APD formation extraction rewritten to 3 parsers + quality gate, "From Database" on-ramp removed, portable bundle refreshed.
