# Casing Review computed values match the template formulas

- **Date:** 2026-10-26
- **Author:** Colton Goodrich (with Claude Code)
- **Commit(s):** see `git log --grep "template formulas"`

## What changed
The values the writer pre-fills over the template's formulas (burst load,
buoyed tension, tension DF, neutral point, cement height, TOC) now equal what
those formulas compute. Liner rows also get the right TOL. Two smaller fixes
are included: a bearing-only section-segment edit no longer collapses that
quarter-side, and the Vertical WBD no longer crashes when no string has a hole
size.

## Why
`writer._write_string_block` overwrites X/Q/R/AA/AB/AC/AD with
`CasingStringDesign` properties, so those properties are the shipped numbers.
Each one differed from the template:
- **Burst load (X).** It used the next string's *MD* where the template uses
  TVD, and the last string fell back to the frac pressure instead of
  hydrostatic. Horizontal example: intermediate 7750 vs 4755 psi, production
  10000 vs 5195 psi.
- **Buoyed tension / tension DF / neutral point (AD/AA/AB).** These used
  `MD·(1−MW/65.4)`. The template uses pressure-area at TVD
  (`wL − 0.052·MW·TVD·As`) and `TVD·(1−MW/65.4)`. On a 20,000' MD / 10,000' TVD
  string the DF was 1.62 vs 1.48: it passed BTC 1.6 when the template fails it.
- **Liner (STRING 4).** B69 (TOL) was never written, so it shipped the template
  well's 7896. Tension used the full MD instead of MD − TOL (AH57).
- **Cement height / TOC (Q/R).** The template's open-hole cap was missing: fill
  to the previous shoe, then the excess rises inside the previous casing's ID.
- **Segment overrides.** The editor stores only the changed fields;
  `effective_segment` returned the override whole, so `length_ft=None` became 0.

## What was added
- Domain fields: `top_depth_tvd_ft`, `next_set_depth_tvd_ft`,
  `prev_set_depth_md_ft`, `prev_id_in`. `finalize` links prev/next.
- `tests/test_casing_domain_template_parity.py`: 6 tests, each evaluating a
  template formula by hand. All 6 fail on the old code.

## What was changed / removed
- `domain.py`: `burst_load_psi`, `tension_air_klbs`, `tension_buoyed_klbs`,
  `neutral_point_ft`, `cement_height_ft`, `top_of_cement_ft` ("TOL" for liners).
- `engine.py`: interpolates the TVD at the liner top.
- `writer.py` `_write_footer_values`: writes B69 = TOL MD and D69 = TOL TVD.
- `sections.py` `SectionDefinition.effective_segment`: merges field by field.
- `wbd.py`: `max(..., default=0.0)` for the widest hole.

## Verification
- `pytest tests/test_casing_domain_template_parity.py`: 6 passed (6 fail with
  the old domain/sections code stashed).
- Re-ran the audit repros: burst 4755/5195, tension 369.7 klbs / DF 1.48 /
  NP 8471 ft, liner air tension 119.5 klbs and B69 = 8700. All match the
  template.
- Full fast suite green.

## Notes / follow-ups
- Burst with a non-zero backup mud (template branch `$B$37<>0`) is still not
  modelled, as before.
- A non-liner STRING 4 shows "Surface" where the template's R57 would print
  "TOL" against B69 = 0.
