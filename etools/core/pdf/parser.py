"""Operator-submitted survey PDF parser — layered pipeline.

The parser tries cheap heuristics first and only escalates to the local
LLM when those fail. The layers, in order:

    Layer 1  Docling  → high-quality markdown (text + table-aware)
    Layer 2  Rules    → regex/pandas pull from the markdown for clean PDFs
    Layer 3  LLM      → text LLM on the markdown, schema-constrained output
    Layer 4  Vision   → vision LLM on rendered page images (scanned PDFs)

Each layer fills in what's missing rather than replacing the previous
result, so a partial-rules + LLM-completion outcome is supported.

If Ollama is unavailable, layers 3-4 are silently skipped — the parser
still returns whatever the rules + Docling extraction yielded.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from etools.config import settings
from etools.core.pdf.docling_extractor import pdf_to_markdown
from etools.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public result type — same shape the UI consumed before, plus provenance.
# ---------------------------------------------------------------------------


_PROVENANCE_FIELDS = (
    "surface_lat",
    "surface_lon",
    "surface_elevation_ft",
    "north_reference",
    "well_name",
    "api",
    "operator",
    "grid_convergence_deg",
    "magnetic_declination_deg",
    "plss_legal",
    "surveys",
)


@dataclass(slots=True)
class ParsedSurvey:
    surveys: pd.DataFrame  # MeasuredDepth / Inclination / Azimuth
    surface_lat: float | None = None
    surface_lon: float | None = None
    surface_elevation_ft: float | None = None
    north_reference: str | None = None
    well_name: str | None = None
    api: str | None = None
    operator: str | None = None
    grid_convergence_deg: float | None = None
    magnetic_declination_deg: float | None = None
    plss_legal: str | None = None
    source_file: str | None = None
    layers_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Per-field provenance — maps field name to the layer that set it
    # ("rules", "llm-text", "llm-vision", "docling-ocr", etc.).
    field_sources: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def parse_survey_pdf(path: str | Path) -> ParsedSurvey:
    path = Path(path)
    log.info("pdf.parse.start", path=str(path))

    result = ParsedSurvey(surveys=pd.DataFrame(), source_file=str(path))

    # ---- Layer 1: Docling ----
    try:
        markdown, doc_meta = pdf_to_markdown(path, with_ocr=False)
        result.layers_used.append("docling")
    except Exception as e:
        log.warning("pdf.docling.failed", error=str(e))
        result.warnings.append(f"Docling failed: {e}")
        markdown = ""
        doc_meta = {"page_count": 0, "looks_scanned": False}

    if doc_meta.get("looks_scanned"):
        # Re-run Docling with OCR to see if we can recover text from images.
        try:
            markdown, doc_meta = pdf_to_markdown(path, with_ocr=True)
            result.layers_used.append("docling-ocr")
        except Exception as e:
            log.warning("pdf.docling-ocr.failed", error=str(e))
            result.warnings.append(f"Docling OCR failed: {e}")

    # ---- Layer 1b: PyMuPDF raw text ----
    # Docling's TableFormer occasionally drops survey-table continuation
    # pages (we've seen std::bad_alloc on dense numeric pages). PyMuPDF's
    # plain text extraction is fast and resilient — we concatenate it with
    # the Docling markdown so the row-regex sees BOTH sources.
    pymupdf_text = _pymupdf_extract_text(path)
    if pymupdf_text:
        # Append after the Docling markdown so docling-derived metadata
        # (well name, location etc.) still wins for non-survey fields.
        markdown = (markdown or "") + "\n\n<<<PYMUPDF>>>\n" + pymupdf_text
        result.layers_used.append("pymupdf-text")

    # ---- Layer 2: Rules ----
    if markdown:
        rules_result = _rules_extract(markdown)
        _merge(result, rules_result)
        result.layers_used.append("rules")

    # ---- Layer 3: LLM (text) ----
    if settings.llm.enabled and _is_incomplete(result) and markdown:
        try:
            from etools.core.llm import OllamaClient
            from etools.core.pdf.llm_extractor import llm_extract

            client = OllamaClient()
            if client.health() and client.has_model():
                llm_result = llm_extract(markdown, client=client)
                _merge(result, _from_llm(llm_result))
                result.layers_used.append("llm-text")
            else:
                log.info("pdf.llm.skip", reason="ollama unavailable or model missing")
        except Exception as e:
            log.warning("pdf.llm.failed", error=str(e))
            result.warnings.append(f"LLM extraction failed: {e}")

    # ---- Layer 4: LLM (vision) — only if we still have nothing ----
    if settings.llm.enabled and result.surveys.empty:
        # Render PDF pages to images on demand; expensive, last resort.
        try:
            from etools.core.pdf.llm_extractor import llm_extract_from_image
            from etools.core.llm import OllamaClient

            client = OllamaClient()
            if client.health():
                images = _render_pages_to_png(path, max_pages=8)
                if images:
                    llm_result = llm_extract_from_image(images, client=client)
                    _merge(result, _from_llm(llm_result))
                    result.layers_used.append("llm-vision")
        except Exception as e:
            log.warning("pdf.llm-vision.failed", error=str(e))
            result.warnings.append(f"Vision LLM extraction failed: {e}")

    if result.surveys.empty:
        result.warnings.append(
            "No MD/INC/AZI table extracted by any layer — the PDF may be image-only "
            "or use a layout the parser doesn't recognize."
        )

    log.info(
        "pdf.parse.done",
        path=str(path),
        survey_rows=len(result.surveys),
        layers=result.layers_used,
    )
    return result


# ---------------------------------------------------------------------------
# Layer 2 — rules-based extraction from Docling markdown
# ---------------------------------------------------------------------------


def rules_extract(markdown: str) -> ParsedSurvey:
    """Public alias — runs the regex/heuristic extraction on Docling markdown."""
    return _rules_extract(markdown)


def _rules_extract(markdown: str) -> ParsedSurvey:
    out = ParsedSurvey(surveys=pd.DataFrame())

    extractors = {
        "surface_lat": _extract_lat,
        "surface_lon": _extract_lon,
        "surface_elevation_ft": _extract_elevation,
        "north_reference": _extract_north_ref,
        "well_name": _extract_well_name,
        "api": _extract_api,
        "operator": _extract_operator,
        "grid_convergence_deg": _extract_grid_convergence,
        "magnetic_declination_deg": _extract_mag_declination,
        "plss_legal": _extract_plss,
    }
    for fname, fn in extractors.items():
        v = fn(markdown)
        setattr(out, fname, v)
        if v is not None:
            out.field_sources[fname] = "rules"

    surveys = _extract_survey_rows(markdown)
    out.surveys = surveys
    if not surveys.empty:
        out.field_sources["surveys"] = "rules"
    return out


_LAT_DEC_RE = re.compile(r"(?:surface\s+)?lat(?:itude)?\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_LON_DEC_RE = re.compile(r"(?:surface\s+)?lon(?:gitude)?\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_LAT_DMS_RE = re.compile(r"\bN\s*(\d{1,3})\s+(\d{1,2})\s+(\d{1,2}(?:\.\d+)?)", re.I)
_LON_DMS_RE = re.compile(r"\bW\s*(\d{1,3})\s+(\d{1,2})\s+(\d{1,2}(?:\.\d+)?)", re.I)
_ELEV_RE = re.compile(r"\b(?:KB|GLE|GL|elev(?:ation)?)\s*[:=]?\s*(\d{3,5}(?:\.\d+)?)", re.I)
# "(4944.3 ft above MSL)" / "4944 ft AMSL" — kelly bushing / ground level.
# Require MSL or AMSL specifically so we don't pick up "200 ft above the
# surface casing shoe" type sentences.
_ELEV_MSL_RE = re.compile(
    r"\(?(\d{3,5}(?:\.\d+)?)\s*(?:ft|feet)\.?\s*(?:above\s+)?(?:AMSL|MSL)",
    re.I,
)
_API_RE = re.compile(r"\bAPI(?:\s*(?:no|number))?\s*[:#]?\s*(\d{10,14})", re.I)
_WELL_RE = re.compile(r"(?:Well\s*Name|Borehole)\s*[:=]?\s*([^\n]+)", re.I)
_OPER_RE = re.compile(r"(?:Operator|Operator Name)\s*[:=]?\s*([^\n]+)", re.I)
_GRID_CONV_RE = re.compile(r"Grid\s*Conv(?:ergence)?\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_MAG_DEC_RE = re.compile(r"(?:MagDec|Magnetic\s+Declination)\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_PLSS_RE = re.compile(
    r"((?:NWNW|NWNE|NENW|NENE|SWNW|SWNE|SENW|SENE|NWSW|NWSE|NESW|NESE|SWSW|SWSE|SESW|SESE)\s+(?:of\s+)?Sec(?:tion)?\.?\s*\d+[^\n]+)",
    re.I,
)


def _extract_lat(text: str) -> float | None:
    m = _LAT_DEC_RE.search(text)
    if m:
        try:
            v = float(m.group(1))
            if -90 <= v <= 90:
                return v
        except ValueError:
            pass
    m = _LAT_DMS_RE.search(text)
    if m:
        d, mm, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return d + mm / 60 + s / 3600
    return None


def _extract_lon(text: str) -> float | None:
    m = _LON_DEC_RE.search(text)
    if m:
        try:
            v = float(m.group(1))
            if -180 <= v <= 180:
                return v
        except ValueError:
            pass
    m = _LON_DMS_RE.search(text)
    if m:
        d, mm, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return -(d + mm / 60 + s / 3600)  # West → negative
    return None


def _extract_elevation(text: str) -> float | None:
    # Multiple matches; pick the first that's a plausible terrestrial elevation.
    for m in _ELEV_RE.finditer(text):
        try:
            v = float(m.group(1))
            if 0 < v < 20000:
                return v
        except ValueError:
            continue
    # Fallback: "(4944.3 ft above MSL)" style — common in directional plans.
    # Filter to plausible terrestrial elevations (Utah oilfield wells: 3500-9000 ft).
    for m in _ELEV_MSL_RE.finditer(text):
        try:
            v = float(m.group(1))
            if 1000 <= v <= 14000:
                return v
        except ValueError:
            continue
    return None


_NORTH_REF_LABELLED = re.compile(
    r"North\s*Reference\s*:?\s*[^A-Za-z]{0,40}?(True|Grid|Magnetic)\s+North",
    re.I | re.DOTALL,
)


def _extract_north_ref(text: str) -> str | None:
    """Return ``"true"``, ``"grid"``, or ``"magnetic"`` (or ``None``).

    Priority:
      1. An explicit ``North Reference: X North`` label — the authoritative
         declaration that operator software emits near the survey header.
      2. The survey-table column header (``Azim True (°)`` vs.
         ``Azim Grid (°)`` vs. ``Azim Mag``).
      3. Free-text ``"true north"`` / ``"grid north"`` / ``"magnetic north"``
         appearances anywhere in the doc.
    """
    # 1. Labelled declaration — most reliable.
    m = _NORTH_REF_LABELLED.search(text)
    if m:
        return m.group(1).lower()

    # 2. Column-header signature — survey table itself tells us.
    lower = text.lower()
    if "azim true" in lower:
        return "true"
    if "azim grid" in lower:
        return "grid"
    if "azim mag" in lower or "azim magnetic" in lower:
        return "magnetic"

    # 3. Free-text fallback.
    if "true north" in lower:
        return "true"
    if "grid north" in lower:
        return "grid"
    if "magnetic north" in lower:
        return "magnetic"
    return None


def _extract_well_name(text: str) -> str | None:
    """First Well Name match that isn't a header label like 'and Number' or empty."""
    for m in _WELL_RE.finditer(text):
        candidate = m.group(1).strip().splitlines()[0]
        # Skip header artifacts like "Well Name and Number"
        if not candidate or candidate.lower().startswith(("and ", "number", "no.")):
            continue
        if len(candidate) < 4:
            continue
        return candidate[:80]
    return None


def _extract_operator(text: str) -> str | None:
    m = _OPER_RE.search(text)
    if m:
        return m.group(1).strip().splitlines()[0][:120]
    return None


def _extract_api(text: str) -> str | None:
    m = _API_RE.search(text)
    return m.group(1)[:14] if m else None


def _extract_grid_convergence(text: str) -> float | None:
    m = _GRID_CONV_RE.search(text)
    return float(m.group(1)) if m else None


def _extract_mag_declination(text: str) -> float | None:
    m = _MAG_DEC_RE.search(text)
    return float(m.group(1)) if m else None


def _extract_plss(text: str) -> str | None:
    m = _PLSS_RE.search(text)
    return m.group(1).strip() if m else None


# Header indicates an MD/Inc/Azi survey block; the rows can either follow on
# new lines (well-formed Markdown table) or be smushed onto the same line by
# Docling when the source PDF rendered the table without explicit row breaks.
_SURVEY_HEADER_RE = re.compile(
    # Header columns: MD … Inc … Azim … plus the column-unit row that
    # follows. We greedily consume up to "Longitude" if present so the
    # parser doesn't tokenize "100" out of "(°/100ft)" as the first MD.
    r"\bMD\s*\(?ft\)?.{0,200}?Inc.{0,200}?Azim(?:.{0,500}?\bLongitude\b\s*\(?[^)\n]{0,20}\)?)?",
    re.I | re.DOTALL,
)


def _extract_survey_rows(markdown: str) -> pd.DataFrame:
    """Find every sequence of (MD, Inc, Azi) triples in the markdown.

    A single PDF can have the survey table broken across multiple pages
    (each with its own MD/Inc/Azim header), and Docling + PyMuPDF can
    each surface a different subset. We scan EVERY header occurrence,
    parse rows independently from each, and union the results.

    Tolerates two styles of output per block:
    * Header on its own line, rows on subsequent lines (typical PyMuPDF /
      Markdown table).
    * Header + all rows joined on a single line (typical Docling
      table-flattened output).
    """
    all_rows: list[tuple[float, float, float]] = []
    for m in _SURVEY_HEADER_RE.finditer(markdown):
        tail = markdown[m.end() :]
        # Stop at the next header (or EOF) so blocks don't bleed into each other.
        next_hdr = _SURVEY_HEADER_RE.search(tail)
        cutoff = next_hdr.start() if next_hdr else min(len(tail), 30_000)
        chunk = tail[:cutoff]

        rows = _parse_rows_linewise(chunk)
        if len(rows) < 3:
            rows = _parse_rows_token_stream(chunk)
        all_rows.extend(rows)

    if len(all_rows) < 3:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows, columns=["MeasuredDepth", "Inclination", "Azimuth"])
    df = df.sort_values("MeasuredDepth").reset_index(drop=True)
    # 1st pass — strip far-outside-the-bulk endpoint junk so it doesn't
    # poison the despike-by-median pass next.
    df = _trim_outlier_endpoints(df)
    # 2nd pass — despike interior spikes (mis-aligned MD/INC/AZI triples)
    # using a robust local-median comparison.
    df = _despike_inclination(df)
    df = df.drop_duplicates("MeasuredDepth").reset_index(drop=True)
    # 3rd pass — final endpoint clean now that interior despike may have
    # exposed a new boundary that needs trimming.
    return _trim_outlier_endpoints(df)


def _despike_inclination(df: pd.DataFrame, *, window: int = 5, threshold: float = 30.0) -> pd.DataFrame:
    """Drop interior rows whose inclination spikes away from local neighbors.

    Token-stream parsing of a 12-column table occasionally locks onto the
    wrong triple (e.g. an azimuth value gets read as MD with an unrelated
    column as INC). The signature is always the same: one row whose INC
    differs by 30°+ from BOTH the rows immediately before and after.
    """
    if len(df) < 2 * window:
        return df

    inc = df["Inclination"].to_numpy()
    keep = [True] * len(df)
    half = window // 2
    for i in range(len(df)):
        lo = max(0, i - half - 1)
        hi = min(len(df), i + half + 2)
        # Median of neighbors excluding self
        neighbors = list(inc[lo:i]) + list(inc[i + 1 : hi])
        if not neighbors:
            continue
        local_median = float(pd.Series(neighbors).median())
        if abs(inc[i] - local_median) > threshold:
            keep[i] = False
    return df.loc[keep].reset_index(drop=True)


def _trim_outlier_endpoints(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows at the head/tail that don't fit the surrounding pattern.

    Operator PDFs sandwich the real survey table between unrelated tables
    (target/KOP markers above, offset-well anti-collision listings below).
    The token-stream parser occasionally swallows a few of those rows.
    A boundary row is treated as bleed-through if it's far from the bulk
    INC behavior of the neighboring "good" rows or sits on an MD gap
    larger than the typical step.
    """
    if len(df) < 8:
        return df

    md = df["MeasuredDepth"].to_numpy()
    inc = df["Inclination"].to_numpy()

    # Trailing pass: trim while the last row is an outlier relative to
    # the median INC of the 5 rows preceding it, OR has a large MD gap.
    end = len(df)
    while end >= 6:
        recent_inc_median = float(pd.Series(inc[end - 6 : end - 1]).median())
        md_gap = md[end - 1] - md[end - 2]
        if abs(inc[end - 1] - recent_inc_median) > 30 or md_gap > 1500:
            end -= 1
            continue
        break

    # Leading pass: same idea from the start.
    start = 0
    while start < end - 6:
        recent_inc_median = float(pd.Series(inc[start + 1 : start + 6]).median())
        md_gap = md[start + 1] - md[start]
        if abs(inc[start] - recent_inc_median) > 30 or md_gap > 1500:
            start += 1
            continue
        break

    return df.iloc[start:end].reset_index(drop=True)


_NUM_RE = re.compile(r"-?\d+\.\d+|-?\d+")


def _parse_rows_linewise(text: str) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        nums = _NUM_RE.findall(line)
        if len(nums) >= 3:
            triple = _try_row(nums[0], nums[1], nums[2])
            if triple:
                rows.append(triple)
                continue
        if rows:
            break  # row block ended
    return rows


def _parse_rows_token_stream(text: str) -> list[tuple[float, float, float]]:
    """Scan numeric tokens greedily: every (md, inc, azi) triple that's valid
    AND whose MD strictly exceeds the previously accepted MD is taken as a row.

    This handles real-world Docling output where comments like "KOP" or
    "Garden Gulch (TGR3)" interleave stray numeric tokens between rows —
    fixed-width scanning fails on those, but the monotonic-MD invariant
    naturally skips over them.
    """
    nums = _NUM_RE.findall(text)
    if len(nums) < 9:
        return []

    rows: list[tuple[float, float, float]] = []
    last_md = -1.0
    i = 0
    while i + 2 < len(nums):
        triple = _try_row(nums[i], nums[i + 1], nums[i + 2])
        if triple and triple[0] > last_md:
            rows.append(triple)
            last_md = triple[0]
            # Move past at least the MD/INC/AZI we just consumed; the
            # remaining row columns will be naturally skipped by the
            # invalid-Inc/Azi constraint until the next row's MD appears.
            i += 3
        else:
            i += 1

    # Real surveys have at least a handful of rows spanning hundreds of feet.
    if len(rows) < 5 or rows[-1][0] - rows[0][0] < 100:
        return []

    # Trailing-row sanity check: anti-collision / target / TD-spec tables on
    # later pages can leak through and stack onto the real survey. Trim
    # while the last row makes EITHER an unphysical inclination jump
    # (>30°) OR a large measured-depth jump (>1500 ft) vs. its predecessor.
    while len(rows) >= 2:
        prev_md, prev_inc, _ = rows[-2]
        last_md, last_inc, _ = rows[-1]
        if abs(last_inc - prev_inc) > 30 or (last_md - prev_md) > 1500:
            rows.pop()
            continue
        break
    return rows


def _try_row(md_s: str, inc_s: str, azi_s: str) -> tuple[float, float, float] | None:
    try:
        md_, inc, azi = float(md_s), float(inc_s), float(azi_s)
    except (TypeError, ValueError):
        return None
    if not (0 <= md_ <= 60_000):
        return None
    if not (0 <= inc <= 180):
        return None
    if not (0 <= azi <= 360):
        return None
    return md_, inc, azi


# ---------------------------------------------------------------------------
# Layer 3 / 4 — LLM extraction (text + vision)
# ---------------------------------------------------------------------------


def llm_text_extract(markdown: str) -> ParsedSurvey:
    """Run the text LLM on Docling markdown. Raises ``OllamaUnavailableError``
    when Ollama isn't reachable; the caller decides whether to swallow it."""
    from etools.core.llm import OllamaClient
    from etools.core.pdf.llm_extractor import llm_extract

    client = OllamaClient()
    if not client.health():
        raise RuntimeError("Ollama is not reachable")
    if not client.has_model():
        raise RuntimeError(f"Ollama model not pulled — run `ollama pull {client.model}`")
    return _from_llm(llm_extract(markdown, client=client))


def llm_vision_extract(path: str | Path, max_pages: int = 8) -> ParsedSurvey:
    """Render PDF pages as PNG and ask the vision LLM to extract."""
    from etools.core.llm import OllamaClient
    from etools.core.pdf.llm_extractor import llm_extract_from_image

    client = OllamaClient()
    if not client.health():
        raise RuntimeError("Ollama is not reachable")
    if not client.has_model(client.vision_model):
        raise RuntimeError(
            f"Vision model '{client.vision_model}' is not pulled — "
            f"run `ollama pull {client.vision_model}` or unset the vision layer."
        )
    # Hard guard: if the configured vision_model is actually a text-only
    # model (qwen3.5, llama3.x, etc.), the API will silently hallucinate.
    # Refuse rather than poison the result.
    if not _looks_like_vision_model(client.vision_model):
        raise RuntimeError(
            f"Configured vision model '{client.vision_model}' is text-only; "
            "set ETOOLS_LLM__VISION_MODEL to a real VL model "
            "(qwen2.5vl, llava, llama3.2-vision, bakllava, moondream)."
        )
    images = _render_pages_to_png(Path(path), max_pages=max_pages)
    if not images:
        raise RuntimeError("Could not render PDF pages for vision LLM (PyMuPDF missing?)")
    return _from_llm(llm_extract_from_image(images, client=client))


_VL_MODEL_HINTS = ("vl", "vision", "llava", "bakllava", "moondream")


def _looks_like_vision_model(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _VL_MODEL_HINTS)


def merge_into(into: ParsedSurvey, more: ParsedSurvey, *, source: str = "unknown") -> None:
    """Public alias — fills in missing fields on ``into`` from ``more``.

    ``source`` records the layer that contributed the new values, for UI
    provenance display.
    """
    _merge(into, more, source=source)


def is_incomplete(parsed: ParsedSurvey) -> bool:
    """Public alias — returns True if SHL/elevation/surveys are missing."""
    return _is_incomplete(parsed)


def _from_llm(llm) -> ParsedSurvey:
    surveys = pd.DataFrame(
        [
            {
                "MeasuredDepth": row.measured_depth_ft,
                "Inclination": row.inclination_deg,
                "Azimuth": row.azimuth_deg,
            }
            for row in llm.surveys
        ]
    )
    if not surveys.empty:
        surveys = surveys.drop_duplicates("MeasuredDepth").sort_values("MeasuredDepth").reset_index(drop=True)
    return ParsedSurvey(
        surveys=surveys,
        surface_lat=llm.surface_latitude_deg,
        surface_lon=llm.surface_longitude_deg,
        surface_elevation_ft=llm.surface_elevation_ft,
        north_reference=llm.north_reference,
        well_name=llm.well_name,
        api=llm.api_number,
        operator=llm.operator,
        grid_convergence_deg=llm.grid_convergence_deg,
        magnetic_declination_deg=llm.magnetic_declination_deg,
        plss_legal=llm.plss_legal,
    )


# ---------------------------------------------------------------------------
# Result merging — fill in only the missing fields.
# ---------------------------------------------------------------------------


def _merge(into: ParsedSurvey, more: ParsedSurvey, *, source: str = "unknown") -> None:
    """Update ``into`` with values from ``more`` only where ``into`` is empty.

    Records ``source`` against each field newly populated for UI provenance.
    """
    fields = (
        "surface_lat",
        "surface_lon",
        "surface_elevation_ft",
        "north_reference",
        "well_name",
        "api",
        "operator",
        "grid_convergence_deg",
        "magnetic_declination_deg",
        "plss_legal",
    )
    for f in fields:
        if getattr(into, f) is None:
            v = getattr(more, f, None)
            if v is not None:
                setattr(into, f, v)
                into.field_sources[f] = source
    if into.surveys.empty and not more.surveys.empty:
        into.surveys = more.surveys
        into.field_sources["surveys"] = source


def _is_incomplete(parsed: ParsedSurvey) -> bool:
    return (
        parsed.surveys.empty
        or parsed.surface_lat is None
        or parsed.surface_lon is None
        or parsed.surface_elevation_ft is None
    )


# ---------------------------------------------------------------------------
# Vision-fallback page rendering (PyMuPDF)
# ---------------------------------------------------------------------------


def vision_transcribe_page(
    path: str | Path, page: int, dpi: int = 300
) -> tuple[str, dict]:
    """Single-page vision diagnostic.

    Renders one page at the requested DPI and asks the vision LLM to do
    only one thing — transcribe MD/INC/AZI rows as JSON — with no other
    fields competing for attention.

    Returns (raw_response_string, meta) where meta has timing and
    image-size info.
    """
    from etools.core.llm import OllamaClient

    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF not installed") from e

    started = time.time()
    doc = fitz.open(str(path))
    if page < 1 or page > len(doc):
        raise ValueError(f"Page {page} out of range (PDF has {len(doc)} pages)")
    pix = doc.load_page(page - 1).get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")

    client = OllamaClient()
    if not client.health():
        raise RuntimeError("Ollama is not reachable")

    prompt = (
        "This is a single page from a directional-survey document. "
        "Look for a table with columns Measured Depth (MD, ft), "
        "Inclination (INC, degrees), Azimuth (AZI, degrees). "
        "Transcribe every visible row into a JSON array. "
        "Return ONLY this JSON shape, nothing else:\n"
        '{"surveys": [{"md": <number>, "inc": <number>, "azi": <number>}, ...]}\n'
        "If there is no such table on this page, return "
        '{"surveys": []}.'
    )
    raw = client.chat_json(
        prompt,
        schema=None,  # plain JSON mode, no fancy schema
        system=(
            "You transcribe numeric tables from images. Copy every row exactly "
            "as printed. Do not summarise, skip, or invent rows."
        ),
        images=[img_bytes],
    )
    elapsed = time.time() - started
    meta = {
        "page": page,
        "dpi": dpi,
        "image_bytes": len(img_bytes),
        "elapsed_s": round(elapsed, 1),
        "total_pages": len(doc),
    }
    log.info("pdf.vision_transcribe", **meta, response_chars=len(raw))
    return raw, meta


def classify_survey_kind(surveys: pd.DataFrame) -> str:
    """Return ``"Planned"`` or ``"AsDrilled"`` based on MD-step regularity.

    Planned trajectories are emitted on a fixed grid (almost always 100 ft,
    sometimes 50 ft) with a small number of "off-grid" markers — KOP,
    Landing Point, casing point, formation tops — that fall between the
    regular stations. As-drilled surveys come straight off the MWD tool
    and have irregular spacing reflecting actual sampling intervals.

    Heuristic: take the consecutive MD differences, round them to the
    nearest foot, and ask what fraction of the differences equal the mode.
    If the mode is the dominant interval (≥75 % of all gaps) and the mode
    itself is a plausible planned-survey step (between 25 ft and 200 ft),
    the survey is Planned. Otherwise it's AsDrilled.
    """
    if surveys is None or len(surveys) < 5:
        return "AsDrilled"
    md = surveys["MeasuredDepth"].to_numpy()
    diffs = pd.Series(md[1:] - md[:-1])
    diffs = diffs[diffs > 0]  # drop zero/negative gaps just in case
    if len(diffs) < 4:
        return "AsDrilled"

    rounded = diffs.round().astype(int)
    mode = rounded.mode().iat[0]
    dominance = (rounded == mode).mean()

    log.info(
        "pdf.classify_survey_kind",
        rows=len(surveys),
        mode_step=int(mode),
        dominance=round(float(dominance), 3),
    )

    if 25 <= mode <= 200 and dominance >= 0.75:
        return "Planned"
    return "AsDrilled"


def _pymupdf_extract_text(path: Path) -> str:
    """Return concatenated plain text from every page via PyMuPDF.

    Used as a supplement to Docling — text-based PDFs where Docling's
    table model dropped a page still yield rows via fitz's column-wise
    text extractor.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("pdf.pymupdf.missing")
        return ""
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # pragma: no cover
        log.warning("pdf.pymupdf.open_failed", error=str(exc))
        return ""
    parts: list[str] = []
    for i in range(len(doc)):
        try:
            parts.append(doc.load_page(i).get_text())
        except Exception as exc:
            log.warning("pdf.pymupdf.page_failed", page=i + 1, error=str(exc))
    return "\n".join(parts)


def _render_pages_to_png(path: Path, max_pages: int = 8) -> list[bytes]:
    """Render the first N pages of a PDF as PNG bytes (for vision LLM)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("pdf.render.no_fitz")
        return []
    out: list[bytes] = []
    doc = fitz.open(str(path))
    for i in range(min(len(doc), max_pages)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=150)
        out.append(pix.tobytes("png"))
    return out
