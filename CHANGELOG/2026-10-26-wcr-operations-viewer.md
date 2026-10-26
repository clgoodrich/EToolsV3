# WCR operations log beside the PDF, click-to-jump

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "operations log beside"`

## What changed
The WCR tab's Operation Summary Reports section has a new button, **Open
operations log beside the PDF**. It opens a full-screen view:
- **Left:** the operations log for every job (Drilling, Completion, …), grouped
  by day, in a clean layout. Each entry shows its time range, duration, depth
  range, the phase/code line, PT/NPT and trouble badges, then the operator's
  comment.
- **Right:** the WCR PDF itself, page by page.
- **Click a day or an entry** and the PDF scrolls to that row and highlights it.
- **The filter box** narrows the list (e.g. "cement", "npt", "stage 12").

Nothing is reworded: values and comments appear exactly as in the report. Only
PDF line wraps are joined, and the parser's internal `<<<PAGE>>>` marker is
dropped.

## Why
Requested: a cleaner format for the completion operations, without changing
the data, plus a way to see each entry in the source PDF.

## What was added
- `etools/core/pdf/ddr_locate.py`: `locate_entries()` finds each entry's page and
  row band by matching its start timestamp (`M/D/YYYY HH:MM`) in the page words,
  walking in order so a row's start is never confused with the previous row's
  identical end time. `page_sizes()` is the helper the viewer uses for page
  dimensions.
- `etools/ui/ops_viewer.py`:
  - A local page-image route `/etools-pdf/<token>/<page>.png`. Pages are
    rendered by PyMuPDF in a worker thread with a small cache; the token is
    random and maps only to the registered file.
  - `build_log_html` / `build_pdf_html`, which escape all PDF text.
  - Head CSS/JS for click-to-jump and filtering.
  - `add_ops_viewer_button`.
- `tests/test_ops_viewer.py`: 4 tests.

## What was changed / removed
- `wcr_tab.py`: adds the head assets once per page and the button in
  `_render_ddr_card` (which now receives the uploaded PDF path).
- `etools/docs/app_guide.md`: the WCR chart and tab table mention the viewer.

## Verification
- Locator on all 18 fixture WCRs that have an operations log: 6,563/6,563
  entries located, always in forward order, under 0.3 s per PDF. For every entry
  with a comment (4,847), the highlighted band contains that comment's first
  words.
- In the running app with South Moon 5-31-32-C4-3H: 642 entries, 76 days and
  36 pages loaded. Clicking "Stage 12" (7/12/2024 02:00) scrolled to page 18 and
  highlighted exactly that row (screenshot checked).
- `pytest tests/test_ops_viewer.py tests/test_help_guide.py`: 7 passed.

## Notes / follow-ups
- Needs the uploaded PDF from the current session. After a restart the temp
  upload may be gone, and the button then says to upload it again.
- Requires an app restart.
