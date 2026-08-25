"""Keep a group of per-well AppState fields consistent with each other.

``post_load_orchestrate`` writes ``state.processed``, ``state.clearances``
and ``state.section_definitions`` in sequence. A failure part-way through
used to leave the *new* well's survey sitting next to the *previous* well's
clearances, with nothing on screen saying the display was a mixture -- and
every tab reads those fields independently, so different tabs could show
different wells at the same time.

Why clear rather than restore: the previous values describe a different
well, so putting them back would recreate exactly the mixture this exists to
prevent. An obviously-unloaded state is the honest outcome.

Why not stage the writes into a dict first: the orchestrator *reads* these
same fields at a dozen points between the writes (``app.py:194-291``), so
redirecting the writes would mean rewriting every read too. Clearing on
failure gives the same user-visible guarantee for a fraction of the risk.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from etools.logging_setup import get_logger

log = get_logger(__name__)


@contextmanager
def clear_group_on_failure(state: Any, fields: Sequence[str]) -> Iterator[None]:
    """Run a block; on any exception reset every named field to ``{}``.

    The exception always propagates -- callers keep their own handling.
    """
    try:
        yield
    except BaseException:
        log.warning("state.group_cleared_after_failure", fields=list(fields))
        for name in fields:
            setattr(state, name, {})
        raise
