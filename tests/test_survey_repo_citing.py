"""SurveyRepository / WellRepository: canonical citing keys and one header per
citing type (the DB holds ``ASDRILLED``/``planned`` spellings and re-uploads)."""

from __future__ import annotations

import pandas as pd
import pytest

from etools.repositories import survey as survey_mod
from etools.repositories import well as well_mod
from etools.repositories.survey import SurveyRepository, canonical_citing_type
from etools.repositories.well import WellRepository


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Engine:
    def connect(self):
        return _Conn()


@pytest.mark.parametrize(
    "raw,expected",
    [("ASDRILLED", "AsDrilled"), ("Asdrilled", "AsDrilled"), ("AsDrilled", "AsDrilled"),
     ("PLANNED", "Planned"), ("planned", "Planned"), (None, "")],
)
def test_canonical_citing_type(raw, expected) -> None:
    assert canonical_citing_type(raw) == expected


def test_points_keep_newest_header_per_citing(monkeypatch) -> None:
    rows = []
    for pkey, up, mds in ((10, "2024-01-01", (0, 100, 200)), (20, "2025-01-01", (0, 150))):
        for md in mds:
            rows.append({"CitingType": "PLANNED", "HeaderPKey": pkey, "HeaderUpload": up, "HeaderNorthRef": "True",
                         "MeasuredDepth": md})
    rows.append({"CitingType": "ASDRILLED", "HeaderPKey": 30, "HeaderUpload": None,
                 "HeaderNorthRef": None,
                 "MeasuredDepth": 0})
    monkeypatch.setattr(survey_mod.pd, "read_sql_query", lambda *a, **k: pd.DataFrame(rows))
    out = SurveyRepository(engine=_Engine()).get_points_by_api_lateral("4301300000")
    assert set(out) == {"AsDrilled", "Planned"}
    assert out["Planned"]["MeasuredDepth"].tolist() == [0, 150]
    assert out["Planned"].attrs["north_reference"] == "True"
    assert out["AsDrilled"].attrs["north_reference"] is None


def test_list_headers_canonical_and_deduped(monkeypatch) -> None:
    base = {"APINumber": "4301300000", "LateralName": "0000"}
    df = pd.DataFrame([
        {**base, "PKey": 1, "CitingType": "PLANNED", "UploadDateTime": pd.Timestamp("2024-01-01")},
        {**base, "PKey": 2, "CitingType": "Planned", "UploadDateTime": pd.Timestamp("2025-01-01")},
        {**base, "PKey": 3, "CitingType": "ASDRILLED", "UploadDateTime": pd.Timestamp("2023-01-01")},
    ])
    monkeypatch.setattr(well_mod.pd, "read_sql_query", lambda *a, **k: df)
    hs = WellRepository(engine=_Engine()).list_headers("4301300000")
    assert sorted((h.pkey, h.citing_type) for h in hs) == [(2, "Planned"), (3, "AsDrilled")]
