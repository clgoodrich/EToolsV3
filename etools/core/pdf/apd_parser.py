"""Parse a DOGM Form 3 — Application for Permit to Drill PDF.

The APD's load-bearing content for the Casing Review:

    Page 1 — header (well/operator/API/elevation/MD-TVD) and the
             "Hole, Casing, and Cement Information" table. Each casing
             string is rendered as a fixed-order column dump that
             PyMuPDF flattens into ~22 lines per string.
    Page 2 — Formation Tops + Safety Factors table (frac gradient at
             shoe, pore pressure, design factors).

We parse with PyMuPDF text + targeted regex; the LLM layer can backfill
if rules miss something, but most APDs are clean machine-generated PDFs.
"""

from __future__ import annotations

import re
from pathlib import Path

from etools.logging_setup import get_logger
from etools.models import (
    APDCasingString,
    APDFormationTop,
    APDLocationRow,
    APDPdfData,
)

log = get_logger(__name__)


_STRING_TAGS = ("Cond", "Surf", "I1", "I2", "I3", "Prod", "Prod1", "Prod2", "Liner")
# Each string row in the PDF starts with a leading-space-padded tag on its
# own line. Followed by 21 more lines: the data dump plus seven blanks for
# the unused stage-2 columns.
_STRING_LINE_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(t) for t in _STRING_TAGS) + r")\s*$",
    re.MULTILINE,
)
_LENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")
_GRADE_THREAD_RE = re.compile(r"\s*([A-Z][A-Z0-9\-]*(?:\s*-\s*\d+)?)\s+([A-Z]{2,6})\s*")


def parse_apd_pdf(
    path: str | Path,
    *,
    mode: str = "rules+llm",
    use_llm: bool | None = None,
) -> APDPdfData:
    """Parse a Form 3 APD PDF and return an ``APDPdfData``.

    Parameters
    ----------
    mode : str
        ``"rules"`` (regex only — fast, no Ollama),
        ``"llm"``   (skip regex, pure LLM extraction),
        ``"rules+llm"`` (regex first, LLM backfills missing fields).
    use_llm : bool | None
        Overrides ``settings.llm.enabled`` when set.
    """
    path = Path(path)
    log.info("apd_pdf.parse.start", path=str(path), mode=mode)

    if mode not in ("rules", "llm", "rules+llm"):
        raise ValueError(f"Unknown mode {mode!r}")

    text = _extract_text(path)
    data = APDPdfData(source_pdf=str(path))
    data.form_type = "apd" if "APPLICATION FOR PERMIT TO DRILL" in text else "unknown"

    if mode != "llm":
        _extract_header(text, data)
        _extract_locations(text, data)
        _extract_casing_table(text, data)
        _extract_formations(text, data)
        _extract_frac_gradient(text, data)
        _extract_bope(text, data)

    # LLM layer — only fills empty fields when mode == 'rules+llm',
    # overwrites everything when mode == 'llm'.
    from etools.config import settings as _s
    if use_llm is None:
        use_llm = bool(_s.llm.enabled)
    needs_llm = mode == "llm" or (
        use_llm and mode == "rules+llm" and _apd_incomplete(data)
    )
    if use_llm and needs_llm and text:
        try:
            from etools.core.llm import OllamaClient
            from etools.core.pdf.apd_llm import llm_apd_extract

            client = OllamaClient()
            if client.health() and client.has_model():
                result = llm_apd_extract(text, client=client)
                _merge_llm(data, result, overwrite=(mode == "llm"))
        except Exception as exc:
            log.warning("apd_pdf.llm.failed", error=str(exc))
            data.warnings.append(f"LLM extraction failed: {exc}")

    log.info(
        "apd_pdf.parse.done",
        path=str(path),
        casing=len(data.casing),
        formations=len(data.formations),
        locations=len(data.locations),
        api=data.api,
    )
    return data


def _apd_incomplete(data: APDPdfData) -> bool:
    """An APD is 'incomplete' if the calc engine can't proceed without LLM help."""
    if not data.api or not data.well_name:
        return True
    if not data.casing:
        return True
    # We expect at least Surface + Production for the calc engine.
    tags = {c.tag for c in data.casing}
    if "Surf" not in tags and "Surface" not in tags:
        return True
    if not any(t.startswith("Prod") for t in tags):
        return True
    return False


def _merge_llm(into: APDPdfData, llm, *, overwrite: bool) -> None:
    """Fill ``into`` from ``llm``. Always-overwrite when ``overwrite=True``,
    otherwise only fill blanks left by the rules layer."""
    scalar_map = {
        "well_name": "well_name",
        "api": "api_number",
        "operator": "operator",
        "field_name": "field_name",
        "county": "county",
        "well_type": "well_type",
        "slant": "slant",
        "proposed_md_ft": "proposed_md_ft",
        "proposed_tvd_ft": "proposed_tvd_ft",
        "ground_elev_ft": "ground_elev_ft",
        "frac_gradient_psi_per_ft": "frac_gradient_psi_per_ft",
    }
    for attr, src in scalar_map.items():
        v = getattr(llm, src, None)
        if v not in (None, "") and (overwrite or getattr(into, attr, None) in (None, "")):
            setattr(into, attr, v)

    if (overwrite or not into.casing) and llm.casing:
        from etools.models import APDCasingString
        into.casing = [APDCasingString(**c.model_dump()) for c in llm.casing]
    if (overwrite or not into.locations) and llm.locations:
        from etools.models import APDLocationRow
        into.locations = [APDLocationRow(**L.model_dump()) for L in llm.locations]
    if (overwrite or not into.formations) and llm.formations:
        from etools.models import APDFormationTop
        into.formations = [APDFormationTop(**f.model_dump()) for f in llm.formations]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def _extract_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to parse APD PDFs") from exc
    doc = fitz.open(str(path))
    pages: list[str] = []
    for i in range(len(doc)):
        try:
            pages.append(doc.load_page(i).get_text("text"))
        except Exception as exc:
            log.warning("apd_pdf.page_failed", page=i + 1, error=str(exc))
            pages.append("")
    return "\n\n<<<PAGE>>>\n\n".join(pages)


# ---------------------------------------------------------------------------
# Header (sections 1-29)
# ---------------------------------------------------------------------------


_HEADER_PATTERNS: dict[str, re.Pattern[str]] = {
    "well_name": re.compile(r"1\.\s*WELL NAME and NUMBER\s*\n([^\n]+)", re.I),
    "well_type": re.compile(r"4\.\s*TYPE OF WELL\s*\n([^\n]+)", re.I),
    "field_name": re.compile(r"3\.\s*FIELD OR WILDCAT\s*\n([^\n]+)", re.I),
    "operator": re.compile(r"6\.\s*NAME OF OPERATOR\s*\n([^\n]+)", re.I),
    "county": re.compile(r"21\.\s*COUNTY\s*\n([^\n]+)", re.I),
}


def _extract_header(text: str, data: APDPdfData) -> None:
    for field_, pat in _HEADER_PATTERNS.items():
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            if val:
                setattr(data, field_, val)

    # API is rendered as "API  43013537270000" on the proposed-wellbore line.
    m = re.search(r"API\s+(\d{10,14})", text)
    if m:
        data.api = m.group(1)

    # Proposed depth: "26. PROPOSED DEPTH\nMD: 18592     TVD: 7650"
    m = re.search(r"MD:\s*(\d+)\s+TVD:\s*(\d+)", text)
    if m:
        data.proposed_md_ft = float(m.group(1))
        data.proposed_tvd_ft = float(m.group(2))

    # Ground elevation: "27. ELEVATION - GROUND LEVEL\n5078"
    m = re.search(
        r"27\.\s*ELEVATION\s*-\s*GROUND LEVEL\s*\n\s*(\d{3,5}(?:\.\d+)?)", text, re.I
    )
    if m:
        data.ground_elev_ft = float(m.group(1))

    # Slant — only the chosen value is non-blank in the printed form.
    m = re.search(
        r"19\.\s*SLANT[^\n]*\n+\s*\n([^\n]+)", text, re.I
    )
    if m and m.group(1).strip():
        data.slant = m.group(1).strip()


# ---------------------------------------------------------------------------
# Section 20 — three location rows
# ---------------------------------------------------------------------------


_LOCATION_NAMES = (
    "Location At Surface",
    "Location At Kickoff Point",
    "Top of Uppermost Producing Zone",
    "At Total Depth",
)

# Document-stated kickoff: "KOP: 7965' MD, 7865' TVD" (TVD optional). The
# directional-plan tables also print "KOP, Build 2 DLS" etc., so anchor on the
# "MD" token to avoid those.
_KOP_MD_RE = re.compile(
    r"KOP[:\s]+([\d,]+)\s*'?\s*MD(?:\s*,\s*([\d,]+)\s*'?\s*TVD)?", re.I
)


def _extract_locations(text: str, data: APDPdfData) -> None:
    # Each location row is rendered as:
    #   "Location At Surface"
    #   "560 FSL   804 FEL"
    #   "SESE"
    #   "23"
    #   "3.0 S"
    #   "2.0 W"
    #   "U"
    name_pat = re.compile(
        r"(" + "|".join(re.escape(n) for n in _LOCATION_NAMES) + r")\s*\n"
        r"\s*(\d{1,5})\s*(FNL|FSL)\s+(\d{1,5})\s*(FEL|FWL)\s*\n"
        r"\s*([NS][EW][NS][EW]|LOT\s*\d{1,2})\s*\n"
        r"\s*(\d{1,2})\s*\n"
        r"\s*(\d+(?:\.\d+)?)\s*([NS])\s*\n"
        r"\s*(\d+(?:\.\d+)?)\s*([EW])\s*\n"
        r"\s*([A-Z])",
        re.I,
    )
    for m in name_pat.finditer(text):
        name = m.group(1)
        d1, dir1 = int(m.group(2)), m.group(3).upper()
        d2, dir2 = int(m.group(4)), m.group(5).upper()
        row = APDLocationRow(
            name=name,
            fnl=float(d1) if dir1 == "FNL" else None,
            fsl=float(d1) if dir1 == "FSL" else None,
            fel=float(d2) if dir2 == "FEL" else None,
            fwl=float(d2) if dir2 == "FWL" else None,
            qtr_qtr=m.group(6).upper(),
            section=m.group(7),
            township=str(int(float(m.group(8)))),
            township_dir=m.group(9).upper(),
            range=str(int(float(m.group(10)))),
            range_dir=m.group(11).upper(),
            meridian=m.group(12).upper(),
        )
        if not any(p.name == row.name for p in data.locations):
            data.locations.append(row)

    _extract_kop_md(text, data)


# "A 5,000 psi BOP system or better will be used", "5000 psi BOP",
# or "...Preventer - rated to 5,000 psi".
_BOPE_PSI_RES = (
    re.compile(r"([\d,]{3,6})\s*psi\s+BOP\b", re.I),
    re.compile(r"\bBOP\b[^.\n]{0,40}?rated to\s*([\d,]{3,6})\s*psi", re.I),
    re.compile(r"\bpreventer\b[^.\n]{0,40}?rated to\s*([\d,]{3,6})\s*psi", re.I),
)


def _extract_bope(text: str, data: APDPdfData) -> None:
    """Pull the permit-stated BOP working pressure (psi) from the
    "Minimum Specifications for Pressure Control" section, if present."""
    for rx in _BOPE_PSI_RES:
        m = rx.search(text)
        if m:
            val = _to_float(m.group(1).replace(",", ""))
            if val and val >= 1000:  # plausible BOP rating, not a stray number
                data.bope_system_psi = val
                return


def _extract_kop_md(text: str, data: APDPdfData) -> None:
    """Pull the document-stated kickoff MD/TVD and attach it to the
    kickoff location row (the row carries the footages; this adds the depth)."""
    m = _KOP_MD_RE.search(text)
    if not m:
        return
    data.kop_md_ft = float(m.group(1).replace(",", ""))
    if m.group(2):
        data.kop_tvd_ft = float(m.group(2).replace(",", ""))
    for loc in data.locations:
        if "kickoff" in (loc.name or "").lower():
            loc.measured_depth = data.kop_md_ft
            loc.tvd_ft = data.kop_tvd_ft
            break


# ---------------------------------------------------------------------------
# Hole, Casing and Cement table
# ---------------------------------------------------------------------------


def _extract_casing_table(text: str, data: APDPdfData) -> None:
    """Parse the Hole/Casing/Cement table from page 1.

    PyMuPDF prints every cell on its own line, in row-major order. Each
    string occupies one tag line + 21 value lines. Stage-2 columns (the
    ones between the lead and tail cement entries) are usually blank.
    """
    idx = text.find("Hole, Casing, and Cement Information")
    if idx < 0:
        return
    # Strip table headers, then start collecting from the first tag we see.
    block = text[idx:]
    end = block.find("ATTACHMENTS")
    if end > 0:
        block = block[:end]

    lines = [ln.rstrip() for ln in block.splitlines()]
    # Find all tag-line indices, then peel 21 fields from each.
    tag_positions: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = _STRING_LINE_RE.match(ln)
        if m:
            tag_positions.append((i, m.group(1)))

    for k, (i, tag) in enumerate(tag_positions):
        # Slice from this tag up to (but not including) the next tag — the
        # Conductor row in particular has only 11 lines, not 22, because
        # conductor cement is single-stage. A fixed 22-line slice would
        # mis-attribute the next string's lead-cement cells to this row's
        # tail-cement columns.
        next_i = tag_positions[k + 1][0] if k + 1 < len(tag_positions) else i + 23
        cells = [ln.strip() for ln in lines[i + 1 : next_i]]
        s = _build_string_from_cells(tag, cells)
        if s is not None:
            data.casing.append(s)


def _build_string_from_cells(tag: str, cells: list[str]) -> APDCasingString | None:
    """Map the 21-line field dump to an ``APDCasingString``."""
    # Layout (0-indexed, after the tag):
    #   0: hole size            6: cement lead type      14-16: stage-2 cement (blank)
    #   1: casing size          7: cement lead sacks     17: cement tail type
    #   2: length top-bottom    8: cement lead yield     18: cement tail sacks
    #   3: weight               9: cement lead weight    19: cement tail yield
    #   4: grade & thread      10-13: blank (stage-2     20: cement tail weight
    #   5: max mud weight             MW/etc.)
    # The conductor row sometimes ships with only one cement stage and
    # ~10 cells total (no tail). Anything shorter than 7 is unusable.
    if len(cells) < 7:
        return None

    s = APDCasingString(tag=tag)
    s.hole_size_in = _to_float(cells[0])
    s.casing_size_in = _to_float(cells[1])
    lm = _LENGTH_RE.search(cells[2])
    if lm:
        s.length_top_ft = float(lm.group(1))
        s.length_bottom_ft = float(lm.group(2))
    s.weight_ppf = _to_float(cells[3])
    gm = _GRADE_THREAD_RE.search(cells[4])
    if gm:
        s.grade = gm.group(1).strip()
        s.collar = gm.group(2).strip()
    elif cells[4].strip():
        # No collar — conductor pipe often ships as just "UKN" or "WELD".
        s.grade = cells[4].strip()
    s.max_mud_weight_ppg = _to_float(cells[5]) if len(cells) > 5 else None
    if len(cells) > 6:
        s.cement_lead_type = cells[6] or None
    if len(cells) > 7:
        s.cement_lead_sacks = _to_int(cells[7])
    if len(cells) > 8:
        s.cement_lead_yield = _to_float(cells[8])
    if len(cells) > 9:
        s.cement_lead_weight_ppg = _to_float(cells[9])
    # Tail cement starts at offset 17 (after 7 blanks for stage 2).
    if len(cells) >= 21:
        s.cement_tail_type = cells[17] or None
        s.cement_tail_sacks = _to_int(cells[18])
        s.cement_tail_yield = _to_float(cells[19])
        s.cement_tail_weight_ppg = _to_float(cells[20])
    return s


# ---------------------------------------------------------------------------
# Formation Tops + Frac gradient (page 2)
# ---------------------------------------------------------------------------


# The page-2 "FORMATION TOPS" table. Header + rows follow, one token per
# PyMuPDF line, until the next section. Columns vary but are typically
# FORMATION | SHL TOP (TVD) | BHL TOP (TVD) | MD TOP (well plan).
_FT_HEADER_RE = re.compile(r"FORMATION\s+TOPS", re.I)
_FT_STOP_RE = re.compile(
    r"DEPTH TO OIL|<<<PAGE>>>|PRESSURE CONTROL|CIRCULATING MEDIUM", re.I
)
# Lines that are column headers / labels, not formation names.
_FT_LABEL_RE = re.compile(
    r"\b(FORMATION|SHL\s+TOP|BHL\s+TOP|MD\s+TOP|\(?TVD\)?|well\s+plan)\b", re.I
)
# A line that is *only* a bare column tag like "MD", "TVD" or "TVD /".
_FT_BARE_LABEL_RE = re.compile(r"^(?:MD|TVD)\s*/?\s*$", re.I)


def _ft_valid_depth(v: float) -> bool:
    """A real formation top is at Surface (0) or hundreds+ of feet down.
    Anything in between is a misparsed header fragment, not a depth."""
    return v == 0.0 or v >= 100.0


def _ft_depth_token(s: str) -> float | None:
    """A FORMATION TOPS cell: ``Surface`` -> 0, ``5,061'`` -> 5061, else None
    (i.e. the line is a formation name, not a depth)."""
    s = s.strip()
    if s.lower() == "surface":
        return 0.0
    m = re.match(r"^(\d[\d,]*)", s)  # leading digits, tolerate ',' and foot mark
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_formations_tops_table(text: str) -> list[APDFormationTop]:
    """Parse the page-2 "FORMATION TOPS" summary table (any names).

    TVD comes from the first depth column (SHL TOP), MD from the last
    (MD TOP / well plan). Returns [] if the table isn't present.
    """
    hdr = _FT_HEADER_RE.search(text)
    if not hdr:
        return []
    block = text[hdr.end():]
    stop = _FT_STOP_RE.search(block)
    if stop:
        block = block[: stop.start()]

    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    rows: list[tuple[str, list[float]]] = []
    name: str | None = None
    vals: list[float] = []

    def _flush() -> None:
        nonlocal name, vals
        if name and vals:
            rows.append((name, vals))
        name, vals = None, []

    for ln in lines:
        if _FT_LABEL_RE.search(ln) or _FT_BARE_LABEL_RE.match(ln):
            continue
        depth = _ft_depth_token(ln)
        if depth is not None:
            if name is not None:
                vals.append(depth)
        elif name is not None and not vals:
            name = f"{name} {ln}"  # multi-line formation name
        else:
            _flush()
            name = ln
    _flush()

    out: list[APDFormationTop] = []
    for nm, vs in rows:
        if not any(c.isalpha() for c in nm):
            continue  # name must have letters
        if not any(_ft_valid_depth(v) for v in vs):
            continue  # no plausible depth -> misparsed header fragment
        tvd = vs[0] if vs else None
        md = vs[2] if len(vs) >= 3 else (vs[-1] if vs else None)
        out.append(APDFormationTop(name=nm, tvd_ft=tvd, md_ft=md))
    return out


# The directional-plan appendix "Formations" table. Rows stream one token per
# line as: MD, TVD, Name, Dip — e.g. "5,097.79 / 5,061.00 / Top Green River /
# 2.42". This list is usually the fullest (every geosteering marker).
_GEO_HEADER_RE = re.compile(r"(?m)^\s*Formations\s*$")
_GEO_STOP_RE = re.compile(
    r"(?im)^\s*(?:MD|TVD)\s*$|\+E/-W|Local Coordinates|Plan Annotations|Comment"
)


def _geo_num(s: str) -> float | None:
    """A geosteering numeric cell like ``5,097.79`` or ``2.42``; else None."""
    s = s.strip()
    if re.fullmatch(r"-?[\d,]+(?:\.\d+)?", s):
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_formations_geosteering(text: str) -> list[APDFormationTop]:
    """Parse the directional-plan appendix formation list (MD, TVD, Name, Dip
    repeating). Returns [] if not present."""
    hdr = _GEO_HEADER_RE.search(text)
    if not hdr:
        return []
    block = text[hdr.end():]
    stop = _GEO_STOP_RE.search(block)
    if stop:
        block = block[: stop.start()]

    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    out: list[APDFormationTop] = []
    nums: list[float] = []
    for ln in lines:
        v = _geo_num(ln)
        if v is not None:
            nums.append(v)
            continue
        if not any(c.isalpha() for c in ln):
            continue
        # A name line. Its depth pair is the last two depth-magnitude numbers
        # since the previous formation (dip / dip-direction values are small
        # and filtered out). Column order varies by operator, so MD is the
        # larger of the pair and TVD the smaller (MD >= TVD always).
        depths = [n for n in nums if _ft_valid_depth(n) and n > 0.0]
        if len(depths) >= 2:
            a, b = depths[-2], depths[-1]
            out.append(
                APDFormationTop(name=ln, tvd_ft=min(a, b), md_ft=max(a, b))
            )
        nums = []
    return out


# Legacy layout: each row is ``name\nTVD\nMD`` and the name is one of a known
# set. Kept as a last-resort fallback so older PDFs don't regress.
_KNOWN_FORMATIONS = (
    "Uinta",
    "Green River",
    "Garden Gulch member",
    "Uteland Butte",
    "Mahogany",
    "Wasatch",
    "Castle Peak",
    "Mancos",
    "Frontier",
    "Lateral TD",
)


def _extract_formations_known(text: str) -> list[APDFormationTop]:
    pat = re.compile(
        r"(" + "|".join(re.escape(n) for n in _KNOWN_FORMATIONS) + r")\s*\n"
        r"\s*([\d,]+)\s*'?\s*\n"
        r"\s*([\d,]+)\s*'?",
        re.I,
    )
    out: list[APDFormationTop] = []
    for m in pat.finditer(text):
        try:
            a = float(m.group(2).replace(",", ""))
            b = float(m.group(3).replace(",", ""))
        except ValueError:
            continue
        if not (_ft_valid_depth(a) and _ft_valid_depth(b)):
            continue  # drop misparsed non-depth values (e.g. a casing size)
        # Column order isn't guaranteed; MD >= TVD physically.
        out.append(APDFormationTop(name=m.group(1), tvd_ft=min(a, b), md_ft=max(a, b)))
    return out


def _plausible_formation_name(nm: str) -> bool:
    """Reject junk the loose table parsers can pick up (header fragments,
    mashed-together multi-name strings, sentences from the drilling plan)."""
    nm = nm.strip()
    if not (2 <= len(nm) <= 35):
        return False
    if not any(c.isalpha() for c in nm):
        return False
    if any(ch in nm for ch in ":%()"):  # sentences / column labels, not names
        return False
    if len(nm.split()) > 5:
        return False
    return True


def _finalize_formations(rows: list[APDFormationTop]) -> list[APDFormationTop]:
    """Drop implausible names and enforce MD >= TVD on every row."""
    out: list[APDFormationTop] = []
    for x in rows:
        if not _plausible_formation_name(x.name):
            continue
        tvd, md = x.tvd_ft, x.md_ft
        if tvd is not None and md is not None and tvd > md:
            tvd, md = md, tvd  # physical guarantee: measured depth >= TVD
        out.append(APDFormationTop(name=x.name.strip(), tvd_ft=tvd, md_ft=md))
    return out


def _extract_formations(text: str, data: APDPdfData) -> None:
    """Formation tops from the APD.

    We parse every table we know how to read — the page-2 "FORMATION TOPS"
    summary, the directional-plan appendix list, and the legacy known-name
    layout — clean each, then keep whichever yielded the **most** valid tops,
    since the user wants the fullest list available.
    """
    candidates = [
        _finalize_formations(_extract_formations_geosteering(text)),
        _finalize_formations(_extract_formations_tops_table(text)),
        _finalize_formations(_extract_formations_known(text)),
    ]
    best = max(candidates, key=len)
    data.formations.extend(best)


_PPG_TO_PSI_PER_FT = 0.05194806  # psi/ft per ppg per ft
# A frac gradient at shoe realistically lands in this psi/ft band. Anything
# outside it (e.g. a casing weight of 24 ppf → 1.25 psi/ft) is not a frac
# gradient and must not be selected.
_FRAC_PLAUSIBLE_LO = 0.40
_FRAC_PLAUSIBLE_HI = 1.10


def _frac_to_psi_per_ft(x: float) -> float:
    """A value >5 is ppg (converted); a small value is already psi/ft."""
    return round(x * _PPG_TO_PSI_PER_FT, 4) if x > 5 else x


def _extract_frac_gradient(text: str, data: APDPdfData) -> None:
    """Pull the production-shoe frac gradient from the Safety Factors table.

    The table renders as a column block with "Frac Grad @ Shoe" as a header
    label followed by per-string values, interleaved with other columns
    (casing weight, safety factors). The old heuristic took ``max(nums[:4])``,
    which on some permits grabbed the casing **weight** (e.g. 24 ppf) and
    mis-converted it as ppg → 1.25 psi/ft, silently inflating burst design
    factors. Instead we convert each candidate to psi/ft and keep only those in
    a physically plausible frac-gradient band, then take the largest (the
    production shoe is deepest → highest gradient).
    """
    m = re.search(r"Frac\s*\n?\s*Grad[^\n]*\n?\s*@?\s*Shoe[^\n]*\n", text, re.I)
    if not m:
        return
    tail = text[m.end() : m.end() + 400]
    # Widen the collection window to ≤60 so casing weights are seen (and then
    # rejected by the plausibility filter) rather than sneaking in under ≤25.
    raw_nums = [
        float(x)
        for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", tail)
        if 0 < float(x) <= 60
    ]
    if not raw_nums:
        return
    candidates = [_frac_to_psi_per_ft(x) for x in raw_nums[:8]]
    plausible = [c for c in candidates if _FRAC_PLAUSIBLE_LO <= c <= _FRAC_PLAUSIBLE_HI]
    if plausible:
        data.frac_gradient_psi_per_ft = max(plausible)
        return
    # Nothing lands in the plausible band — fall back to the old behaviour but
    # flag it so a reviewer verifies against the permit instead of trusting a
    # silently-wrong number.
    chosen = _frac_to_psi_per_ft(max(raw_nums[:4]) if len(raw_nums) >= 4 else raw_nums[-1])
    data.frac_gradient_psi_per_ft = chosen
    data.warnings.append(
        f"Frac gradient @ shoe parsed as {chosen} psi/ft, outside the expected "
        f"{_FRAC_PLAUSIBLE_LO}–{_FRAC_PLAUSIBLE_HI} psi/ft range — verify against the permit."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(s: str) -> float | None:
    if not s:
        return None
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> int | None:
    v = _to_float(s)
    return int(v) if v is not None else None
