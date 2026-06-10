"""Multi-document workspace layer for :class:`AppState`.

The app keeps a single, module-scope ``AppState`` whose *data* fields hold
the **currently active** well (loaded survey, processed results,
clearances, parsed APD/WCR, section geometry, casing knobs, …). Every tab
reads those fields directly by closure, and that must keep working — so we
do NOT move the fields into a sub-object.

Instead this module adds an *open-buffers* model on top of that single
live state:

* ``state.documents`` — ordered ``{doc_id: WellDocument}`` of every well
  the user has loaded this session. Each ``WellDocument`` is a snapshot of
  the per-well data fields (see ``DOCUMENT_FIELDS``).
* ``state.active_doc_id`` — which buffer is currently mirrored into the
  live ``AppState`` fields.

Switching documents = capture the live fields into the outgoing buffer,
copy the incoming buffer's fields back onto the live state, then fire a
full UI refresh. The live ``AppState`` object identity never changes, so
the tab closures stay valid across switches *and* across WebSocket
reconnects (``documents`` lives on the persistent state, so it survives a
reconnect the same way the active well already does).

Documents are keyed by ``API|lateral`` (see :func:`document_id_for`), so
re-loading the same well from a different source (DB → APD → WCR) updates
the one buffer in place rather than spawning duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a runtime import cycle (state imports nothing from here)
    from etools.ui.state import AppState

# The per-well data fields on AppState. Everything NOT listed here is
# session infrastructure that must never be swapped when changing
# documents: the bound callbacks (``post_load`` / ``fire_refresh`` /
# ``viz_refresh``) and the workspace bookkeeping itself
# (``documents`` / ``active_doc_id``).
#
# Keep this in sync with AppState. The unit test
# ``test_document_fields_cover_appstate`` guards against drift.
DOCUMENT_FIELDS: tuple[str, ...] = (
    "headers",
    "primary",
    "surveys",
    "selected_citing",
    "processed",
    "clearances",
    "extra",
    "apd_data",
    "apd_pdf_path",
    "apd_pdf_name",
    "casing_survey_df",
    "casing_survey_label",
    "casing_overrides",
    "casing_frac_gradient_psi_per_ft",
    "bope_overrides",
    "casing_last_output_path",
    "section_definitions",
    "wcr_data",
    "wcr_pdf_path",
    "wcr_pdf_name",
    "wcr_survey_df",
    "wcr_survey_label",
    "wcr_survey_source",
)

# Fields that are managed by the workspace itself and must be excluded from
# any per-document snapshot, even though they live on AppState.
INFRA_FIELDS: frozenset[str] = frozenset(
    {"post_load", "fire_refresh", "viz_refresh", "documents", "active_doc_id"}
)


@dataclass(slots=True)
class WellDocument:
    """One open well buffer — a snapshot of the AppState data fields."""

    id: str
    label: str
    subtitle: str = ""
    source: str = ""  # where the well came from: "APD", "WCR", "APD+WCR", "DB"
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Identity / labelling
# ---------------------------------------------------------------------------
def document_id_for(api: str | None, lateral: str | None) -> str:
    """Stable buffer key for a well. ``API|lateral``, both normalised."""
    a = (api or "").strip() or "unknown"
    L = (lateral or "0000").strip() or "0000"
    return f"{a}|{L}"


def _label_for(state: "AppState") -> tuple[str, str, str]:
    """Return ``(doc_id, label, subtitle)`` derived from the live primary."""
    p = state.primary
    if p is None:
        return ("", "", "")
    doc_id = document_id_for(p.api, p.lateral)
    label = (p.well_name or p.api or "Unnamed well").strip()
    bits = [f"API {p.api}/{p.lateral}"]
    if p.citing_type:
        bits.append(p.citing_type)
    return (doc_id, label, " · ".join(bits))


def _source_for(state: "AppState") -> str:
    """Which document the well came from: APD permit, WCR Form 8, or the DB."""
    has_apd = getattr(state, "apd_data", None) is not None
    has_wcr = getattr(state, "wcr_data", None) is not None
    if has_apd and has_wcr:
        return "APD+WCR"
    if has_apd:
        return "APD"
    if has_wcr:
        return "WCR"
    return "DB"


# ---------------------------------------------------------------------------
# Capture / apply
# ---------------------------------------------------------------------------
def capture_document_data(state: "AppState") -> dict[str, Any]:
    """Snapshot the live per-well fields into a plain dict (by reference).

    No deep copy: each load mints fresh objects, and only one buffer is
    ever live at a time, so distinct documents never share a mutable
    object. The snapshot simply holds the current references so they can
    be restored verbatim later.
    """
    return {f: getattr(state, f) for f in DOCUMENT_FIELDS}


def apply_document_data(state: "AppState", data: dict[str, Any]) -> None:
    """Write a snapshot back onto the live AppState fields."""
    for f in DOCUMENT_FIELDS:
        if f in data:
            setattr(state, f, data[f])


def empty_document_data() -> dict[str, Any]:
    """A fresh snapshot equivalent to a brand-new, empty AppState.

    Constructs new container instances each call so two cleared buffers
    never alias the same list/dict.
    """
    from etools.ui.state import AppState

    fresh = AppState()
    return {f: getattr(fresh, f) for f in DOCUMENT_FIELDS}


# ---------------------------------------------------------------------------
# Workspace operations
# ---------------------------------------------------------------------------
def upsert_active_document(state: "AppState") -> str | None:
    """Create or update the buffer for the currently loaded well.

    Called at the tail of the post-load pipeline once every derived field
    (processed / clearances / section_definitions) is populated, so the
    snapshot is complete. Derives the buffer id + label from
    ``state.primary``; re-loading the same API/lateral updates the
    existing buffer in place (merge semantics). Returns the doc id, or
    ``None`` if there is no primary to key on.
    """
    doc_id, label, subtitle = _label_for(state)
    if not doc_id:
        return None
    doc = state.documents.get(doc_id)
    snapshot = capture_document_data(state)
    source = _source_for(state)
    if doc is None:
        state.documents[doc_id] = WellDocument(
            id=doc_id, label=label, subtitle=subtitle, source=source, data=snapshot
        )
    else:
        doc.label = label
        doc.subtitle = subtitle
        doc.source = source
        doc.data = snapshot
    state.active_doc_id = doc_id
    return doc_id


def switch_document(state: "AppState", new_id: str) -> bool:
    """Make ``new_id`` the active buffer. Caller fires the UI refresh.

    Captures the live fields back into the outgoing buffer first so any
    unsaved edits (casing knobs, segment overrides) are preserved, then
    copies the incoming buffer onto the live state. Returns ``True`` if a
    switch actually happened.
    """
    if new_id == state.active_doc_id:
        return False
    target = state.documents.get(new_id)
    if target is None:
        return False
    # Preserve edits made to the currently-active buffer.
    if state.active_doc_id is not None:
        cur = state.documents.get(state.active_doc_id)
        if cur is not None:
            cur.data = capture_document_data(state)
            cur.source = _source_for(state)
    apply_document_data(state, target.data)
    state.active_doc_id = new_id
    return True


def remove_document(state: "AppState", doc_id: str) -> str | None:
    """Close a buffer. If it was active, fall back to another (or empty).

    Returns the id of the buffer that is active afterwards (``None`` when
    no buffers remain — the live state is reset to empty in that case).
    Caller fires the UI refresh.
    """
    state.documents.pop(doc_id, None)
    if state.active_doc_id != doc_id:
        return state.active_doc_id
    # We closed the active buffer — pick the next one if any remain.
    nxt = next(iter(state.documents), None)
    if nxt is None:
        apply_document_data(state, empty_document_data())
        state.active_doc_id = None
        return None
    apply_document_data(state, state.documents[nxt].data)
    state.active_doc_id = nxt
    return nxt
