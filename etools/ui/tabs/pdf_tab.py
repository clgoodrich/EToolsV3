"""PDF Import tab — upload a survey PDF, parse, preview, inject into the pipeline.

The UI orchestrates each parser layer (Docling → rules → LLM) so we can show
per-stage progress and keep the user oriented during the ~50-90 s run.
"""

from __future__ import annotations

import asyncio
import tempfile
import traceback
from functools import partial
from pathlib import Path
from typing import Callable

import pandas as pd
from nicegui import events, ui

from etools.config import settings
from etools.core.pdf import (
    ParsedSurvey,
    classify_survey_kind,
    is_incomplete,
    llm_text_extract,
    llm_vision_extract,
    merge_into,
    pdf_to_markdown,
    rules_extract,
    vision_transcribe_page,
)
from etools.logging_setup import get_logger
from etools.models import WellHeader
from etools.ui.state import AppState, reset_survey_edits

log = get_logger(__name__)


async def _io(func, *args, **kwargs):
    """Run a blocking function on the default thread pool.

    We bypass ``nicegui.run.io_bound`` because NiceGUI's wrapper swallows
    ``CancelledError`` and returns ``None`` instead of letting it propagate,
    which breaks our ``except CancelledError`` handler.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def render_pdf_tab(
    state: AppState,
    *,
    on_inject: Callable[[], object] | None = None,
) -> Callable[[], None]:
    parsed_state: dict = {
        "result": None,
        "tmp_path": None,
        "markdown": None,
        "task": None,  # in-flight asyncio.Task — populated only during parse
    }

    with ui.column().classes("p-4 gap-3 w-full"):
        ui.label("PDF Survey Import").classes("text-2xl font-semibold")
        ui.label(
            "Upload an operator-submitted directional survey PDF. "
            "The parser will extract MD/INC/AZI plus surface coordinates, elevation, "
            "and the north reference where present."
        ).classes("text-sm text-gray-600")

        # Upload widget alongside the run buttons.
        with ui.row().classes("gap-3 items-center w-full"):
            upload_widget = ui.upload(
                label="Drop a PDF here or click to browse",
                auto_upload=True,
                multiple=False,
                on_upload=lambda e: handle_upload(e),
                on_rejected=lambda e: ui.notify(f"Upload rejected: {e}", type="negative"),
            ).classes("max-w-md").props("accept=.pdf")

            with ui.row().classes("gap-2 items-center"):
                run_rules_btn = ui.button(
                    "Run rules",
                    icon="rule",
                    on_click=lambda: start_parse(mode="rules"),
                ).props("color=primary")
                run_rules_btn.tooltip(
                    "Docling + PyMuPDF + regex extraction only. Fast (~50 s) and "
                    "handles most operator PDFs without touching the LLM."
                )
                run_rules_btn.disable()

                run_llm_btn = ui.button(
                    "Run LLM",
                    icon="psychology",
                    on_click=lambda: start_parse(mode="llm"),
                ).props("color=primary")
                run_llm_btn.tooltip(
                    "Skip the rules layer; hand the Docling/PyMuPDF markdown straight "
                    "to the local LLM for metadata extraction."
                )
                run_llm_btn.disable()

                run_both_btn = ui.button(
                    "Run both",
                    icon="merge",
                    on_click=lambda: start_parse(mode="both"),
                ).props("color=primary")
                run_both_btn.tooltip(
                    "Rules first, then LLM — LLM fills in anything rules missed."
                )
                run_both_btn.disable()

                # Visual separator between the run group and the use-this-survey action.
                ui.separator().props("vertical").classes("mx-2 h-10")

                inject_btn = ui.button(
                    "Use this survey",
                    icon="check_circle",
                    on_click=lambda: inject_into_pipeline(),
                ).props("color=positive")
                inject_btn.disable()
                # NOTE: `inject_into_pipeline` is async — NiceGUI's on_click
                # awaits coroutines returned from the handler automatically.

        # Status banner + linear progress
        status_banner = ui.label("Awaiting upload…").classes(
            "text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
        )
        progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
        progress.visible = False

        # LLM availability indicator
        llm_label = ui.label("").classes("text-xs text-gray-500")
        _refresh_llm_status(llm_label)

        ui.separator()

        # Metadata card
        meta_card = ui.card().classes("w-full")
        with meta_card:
            ui.label("Extracted metadata").classes("text-sm font-semibold")
            meta_grid = ui.grid(columns=4).classes("gap-x-6 gap-y-1 text-sm w-full")
            with meta_grid:
                ui.label("(no PDF loaded yet)").classes("text-gray-500 italic col-span-4")

        warnings_label = ui.label("").classes("text-sm text-amber-700")

        ui.label("Parsed survey").classes("text-sm font-semibold mt-2")
        survey_grid = ui.aggrid(
            {
                "columnDefs": [],
                "rowData": [],
                "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
            }
        ).classes("w-full").style("height: 500px")

        # Secondary / utility actions
        with ui.row().classes("gap-2 mt-2"):
            rerun_llm_btn = ui.button(
                "Re-run LLM",
                icon="replay",
                on_click=lambda: rerun_llm(),
            ).props("flat color=secondary")
            rerun_llm_btn.disable()
            vision_debug_btn = ui.button(
                "Vision debug (single page)",
                icon="science",
                on_click=lambda: open_vision_debug(),
            ).props("flat color=secondary")
            vision_debug_btn.disable()
            ui.button("Clear", icon="close", on_click=lambda: clear_all()).props("flat")

    # ------------------------------------------------------------------
    # Modal lock — built once, reused for every parse run
    # ------------------------------------------------------------------

    with ui.dialog().props("persistent no-escape-dismiss") as busy_dialog, ui.card().classes(
        "min-w-[480px]"
    ):
        ui.label("Processing PDF").classes("text-lg font-semibold")
        ui.label(
            "The UI is locked until extraction finishes — closing this dialog "
            "or clicking elsewhere would corrupt the in-flight parse. "
            "Use Cancel below to abort safely."
        ).classes("text-xs text-gray-500 mb-2")
        with ui.row().classes("items-center gap-3"):
            ui.spinner(size="lg", color="primary")
            busy_status = ui.label("Starting…").classes("text-sm")
        busy_progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
        with ui.row().classes("justify-end w-full mt-2"):
            cancel_btn = ui.button(
                "Cancel", icon="cancel", on_click=lambda: cancel_parse()
            ).props("color=negative flat")

    # ------------------------------------------------------------------
    # Pipeline driver
    # ------------------------------------------------------------------

    def set_progress(fraction: float, message: str, *, color: str = "blue") -> None:
        f = max(0.0, min(1.0, fraction))
        progress.visible = True
        progress.value = f
        status_banner.text = message
        status_banner.classes(
            replace=f"text-sm px-3 py-2 rounded bg-{color}-100 text-{color}-800"
        )
        # Mirror progress + status into the modal busy dialog.
        busy_progress.value = f
        busy_status.text = message

    def cancel_parse() -> None:
        """Cancel the in-flight parse task, if any.

        Note: Python threads can't be killed mid-run, so cancellation works
        by interrupting the ``await`` — the underlying Docling/LLM thread keeps
        running uselessly in the background until it returns. The user's UI
        unlocks immediately, which is what they actually care about.
        """
        task = parsed_state.get("task")
        if task is None or task.done():
            ui.notify("Nothing to cancel.", type="info")
            return
        task.cancel()
        cancel_btn.disable()
        busy_status.text = "Cancelling — current step finishes in background, then UI returns…"

    async def handle_upload(e: events.UploadEventArguments) -> None:
        """Save the uploaded PDF and enable Parse + Vision-debug buttons.

        Parsing does NOT start automatically — user clicks 'Parse PDF' to run.
        """
        upload = getattr(e, "file", None) or getattr(e, "content", None)
        upload_name = getattr(upload, "name", None) or getattr(e, "name", "uploaded.pdf")
        log.info("pdf.upload.received", name=upload_name)

        clear_all(reset_widget=False)

        try:
            tmp_path = await _save_upload(upload, upload_name)
        except Exception as exc:
            _show_error(status_banner, f"Failed to save upload: {exc}")
            _safe_reset(upload_widget)
            return

        parsed_state["tmp_path"] = tmp_path
        parsed_state["upload_name"] = upload_name
        parsed_state["markdown"] = None
        vision_debug_btn.enable()
        _set_run_buttons(True)

        _safe_reset(upload_widget)

        status_banner.text = (
            f"Saved {upload_name}. Click 'Parse PDF' to run the full pipeline, "
            "or 'Vision debug' to test a single page."
        )
        status_banner.classes(
            replace="text-sm px-3 py-2 rounded bg-blue-100 text-blue-800"
        )

    def _set_run_buttons(enabled: bool) -> None:
        for b in (run_rules_btn, run_llm_btn, run_both_btn):
            (b.enable if enabled else b.disable)()

    async def start_parse(*, mode: str = "rules") -> None:
        """User-triggered: run the pipeline in one of three modes.

        ``mode`` is one of:
        - ``"rules"`` — Docling + PyMuPDF + regex only, no LLM call.
        - ``"llm"``   — Docling + PyMuPDF, then LLM (skip rules).
        - ``"both"``  — Rules first, then LLM fills in anything missing.
        """
        tmp_path = parsed_state.get("tmp_path")
        upload_name = parsed_state.get("upload_name", "uploaded.pdf")
        if not tmp_path:
            ui.notify("Upload a PDF first.", type="warning")
            return

        _set_run_buttons(False)
        set_progress(0.05, f"Parsing {upload_name} ({mode}). Starting Docling extraction…")
        busy_dialog.open()
        cancel_btn.enable()
        task = asyncio.create_task(
            _run_pipeline(
                upload_name=upload_name,
                tmp_path=tmp_path,
                force_llm=(mode == "both"),
                force_vision=False,
                llm_only=(mode == "llm"),
                skip_llm=(mode == "rules"),
            )
        )
        parsed_state["task"] = task
        try:
            result = await task
            _render_result(
                result,
                upload_name=upload_name,
                meta_grid=meta_grid,
                survey_grid=survey_grid,
                inject_btn=inject_btn,
                rerun_llm_btn=rerun_llm_btn,
                warnings_label=warnings_label,
                status_banner=status_banner,
                progress=progress,
            )
        except asyncio.CancelledError:
            log.info("pdf.parse.cancelled")
            status_banner.text = "Parse cancelled by user."
            status_banner.classes(
                replace="text-sm px-3 py-2 rounded bg-amber-100 text-amber-800"
            )
            progress.visible = False
            ui.notify("Parse cancelled.", type="warning")
            # Keep tmp_path so Vision debug / re-parse still work.
            _set_run_buttons(True)
        except Exception as exc:
            tb = traceback.format_exc()
            log.exception("pdf.parse.failed", error=str(exc))
            _show_error(status_banner, f"Parser raised: {exc}")
            with meta_card:
                ui.label("Traceback").classes("text-sm font-semibold text-red-700 mt-2")
                ui.code(tb).classes("text-xs w-full")
            progress.visible = False
            _set_run_buttons(True)
        finally:
            parsed_state["task"] = None
            busy_dialog.close()

    async def _run_pipeline(
        *, upload_name: str, tmp_path: str, force_llm: bool, force_vision: bool,
        llm_only: bool = False, skip_llm: bool = False,
    ) -> ParsedSurvey:
        """Run all parser layers. Returns the ParsedSurvey — the caller is
        responsible for rendering it, because NiceGUI's slot context doesn't
        propagate into ``asyncio.create_task`` children.

        ``llm_only`` skips the rules layer entirely (Docling → LLM only).
        """
        result = ParsedSurvey(surveys=pd.DataFrame(), source_file=tmp_path)

        # Layer 1: Docling
        set_progress(0.10, f"Running Docling on {upload_name}… (~50 s)")
        markdown, doc_meta = await _io(pdf_to_markdown, tmp_path, with_ocr=False)
        result.layers_used.append("docling")
        parsed_state["markdown"] = markdown

        if doc_meta.get("looks_scanned"):
            set_progress(0.30, "PDF appears scanned — re-running Docling with OCR…")
            markdown, doc_meta = await _io(pdf_to_markdown, tmp_path, with_ocr=True)
            result.layers_used.append("docling-ocr")
            parsed_state["markdown"] = markdown

        # Layer 1b: PyMuPDF text supplement (catches table-continuation pages
        # Docling drops on std::bad_alloc, and gives the row-regex a second
        # source to union against).
        from etools.core.pdf.parser import _pymupdf_extract_text

        pymupdf_text = await _io(_pymupdf_extract_text, Path(tmp_path))
        if pymupdf_text:
            markdown = (markdown or "") + "\n\n<<<PYMUPDF>>>\n" + pymupdf_text
            result.layers_used.append("pymupdf-text")
            parsed_state["markdown"] = markdown

        # Layer 2: rules — skipped when llm_only is set
        if not llm_only:
            set_progress(0.55, "Docling done. Running rules-based extraction…")
            rules_result = await _io(rules_extract, markdown)
            merge_into(result, rules_result, source="rules")
            result.layers_used.append("rules")
        else:
            set_progress(0.55, "Skipping rules layer (LLM-only mode)…")
            result.layers_used.append("rules-skipped")

        # Layer 3: text LLM — runs in llm_only / force_llm modes, or when
        # rules left fields missing. ``skip_llm`` ("Run rules" button) hard-
        # disables it regardless.
        should_llm = (
            settings.llm.enabled
            and not skip_llm
            and (llm_only or force_llm or is_incomplete(result))
        )
        if should_llm and not force_vision:
            set_progress(0.65, "Running text LLM extraction (qwen3.5)… (~30 s)")
            try:
                llm_result = await _io(llm_text_extract, markdown)
                merge_into(result, llm_result, source="llm-text")
                result.layers_used.append("llm-text")
            except Exception as exc:
                log.warning("pdf.llm.failed", error=str(exc))
                result.warnings.append(f"LLM extraction failed: {exc}")

        # Layer 4: vision LLM
        if settings.llm.enabled and not skip_llm and (force_vision or result.surveys.empty):
            set_progress(0.85, "Running vision LLM on rendered pages… (~60 s)")
            try:
                vision_result = await _io(llm_vision_extract, tmp_path)
                merge_into(result, vision_result, source="llm-vision")
                result.layers_used.append("llm-vision")
            except Exception as exc:
                log.warning("pdf.llm-vision.failed", error=str(exc))
                result.warnings.append(f"Vision LLM extraction failed: {exc}")

        if result.surveys.empty and "llm-vision" not in result.layers_used:
            result.warnings.append(
                "No MD/INC/AZI table extracted — try checking 'Force vision LLM'."
            )

        parsed_state["result"] = result
        return result

    async def _rerun_llm_body() -> tuple[ParsedSurvey, list[str]] | None:
        """Compute-only — returns ``(result, change_log)``. Caller renders."""
        markdown = parsed_state.get("markdown")
        result = parsed_state.get("result") or ParsedSurvey(surveys=pd.DataFrame())

        set_progress(0.5, "Re-running text LLM on Docling markdown…")
        more = await _io(llm_text_extract, markdown)
        tag = "llm-text (manual re-run)"
        source = "llm-text (manual)"

        # Diff each field; report agreed / changed / newly filled.
        change_log: list[str] = []
        scalar_fields = (
            "well_name", "api", "operator",
            "surface_lat", "surface_lon", "surface_elevation_ft",
            "north_reference", "grid_convergence_deg",
            "magnetic_declination_deg", "plss_legal",
        )
        for f in scalar_fields:
            old = getattr(result, f)
            new = getattr(more, f, None)
            if new is None:
                continue
            if old is None:
                change_log.append(f"{f}: filled in → {new!r}")
                setattr(result, f, new)
                result.field_sources[f] = source
            elif old == new:
                change_log.append(f"{f}: agreed (still {old!r})")
                # keep existing source — no change in authority
            else:
                change_log.append(f"{f}: changed {old!r} → {new!r}")
                setattr(result, f, new)
                result.field_sources[f] = source

        if not more.surveys.empty:
            old_n = len(result.surveys)
            new_n = len(more.surveys)
            if old_n == 0:
                change_log.append(f"surveys: filled in {new_n} rows")
                result.surveys = more.surveys
                result.field_sources["surveys"] = source
            elif old_n == new_n:
                change_log.append(f"surveys: same row count ({new_n}); replaced with LLM version")
                result.surveys = more.surveys
                result.field_sources["surveys"] = source
            else:
                change_log.append(
                    f"surveys: row count changed {old_n} → {new_n}; replaced with LLM version"
                )
                result.surveys = more.surveys
                result.field_sources["surveys"] = source
        else:
            change_log.append("surveys: LLM returned no rows; keeping previous version")

        result.layers_used.append(tag)
        parsed_state["result"] = result
        return result, change_log

    async def rerun_llm() -> None:
        """Force a fresh LLM run on the cached markdown / file. UI locked
        and cancellable while it runs."""
        if not parsed_state.get("markdown"):
            ui.notify("No PDF loaded to re-run.", type="warning")
            return

        busy_dialog.open()
        cancel_btn.enable()
        task = asyncio.create_task(_rerun_llm_body())
        parsed_state["task"] = task
        try:
            payload = await task
            if payload is not None:
                result, change_log = payload
                tmp_path = parsed_state.get("tmp_path")
                _render_result(
                    result,
                    upload_name=Path(tmp_path).name if tmp_path else "(re-run)",
                    meta_grid=meta_grid,
                    survey_grid=survey_grid,
                    inject_btn=inject_btn,
                    rerun_llm_btn=rerun_llm_btn,
                    warnings_label=warnings_label,
                    status_banner=status_banner,
                    progress=progress,
                )
                _show_change_log_dialog(change_log)
        except asyncio.CancelledError:
            log.info("pdf.rerun_llm.cancelled")
            ui.notify("LLM re-run cancelled.", type="warning")
            status_banner.text = "Re-run cancelled by user."
            status_banner.classes(
                replace="text-sm px-3 py-2 rounded bg-amber-100 text-amber-800"
            )
            progress.visible = False
        except Exception as exc:
            log.exception("pdf.rerun_llm.failed", error=str(exc))
            _show_error(status_banner, f"LLM re-run failed: {exc}")
        finally:
            parsed_state["task"] = None
            busy_dialog.close()

    # ------------------------------------------------------------------
    # Use survey / clear / refresh
    # ------------------------------------------------------------------

    async def inject_into_pipeline() -> None:
        import asyncio as _asyncio
        result = parsed_state.get("result")
        if result is None or result.surveys.empty:
            ui.notify("Nothing parsed to inject.", type="warning")
            return
        if result.surface_lat is None or result.surface_lon is None:
            ui.notify(
                "Need surface lat/lon to process the survey. "
                "Try checking 'Always run LLM' and re-uploading.",
                type="warning",
            )
            return

        api = (result.api or "0000000000")[:10]
        # Classify the survey by MD-step regularity: regular ~100 ft spacing
        # → Planned; irregular spacing → AsDrilled.
        citing_type = classify_survey_kind(result.surveys)
        log.info("pdf.inject.kind", citing_type=citing_type, points=len(result.surveys))
        synthetic = WellHeader(
            pkey=-1,
            api=api,
            lateral="0000",
            well_name=result.well_name or "(from PDF)",
            operator=result.operator or "(unknown)",
            citing_type=citing_type,
            survey_company=None,
            survey_type=None,
            surface_elevation=result.surface_elevation_ft,
            elevation_reference=None,
            north_reference=result.north_reference,
            grid_convergence=result.grid_convergence_deg,
            grid_scale_factor=None,
            surface_lat=result.surface_lat,
            surface_lon=result.surface_lon,
            surface_x=None,
            surface_y=None,
            utm_zone="12T",
            plss_location=result.plss_legal,
            upload_filename=result.source_file,
            upload_datetime=None,
        )
        state.headers = [synthetic]
        state.primary = synthetic
        state.surveys = {citing_type: result.surveys.copy()}
        state.selected_citing = citing_type
        state.processed = {}
        state.clearances = {}
        reset_survey_edits(state)
        ui.notify(
            f"Injected {len(result.surveys)} points as '{citing_type}'.",
            type="positive",
        )
        if on_inject is not None:
            res = on_inject()
            if _asyncio.iscoroutine(res):
                await res

    def clear_all(*, reset_widget: bool = True) -> None:
        parsed_state["result"] = None
        parsed_state["tmp_path"] = None
        parsed_state["upload_name"] = None
        parsed_state["markdown"] = None
        meta_grid.clear()
        with meta_grid:
            ui.label("(no PDF loaded yet)").classes("text-gray-500 italic col-span-4")
        warnings_label.text = ""
        survey_grid.options["columnDefs"] = []
        survey_grid.options["rowData"] = []
        survey_grid.update()
        inject_btn.disable()
        rerun_llm_btn.disable()
        vision_debug_btn.disable()
        _set_run_buttons(False)
        progress.visible = False
        progress.value = 0.0
        status_banner.text = "Awaiting upload…"
        status_banner.classes(
            replace="text-sm px-3 py-2 rounded bg-slate-100 text-slate-700"
        )
        if reset_widget:
            _safe_reset(upload_widget)

    def open_vision_debug() -> None:
        """Pop a small dialog: page number + DPI → call vision_transcribe_page."""
        tmp_path = parsed_state.get("tmp_path")
        if not tmp_path:
            ui.notify("Load a PDF first.", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("min-w-[420px]"):
            ui.label("Vision debug — single page transcription").classes(
                "text-lg font-semibold"
            )
            ui.label(
                "Renders one page at the chosen DPI and asks the vision LLM only "
                "to transcribe MD/INC/AZI rows. Raw response is dumped to "
                "output/llm_debug/."
            ).classes("text-xs text-gray-500")
            page_input = ui.number("Page (1-based)", value=1, min=1, step=1).classes("w-full")
            dpi_input = ui.number("DPI", value=300, min=72, max=600, step=50).classes("w-full")
            result_box = ui.code("").classes("w-full max-h-[300px] overflow-auto text-xs")
            result_box.visible = False

            async def run() -> None:
                page = int(page_input.value or 1)
                dpi = int(dpi_input.value or 300)
                run_btn.disable()
                result_box.visible = True
                result_box.content = f"Running… (page {page} @ {dpi} dpi)"
                try:
                    raw, meta = await _io(vision_transcribe_page, tmp_path, page, dpi)
                except Exception as exc:
                    log.exception("pdf.vision_debug.failed", error=str(exc))
                    result_box.content = f"ERROR: {exc}"
                    run_btn.enable()
                    return
                result_box.content = (
                    f"# page {meta['page']} of {meta['total_pages']}  "
                    f"({meta['image_bytes']} bytes png, {meta['elapsed_s']}s)\n\n"
                    f"{raw}"
                )
                run_btn.enable()

            with ui.row().classes("justify-end w-full mt-2 gap-2"):
                ui.button("Close", on_click=dlg.close).props("flat")
                run_btn = ui.button("Run", on_click=run).props("color=primary")
        dlg.open()

    def refresh() -> None:
        # PDF tab is independent of well-load state; nothing to refresh on load.
        _refresh_llm_status(llm_label)

    return refresh


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe_reset(widget) -> None:
    """Clear the QUploader queue. Wrapped because ``reset()`` raises if
    the widget hasn't fully mounted yet (e.g., from an early-fire handler)."""
    try:
        widget.reset()
    except Exception:  # pragma: no cover
        pass


async def _save_upload(upload, name: str) -> str:
    suffix = Path(name).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    tmp.close()
    if upload is not None and hasattr(upload, "save"):
        await upload.save(tmp_path)
    elif upload is not None and hasattr(upload, "read"):
        read_result = upload.read()
        if hasattr(read_result, "__await__"):
            data = await read_result
        else:
            data = read_result
        Path(tmp_path).write_bytes(data if isinstance(data, bytes) else bytes(data))
    else:
        raise RuntimeError(f"Don't know how to read upload object: {type(upload).__name__}")
    return tmp_path


def _refresh_llm_status(label: ui.label) -> None:
    try:
        from etools.core.llm import OllamaClient

        cli = OllamaClient()
        if not settings.llm.enabled:
            label.text = "LLM: disabled in config"
        elif cli.health() and cli.has_model():
            label.text = f"LLM: ready ({settings.llm.model})"
        elif cli.health():
            label.text = f"LLM: Ollama up but model '{settings.llm.model}' not pulled"
        else:
            label.text = "LLM: Ollama not running (rules-only mode)"
    except Exception as exc:
        label.text = f"LLM: status check failed ({exc})"


def _show_error(banner: ui.label, message: str) -> None:
    banner.text = message
    banner.classes(replace="text-sm px-3 py-2 rounded bg-red-100 text-red-800")
    ui.notify(message, type="negative")


_SOURCE_COLORS = {
    "rules": "bg-slate-200 text-slate-700",
    "llm-text": "bg-indigo-100 text-indigo-800",
    "llm-vision": "bg-purple-100 text-purple-800",
    "llm-text (manual)": "bg-indigo-200 text-indigo-900",
    "llm-vision (manual)": "bg-purple-200 text-purple-900",
}


def _source_badge(source: str | None) -> str:
    """HTML for a small inline provenance badge next to a metadata value."""
    if not source:
        return ""
    cls = _SOURCE_COLORS.get(source, "bg-gray-100 text-gray-700")
    return f'<span class="text-[10px] px-1.5 py-0.5 rounded ml-2 {cls}">{source}</span>'


def _render_result(
    result: ParsedSurvey,
    *,
    upload_name: str,
    meta_grid,
    survey_grid,
    inject_btn,
    rerun_llm_btn,
    warnings_label,
    status_banner,
    progress,
) -> None:
    sources = result.field_sources
    meta_grid.clear()
    rows: list[tuple[str, object, str | None]] = [
        ("Source file", upload_name, None),
        ("Well name", result.well_name or "—", sources.get("well_name")),
        ("API (PDF)", result.api or "—", sources.get("api")),
        ("Operator", result.operator or "—", sources.get("operator")),
        ("North ref", result.north_reference or "—", sources.get("north_reference")),
        ("Surface lat", result.surface_lat, sources.get("surface_lat")),
        ("Surface lon", result.surface_lon, sources.get("surface_lon")),
        ("Elevation (ft)", result.surface_elevation_ft, sources.get("surface_elevation_ft")),
        ("Grid convergence (°)", result.grid_convergence_deg, sources.get("grid_convergence_deg")),
        ("Magnetic decl. (°)", result.magnetic_declination_deg, sources.get("magnetic_declination_deg")),
        ("PLSS legal", result.plss_legal or "—", sources.get("plss_legal")),
        ("Survey points", len(result.surveys), sources.get("surveys")),
        ("Layers used", " → ".join(result.layers_used) if result.layers_used else "—", None),
    ]
    with meta_grid:
        for label, value, source in rows:
            ui.label(label).classes("text-gray-500")
            text = str(value) if value not in (None, "") else "—"
            badge = _source_badge(source)
            if badge:
                ui.html(f'<span>{text}</span>{badge}').classes("text-sm")
            else:
                ui.label(text)

    warnings_label.text = " · ".join(result.warnings) if result.warnings else ""

    df = result.surveys
    if df.empty:
        survey_grid.options["columnDefs"] = []
        survey_grid.options["rowData"] = []
        survey_grid.update()
        inject_btn.disable()
        rerun_llm_btn.enable()
        status_banner.text = (
            f"Parsed {upload_name} — no MD/INC/AZI table found. "
            "Try checking 'Force vision LLM' and re-uploading."
        )
        status_banner.classes(
            replace="text-sm px-3 py-2 rounded bg-amber-100 text-amber-800"
        )
        ui.notify("No survey table found.", type="warning")
    else:
        # Display-only formatting: lat/lon → 5 dp, all other numeric → 2 dp.
        # The underlying `result.surveys` (which gets injected into state on
        # "Use this survey") stays at full precision.
        display_df = df.copy()
        col_defs = []
        for c in df.columns:
            spec: dict = {"field": c, "headerName": c}
            if pd.api.types.is_numeric_dtype(df[c]):
                cl = c.lower()
                digits = 5 if ("lat" in cl or "lon" in cl) else 2
                display_df[c] = display_df[c].round(digits)
                spec[":valueFormatter"] = (
                    "function(p) { "
                    "if (p.value === null || p.value === undefined) return ''; "
                    "if (typeof p.value !== 'number' || isNaN(p.value)) return p.value; "
                    f"return p.value.toFixed({digits}); "
                    "}"
                )
            col_defs.append(spec)
        survey_grid.options["columnDefs"] = col_defs
        survey_grid.options["rowData"] = display_df.to_dict(orient="records")
        survey_grid.update()
        inject_btn.enable()
        rerun_llm_btn.enable()
        status_banner.text = f"Parsed {upload_name} — {len(df)} survey points extracted."
        status_banner.classes(
            replace="text-sm px-3 py-2 rounded bg-emerald-100 text-emerald-800"
        )
        ui.notify(f"Parsed {len(df)} survey points.", type="positive")

    progress.value = 1.0


def _three_decimal_fmt(col: str):
    """Formatter: lat/lon → 5 decimal places, everything else numeric → 2."""
    name = col.lower()
    digits = 5 if ("lat" in name or "lon" in name) else 2
    return {
        "function": (
            "params.value === null || params.value === undefined ? '' : "
            f"(typeof params.value === 'number' ? params.value.toFixed({digits}) : params.value)"
        )
    }


def _show_change_log_dialog(change_log: list[str]) -> None:
    """Pop a summary of what the manual LLM re-run actually changed.

    Categorises each line by its keyword (agreed/changed/filled/etc.) so the
    user can tell at a glance whether the LLM contributed anything.
    """
    if not change_log:
        ui.notify("LLM re-run produced no changes.", type="info")
        return

    counts = {"agreed": 0, "changed": 0, "filled in": 0, "other": 0}
    for line in change_log:
        if "agreed" in line:
            counts["agreed"] += 1
        elif "changed" in line:
            counts["changed"] += 1
        elif "filled in" in line:
            counts["filled in"] += 1
        else:
            counts["other"] += 1

    summary = (
        f"{counts['agreed']} agreed · "
        f"{counts['changed']} changed · "
        f"{counts['filled in']} filled · "
        f"{counts['other']} other"
    )

    with ui.dialog() as dlg, ui.card().classes("min-w-[520px] max-w-[640px]"):
        ui.label("LLM re-run summary").classes("text-lg font-semibold")
        ui.label(summary).classes("text-sm text-gray-700 mb-2")
        with ui.column().classes("gap-1 max-h-[400px] overflow-y-auto"):
            for line in change_log:
                color = (
                    "text-emerald-700" if "filled in" in line
                    else "text-amber-700" if "changed" in line
                    else "text-gray-600"
                )
                ui.label(f"· {line}").classes(f"text-xs font-mono {color}")
        with ui.row().classes("justify-end w-full mt-2"):
            ui.button("OK", on_click=dlg.close).props("flat color=primary")
    dlg.open()
