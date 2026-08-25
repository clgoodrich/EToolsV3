"""The Load Well handler must not block the event loop on a DB call."""
from __future__ import annotations

import inspect

from etools.ui import app as app_module


def _load_handler_source() -> str:
    src = inspect.getsource(app_module)
    start = src.index("async def load_handler")
    return src[start : start + 1500]


def test_service_load_is_offloaded_to_a_thread():
    body = _load_handler_source()
    assert "service.load(lookup)" not in body, (
        "service.load is a blocking pyodbc call; running it on the event loop "
        "freezes the whole server for every client until the ODBC timeout"
    )
    assert "to_thread" in body or "run_in_executor" in body


def test_well_not_found_is_still_handled_separately():
    # The typed empty-state error must keep its friendly warning toast rather
    # than collapsing into the generic red failure branch.
    body = _load_handler_source()
    assert "WellNotFoundError" in body
    assert 'type="warning"' in body


def test_asyncio_is_available_at_module_scope():
    # to_thread must resolve without a local import inside the handler.
    src = inspect.getsource(app_module)
    header = src[: src.index("def build_app")]
    assert "import asyncio" in header
