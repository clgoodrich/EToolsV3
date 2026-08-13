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
- [2026-08-13 Formations tab, extraction rewrite & Load-Well cleanup](2026-08-13-formations-and-load-tab.md) — Casing Review gets a Formations tab, APD formation extraction rewritten to 3 parsers + quality gate, "From Database" on-ramp removed, portable bundle refreshed.
