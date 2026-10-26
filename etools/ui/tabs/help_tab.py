"""Help tab — renders the user guide (``etools/docs/app_guide.md``).

The guide is plain Markdown with Mermaid flow charts, kept outside the code
so it can be edited without touching Python. Mermaid ships with NiceGUI, so
the charts render offline (portable bundle included).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from nicegui import ui

GUIDE_PATH = Path(__file__).resolve().parents[2] / "docs" / "app_guide.md"

# ui.html/markdown strip <style>; page CSS belongs in the head.
_HELP_CSS = """
<style>
.help-doc { max-width: 1100px; line-height: 1.55; }
.help-doc h1 { font-size: 1.75rem; font-weight: 700; margin: .25rem 0 .75rem; }
.help-doc h2 { font-size: 1.3rem; font-weight: 650; margin: 1.75rem 0 .5rem;
               padding-bottom: .25rem; border-bottom: 1px solid #e2e8f0; }
.help-doc p, .help-doc li { font-size: .95rem; color: #1e293b; }
.help-doc ul { list-style: disc; padding-left: 1.5rem; }
.help-doc table { border-collapse: collapse; width: auto; margin: .5rem 0 1rem;
                  font-size: .88rem; }
.help-doc th, .help-doc td { border: 1px solid #cbd5e1; padding: .35rem .6rem;
                             vertical-align: top; text-align: left; }
.help-doc th { background: #f1f5f9; font-weight: 600; }
.help-doc code { background: #f1f5f9; padding: 0 .25rem; border-radius: 3px;
                 font-size: .85em; }
.help-doc hr { margin: 1.5rem 0; border-color: #e2e8f0; }
.help-doc .mermaid, .help-doc svg { max-width: 100%; }
.help-doc .mermaid { overflow-x: auto; margin: .75rem 0 1.25rem; }
</style>
"""


def load_guide() -> str:
    """The guide's Markdown, or a short notice if the file is missing."""
    try:
        return GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "# Help\n\nThe user guide file is missing: "
            f"`{GUIDE_PATH}`. Reinstall or copy it back into `etools/docs/`."
        )


def render_help_tab() -> Callable[[], None]:
    ui.add_head_html(_HELP_CSS)
    with ui.column().classes("p-6 w-full"):
        ui.markdown(
            load_guide(), extras=["fenced-code-blocks", "tables", "mermaid"]
        ).classes("help-doc")
    return lambda: None  # static page: nothing to refresh per well
