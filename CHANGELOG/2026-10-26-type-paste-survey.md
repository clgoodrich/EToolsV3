# Type or paste a survey by hand

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "type / paste survey"`

## What changed
The WCR and Casing Review tabs can take a survey typed or pasted into a table,
not only a survey PDF. This matters because 41 of the 63 test WCRs don't carry
their survey.

- When there's no survey, a **Type / paste survey** button sits next to the
  *Survey PDF* upload.
- When there is one, a pencil next to the green survey chip opens the same
  table pre-filled, to correct or replace it.
- The table works like a spreadsheet: MD / Inclination / Azimuth columns,
  Enter moves down, Delete clears a cell, and rows grow as you type. Ctrl+V
  pastes a block copied from Excel. A header row picks the columns by name, so
  a full export with TVD / N / E columns still works. Text copied from a PDF or
  a CSV works too. Pasted rows go below the last filled row.
- You choose whether the azimuths are True or Grid north. It defaults to the
  loaded survey's reference, otherwise Grid.
- **Use this survey** checks the rows first:
  - every filled row has all three numbers;
  - inclination is 0–180° and azimuth 0–360°;
  - no MD appears twice;
  - there are at least two stations.

  Problems show in red, naming the row. Blank rows are ignored and the rows are
  sorted by MD.

## Why
Before this, a WCR without an attached survey report could only get one from a
survey PDF upload, after the SQL Server lookup was removed.

## What was added
- `etools/core/survey/manual.py`:
  - `parse_pasted_rows` turns pasted text into `(md, inc, azi)` rows;
  - `build_manual_survey` validates them and returns the same
    `MeasuredDepth` / `Inclination` / `Azimuth` frame, with
    `attrs["north_reference"]`, that the PDF readers produce.
- `etools/ui/survey_entry.py`: `build_survey_entry(on_apply)` builds the
  dialog once per tab and returns its `open(initial=None)` function.
- `tests/test_manual_survey.py` (10 tests).

## What was changed / removed
- `wcr_tab`:
  - The typed survey is stored on `state.wcr_survey_*` with source
    `"manual"`, so a refresh doesn't put the previous survey back.
  - The survey chip and the upload row are drawn by one helper,
    `_render_survey_status`.
  - The stale SQL Server text was removed from the module docstring.
- `casing_review_tab`: the typed survey is set as `state.casing_survey_df`. The
  survey chip has the same compact style and colours as on the WCR tab.
- `promote.py` / `state.py`: removed the leftover "load the well from the DB"
  wording.
- Help guide (`etools/docs/app_guide.md`): the flow charts, the tab table and
  troubleshooting mention the table.

## Verification
- In the browser, on South Moon (a WCR without a survey):
  - pasted a tab-separated block with MD/Inc/Azi/TVD headers, and the TVD
    column was ignored;
  - typed a row, with Enter/Tab navigation;
  - a half-filled row gave "Row 5: …"; Delete cleared it;
  - *Use this survey* set the chip to "Typed / pasted (4 stations, grid north)"
    and enabled Generate.
- On the Myton City APD, the pencil opened the table pre-filled with the 194
  planned stations, Grid north.
- Pasting South Moon's real 203-station survey through `parse_pasted_rows` →
  `build_manual_survey` gave a frame identical to the CSV fixture. The WCR
  workbooks generated from each have 0 differing cells.
- Full suite: 292 passed.

## Notes / follow-ups
- AG Grid gotcha: NiceGUI sets an `autoSizeStrategy`, and `flex` columns then
  leave the grid stuck blank (`ag-delay-render`). The table uses
  `fitGridWidth` instead.
