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
from etools.models import DDRKeyEvent, DDRRecord, KeyEventType

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


class LLMDDRExtraction(BaseModel):
    summary: Optional[str] = Field(
        None,
        description=(
            "2-4 sentence narrative of the well's drilling/completion: spud "
            "and TD dates, total days, key phases, any major NPT or sidetracks."
        ),
    )
    events: list[LLMDDREvent] = Field(
        default_factory=list,
        description="Additional events the regex layer didn't catch.",
    )


_SYSTEM_PROMPT = (
    "You are a petroleum-engineering assistant analysing a Daily Drilling "
    "Report (DDR) extracted from a well completion report. You produce a "
    "concise summary of the well's history and identify any operational "
    "events that haven't already been tagged. Be conservative — only emit "
    "events you can identify confidently from the comments."
)


def augment_ddr_with_llm(
    record: DDRRecord,
    *,
    client: OllamaClient | None = None,
    max_rows: int = 200,
) -> DDRRecord:
    """Add an LLM-generated summary and any missed events to ``record``.

    Mutates the input record and returns it. If Ollama is unreachable or
    the model isn't pulled, this is a no-op.
    """
    cli = client or OllamaClient()
    if not cli.health() or not cli.has_model():
        log.info("ddr.llm.skip", reason="ollama unavailable or model missing")
        return record

    # Compress the time log so the prompt fits.
    already_tagged = {e.source_index for e in record.key_events}
    compressed_lines: list[str] = []
    for entry in record.entries:
        comment = (entry.comment or "").strip()
        if not comment:
            continue
        tag = "TAGGED" if entry.index in already_tagged else "FREE"
        ts = entry.start_time.strftime("%Y-%m-%d %H:%M") if entry.start_time else "?"
        depth = (
            f"{entry.start_depth_ftkb:.0f}" if entry.start_depth_ftkb else "—"
        )
        code = entry.code2 or "—"
        compressed_lines.append(
            f"[{entry.index:>4}|{tag}] {ts} {code:<8} {depth:>6}  "
            f"{comment[:160]}"
        )
        if len(compressed_lines) >= max_rows:
            break

    prompt = (
        f"DDR Job: {record.job_category or 'Unknown'}\n"
        f"Well: {record.well_name or 'unknown'} (API {record.api or 'unknown'})\n"
        f"Date range: {record.start_date} → {record.end_date}\n"
        f"Total rows in log: {len(record.entries)}, "
        f"rows shown below: {len(compressed_lines)}\n"
        f"Rows already tagged by regex: {len(already_tagged)}\n\n"
        "Each line below is one time-log entry. Format:\n"
        "  [index|TAGGED|FREE] timestamp code depth comment\n"
        "FREE rows have not been categorized yet — those are the ones to look "
        "at for additional events. TAGGED rows are context.\n\n"
        "Time log:\n"
        + "\n".join(compressed_lines)
        + "\n\nReturn:\n"
        "  - A 2-4 sentence `summary` covering when the well spud, when TD was "
        "reached, how many days drilling and completion took, and any notable "
        "NPT, sidetracks, fishing, or completion issues.\n"
        "  - An `events` list of any operational events you can identify in "
        "the FREE rows. Use the `source_row` index from the bracketed prefix. "
        "Skip anything ambiguous — better to under-emit than to hallucinate."
    )

    try:
        result = extract_with_schema(
            prompt, LLMDDRExtraction, client=cli, system=_SYSTEM_PROMPT
        )
    except Exception as exc:
        log.warning("ddr.llm.failed", error=str(exc))
        return record

    if result.summary:
        record.summary = result.summary.strip()
    added = 0
    valid_types = set(KeyEventType.__args__)  # type: ignore[attr-defined]
    for ev in result.events:
        etype = ev.event_type
        if etype not in valid_types:
            etype = "Other"
        # Don't double-emit something the rules already caught for this row.
        if any(
            existing.source_index == ev.source_row and existing.event_type == etype
            for existing in record.key_events
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
    log.info(
        "ddr.llm.augmented",
        job=record.job_category,
        new_events=added,
        has_summary=bool(record.summary),
    )
    return record
