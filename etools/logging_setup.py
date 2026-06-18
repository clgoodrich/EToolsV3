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

# Ring buffer of the most recent uncaught exceptions. The NiceGUI
# page.disconnect handler reads this so we can correlate a websocket drop
# with the exception that likely caused it.
last_error_ring: list[dict] = []


def recent_errors(n: int = 3) -> list[dict]:
    """Return the most recent uncaught exceptions (newest last)."""
    return list(last_error_ring[-n:])


def configure_logging() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # Replace stdout with a UTF-8 wrapper before stdlib logging captures it.
    sys.stdout = _utf8_stream(sys.stdout)
    sys.stderr = _utf8_stream(sys.stderr)

    # Console honors ETOOLS_LOG_LEVEL; the FILE always records full DEBUG so a
    # user can hand us a complete session trace when something breaks, even
    # while the visible console stays quiet. The root logger + structlog must
    # therefore run at the lower of the two so DEBUG records reach the file.
    console_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    file_level = logging.DEBUG
    root_level = min(console_level, file_level)

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
        file_handler.setLevel(file_level)
    except Exception as exc:  # pragma: no cover
        file_handler = None
        print(f"[logging] file handler init failed: {exc}", file=sys.stderr)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(console_level)
    handlers: list[logging.Handler] = [stream_handler]
    if file_handler is not None:
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=root_level,
        handlers=handlers,
        force=True,  # in case basicConfig was called earlier with the old stream
    )

    # Capture exc_info from log.exception()/logger.error(exc_info=True) into
    # the same ring buffer, so page.disconnect can surface UI handler errors
    # (e.g. the wcr_tab blur cascade) without us routing every call site
    # through sys.excepthook.
    class _ExcRingFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            exc_info = getattr(record, "exc_info", None)
            # The same record passes through every handler; tag it so the
            # second handler's copy of this filter doesn't double-append.
            if exc_info and exc_info[0] is not None and not getattr(record, "_etools_rung", False):
                etype, evalue, etb = exc_info
                tb_str = "".join(traceback.format_exception(etype, evalue, etb))
                last_error_ring.append({
                    "type": etype.__name__,
                    "msg": str(evalue),
                    "tb": tb_str,
                })
                while len(last_error_ring) > 10:
                    last_error_ring.pop(0)
                record._etools_rung = True
            return True

    # Filters attached to a logger only fire for records originating at that
    # logger — they don't fire for propagated records. Attaching to each
    # handler instead means every record (from any logger) flows through.
    _ring_filter = _ExcRingFilter()
    for h in handlers:
        h.addFilter(_ring_filter)

    # Silence the per-request firehose from httpx/httpcore/urllib3 — every
    # Ollama health poll otherwise dumps ~12 lines of connect_tcp /
    # send_request_headers / receive_response noise that drowns out real
    # app events and makes the page.disconnect cause invisible.
    for noisy in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection",
                  "urllib3", "urllib3.connectionpool", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(root_level),
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
        last_error_ring.append({
            "type": exc_type.__name__ if exc_type else "?",
            "msg": str(exc_value),
            "tb": tb_str,
        })
        # Keep the ring bounded.
        while len(last_error_ring) > 10:
            last_error_ring.pop(0)
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
