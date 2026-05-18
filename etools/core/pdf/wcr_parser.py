"""Parse a DOGM Well Completion Report (WCR) PDF into structured fields.

Layered pipeline (mirroring ``parse_survey_pdf``):

    Layer 1  Docling  → high-quality markdown
    Layer 1b PyMuPDF  → plain text supplement (catches pages Docling drops)
    Layer 2  Rules    → regex on the combined text for clean form fields
    Layer 3  LLM      → schema-constrained text LLM fills in what's missing
    Layer 4  Vision   → vision LLM on rendered page images (scanned PDFs)

Each layer only fills in fields the previous layers missed. If Ollama is
unavailable or disabled, layers 3-4 are silently skipped — the rules layer
covers most clean DOGM Form 8 PDFs on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

from etools.config import settings
from etools.logging_setup import get_logger
from etools.models import (
    CasingRow,
    FormationTop,
    PerfStage,
    WCRPdfData,
    WellPositionRow,
)

log = get_logger(__name__)


def parse_wcr_pdf(
    path: str | Path,
    *,
    use_llm: bool | None = None,
    use_vision: bool = False,
    mode: str = "rules+llm",
    max_pages: int | None = None,
    skip_docling: bool = False,
) -> WCRPdfData:
    """Run the layered pipeline and return a populated WCRPdfData.

    Parameters
    ----------
    use_llm : bool | None
        Defaults to ``settings.llm.enabled``. Pass ``False`` to force
        rules-only behaviour (faster, no Ollama dependency).
    use_vision : bool
        Opt into the vision pass for scanned PDFs.
    mode : str
        One of:
          - ``"rules"``: extract via PyMuPDF + Docling + regex only. LLM
            never runs even if Ollama is available.
          - ``"llm"``: skip the regex layer entirely; rely on the LLM to
            fill the schema from the Docling/PyMuPDF text. Requires Ollama.
          - ``"rules+llm"`` *(default)*: regex first, LLM backfills any
            field the rules left empty.
    max_pages : int | None
        If set, only the first ``max_pages`` pages of the PDF are passed
        to Docling and the regex layer. Useful for skipping the
        Operation Summary appendix (Form 8 itself fits in 2-3 pages).
    """
    path = Path(path)
    log.info("wcr_pdf.parse.start", path=str(path), mode=mode, max_pages=max_pages)

    if mode not in ("rules", "llm", "rules+llm"):
        raise ValueError(f"Unknown mode {mode!r}; expected rules, llm, or rules+llm")

    # If the caller capped page count, slice the PDF first so every layer
    # sees the same subset.
    work_path = path
    if max_pages is not None and max_pages > 0:
        try:
            work_path = _slice_pdf(path, max_pages)
        except Exception as exc:
            log.warning("wcr_pdf.slice_failed", error=str(exc))
            work_path = path

    # ---- Layer 1 + 1b: extract text ----
    pymupdf_text = _extract_text(work_path)
    docling_markdown = ""
    if not skip_docling:
        try:
            from etools.core.pdf.docling_extractor import pdf_to_markdown

            docling_markdown, _meta = pdf_to_markdown(work_path, with_ocr=False)
        except Exception as exc:
            log.warning("wcr_pdf.docling.failed", error=str(exc))

    combined = pymupdf_text
    if docling_markdown:
        combined = combined + "\n\n<<<DOCLING>>>\n" + docling_markdown
    combined = _collapse_padded_dates(combined)
    combined = _collapse_padded_numbers(combined)

    data = WCRPdfData(source_pdf=str(path))
    data.form_type = _detect_form_type(combined)
    if data.form_type == "form15":
        data.warnings.append(
            "This PDF is a FORM 15 (Workover/Recompletion Tax Credit "
            "Application), not a Form 8 Well Completion Report. WCR field "
            "extraction will return empty results — the form's schema is "
            "different."
        )
        log.info("wcr_pdf.detected_form15", path=str(path))
    layers_used: list[str] = ["pymupdf"]
    if docling_markdown:
        layers_used.append("docling")

    # ---- Layer 2: rules (skipped in 'llm' mode) ----
    if mode != "llm":
        _extract_header(combined, data)
        _extract_positions(combined, data)
        _extract_casing(combined, data)
        _extract_formations(combined, data)
        _extract_perf_stages(combined, data)
        _extract_section_33_intervals(combined, data)
        layers_used.append("rules")
    else:
        layers_used.append("rules-skipped")

    # ---- Layer 2b: DDR (Operation Summary Report appendix) ----
    # Always runs — DDR comments carry events (KOP, EOC, frac stages, NPT)
    # that are richer than what's on the Form 8 itself.
    try:
        from etools.core.pdf.ddr_events import extract_events
        from etools.core.pdf.ddr_parser import parse_ddrs_from_text

        ddrs = parse_ddrs_from_text(combined)
        for ddr in ddrs:
            ddr.key_events = extract_events(ddr)
        data.ddrs = ddrs
        if ddrs:
            layers_used.append("ddr")
    except Exception as exc:
        log.warning("wcr_pdf.ddr.failed", error=str(exc))
        data.warnings.append(f"DDR parse failed: {exc}")

    # ---- Layer 3: LLM (text) ----
    if use_llm is None:
        use_llm = bool(settings.llm.enabled)
    # In 'llm' mode we force a call regardless of completeness; in
    # 'rules+llm' mode the LLM only runs if something's missing.
    needs_llm = mode == "llm" or (use_llm and _wcr_incomplete(data))
    if mode == "rules":
        needs_llm = False
    if use_llm and needs_llm and combined:
        try:
            from etools.core.llm import OllamaClient
            from etools.core.pdf.llm_extractor import llm_wcr_extract

            client = OllamaClient()
            if client.health() and client.has_model():
                llm_result = llm_wcr_extract(combined, client=client)
                _merge_llm(data, llm_result)
                layers_used.append("llm-text")
            else:
                log.info("wcr_pdf.llm.skip", reason="ollama unavailable or model missing")
        except Exception as exc:
            log.warning("wcr_pdf.llm.failed", error=str(exc))
            data.warnings.append(f"LLM extraction failed: {exc}")

    # ---- DDR LLM augmentation ----
    # Adds a free-text summary per DDR + catches events the regex missed.
    if use_llm and data.ddrs:
        try:
            from etools.core.llm import OllamaClient
            from etools.core.pdf.ddr_llm import augment_ddr_with_llm

            client = OllamaClient()
            if client.health() and client.has_model():
                for ddr in data.ddrs:
                    augment_ddr_with_llm(ddr, client=client)
                layers_used.append("ddr-llm")
        except Exception as exc:
            log.warning("wcr_pdf.ddr_llm.failed", error=str(exc))
            data.warnings.append(f"DDR LLM augmentation failed: {exc}")

    # ---- Layer 4: LLM (vision) — opt-in / last resort ----
    if use_vision and use_llm and _wcr_incomplete(data):
        try:
            from etools.core.llm import OllamaClient
            from etools.core.pdf.llm_extractor import llm_wcr_extract_from_image

            client = OllamaClient()
            if client.health():
                images = _render_pages_to_png(path, max_pages=6)
                if images:
                    llm_result = llm_wcr_extract_from_image(images, client=client)
                    _merge_llm(data, llm_result)
                    layers_used.append("llm-vision")
        except Exception as exc:
            log.warning("wcr_pdf.llm_vision.failed", error=str(exc))
            data.warnings.append(f"Vision LLM extraction failed: {exc}")

    log.info(
        "wcr_pdf.parse.done",
        path=str(path),
        positions=len(data.positions),
        casing=len(data.casing),
        formations=len(data.formations),
        stages=len(data.perf_stages),
        layers=layers_used,
    )
    return data


# ---------------------------------------------------------------------------
# LLM-result merging — only fill fields the rules layer left empty.
# ---------------------------------------------------------------------------


def _wcr_incomplete(data: WCRPdfData) -> bool:
    """A WCR is 'incomplete' if any of the load-bearing fields for the
    Excel output are missing. We escalate to the LLM in that case."""
    if not data.well_name or not data.api:
        return True
    if data.elevation_ft is None:
        return True
    if data.total_md_ft is None:
        return True
    if not data.positions:
        return True
    if not data.perf_stages:
        return True
    return False


def _merge_llm(into: WCRPdfData, llm) -> None:
    """Fill empty fields on ``into`` from the LLM result without overwriting
    anything the rules layer already extracted."""
    # Scalar fields
    scalar_map = {
        "well_name": "well_name",
        "api": "api_number",
        "operator": "operator",
        "well_type": "well_type",
        "field_name": "field_name",
        "county": "county",
        "well_status": "well_status",
        "spud_date": "spud_date",
        "rotary_date": "rotary_date",
        "td_date": "td_date",
        "completion_date": "completion_date",
        "elevation_ft": "elevation_ft",
        "ground_elev_ft": "ground_elev_ft",
        "total_md_ft": "total_md_ft",
        "total_tvd_ft": "total_tvd_ft",
        "pbtd_md_ft": "pbtd_md_ft",
        "pbtd_tvd_ft": "pbtd_tvd_ft",
    }
    for attr, src in scalar_map.items():
        if getattr(into, attr, None) in (None, ""):
            value = getattr(llm, src, None)
            if value not in (None, ""):
                setattr(into, attr, value)

    # Positions — add any whose name isn't already represented.
    have_position_names = {p.name.lower() for p in into.positions}
    for p in getattr(llm, "positions", []) or []:
        if p.name and p.name.lower() not in have_position_names:
            into.positions.append(
                WellPositionRow(
                    name=p.name,
                    fnl=p.fnl,
                    fsl=p.fsl,
                    fel=p.fel,
                    fwl=p.fwl,
                    qtr_qtr=p.qtr_qtr,
                    section=p.section,
                    township=p.township,
                    township_dir=p.township_dir,
                    range=p.range,
                    range_dir=p.range_dir,
                    meridian=p.meridian,
                    utm_easting=p.utm_easting,
                    utm_northing=p.utm_northing,
                )
            )
            have_position_names.add(p.name.lower())

    # Formations — append everything the LLM found if rules came up empty.
    if not into.formations:
        for f in getattr(llm, "formations", []) or []:
            into.formations.append(
                FormationTop(name=f.name, top_md=f.top_md, top_tvd=f.top_tvd)
            )

    # Perf stages — same idea; trust the LLM only when rules missed.
    if not into.perf_stages:
        for s in getattr(llm, "perf_stages", []) or []:
            if s.interval_top_md is None or s.interval_bottom_md is None:
                continue
            into.perf_stages.append(
                PerfStage(
                    stage=int(s.stage),
                    interval_top_md=float(s.interval_top_md),
                    interval_bottom_md=float(s.interval_bottom_md),
                    num_perfs=s.num_perfs,
                )
            )
        into.perf_stages.sort(key=lambda x: x.stage)

    # Casing — append by feature code where rules missed it.
    have_features = {c.feature.upper() for c in into.casing}
    for c in getattr(llm, "casing", []) or []:
        if c.feature and c.feature.upper() not in have_features:
            into.casing.append(
                CasingRow(
                    feature=c.feature.upper(),
                    diameter=c.diameter_in,
                    weight=c.weight_ppf,
                    grade=c.grade,
                    top_md=c.top_md_ft,
                    bottom_md=c.bottom_md_ft,
                )
            )
            have_features.add(c.feature.upper())


def _slice_pdf(path: Path, max_pages: int) -> Path:
    """Write a temp PDF containing only the first ``max_pages`` pages, so
    both PyMuPDF and Docling see a much smaller document.

    Returns the temp path — falls back to the original on any failure (caller
    handles that). We don't bother cleaning up the temp file; OS will eventually.
    """
    import tempfile

    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF required to slice PDF") from exc

    src = fitz.open(str(path))
    n = min(max_pages, len(src))
    out = fitz.open()
    out.insert_pdf(src, from_page=0, to_page=n - 1)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", prefix="wcr_slice_")
    tmp_path = Path(tmp.name)
    tmp.close()
    out.save(str(tmp_path))
    out.close()
    src.close()
    log.info("wcr_pdf.slice", source=str(path), output=str(tmp_path), pages=n)
    return tmp_path


def _render_pages_to_png(path: Path, max_pages: int = 6) -> list[bytes]:
    """Render the first N pages of a PDF as PNG bytes (for the vision LLM)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    out: list[bytes] = []
    doc = fitz.open(str(path))
    for i in range(min(len(doc), max_pages)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=150)
        out.append(pix.tobytes("png"))
    return out


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def _extract_text(path: Path) -> str:
    """Concatenate every page's text. The Form 8 layout is mostly linear once
    extracted; we keep page breaks as a delimiter so downstream parsers can
    detect the boundary between Form 8 fields and the Operation Summary."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to parse WCR PDFs") from exc
    doc = fitz.open(str(path))
    pages: list[str] = []
    for i in range(len(doc)):
        try:
            pages.append(doc.load_page(i).get_text("text"))
        except Exception as exc:  # pragma: no cover
            log.warning("wcr_pdf.page_failed", page=i + 1, error=str(exc))
            pages.append("")
    return "\n\n<<<PAGE>>>\n\n".join(pages)


# ---------------------------------------------------------------------------
# Header fields (Sections 1-26)
# ---------------------------------------------------------------------------

_HEADER_PATTERNS: dict[str, re.Pattern[str]] = {
    "well_name": re.compile(r"1\.\s*WELL NAME\s*\n([^\n]+)", re.I),
    "well_type": re.compile(r"2\.\s*TYPE OF WELL\s*\n([^\n]+)", re.I),
    "api": re.compile(r"4\.\s*API NUMBER\s*\n(\d{10,14})", re.I),
    "operator": re.compile(r"5\.\s*NAME OF OPERATOR\s*\n([^\n]+)", re.I),
    "field_name": re.compile(r"7\.\s*FIELD NAME\s*\n([^\n]+)", re.I),
    "county": re.compile(r"14\.\s*COUNTY\s*\n([^\n]+)", re.I),
    "spud_date": re.compile(r"15\.\s*DATE SPUDDED \(SPUD RIG\)\s*\n(\d{2}/\d{2}/\d{4})", re.I),
    "rotary_date": re.compile(r"16\.\s*DATE SPUDDED \(ROTARY RIG\)\s*\n(\d{2}/\d{2}/\d{4})", re.I),
    "td_date": re.compile(r"17\.\s*DATE TOTAL DEPTH REACHED\s*\n(\d{2}/\d{2}/\d{4})", re.I),
    "completion_date": re.compile(
        r"18\.\s*DATE\s*\n?\s*COMPLETED/ABANDONED\s*\n(\d{2}/\d{2}/\d{4})", re.I
    ),
    "well_status": re.compile(r"26\.\s*CURRENT WELL STATUS\s*\n([^\n]+)", re.I),
}


# PyMuPDF sometimes renders form-field text with a space between every glyph
# ("0 3 / 0 1 / 2 0 2 3"). Collapse those padded date sequences before regex.
_PADDED_DATE_RE = re.compile(r"(?:\d\s){1,2}\d\s*/\s*(?:\d\s){1,2}\d\s*/\s*(?:\d\s){1,4}\d")
# Same problem for long numerics: "8 8 1 0" → "8810" (perf MDs, casing
# weights, sacks). Trigger only on runs of 4+ digits separated by a
# *single space* (not newline) so we don't collapse section + township
# pairs like "3 1\n3.0 S" or row-spanning patterns.
_PADDED_NUM_RE = re.compile(r"(?<!\d)(?:\d ){3,}\d(?!\d)")


# ---------------------------------------------------------------------------
# Form-type detection
# ---------------------------------------------------------------------------


# Header signatures DOGM uses to identify which form was filed. We match
# on multiple cues so a single mis-rendered glyph doesn't flip the result.
_FORM15_SIGNATURES = (
    re.compile(r"\bFORM\s*15\b", re.I),
    re.compile(r"\bWorkover\s*/\s*Recompletion\s+Tax\s+Credit", re.I),
    re.compile(r"Tax\s+Credit\s+Application", re.I),
)
_FORM8_SIGNATURES = (
    re.compile(r"\bWELL\s+COMPLETION\s+OR\s+RECOMPLETION\s+REPORT", re.I),
    re.compile(r"\bFORM\s*8\b", re.I),
    # Section-27 title is unique to the WCR.
    re.compile(r"27\.\s*LOCATION\s+OF\s+WELL", re.I),
)


def _detect_form_type(text: str) -> str:
    """Return ``"wcr"``, ``"form15"``, or ``"unknown"``.

    Form 15 wins over Form 8 if both fire, because some Form 15 PDFs
    contain WCR-like boilerplate; the Form 15 markers are more specific.
    """
    form15_hits = sum(1 for pat in _FORM15_SIGNATURES if pat.search(text))
    form8_hits = sum(1 for pat in _FORM8_SIGNATURES if pat.search(text))
    if form15_hits >= 2:
        return "form15"
    if form8_hits >= 2:
        return "wcr"
    if form15_hits:
        return "form15"
    if form8_hits:
        return "wcr"
    return "unknown"


def _collapse_padded_dates(text: str) -> str:
    def fix(m: re.Match[str]) -> str:
        return re.sub(r"\s+", "", m.group(0))

    return _PADDED_DATE_RE.sub(fix, text)


def _collapse_padded_numbers(text: str) -> str:
    """Collapse "8 8 1 0" → "8810" for runs of 3+ single digits.

    Only runs out of the date collapser so it doesn't interfere with dates
    (which have ``/`` separators).
    """

    def fix(m: re.Match[str]) -> str:
        return re.sub(r"\s+", "", m.group(0))

    return _PADDED_NUM_RE.sub(fix, text)


def _extract_header(text: str, data: WCRPdfData) -> None:
    for field, pat in _HEADER_PATTERNS.items():
        m = pat.search(text)
        if m:
            setattr(data, field, m.group(1).strip())

    # Elevations: "21. DEPTH REFERENCE ELEVATION\n5742 (US Feet)"
    m = re.search(
        r"21\.\s*DEPTH REFERENCE ELEVATION\s*\n(\d{3,5}(?:\.\d+)?)", text, re.I
    )
    if m:
        data.elevation_ft = float(m.group(1))
    m = re.search(
        r"22\.\s*GRADED GROUND LEVEL ELEVATION\s*\n(\d{3,5}(?:\.\d+)?)", text, re.I
    )
    if m:
        data.ground_elev_ft = float(m.group(1))

    # Total depth + PBTD: "24. TOTAL DEPTH\nMD 19263 TVD 8387"
    m = re.search(r"24\.\s*TOTAL DEPTH\s*\n\s*MD\s*(\d+)\s*TVD\s*(\d+)", text, re.I)
    if m:
        data.total_md_ft = float(m.group(1))
        data.total_tvd_ft = float(m.group(2))
    m = re.search(
        r"25\.\s*PLUGGED BACK TOTAL DEPTH\s*\n\s*MD\s*(\d+)\s*TVD\s*(\d+)", text, re.I
    )
    if m:
        data.pbtd_md_ft = float(m.group(1))
        data.pbtd_tvd_ft = float(m.group(2))


# ---------------------------------------------------------------------------
# Section 27 — well-position rows
# ---------------------------------------------------------------------------

# Lines look like:
#   "Surface 1921 FNL 1239 FWL SWNW 31 3.0 S 4.0 W U 552369 4447779"
#   "Producing Interval Top 1641 FNL 148 FWL SWNW 3 1 3.0 S 4.0 W U"
#   "Producing Interval\nBottom 1650 FNL 196 FEL SENE 3 2 3.0 S 4.0 W U"
#   "Total Depth 1649 FNL 136 FEL SENE 3 2 3.0 S 4.0 W U"
#
# The Section column sometimes renders as "3 1" instead of "31" because of
# the form's narrow cell. We tolerate one space inside the section number.

_POSITION_NAMES = (
    "Surface",
    "Producing Interval Top",
    "Producing Interval Bottom",
    "Total Depth",
)

_POSITION_RE = re.compile(
    r"(?P<name>Surface|Producing\s+Interval\s+Top|Producing\s+Interval\s*\n?\s*Bottom|Total\s+Depth)\s+"
    r"(?P<d1>\d{1,5})\s+(?P<dir1>FNL|FSL)\s+"
    r"(?P<d2>\d{1,5})\s+(?P<dir2>FEL|FWL)\s+"
    # QQ can be a 4-letter quarter-of-quarter (SWNW / SENE / …) OR a
    # Government-lot designation (LOT1, LOT2, …) when the section
    # isn't a standard mile-square.
    r"(?P<qq>[NS][EW][NS][EW]|LOT\s*\d{1,2})\s+"
    r"(?P<sec>\d{1,2}(?:\s\d)?)\s+"
    r"(?P<twp>\d+(?:\.\d+)?)\s*(?P<twpdir>[NS])\s+"
    r"(?P<rng>\d+(?:\.\d+)?)\s*(?P<rngdir>[EW])\s+"
    r"(?P<mer>[A-Z])"
    r"(?:\s+(?P<utme>\d{4,7})\s+(?P<utmn>\d{4,8}))?",
    re.I | re.MULTILINE,
)


def _extract_positions(text: str, data: WCRPdfData) -> None:
    for m in _POSITION_RE.finditer(text):
        name = re.sub(r"\s+", " ", m.group("name").strip())
        # Normalise the canonical name we expose
        for canon in _POSITION_NAMES:
            if canon.lower() == name.lower():
                name = canon
                break

        fnl = fsl = fel = fwl = None
        d1, d2 = int(m.group("d1")), int(m.group("d2"))
        if m.group("dir1").upper() == "FNL":
            fnl = float(d1)
        else:
            fsl = float(d1)
        if m.group("dir2").upper() == "FEL":
            fel = float(d2)
        else:
            fwl = float(d2)

        sec = m.group("sec").replace(" ", "")
        twp_raw = m.group("twp")
        rng_raw = m.group("rng")
        try:
            twp = str(int(float(twp_raw)))
        except ValueError:
            twp = twp_raw
        try:
            rng = str(int(float(rng_raw)))
        except ValueError:
            rng = rng_raw

        row = WellPositionRow(
            name=name,
            fnl=fnl,
            fsl=fsl,
            fel=fel,
            fwl=fwl,
            qtr_qtr=m.group("qq").upper(),
            section=sec,
            township=twp,
            township_dir=m.group("twpdir").upper(),
            range=rng,
            range_dir=m.group("rngdir").upper(),
            meridian=m.group("mer").upper(),
            utm_easting=float(m.group("utme")) if m.group("utme") else None,
            utm_northing=float(m.group("utmn")) if m.group("utmn") else None,
        )
        # De-dup on name
        if not any(p.name == row.name for p in data.positions):
            data.positions.append(row)


# ---------------------------------------------------------------------------
# Section 28 — casing
# ---------------------------------------------------------------------------

# Casing block lives between "28. HOLE, CASING AND CEMENT" and "29. TUBING".
# Each row begins with a STRING code (COND/SURF/INT/LINER/PROD) followed by
# numerical fields. PyMuPDF text extraction collapses tabs to spaces, so we
# split on whitespace and use the row's STRING token as the anchor.

_CASING_STRINGS = ("COND", "SURF", "INT", "LINER", "PROD", "PROD1", "PROD2")
_CASING_BLOCK_RE = re.compile(
    r"28\.\s*HOLE, CASING AND CEMENT INFORMATION(.*?)(?:29\.\s*TUBING|$)",
    re.I | re.DOTALL,
)


def _extract_casing(text: str, data: WCRPdfData) -> None:
    m = _CASING_BLOCK_RE.search(text)
    if not m:
        return
    block = m.group(1)
    for line in block.splitlines():
        toks = line.split()
        if not toks:
            continue
        if toks[0].upper() not in _CASING_STRINGS:
            continue
        # Pull only what's immediately useful for the Excel output;
        # we don't need to parse every column perfectly.
        feature = toks[0]
        nums = _floats_in(toks[1:])
        row = CasingRow(
            feature=feature,
            diameter=nums[1] if len(nums) > 1 else None,
            weight=nums[2] if len(nums) > 2 else None,
            top_md=_find_first(nums, predicate=lambda v: 0 <= v < 30000, skip=3),
            bottom_md=_find_last(nums, predicate=lambda v: 100 <= v < 30000),
        )
        data.casing.append(row)


def _floats_in(toks: list[str]) -> list[float]:
    out: list[float] = []
    for t in toks:
        try:
            out.append(float(t.replace(",", "")))
        except ValueError:
            continue
    return out


def _find_first(values: list[float], *, predicate, skip: int = 0) -> float | None:
    for i, v in enumerate(values):
        if i < skip:
            continue
        if predicate(v):
            return v
    return None


def _find_last(values: list[float], *, predicate) -> float | None:
    for v in reversed(values):
        if predicate(v):
            return v
    return None


# ---------------------------------------------------------------------------
# Section 32 — formation tops
# ---------------------------------------------------------------------------

_FORMATIONS_BLOCK_RE = re.compile(
    r"32\.\s*FORMATION DETAILS and STRATIGRAPHIC MARKERS(.*?)(?:33\.\s*COMPLETED|$)",
    re.I | re.DOTALL,
)
# Each formation appears as "<index>\n<NAME>\n<TOP_MD>\n<TOP_TVD>\n<description>" or
# "<NAME>  <TOP_MD>  <TOP_TVD>  <description>" depending on PyMuPDF flow.
_FORMATION_ROW_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9 \-/]+?)\s+(\d{2,5})\s+(\d{2,5})\s+([A-Za-z ,]+)\s*$",
    re.MULTILINE,
)


def _extract_formations(text: str, data: WCRPdfData) -> None:
    m = _FORMATIONS_BLOCK_RE.search(text)
    if not m:
        return
    block = m.group(1)
    for fm in _FORMATION_ROW_RE.finditer(block):
        name = fm.group(1).strip()
        if name in {"FR", "FORMATION NAME"} or "DESCRIPTION" in name:
            continue
        data.formations.append(
            FormationTop(
                name=name,
                top_md=float(fm.group(2)),
                top_tvd=float(fm.group(3)),
                description=fm.group(4).strip(),
            )
        )


# ---------------------------------------------------------------------------
# Stage perf table (pg 3)
# ---------------------------------------------------------------------------

# Stage rows look like:
#   "1\t18,989\t19,202\t16\t0.4\t620,559\t\t\t12,726"
#   "43\t8,808\t9,022\t16\t0.4\t599,193\t\t\t10,403"
# After PyMuPDF extraction the whitespace varies; we anchor on the stage
# number (1-99), two depth columns with commas, and num_perfs.

_STAGE_ROW_RE = re.compile(
    r"^\s*(?P<stage>\d{1,3})\s+"
    r"(?P<top>\d{1,3}(?:,\d{3})+|\d{3,5})\s+"
    r"(?P<bot>\d{1,3}(?:,\d{3})+|\d{3,5})\s+"
    r"(?P<perfs>\d{1,4})\s+"
    r"(?P<size>\d+\.\d+|\d+)",
    re.MULTILINE,
)


_SECTION_33_RE = re.compile(
    r"33\.\s*COMPLETED and TESTED INTERVALS(.*?)(?:34A?\.\s*PRODUCTION|$)",
    re.I | re.DOTALL,
)


def _extract_section_33_intervals(text: str, data: WCRPdfData) -> None:
    """Pull the overall perf interval(s) from Section 33 as a fallback.

    Many WCRs omit the per-stage perf table but still report the overall
    completed interval(s) in Section 33 (FR / TOP MD / BOTTOM MD / TVD /
    stim / status). Each row becomes a synthetic PerfStage so downstream
    consumers (Frac_Start / Frac_End in the WCR location rows) still work.
    """
    if data.perf_stages:
        return  # We already have per-stage detail; don't overwrite.
    m = _SECTION_33_RE.search(text)
    if not m:
        return
    block = m.group(1)
    # Each row begins with a single FR digit, then 4 floats (top MD, bottom
    # MD, top TVD, bottom TVD), then stim type + status.
    row_re = re.compile(
        r"^\s*(\d+)\s+(\d{3,5})\s+(\d{3,5})\s+(\d{3,5})\s+(\d{3,5})\s+(\S.*?)\s+([A-Z]+(?:\s+[A-Z]+)*)",
        re.MULTILINE,
    )
    stage_no = 1
    for rm in row_re.finditer(block):
        top = float(rm.group(2))
        bot = float(rm.group(3))
        if top < 100 or bot < 100 or top >= bot:
            continue
        data.perf_stages.append(
            PerfStage(
                stage=stage_no,
                interval_top_md=top,
                interval_bottom_md=bot,
                num_perfs=None,
                size_in=None,
            )
        )
        stage_no += 1


def _extract_perf_stages(text: str, data: WCRPdfData) -> None:
    seen: set[int] = set()
    for m in _STAGE_ROW_RE.finditer(text):
        stage = int(m.group("stage"))
        # Stages number 1-N for a single well; skip duplicates and absurd values.
        if stage < 1 or stage > 200 or stage in seen:
            continue
        top = float(m.group("top").replace(",", ""))
        bot = float(m.group("bot").replace(",", ""))
        # Sanity: depths should both be in the lateral range (>1000 ft, MD-ordered).
        if top < 1000 or bot < 1000 or top >= bot:
            continue
        try:
            num_perfs = int(m.group("perfs"))
        except ValueError:
            num_perfs = None
        try:
            size = float(m.group("size"))
        except ValueError:
            size = None
        data.perf_stages.append(
            PerfStage(
                stage=stage,
                interval_top_md=top,
                interval_bottom_md=bot,
                num_perfs=num_perfs,
                size_in=size,
            )
        )
        seen.add(stage)
    data.perf_stages.sort(key=lambda s: s.stage)
