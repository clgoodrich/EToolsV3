"""Casing Review (APD engineering review) Excel generation.

The Casing Review workbook is a 15-sheet calculator owned by the engineering
group. It evaluates each casing string (Conductor / Surface / Intermediate /
Production / Liner) for collapse, burst, and tension design factors against a
2,674-row Casing Strengths lookup. The formulas, named ranges, and reference
sheets are far too involved to regenerate from scratch — instead we ship the
reference workbook as a template (``templates/casing_review_template.xlsx``)
and write only the input cells from a parsed APD Application for Permit to
Drill PDF.
"""

from etools.core.casing_review.generator import (
    CASING_REVIEW_TEMPLATE,
    StringInputs,
    CasingReviewInputs,
    generate_casing_review,
)

__all__ = [
    "CASING_REVIEW_TEMPLATE",
    "StringInputs",
    "CasingReviewInputs",
    "generate_casing_review",
]
