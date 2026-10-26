# In-app Help tab with a plain-language guide and flow charts

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "Help tab"`

## What changed
A new **Help** tab (last in the tab bar) explains the whole app in plain
language, with six colour-coded flow charts:
1. The big picture: two ways in (APD or WCR) → the tabs → the outputs.
2. APD → Casing Review workbook, including every decision (same well? survey
   in the DB? can the well be placed?) and the Casing Review sub-tabs.
3. WCR → WCR workbook, including how the KOP is chosen, Save updated Excel
   and the personal tracking record.
4. The pipeline that runs whenever a well becomes active.
5. Working with several wells (the switcher, Clear all).
6. Where the information comes from.

It also has tab-by-tab and button-by-button tables, where files are saved, a
troubleshooting table and a glossary.

## Why
Requested: documentation outside the code, inside the app, with an exhaustive
and simple flow chart.

## What was added
- `etools/docs/app_guide.md`: the guide (Markdown + Mermaid). It lives inside
  the package so the portable bundle ships it. Edit this file to change the
  Help page; it is read on every page load.
- `etools/ui/tabs/help_tab.py`: renders the guide (NiceGUI markdown with
  Mermaid, which is bundled, so it works offline).
- `tests/test_help_guide.py`: the guide exists inside the package, has its
  charts, and mentions every top-level tab (it fails if a tab is added without
  documentation).

## What was changed / removed
- `etools/ui/app.py`: adds the Help tab, rendered behind `safe_tab_render`
  like the others.

## Verification
- Ran the app and opened Help in a browser: all 6 charts render with no Mermaid
  errors and all 6 tables show. Checked readability by screenshot (the
  several-wells chart was switched to top-down after it rendered too small).
- `pytest tests/test_help_guide.py`: 3 passed.

## Notes / follow-ups
- The guide documents what a user can reach. The old "From Database" load path
  and the standalone survey-PDF tab still exist in code but have no button.
