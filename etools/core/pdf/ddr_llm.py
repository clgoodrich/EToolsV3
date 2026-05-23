"""LLM augmentation for a parsed DDR.

Two things the LLM does that rules can't:

    1. Generate a natural-language summary of the well's history — what
       phases ran, what went well, where time was lost.
    2. Catch typed events whose comment phrasing didn't match a regex
       (e.g. a cement job described without our exact keywords, a fish
       described in unusual terms, a formation pick called out
       mid-comment).

The LLM never gets the raw 100kB time log — we compress to one short line
per entry (timestamp, code2, depth, first 120 chars of comment) and only
include rows the rules layer didn't already categorize. That keeps the
prompt under ~30k tokens even for long completion DDRs.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from etools.core.llm import OllamaClient, extract_with_schema
from etools.logging_setup import get_logger
from etools.models import DDRKeyEvent, DDRRecord, DDRTimeLogEntry, KeyEventType

log = get_logger(__name__)


class LLMDDREvent(BaseModel):
    event_type: str = Field(
        description=(
            "One of: KOP, EOC, Landing, CasingRun, CementJob, FIT, "
            "FormationPick, PerforationGuns, FracStage, Plug, Fish, BHA, "
            "NPT, Other"
        )
    )
    md_ft: Optional[float] = None
    tvd_ft: Optional[float] = None
    description: str
    source_row: int = Field(description="The 0-based time-log row index this event came from")


class LLMDDRSummary(BaseModel):
    """Schema for the summary-only LLM call (tiny prompt, fast)."""

    summary: str = Field(
        description=(
            "2-4 sentence narrative of the well's drilling/completion: spud "
            "and TD dates, total days, key phases, casing strings, frac stage "
            "count, any major NPT or sidetracks."
        )
    )


class LLMDDRExtraction(BaseModel):
    """Schema for the combined summary+events call (legacy / smaller DDRs)."""

    summary: Optional[str] = None
    events: list[LLMDDREvent] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You are a petroleum-engineering assistant analysing Daily Drilling "
    "Reports (DDRs) from oil & gas well completion reports. You understand "
    "drilling, completion, and workover operations.\n\n"
    "Domain notes:\n"
    "  - MD = measured depth along the wellbore (ft); TVD = true vertical "
    "depth (ft).\n"
    "  - Comments use heavy abbreviations: F/ = from, T/ = to, W/ = with, "
    "TIH = trip in hole, TOOH/POOH = trip out of hole, BHA = bottom-hole "
    "assembly, RIH = run in hole, MD = measured depth, RPM = rotation, "
    "WOB = weight on bit, BPM = barrels per minute, PSI = pressure, "
    "PPG = pounds per gallon (mud weight), GPM = gallons per minute "
    "(circ rate), DLS = dogleg severity, FIT = formation integrity test, "
    "MIRU/RDMO = rig in / rig out, NU/ND = nipple up/down BOPs, "
    "KOP = kickoff point, EOC = end of curve, TD = total depth, "
    "TOC = top of cement, MWD = measure while drilling.\n"
    "  - Event types you can emit (use exactly these strings): KOP, EOC, "
    "Landing, CasingRun, CementJob, FIT, FormationPick, PerforationGuns, "
    "FracStage, Plug, Fish, BHA, NPT, Other.\n"
    "  - NPT (non-productive time) is anything tagged NPT in the ops "
    "category OR comments mentioning rig repair, weather delay, waiting "
    "on cement, waiting on orders, equipment failure.\n"
    "  - FormationPick = the driller noting which geological formation "
    "the bit just entered (e.g. \"DRILLED INTO MAHOGANY BENCH @ 4794\").\n\n"
    "Be conservative — only emit events you can identify confidently from "
    "the comments. Numeric fields must be numbers (no commas, no units in "
    "the value)."
)


def _compute_stats_block(record: DDRRecord) -> str:
    """Hand the LLM pre-computed totals so the summary doesn't fabricate numbers."""
    entries = record.entries
    if not entries:
        return "(no entries)"

    # Date range from the actual entries (more accurate than the header dates).
    first_ts = next((e.start_time for e in entries if e.start_time), None)
    last_ts = next((e.end_time for e in reversed(entries) if e.end_time), None)
    days = (last_ts - first_ts).days if first_ts and last_ts else None

    # Depth range.
    depths = [
        d for e in entries
        for d in (e.start_depth_ftkb, e.end_depth_ftkb)
        if d is not None
    ]
    min_depth = min(depths) if depths else None
    max_depth = max(depths) if depths else None

    # Productive vs non-productive time.
    pt_hours = sum(e.duration_hr or 0 for e in entries if e.ops_category == "PT")
    npt_hours = sum(e.duration_hr or 0 for e in entries if e.ops_category == "NPT")
    inactive_hours = sum(
        e.duration_hr or 0 for e in entries if e.ops_category == "INACTIVE"
    )

    # Event counts (already-tagged + their breakdown).
    event_counts: dict[str, int] = {}
    for ev in record.key_events:
        event_counts[ev.event_type] = event_counts.get(ev.event_type, 0) + 1

    parts = [
        f"  Date range: {first_ts.date() if first_ts else '?'} → "
        f"{last_ts.date() if last_ts else '?'}"
        + (f" ({days} days elapsed)" if days is not None else ""),
        f"  Depth range: "
        + (f"{min_depth:.0f} → {max_depth:.0f} ftKB" if depths else "n/a"),
        f"  Productive time: {pt_hours:.1f}h, "
        f"Non-productive (NPT): {npt_hours:.1f}h, "
        f"Inactive: {inactive_hours:.1f}h",
    ]
    if event_counts:
        ev_str = ", ".join(f"{k}={v}" for k, v in sorted(event_counts.items()))
        parts.append(f"  Rules-extracted events: {ev_str}")
    return "\n".join(parts)


def augment_ddr_with_llm(
    record: DDRRecord,
    *,
    client: OllamaClient | None = None,
    max_rows: int = 50,
    comment_chars: int = 100,
    do_events: bool = True,
) -> DDRRecord:
    """Add an LLM-generated summary and any missed events to ``record``.

    Two-call pipeline so prompts stay small enough for CPU inference:

    1. **Summary call** — sees only the pre-computed stats block. ~2 KB
       prompt, finishes in ~30-60 s.
    2. **Event-mining call** (optional, gated on ``do_events``) — sees
       a small sample of FREE rows (uncategorized by rules). Skipped
       when the rules layer already produced a healthy event list.
    """
    cli = client or OllamaClient()
    if not cli.health() or not cli.has_model():
        log.info("ddr.llm.skip", reason="ollama unavailable or model missing")
        return record

    # ---- Step 1: SUMMARY ----
    summary = _llm_summary(record, cli)
    if summary:
        record.summary = summary.strip()

    # ---- Step 2: EVENT MINING (optional) ----
    if do_events:
        added = _llm_event_mining(
            record, cli, max_rows=max_rows, comment_chars=comment_chars
        )
    else:
        added = 0

    log.info(
        "ddr.llm.augmented",
        job=record.job_category,
        new_events=added,
        has_summary=bool(record.summary),
    )
    return record


def _llm_summary(record: DDRRecord, cli: OllamaClient) -> str | None:
    """Tiny prompt — stats only. Reliable on CPU."""
    stats = _compute_stats_block(record)
    prompt = (
        f"Daily Drilling Report — well summary task.\n\n"
        f"Job: {record.job_category or 'Unknown'}\n"
        f"Well: {record.well_name or 'unknown'} (API {record.api or 'unknown'})\n\n"
        "Statistics from the time log (these are accurate, use them):\n"
        f"{stats}\n\n"
        "Write a 2-4 sentence summary suitable for briefing a petroleum "
        "engineer. Cover:\n"
        "  - Spud date and TD date if visible\n"
        "  - Total elapsed days\n"
        "  - Depth interval drilled (or completion-interval covered)\n"
        "  - Productive vs non-productive split\n"
        "  - Headline events from the rules-tagged list (e.g. how many "
        "frac stages, casing runs, NPT events of note)\n"
        "Be specific with numbers. Do NOT invent values that aren't in the "
        "stats block above."
    )
    try:
        result = extract_with_schema(
            prompt, LLMDDRSummary, client=cli, system=_SYSTEM_PROMPT
        )
        return result.summary
    except Exception as exc:
        log.warning("ddr.llm.summary_failed", error=str(exc))
        return None


def _llm_event_mining(
    record: DDRRecord, cli: OllamaClient, *, max_rows: int, comment_chars: int
) -> int:
    """Look for events in FREE rows the rules missed. Returns count added."""
    already_tagged = {e.source_index for e in record.key_events}
    free_candidates = [
        e for e in record.entries
        if (e.comment or "").strip() and e.index not in already_tagged
    ]
    if not free_candidates:
        return 0
    # Sample to fit the prompt — head + tail + middle slice.
    if len(free_candidates) > max_rows:
        head = free_candidates[:max_rows // 2]
        tail = free_candidates[-(max_rows // 2):]
        free_candidates = sorted(head + tail, key=lambda e: e.index)
    compressed = []
    for e in free_candidates:
        ts = e.start_time.strftime("%m-%d %H:%M") if e.start_time else "?"
        depth = f"{e.start_depth_ftkb:.0f}" if e.start_depth_ftkb else "—"
        compressed.append(
            f"[{e.index:>4}] {ts} {(e.code2 or '—'):<8} {depth:>6}  "
            f"{(e.comment or '')[:comment_chars]}"
        )
    prompt = (
        f"DDR event-mining task for {record.well_name or 'unknown'}.\n\n"
        f"These are uncategorized time-log entries. Identify any that "
        f"contain real operational events (formation picks, screen-outs, "
        f"BHA failures, mud losses, kicks, plugs set/drilled).\n\n"
        f"Format: [row_index] timestamp code depth comment\n\n"
        + "\n".join(compressed)
        + "\n\nFor each event you can identify with confidence, emit an "
        "entry with event_type, source_row (the bracketed index), and a "
        "one-sentence description. Skip anything ambiguous."
    )
    try:
        result = extract_with_schema(
            prompt, LLMDDRExtraction, client=cli, system=_SYSTEM_PROMPT
        )
    except Exception as exc:
        log.warning("ddr.llm.events_failed", error=str(exc))
        return 0

    added = 0
    valid_types = set(KeyEventType.__args__)  # type: ignore[attr-defined]
    for ev in result.events or []:
        etype = ev.event_type if ev.event_type in valid_types else "Other"
        if any(
            x.source_index == ev.source_row and x.event_type == etype
            for x in record.key_events
        ):
            continue
        record.key_events.append(
            DDRKeyEvent(
                event_type=etype,  # type: ignore[arg-type]
                md_ft=ev.md_ft,
                tvd_ft=ev.tvd_ft,
                description=ev.description,
                source_index=ev.source_row,
                confidence=0.7,
            )
        )
        added += 1
    return added


