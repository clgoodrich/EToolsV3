"""Operations viewer: the WCR's operations log, cleanly laid out, beside the PDF.

Left: every Operation Summary Report entry grouped by day, reformatted for
reading. Nothing is reworded: the operator's comment is shown verbatim, only
whitespace (PDF line wraps) is tidied. Right: the PDF itself, page by page.
Clicking a day or an entry scrolls the PDF to that row and highlights it.

Pages are rendered to PNG on demand by PyMuPDF through a small local route
(``/etools-pdf/<token>/<page>.png``), so this works offline and doesn't
depend on the browser's PDF plug-in. Tokens are random and map to the one
file registered for them, so the route can't be used to read other files.
"""

from __future__ import annotations

import asyncio
import html
import re
import secrets
from collections import OrderedDict
from pathlib import Path

from fastapi import Response
from nicegui import app, ui

from etools.core.pdf.ddr_locate import PageSpot, locate_entries, page_sizes
from etools.logging_setup import get_logger

log = get_logger(__name__)

_RENDER_SCALE = 1.75  # ~126 dpi: crisp table text without huge images
_TOKENS: dict[str, Path] = {}
_PNG_CACHE: "OrderedDict[tuple[str, int], bytes]" = OrderedDict()
_PNG_CACHE_MAX = 80


def register_pdf(path: str | Path) -> str:
    """Return a token the page route will serve ``path`` under."""
    p = Path(path).resolve()
    for tok, known in _TOKENS.items():
        if known == p:
            return tok
    tok = secrets.token_urlsafe(12)
    _TOKENS[tok] = p
    return tok


def _render_page_png(path: Path, page: int) -> bytes:
    import fitz  # PyMuPDF

    with fitz.open(str(path)) as doc:
        pix = doc.load_page(page).get_pixmap(matrix=fitz.Matrix(_RENDER_SCALE, _RENDER_SCALE))
        return pix.tobytes("png")


@app.get("/etools-pdf/{token}/{page}.png")
def _pdf_page(token: str, page: int) -> Response:
    # Plain ``def``: FastAPI runs it in a worker thread, off the event loop.
    path = _TOKENS.get(token)
    if path is None or not path.exists() or page < 0:
        return Response(status_code=404)
    key = (token, page)
    png = _PNG_CACHE.get(key)
    if png is None:
        try:
            png = _render_page_png(path, page)
        except Exception as exc:
            log.warning("ops_viewer.page_render_failed", page=page, error=str(exc))
            return Response(status_code=404)
        _PNG_CACHE[key] = png
        while len(_PNG_CACHE) > _PNG_CACHE_MAX:
            _PNG_CACHE.popitem(last=False)
    else:
        _PNG_CACHE.move_to_end(key)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------------
# Formatting (layout only: values and wording are never changed)
# ---------------------------------------------------------------------------
def _tidy(s: str | None) -> str:
    """Collapse PDF line-wrap whitespace and drop the parser's own page-break
    marker (``<<<PAGE>>>``, not report text); nothing else is altered."""
    return re.sub(r"\s+", " ", (s or "").replace("<<<PAGE>>>", " ")).strip()


def _num(v: float | None) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def _hours(v: float | None) -> str:
    return "" if v is None else f"{v:g} h"


def _time_range(e) -> str:
    st, en = e.start_time, e.end_time
    if st is None:
        return ""
    s = st.strftime("%H:%M")
    if en is None:
        return s
    if en.date() != st.date():
        return f"{s} – {en.month}/{en.day} {en.strftime('%H:%M')}"
    return f"{s} – {en.strftime('%H:%M')}"


def _depths(e) -> str:
    a, b = e.start_depth_ftkb, e.end_depth_ftkb
    if a is None and b is None:
        return ""
    if a is None or b is None or a == b:
        return f"at {_num(a if a is not None else b)} ftKB"
    return f"{_num(a)} → {_num(b)} ftKB"


def _operation(e) -> str:
    parts: list[str] = []
    for p in (e.phase, e.code1, e.code2):
        t = _tidy(p)
        if t and t not in parts:
            parts.append(t)
    return " · ".join(parts)


def _attrs(spot: PageSpot | None) -> str:
    if spot is None:
        return ""
    return (
        f' data-page="{spot.page}" data-top="{spot.top:.4f}"'
        f' data-bottom="{spot.bottom:.4f}"'
    )


def _day_label(d) -> str:
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


def build_log_html(ddrs, spots: dict[tuple[int, int], PageSpot]) -> str:
    """The left pane: jobs → days → entries, every value escaped."""
    esc = html.escape
    out: list[str] = [
        '<input id="ops-filter" class="ops-filter" type="search" '
        'placeholder="Filter entries (e.g. cement, NPT, stage 12)…">'
    ]
    if len(ddrs) > 1:
        out.append('<div class="ops-jobs">Jump to: ' + " ".join(
            f'<a class="ops-joblink" href="#ops-job-{i}">{esc(d.job_category or "Report")}</a>'
            for i, d in enumerate(ddrs)
        ) + "</div>")
    for di, ddr in enumerate(ddrs):
        span = " → ".join(
            f"{x.month}/{x.day}/{x.year}" for x in (ddr.start_date, ddr.end_date) if x
        )
        out.append(
            f'<div class="ops-job" id="ops-job-{di}">{esc(ddr.job_category or "Operations")}'
            f'<span class="ops-job-meta">{esc(span)} · {len(ddr.entries)} entries</span></div>'
        )
        days: "OrderedDict[object, list[int]]" = OrderedDict()
        for ei, e in enumerate(ddr.entries):
            days.setdefault(e.start_time.date() if e.start_time else None, []).append(ei)
        for day, idxs in days.items():
            first = next((spots[(di, i)] for i in idxs if (di, i) in spots), None)
            hrs = sum(ddr.entries[i].duration_hr or 0.0 for i in idxs)
            title = _day_label(day) if day else "No date"
            out.append('<div class="ops-day-block">')
            out.append(
                f'<div class="ops-day{" ops-jump" if first else ""}"{_attrs(first)}>'
                f'{esc(title)}<span class="ops-day-meta">{len(idxs)} entries'
                f'{" · " + _hours(hrs) if hrs else ""}</span></div>'
            )
            for ei in idxs:
                e = ddr.entries[ei]
                spot = spots.get((di, ei))
                comment = _tidy(e.comment)
                op = _operation(e)
                badges = ""
                cat = _tidy(e.ops_category).upper()
                if cat:
                    badges += f'<span class="ops-badge ops-{esc(cat.lower())}">{esc(cat)}</span>'
                for t in e.trouble or []:
                    badges += f'<span class="ops-badge ops-trouble">{esc(t)}</span>'
                search = " ".join(
                    x for x in (comment, op, cat, " ".join(e.trouble or []), _depths(e)) if x
                ).lower()
                out.append(
                    f'<div class="ops-entry{" ops-jump" if spot else ""}"{_attrs(spot)}'
                    f' data-text="{esc(search, quote=True)}">'
                    f'<div class="ops-line"><span class="ops-time">{esc(_time_range(e))}</span>'
                    f'<span class="ops-dur">{esc(_hours(e.duration_hr))}</span>'
                    f'<span class="ops-depth">{esc(_depths(e))}</span>{badges}</div>'
                    + (f'<div class="ops-op">{esc(op)}</div>' if op else "")
                    + (f'<div class="ops-comment">{esc(comment)}</div>' if comment else "")
                    + "</div>"
                )
            out.append("</div>")
    return "".join(out)


def build_pdf_html(token: str, sizes: list[tuple[float, float]]) -> str:
    """The right pane: every page as a lazily loaded image."""
    pages = "".join(
        f'<div class="ops-pg" id="ops-pg-{i}" style="aspect-ratio:{w:.1f}/{h:.1f}">'
        f'<img loading="lazy" src="/etools-pdf/{token}/{i}.png" alt="Page {i + 1}">'
        f'<div class="ops-pgno">Page {i + 1}</div></div>'
        for i, (w, h) in enumerate(sizes)
    )
    return pages + '<div id="ops-hl" class="ops-hl"></div>'


# ---------------------------------------------------------------------------
# Page assets (head: ui.html strips <style>/<script>)
# ---------------------------------------------------------------------------
HEAD_ASSETS = """
<style>
.ops-wrap { display:flex; gap:12px; height: calc(100vh - 92px); }
#ops-log-pane { flex: 0 0 42%; overflow-y:auto; padding-right:6px; }
#ops-pdf-pane { flex: 1 1 auto; overflow-y:auto; position:relative; background:#94a3b8;
                padding:10px; border-radius:6px; }
.ops-filter { width:100%; padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px;
              margin-bottom:8px; font-size:.9rem; position:sticky; top:0; z-index:2;
              background:#fff; box-shadow:0 2px 4px rgba(255,255,255,.9); }
.ops-jobs { font-size:.8rem; color:#475569; margin-bottom:6px; }
.ops-joblink { color:#1d4ed8; margin-right:8px; text-decoration:underline; }
.ops-job { font-weight:700; font-size:1rem; margin:14px 0 4px; color:#0f172a; }
.ops-job-meta, .ops-day-meta { font-weight:400; font-size:.78rem; color:#64748b; margin-left:8px; }
.ops-day { font-weight:600; font-size:.88rem; background:#e2e8f0; padding:4px 8px;
           border-radius:4px; margin:8px 0 2px; position:sticky; top:38px; z-index:1; }
.ops-entry { border-left:3px solid #cbd5e1; padding:4px 8px; margin:2px 0; border-radius:3px; }
.ops-jump { cursor:pointer; }
.ops-entry.ops-jump:hover, .ops-day.ops-jump:hover { background:#eff6ff; }
.ops-entry.active { background:#dbeafe; border-left-color:#1d4ed8; }
.ops-day.active { background:#bfdbfe; }
.ops-line { display:flex; flex-wrap:wrap; gap:8px; align-items:baseline; font-size:.8rem; }
.ops-time { font-family:ui-monospace,monospace; font-weight:600; color:#0f172a; }
.ops-dur, .ops-depth { color:#475569; }
.ops-op { font-size:.78rem; color:#334155; font-style:italic; }
.ops-comment { font-size:.85rem; color:#0f172a; white-space:normal; }
.ops-badge { font-size:.68rem; padding:0 5px; border-radius:3px; background:#e2e8f0; color:#334155; }
.ops-badge.ops-npt { background:#fee2e2; color:#991b1b; }
.ops-badge.ops-pt { background:#dcfce7; color:#166534; }
.ops-badge.ops-trouble { background:#fef3c7; color:#92400e; }
.ops-pg { position:relative; width:100%; background:#fff; margin:0 auto 10px;
          box-shadow:0 1px 3px rgba(0,0,0,.3); }
.ops-pg img { width:100%; height:100%; display:block; }
.ops-pgno { position:absolute; right:6px; bottom:4px; font-size:.7rem; color:#64748b; }
.ops-hl { position:absolute; left:0; right:0; display:none; pointer-events:none;
          background:rgba(250,204,21,.28); outline:2px solid rgba(202,138,4,.9); }
</style>
<script>
window.etoolsOps = {
  jump(el) {
    const pane = document.getElementById('ops-pdf-pane');
    const pg = document.getElementById('ops-pg-' + el.dataset.page);
    if (!pane || !pg) return;
    const top = +el.dataset.top, bot = +el.dataset.bottom;
    const hl = document.getElementById('ops-hl');
    pg.appendChild(hl);
    hl.style.top = (top * 100) + '%';
    hl.style.height = Math.max((bot - top) * 100, 0.8) + '%';
    hl.style.display = 'block';
    pane.scrollTo({top: pg.offsetTop + top * pg.offsetHeight - 70, behavior: 'smooth'});
    document.querySelectorAll('#ops-log-pane .active').forEach(x => x.classList.remove('active'));
    el.classList.add('active');
  },
  filter(q) {
    q = (q || '').toLowerCase().trim();
    document.querySelectorAll('#ops-log-pane .ops-day-block').forEach(b => {
      let any = false;
      b.querySelectorAll('.ops-entry').forEach(e => {
        const m = !q || (e.dataset.text || '').includes(q);
        e.style.display = m ? '' : 'none';
        any = any || m;
      });
      b.style.display = any ? '' : 'none';
    });
  },
};
document.addEventListener('click', ev => {
  const t = ev.target.closest('#ops-log-pane .ops-jump');
  if (t) window.etoolsOps.jump(t);
});
document.addEventListener('input', ev => {
  if (ev.target && ev.target.id === 'ops-filter') window.etoolsOps.filter(ev.target.value);
});
</script>
"""


def add_ops_viewer_button(pdf_path: str | None, ddrs) -> None:
    """A button that opens the viewer in a full-screen dialog.

    Built inside the caller's card, so it is cleared with the card on the
    next render (no dialog accumulates). The log is located and built only
    when the button is clicked.
    """
    has_entries = any(d.entries for d in ddrs or [])
    available = bool(pdf_path) and Path(pdf_path).exists()

    with ui.dialog().props("maximized") as dlg, ui.card().classes("w-full h-full p-3"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Operations log beside the report").classes("text-lg font-semibold")
            ui.label(
                "Click a day or an entry to jump to it in the PDF. Wording and values "
                "are exactly as in the report — only the layout is cleaned up."
            ).classes("text-xs text-gray-500")
            ui.button(icon="close", on_click=dlg.close).props("flat round dense")
        body = ui.column().classes("w-full")

    async def _open() -> None:
        btn.props("loading")
        try:
            spots, sizes = await asyncio.gather(
                asyncio.to_thread(locate_entries, pdf_path, ddrs),
                asyncio.to_thread(page_sizes, pdf_path),
            )
            token = register_pdf(pdf_path)
            left = build_log_html(ddrs, spots)
            right = build_pdf_html(token, sizes)
        except Exception as exc:
            log.exception("ops_viewer.open_failed")
            ui.notify(f"Couldn't open the operations viewer: {exc}", type="negative")
            return
        finally:
            btn.props(remove="loading")
        body.clear()
        with body:
            ui.html(
                f'<div class="ops-wrap"><div id="ops-log-pane">{left}</div>'
                f'<div id="ops-pdf-pane">{right}</div></div>',
                sanitize=False,
            ).classes("w-full")
        dlg.open()

    btn = ui.button(
        "Open operations log beside the PDF", icon="vertical_split", on_click=_open
    ).props("outline dense")
    if not has_entries:
        btn.disable()
        btn.tooltip("No operations-log entries were parsed from this PDF.")
    elif not available:
        btn.disable()
        btn.tooltip("The uploaded PDF is no longer available — upload it again.")
