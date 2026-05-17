"""Docling-based PDF → markdown extraction.

We disable OCR by default — most operator PDFs are text-based and OCR
adds 8–30 seconds per page on CPU. The extractor exposes a
``with_ocr`` toggle for the few scanned PDFs where it's needed.
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

from etools.logging_setup import get_logger

log = get_logger(__name__)


_DEBUG_DIR = Path("output") / "llm_debug"


def _dump_markdown(md: str, *, source: Path, with_ocr: bool) -> Path | None:
    """Write the full Docling markdown to disk for inspection."""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        tag = "ocr" if with_ocr else "no-ocr"
        path = _DEBUG_DIR / f"{ts}_docling_{tag}_{source.stem}.md"
        path.write_text(md, encoding="utf-8")
        return path
    except Exception as exc:  # pragma: no cover
        log.warning("docling.debug_dump.failed", error=str(exc))
        return None


@lru_cache(maxsize=2)
def _converter(with_ocr: bool):
    """Build (and cache) a DocumentConverter with the requested OCR setting.

    Importing docling and constructing a converter is expensive — keep both
    instances cached for the lifetime of the process.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = with_ocr
    opts.do_table_structure = True

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def pdf_to_markdown(path: str | Path, *, with_ocr: bool = False) -> tuple[str, dict]:
    """Run Docling and return ``(markdown, meta)``.

    ``meta`` carries timing + page count + (heuristic) "looks_scanned" so
    the caller can decide whether to retry with OCR enabled.
    """
    path = Path(path)
    started = time.time()
    converter = _converter(with_ocr)
    result = converter.convert(str(path))
    md = result.document.export_to_markdown()
    elapsed = time.time() - started

    page_count = len(result.document.pages or {})
    looks_scanned = (
        page_count > 0 and len(md.strip()) < page_count * 200  # < ~200 chars per page → likely image
    )

    dump_path = _dump_markdown(md, source=path, with_ocr=with_ocr)
    log.info(
        "pdf.docling",
        path=str(path),
        with_ocr=with_ocr,
        pages=page_count,
        markdown_chars=len(md),
        elapsed_s=round(elapsed, 1),
        looks_scanned=looks_scanned,
        debug_dump=str(dump_path) if dump_path else None,
    )
    return md, {
        "page_count": page_count,
        "elapsed_s": elapsed,
        "looks_scanned": looks_scanned,
        "with_ocr": with_ocr,
    }
