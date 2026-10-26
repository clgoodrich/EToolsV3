"""Workspace (multi-document) layer tests.

Guards the two things most likely to silently break:

* **Field drift** — every AppState field must be classified as either
  per-document data or session infrastructure, or switching wells would
  leak/lose state for the unclassified field.
* **Switch/merge/close semantics** — buffers stay independent, live edits
  survive a round-trip switch, re-loading the same well merges in place,
  and closing falls back sanely.
"""

from __future__ import annotations

import dataclasses

from etools.models import WellHeader
from etools.ui import workspace as w
from etools.ui.state import AppState


def _hdr(api: str, lateral: str = "0000", name: str | None = None) -> WellHeader:
    return WellHeader(pkey=1, api=api, lateral=lateral, well_name=name)


def test_document_fields_cover_appstate() -> None:
    """DOCUMENT_FIELDS ∪ INFRA_FIELDS must partition AppState exactly."""
    fields = {f.name for f in dataclasses.fields(AppState)}
    classified = set(w.DOCUMENT_FIELDS) | set(w.INFRA_FIELDS)
    assert fields - classified == set(), "unclassified AppState field(s)"
    assert classified - fields == set(), "classified field not on AppState"
    # documents/active_doc_id must be infra, never captured per-document.
    assert "documents" not in w.DOCUMENT_FIELDS
    assert "active_doc_id" not in w.DOCUMENT_FIELDS


def test_upsert_and_switch_preserve_independent_buffers() -> None:
    s = AppState()

    s.primary = _hdr("4301354722", name="Well A")
    s.headers = [s.primary]
    s.apd_data = "APD_A"
    s.casing_overrides = {0: {"x": 1}}
    id_a = w.upsert_active_document(s)

    s.primary = _hdr("4301399999", name="Well B")
    s.headers = [s.primary]
    s.apd_data = "APD_B"
    s.casing_overrides = {1: {"y": 2}}
    id_b = w.upsert_active_document(s)

    assert list(s.documents) == [id_a, id_b]
    assert s.active_doc_id == id_b

    # Unsaved live edit on B, then switch to A.
    s.casing_overrides[2] = {"z": 3}
    assert w.switch_document(s, id_a) is True
    assert s.apd_data == "APD_A"
    assert s.casing_overrides == {0: {"x": 1}}

    # Switch back — B's edit must have been captured on switch-away.
    w.switch_document(s, id_b)
    assert s.apd_data == "APD_B"
    assert s.casing_overrides == {1: {"y": 2}, 2: {"z": 3}}


def test_switch_to_active_or_missing_is_noop() -> None:
    s = AppState()
    s.primary = _hdr("4301354722", name="A")
    s.headers = [s.primary]
    id_a = w.upsert_active_document(s)
    assert w.switch_document(s, id_a) is False  # already active
    assert w.switch_document(s, "nope|0000") is False  # unknown id


def test_reload_same_well_merges_in_place() -> None:
    s = AppState()
    s.primary = _hdr("4301354722", name="Well A")
    s.headers = [s.primary]
    s.apd_data = "v1"
    id1 = w.upsert_active_document(s)

    # Re-load same API/lateral from another source.
    s.primary = _hdr("4301354722", name="Well A (renamed)")
    s.headers = [s.primary]
    s.apd_data = "v2"
    id2 = w.upsert_active_document(s)

    assert id1 == id2
    assert len(s.documents) == 1
    assert s.documents[id1].label == "Well A (renamed)"
    assert s.documents[id1].data["apd_data"] == "v2"


def test_remove_active_falls_back_then_empties() -> None:
    s = AppState()
    for api, name, payload in (
        ("4301354722", "A", "APD_A"),
        ("4301399999", "B", "APD_B"),
    ):
        s.primary = _hdr(api, name=name)
        s.headers = [s.primary]
        s.apd_data = payload
        w.upsert_active_document(s)
    id_a = "4301354722|0000"
    id_b = "4301399999|0000"

    # Close the active buffer (B) → falls back to A.
    nxt = w.remove_document(s, s.active_doc_id)
    assert nxt == id_a
    assert list(s.documents) == [id_a]
    assert s.apd_data == "APD_A"

    # Close the last one → live state reset to empty.
    nxt = w.remove_document(s, id_b if False else id_a)
    assert nxt is None
    assert s.active_doc_id is None
    assert s.apd_data is None
    assert s.casing_overrides == {}


def test_document_source_tagging() -> None:
    """The switcher badge tracks where the well came from (DB/APD/WCR)."""
    s = AppState()
    s.primary = _hdr("4301354722", name="A")
    s.headers = [s.primary]
    id_a = w.upsert_active_document(s)
    assert s.documents[id_a].source == "DB"

    s.apd_data = "APD"
    w.upsert_active_document(s)
    assert s.documents[id_a].source == "APD"

    s.wcr_data = "WCR"
    w.upsert_active_document(s)
    assert s.documents[id_a].source == "APD+WCR"

    # Switching away refreshes the outgoing buffer's source too.
    s.primary = _hdr("4301399999", name="B")
    s.headers = [s.primary]
    s.apd_data = None
    s.wcr_data = "WCR_B"
    id_b = w.upsert_active_document(s)
    assert s.documents[id_b].source == "WCR"
    w.switch_document(s, id_a)
    assert s.documents[id_b].source == "WCR"


def test_upsert_without_primary_is_noop() -> None:
    s = AppState()
    assert w.upsert_active_document(s) is None
    assert s.documents == {}
    assert s.active_doc_id is None


# ---------------------------------------------------------------------------
# begin_document — loading a new well must not inherit the previous one's
# per-well fields (the partial-reset defect).
# ---------------------------------------------------------------------------
class _Parsed:
    def __init__(self, api: str) -> None:
        self.api = api


def _loaded_well_a() -> AppState:
    s = AppState()
    s.primary = _hdr("4301354722", name="Well A")
    s.headers = [s.primary]
    s.apd_data = _Parsed("43013547220000")
    s.casing_overrides = {0: {"x": 1}}
    s.casing_frac_gradient_psi_per_ft = 0.9
    s.bope_overrides = {"op_max": 1.0}
    s.casing_survey_df = "SURVEY_A"
    s.wcr_data = _Parsed("4301354722")
    s.section_definitions = {"conc": "A"}
    s.extra = {"k": "A"}
    w.upsert_active_document(s)
    return s


def test_begin_document_for_other_well_drops_previous_wells_fields() -> None:
    s = _loaded_well_a()
    s.casing_overrides[1] = {"late": "edit"}  # unsaved edit on A
    w.begin_document(s, w.document_id_for("4301399999", "0000"))
    empty = w.empty_document_data()
    for f in w.DOCUMENT_FIELDS:
        assert getattr(s, f) == empty[f], f
    assert s.active_doc_id is None
    # A's buffer kept everything, including the edit made after its upsert.
    a = s.documents[w.document_id_for("4301354722", "0000")].data
    assert a["casing_overrides"] == {0: {"x": 1}, 1: {"late": "edit"}}
    assert a["wcr_data"].api == "4301354722"


def test_begin_document_parse_keep_fields_stay_off_the_outgoing_buffer() -> None:
    s = _loaded_well_a()
    # A new permit for well B was just parsed into the live state.
    s.apd_data = _Parsed("43013999990000")
    s.apd_pdf_name = "b.pdf"
    w.begin_document(
        s,
        w.document_id_for("4301399999", "0000"),
        keep=("apd_data", "apd_pdf_path", "apd_pdf_name"),
    )
    assert s.apd_data.api == "43013999990000"
    assert s.apd_pdf_name == "b.pdf"
    # The rest of the APD family belonged to A and must not carry over.
    assert s.casing_overrides == {}
    assert s.casing_frac_gradient_psi_per_ft is None
    assert s.casing_survey_df is None
    assert s.wcr_data is None
    a = s.documents[w.document_id_for("4301354722", "0000")].data
    assert a["apd_data"].api == "43013547220000"
    assert a["apd_pdf_name"] is None


def test_begin_document_keeps_a_matching_source_family() -> None:
    s = AppState()
    s.wcr_data = _Parsed("43013999990000")
    s.wcr_survey_label = "wcr survey"
    s.apd_data = _Parsed("4301311111")  # some other well's permit
    w.begin_document(s, w.document_id_for("4301399999", "0000"))
    assert s.wcr_data.api == "43013999990000"
    assert s.wcr_survey_label == "wcr survey"
    assert s.apd_data is None


def test_begin_document_same_active_well_is_a_noop() -> None:
    s = _loaded_well_a()
    w.begin_document(s, w.document_id_for("4301354722", "0000"))
    assert s.casing_overrides == {0: {"x": 1}}
    assert s.active_doc_id == w.document_id_for("4301354722", "0000")


def test_begin_document_restores_incoming_wells_buffer() -> None:
    s = _loaded_well_a()
    id_a = s.active_doc_id
    w.begin_document(s, w.document_id_for("4301399999", "0000"))
    s.primary = _hdr("4301399999", name="Well B")
    w.upsert_active_document(s)
    # Re-load A: its section overrides/extras come back from its buffer.
    w.begin_document(s, id_a)
    assert s.section_definitions == {"conc": "A"}
    assert s.extra == {"k": "A"}
