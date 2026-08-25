"""A DB failure while fetching WCR extras must be visible, not silent."""
from __future__ import annotations

from etools.services import wcr_pdf_service


class _Boom:
    def __init__(self):
        raise RuntimeError("SQL Server unreachable")


def test_db_extras_returns_none_pair_without_an_api():
    assert wcr_pdf_service._db_extras(None) == (None, None)


def test_db_extras_warns_when_the_database_is_unreachable(monkeypatch):
    monkeypatch.setattr("etools.repositories.WCRRepository", _Boom, raising=True)
    warnings: list[str] = []
    casing, perf = wcr_pdf_service._db_extras("4301354722", warnings=warnings)
    assert (casing, perf) == (None, None)
    assert len(warnings) == 1
    assert "casing" in warnings[0].lower()
    assert "database" in warnings[0].lower()


def test_db_extras_without_a_warnings_sink_still_degrades(monkeypatch):
    monkeypatch.setattr("etools.repositories.WCRRepository", _Boom, raising=True)
    assert wcr_pdf_service._db_extras("4301354722") == (None, None)
