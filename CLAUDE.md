# CLAUDE.md — working agreement for this repo

Guidance for Claude Code (and humans) working in EToolsV3. These instructions
override default behavior.

## Project

ETools is a local NiceGUI + FastAPI app for Utah DOGM: directional surveys, PLSS
location, WCR (Form 8) and Casing Review Excel generation, and APD (Form 3) parsing.

- **No hot reload.** `etools/main.py` runs `ui.run(..., reload=False)`. Code changes
  require a full restart: `Stop ETools.bat` → `Launch ETools.bat`.
- **Excel generation is template/schema-driven.** Casing Review copies a template
  byte-for-byte then overwrites cells; the WCR generator builds to a pinned schema.
  Match the app's own build format, not legacy hand-made workbooks.
- **Portable bundle** lives at `C:\Users\colto\Documents\ETools_Portable\` and has its
  own copy of the source. After a change that affects it, refresh app source with
  `robocopy <repo>\etools <bundle>\app\etools /MIR /XD __pycache__ /XF *.pyc`
  (see `scripts/build_portable.ps1` for a full rebuild).

## Push policy — REQUIRED

**Push after every completed major change.** When a major change is done and verified:

1. Write a change-log entry under `CHANGELOG/` (see below).
2. Commit the work (if not on a feature branch, branch first per default git rules).
3. **`git push`** to `origin`.

A "major change" is a new feature, a removed feature, a parser/algorithm rewrite, a
schema/template change, or anything that alters app behavior or output. Trivial edits
(typos, formatting, one-liners) don't require a push of their own.

## Change log — REQUIRED

Every major change gets a Markdown file in **`CHANGELOG/`**, one file per change,
recording *what was done, what was added, what changed/removed, and how it was
verified*.

- Copy `CHANGELOG/TEMPLATE.md` → `CHANGELOG/YYYY-MM-DD-short-slug.md`.
- Fill in every section concretely (name the files/functions).
- Add a one-line pointer to the top of the Index in `CHANGELOG/README.md` (newest
  first).
- Then commit and push per the policy above.
