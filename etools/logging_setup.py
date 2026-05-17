"""Structured logging via structlog with stdlib bridge.

Forces UTF-8 stdout on Windows so Unicode in log payloads (emoji, em-dashes,
non-ASCII glyphs from PDF text or LLM output) doesn't crash the print call.

Logs are duplicated to ``output/logs/etools.log`` (rotated) so we have a
persistent trace when the launcher console closes or the WebSocket drops.
"""

from __future__ import annotations

import io
import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

import structlog

from etools.config import settings


def _utf8_stream(stream):
    """Wrap a TextIO stream so it can encode any character (replaces unencodables)."""
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return stream  # not a real terminal stream — leave alone
    try:
        return io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:  # pragma: no cover
        return stream


_INSTALLED = False


def configure_logging() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # Replace stdout with a UTF-8 wrapper before stdlib logging captures it.
    sys.stdout = _utf8_stream(sys.stdout)
    sys.stderr = _utf8_stream(sys.stderr)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # File handler: persistent rotating log under output/logs/.
    log_dir = settings.output_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "etools.log",
            maxBytes=5_000_000,  # 5 MB per file
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler.setLevel(level)
    except Exception as exc:  # pragma: no cover
        file_handler = None
        print(f"[logging] file handler init failed: {exc}", file=sys.stderr)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if file_handler is not None:
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,  # in case basicConfig was called earlier with the old stream
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Global exception hooks — capture stuff that would otherwise vanish
    # into the void (NiceGUI swallows some, Python exits on others).
    _install_exception_hooks(file_path=log_dir / "etools.log" if file_handler else None)


def _install_exception_hooks(*, file_path: Path | None) -> None:
    """Route uncaught exceptions into the structured logger."""
    root_log = structlog.get_logger("uncaught")

    def _hook(exc_type, exc_value, exc_tb) -> None:
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        root_log.error(
            "uncaught.exception",
            error_type=exc_type.__name__ if exc_type else "?",
            error=str(exc_value),
            traceback=tb_str,
        )

    sys.excepthook = _hook

    def _thread_hook(args) -> None:
        _hook(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _thread_hook

    # asyncio: wire up via the running loop the first time we see one.
    try:
        import asyncio

        def _loop_hook(loop, ctx):
            exc = ctx.get("exception")
            if exc:
                _hook(type(exc), exc, exc.__traceback__)
            else:
                root_log.error("asyncio.error", message=ctx.get("message"))

        asyncio.get_event_loop_policy().get_event_loop().set_exception_handler(_loop_hook)
    except Exception:  # pragma: no cover
        pass


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
