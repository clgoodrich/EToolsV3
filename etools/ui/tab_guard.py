"""Render one tab in isolation.

``root()`` builds seven tabs in sequence. Before this module, an exception
in any of them -- most realistically ``FileNotFoundError`` from a missing
gitignored data file, raised eagerly inside ``CasingReviewService()`` at
``casing_review_tab.py:193`` -- propagated out of ``root()`` and the whole
page failed to render, for every user, with the cause only in the log.

A broken tab now shows an inline explanation and the other six work.
"""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from etools.logging_setup import get_logger

log = get_logger(__name__)

RefreshCallback = Callable[[], None]


def describe_tab_failure(name: str, exc: Exception) -> str:
    """Explain a tab render failure in terms the user can act on."""
    base = f"The {name} tab could not be loaded."
    if isinstance(exc, FileNotFoundError):
        text = str(exc)
        # Match the failure against the known data files so we can print the
        # real build command rather than just echoing the exception.
        try:
            from etools.preflight import required_data_files

            for status in required_data_files():
                if status.path.name and status.path.name in text:
                    return (
                        f"{base}\n\n"
                        f"Missing data file: {status.name} "
                        f"(expected at {status.path}).\n"
                        f"Needed for: {status.purpose}\n"
                        f"To fix: {status.build_hint}"
                    )
        except Exception:  # pragma: no cover - preflight must never mask exc
            log.exception("tab_guard.preflight_lookup_failed")
        return f"{base}\n\nMissing file: {text}"
    return f"{base}\n\n{type(exc).__name__}: {exc}"


def _default_panel(name: str, exc: Exception) -> None:
    with ui.column().classes("p-6 gap-2 w-full"):
        ui.label(f"{name} unavailable").classes(
            "text-lg font-semibold text-red-700"
        )
        ui.label(describe_tab_failure(name, exc)).classes(
            "text-sm text-red-800 bg-red-50 p-3 rounded whitespace-pre-wrap"
        )
        ui.label(
            "The other tabs are unaffected. Restart ETools after fixing this."
        ).classes("text-xs text-gray-500")


def safe_tab_render(
    name: str,
    render: Callable[[], RefreshCallback | None],
    *,
    panel: Callable[[str, Exception], None] | None = None,
) -> RefreshCallback:
    """Render a tab, substituting an error panel if it raises.

    Always returns a callable, so ``refresh_callbacks`` stays uniform and
    ``fire_refresh`` never has to special-case a failed tab.
    """
    try:
        callback = render()
    except Exception as exc:
        # Both of these can themselves raise, and if either does the guard is
        # defeated and the page dies anyway -- which is the whole thing this
        # module exists to prevent. Logging blew up for real during
        # verification: structlog writing to a cp1252 console raised
        # UnicodeEncodeError on a traceback containing an em-dash. The same
        # nested guard already exists at casing_review_tab.py:2499.
        try:
            log.exception("tab.render_failed", tab=name, error=str(exc))
        except Exception:
            pass
        try:
            (panel or _default_panel)(name, exc)
        except Exception:
            pass
        return lambda: None
    return callback if callable(callback) else (lambda: None)
