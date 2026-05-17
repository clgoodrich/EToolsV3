"""Application entry point.

Run with::

    python -m etools.main
    # or, after `pip install -e .`:
    etools

Opens a local browser at http://localhost:8080/.
"""

from __future__ import annotations

from nicegui import ui

from etools.config import settings
from etools.logging_setup import configure_logging, get_logger
from etools.ui.app import build_app


def run() -> None:
    configure_logging()
    log = get_logger(__name__)
    log_file = settings.output_dir / "logs" / "etools.log"
    log.info(
        "etools.start",
        port=settings.port,
        db_server=settings.db.server,
        db_database=settings.db.database,
        log_level=settings.log_level,
        log_file=str(log_file),
    )
    print(f"\n[etools] Persistent log: {log_file}\n")
    build_app()
    ui.run(
        host="127.0.0.1",
        port=settings.port,
        title="ETools — DOGM",
        reload=False,
        show=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
