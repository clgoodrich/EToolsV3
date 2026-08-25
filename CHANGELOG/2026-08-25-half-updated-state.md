# Half-updated state: no more showing two wells at once

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** 1fffb8f, (segment-override commit)

## What changed

A load that failed part-way through used to leave the new well's survey sitting
beside the previous well's clearances, with nothing on screen saying so. The
three fields that describe one well are now kept consistent with each other: if
any step fails, the whole group is cleared rather than half-updated.

Separately, a geometry edit that saved but failed to repaint now says so instead
of looking like it did nothing.

## Why

Audit findings 7.D1, 7.D2 and 7.D3, ranked fifth in the failure-path review.

`post_load_orchestrate` (`app.py:172-352`) writes `state.processed` (`:179`),
`state.clearances` (`:239`) and `state.section_definitions` (`:287`) in sequence.
Each inner step re-raises into one outer `except`, and nothing was rolled back.
Every tab reads those fields independently, so different tabs could show
different wells at the same time.

7.D2 is the same shape from the other direction: Step 2b's handler deliberately
does *not* re-raise, so a failed section seed silently kept the previous well's
PLSS sections.

7.D3: `_fire_viz_refresh` wrapped both callbacks in `except Exception:
log.warning(...)` with no `ui.notify`. The override is already written to the
`SectionDefinition` by that point — and feeds the Excel generator from there — so
a silent failure meant the data changed but the screen did not, which reads as
"my edit did nothing" and invites the user to make it twice.

## What was added

- **`etools/ui/state_staging.py`** — `clear_group_on_failure(state, fields)`.
- **`tests/test_post_load_staging.py`** (5) and
  **`tests/test_segment_override_feedback.py`** (3).

## What was changed / removed

- **`etools/ui/app.py`** — the three writes are grouped under
  `clear_group_on_failure`; Step 2b now blanks `section_definitions` explicitly.
- **`etools/ui/tabs/casing_review_tab.py`** — `_fire_viz_refresh` collects which
  targets failed and raises one combined `ui.notify` that states the edit *was*
  saved.

## Verification

- New tests: 8 passed, each verified failing first.
- Full suite: **202 passed** in 8:07, exit 0.
- End-to-end: with well A loaded, a simulated step-2 failure after writing well
  B's survey leaves all three fields empty instead of mixed.
- `_fire_viz_refresh` exercised directly in all three states — map-fails
  (plat still runs), both-fail (one combined message), both-succeed (silent).

## Notes / follow-ups

- **Deviation from the plan, deliberate.** The planned design staged the writes
  into a dict and committed on success. Abandoned during implementation: the
  orchestrator *reads* those same fields at a dozen points between the writes
  (`app.py:194-291`), so redirecting the writes meant rewriting every read — a
  large, risky diff for a defensive fix. Clearing the group on failure gives the
  identical user-visible guarantee. Rationale is recorded in the plan file.
- Clearing rather than restoring is intentional: the previous values describe a
  *different* well, so restoring them would recreate the mixture this prevents.
- The wiring uses non-standard indentation to avoid re-indenting the whole
  orchestrator body. Structure was verified by AST rather than by it merely
  parsing: one guard wrapping all 8 steps, all 4 field assignments inside it,
  outer `except` and `finally` intact.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
