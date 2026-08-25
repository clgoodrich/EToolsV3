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
from etools.preflight import format_preflight_report, missing_data_files
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

    # Tell the user about missing data files up front. Without this the
    # server starts and binds the port, then every page load dies inside
    # root() with the real cause visible only in the log.
    missing = missing_data_files()
    if missing:
        print(format_preflight_report(missing))
        log.warning(
            "etools.preflight.missing_data_files",
            files=[s.name for s in missing],
            paths=[str(s.path) for s in missing],
        )

    build_app()
    _open_in_default_browser(f"http://127.0.0.1:{settings.port}/")
    ui.run(
        host="127.0.0.1",
        port=settings.port,
        title="ETools — DOGM",
        reload=False,
        show=False,  # we open the URL ourselves — Python's webbrowser
                     # module on Windows mis-routes to IE instead of the
                     # OS default browser.
        reconnect_timeout=30.0,
    )


def _open_in_default_browser(url: str) -> None:
    """Open ``url`` in the OS's real default browser.

    Python's ``webbrowser`` module on Windows often picks Internet Explorer
    even when Firefox/Edge/Chrome is the registered default. ``os.startfile``
    routes through the Windows shell, which respects the per-user default
    set in Settings → Apps → Default Apps.
    """
    import os
    import sys
    import threading

    def _go():
        try:
            if sys.platform == "win32":
                os.startfile(url)  # noqa: S606  — shell call to default handler
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", url])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", url])
        except Exception:
            # Fall back to webbrowser if the shell call fails.
            import webbrowser
            webbrowser.open(url, new=2)

    # Defer slightly so the server is listening when the browser hits the URL.
    threading.Timer(1.0, _go).start()


if __name__ in {"__main__", "__mp_main__"}:
    run()
