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

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from pydantic import BaseModel, Field

from etools.config import settings
from etools.core.llm import OllamaClient, extract_with_schema
from etools.logging_setup import get_logger
from etools.models import DDRKeyEvent, DDRRecord, KeyEventType

log = get_logger(__name__)

# The translation prompts fit comfortably in 8k context; a tighter KV
# cache is faster on CPU and lets Ollama batch parallel requests.
_NARRATIVE_NUM_CTX = 8192


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


class LLMEntryTranslation(BaseModel):
    """One row's telegram-terse plain-English translation."""

    row: int = Field(description="The bracketed [row] index being translated")
    text: str = Field(
        description=(
            "Caveman-terse plain English: short fragments, no filler "
            "words, every abbreviation expanded, every number kept."
        )
    )


class LLMDDRTranslations(BaseModel):
    """Schema for one chunk of per-row translations."""

    items: list[LLMEntryTranslation] = Field(default_factory=list)


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
    "TOC = top of cement, MWD = measure while drilling, "
    "HSM = held safety meeting, JSA = job safety analysis, "
    "SWI/WSI = shut well in, SDFN/SDFD = shut down for night/day, "
    "LD = lay down, PU = pick up, CBL = cement bond log, "
    "SICP = shut-in casing pressure, SITP = shut-in tubing pressure, "
    "ISIP = instantaneous shut-in pressure, DV tool = cement stage tool, "
    "RBP = retrievable bridge plug, TAC = tubing anchor catcher, "
    "SPF = shots per foot (perforating), WHP = wellhead pressure.\n"
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
    ]
    if depths:
        parts.append(f"  Depth range: {min_depth:.0f} → {max_depth:.0f} ftKB")
    if pt_hours or npt_hours or inactive_hours:
        parts.append(
            f"  Productive time: {pt_hours:.1f}h, "
            f"Non-productive (NPT): {npt_hours:.1f}h, "
            f"Inactive: {inactive_hours:.1f}h"
        )
    if event_counts:
        ev_str = ", ".join(f"{k}={v}" for k, v in sorted(event_counts.items()))
        parts.append(f"  Rules-extracted events: {ev_str}")

    # Daily-block / report-row DDRs have no PT/NPT or depth columns, so
    # the numbers above are mostly empty — hand the LLM the per-period
    # headlines instead so the summary has something concrete to say.
    if not depths and pt_hours == 0 and npt_hours == 0:
        headlines = [
            f"    {e.start_time.date() if e.start_time else '?'}: "
            f"{(e.phase or (e.comment or '')[:80]).strip()}"
            for e in entries[:20]
            if e.phase or e.comment
        ]
        if headlines:
            parts.append("  Report-period headlines:\n" + "\n".join(headlines))
    return "\n".join(parts)


def augment_ddr_with_llm(
    record: DDRRecord,
    *,
    client: OllamaClient | None = None,
    max_rows: int = 50,
    comment_chars: int = 100,
    do_events: bool = True,
    do_narrative: bool = False,
    progress: Callable[[str, float | None], None] | None = None,
) -> DDRRecord:
    """Add an LLM-generated summary and any missed events to ``record``.

    Pipeline of small calls so prompts stay manageable for CPU inference:

    1. **Summary call** — sees only the pre-computed stats block. ~2 KB
       prompt, finishes in ~30-60 s.
    2. **Event-mining call** (optional, gated on ``do_events``) — sees
       a small sample of FREE rows (uncategorized by rules). Skipped
       when the rules layer already produced a healthy event list.
    3. **Narrative pass** (optional, gated on ``do_narrative``) — walks
       the ENTIRE time log in chunks and writes a day-by-day plain-English
       retelling. One LLM call per ~30 entries, so this is by far the
       slowest step (minutes per DDR on CPU).
    """
    cli = client or OllamaClient()
    if not cli.health() or not cli.has_model():
        log.info("ddr.llm.skip", reason="ollama unavailable or model missing")
        return record

    def _p(text: str, frac: float | None = None) -> None:
        if progress is not None:
            progress(text, frac)

    # ---- Step 1: SUMMARY ----
    _p("writing summary…", 0.0)
    summary = _llm_summary(record, cli)
    if summary:
        record.summary = summary.strip()

    # ---- Step 2: EVENT MINING (optional) ----
    if do_events:
        _p("mining events…", None)
        added = _llm_event_mining(
            record, cli, max_rows=max_rows, comment_chars=comment_chars
        )
    else:
        added = 0

    # ---- Step 3: FULL PLAIN-ENGLISH NARRATIVE (optional) ----
    if do_narrative:
        narrative = _llm_narrative(record, cli, progress=_p)
        if narrative:
            record.narrative = narrative

    log.info(
        "ddr.llm.augmented",
        job=record.job_category,
        new_events=added,
        has_summary=bool(record.summary),
        has_narrative=bool(record.narrative),
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


def _narrative_line(e, comment_chars: int = 240) -> str:
    """One compressed time-log row for the narrative prompt."""
    ts = e.start_time.strftime("%m-%d %H:%M") if e.start_time else "?"
    dur = f"{e.duration_hr:g}h" if e.duration_hr is not None else "?"
    op = e.code2 or e.code1 or e.phase or "—"
    if e.start_depth_ftkb is not None and e.end_depth_ftkb is not None:
        depth = f"{e.start_depth_ftkb:.0f}->{e.end_depth_ftkb:.0f}ft"
    elif e.start_depth_ftkb is not None:
        depth = f"@{e.start_depth_ftkb:.0f}ft"
    else:
        depth = ""
    cat = e.ops_category or ""
    comment = (e.comment or "").replace("\n", " ").strip()[:comment_chars]
    return f"[{e.index}] {ts} ({dur}) {op} {depth} {cat}: {comment}"


def _chunk_entries(
    entries: list, *, max_entries: int, char_budget: int, comment_chars: int
) -> list[list]:
    """Greedy-pack entries into prompt-sized chunks.

    Columnar time logs pack ~30 short rows per chunk; daily-block DDRs
    carry multi-kilobyte comments, so the character budget kicks in and
    a chunk may hold only one or two entries. Both caps keep each prompt
    inside the client's context window and each response inside its
    output-token cap.
    """
    chunks: list[list] = []
    cur: list = []
    cur_chars = 0
    for e in entries:
        n = len(_narrative_line(e, comment_chars))
        if cur and (len(cur) >= max_entries or cur_chars + n > char_budget):
            chunks.append(cur)
            cur, cur_chars = [], 0
        cur.append(e)
        cur_chars += n
    if cur:
        chunks.append(cur)
    return chunks


def _llm_narrative(
    record: DDRRecord,
    cli: OllamaClient,
    *,
    max_entries_per_chunk: int = 30,
    chunk_char_budget: int = 4500,
    comment_chars: int = 4000,
    progress: Callable[[str, float | None], None] | None = None,
) -> str | None:
    """Telegram-terse plain-English translation of the WHOLE time log.

    Every entry gets its own translation, written back onto
    ``entry.plain_english`` so the UI can show it next to the original
    log text. The log is fed to the LLM in budget-packed chunks so each
    prompt stays small and each response fits the client's output-token
    cap (the budget is sized so even verbatim-length translations fit);
    a chunk whose response fails validation is split in half and
    retried. Returns the stitched dated lines (also stored as
    ``record.narrative``).
    """
    entries = [
        e
        for e in record.entries
        if (e.comment or "").strip() or e.code2 or e.code1 or e.phase
    ]
    if not entries:
        return None

    chunks = _chunk_entries(
        entries,
        max_entries=max_entries_per_chunk,
        char_budget=chunk_char_budget,
        comment_chars=comment_chars,
    )
    by_index = {e.index: e for e in entries}

    # Bulk translation is a mechanical task — use the configured smaller
    # model when it's actually pulled (~3x faster on CPU than the 9b).
    model: str | None = None
    if settings.llm.fast_model:
        if cli.has_model(settings.llm.fast_model):
            model = settings.llm.fast_model
            # Load it now so the first chunk doesn't pay the cold start
            # (measured: a cold first call can blow its read timeout).
            if progress is not None:
                progress(f"loading {model}…", None)
            if not cli.warm(model):
                model = None
        else:
            log.info(
                "ddr.llm.fast_model_missing",
                fast_model=settings.llm.fast_model,
                fallback=cli.model,
            )

    # Chunks are independent (each writes to its own entries), so run a few
    # concurrently — Ollama batches simultaneous generations, which buys
    # ~1.35x wall-clock at 2 streams even on CPU.
    workers = max(1, settings.llm.parallel_requests)
    total = len(chunks)
    done_lock = threading.Lock()
    done = {"n": 0}
    if progress is not None:
        progress(f"translating log 0/{total}…", 0.0)

    def _run(chunk: list) -> None:
        translated = _translate_chunk(
            record, chunk, cli, comment_chars, by_index, model=model
        )
        with done_lock:
            done["n"] += 1
            k = done["n"]
        log.info(
            "ddr.llm.narrative_chunk",
            job=record.job_category,
            chunk=f"{k}/{total}",
            translated=f"{translated}/{len(chunk)}",
            model=model or cli.model,
        )
        if progress is not None:
            progress(f"translating log {k}/{total}…", k / total)

    if workers == 1 or total == 1:
        for chunk in chunks:
            _run(chunk)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_run, chunks))

    # Stitched fallback text (export / non-side-by-side consumers).
    pieces = [
        f"**{e.start_time.strftime('%m-%d') if e.start_time else '?'}:** {e.plain_english}"
        for e in entries
        if e.plain_english
    ]
    return "\n\n".join(pieces).strip() or None


def _translate_chunk(
    record: DDRRecord,
    chunk: list,
    cli: OllamaClient,
    comment_chars: int,
    by_index: dict,
    model: str | None = None,
) -> int:
    """Translate one chunk; on failure split in half and retry.

    The usual failure mode is the model's JSON getting truncated by the
    output-token cap — halving the chunk halves the response. A single
    entry that still fails is left untranslated. Returns the number of
    entries translated.
    """
    lines = "\n".join(_narrative_line(e, comment_chars) for e in chunk)
    prompt = (
        f"Translation task — {record.job_category or 'DDR'} job on "
        f"{record.well_name or 'unknown well'}.\n\n"
        "Below is a slice of the rig's time log, one line per entry:\n"
        "  [row] timestamp (duration) operation-code depth-range PT/NPT: comment\n\n"
        f"{lines}\n\n"
        "Translate EVERY row into caveman-simple plain English — one "
        "item per [row] index. The reader knows NOTHING about drilling: "
        "if a single abbreviation or oilfield term survives untranslated, "
        "the translation has failed. Style rules:\n"
        "  - Telegram-terse fragments. No filler ('the crew proceeded "
        "to', 'in order to', 'subsequently').\n"
        "  - Expand EVERY abbreviation into simple words. Examples:\n"
        "      'TOOH F/ 8200 T/ SURF W/ BHA. NU BOP. SDFN.'\n"
        "      -> 'Pulled pipe out of hole, 8200 ft to surface, with "
        "bottom-hole tool assembly. Bolted up blowout preventer. Shut "
        "down for night.'\n"
        "      'RIH w/ CBL tools. LD 180 jts 2 7/8\" J-55 tbg.'\n"
        "      -> 'Ran cement-quality logging tools into hole. Laid "
        "down 180 joints of 2 7/8 inch steel tubing.'\n"
        "      'MIRU. SWI. RDMO.' -> 'Moved in and set up rig. Shut "
        "well in. Took down rig and moved off.'\n"
        "    Never leave these as-is: TIH/TOOH/RIH/POOH, jts, tbg, csg, "
        "BHA, BOP, CBL, WH, SICP/SITP, MIRU/RDMO, HSM/JSA, SWI, SDFN, "
        "C/O, F/, T/, W/.\n"
        "  - Keep EVERY number, written as digits with its unit "
        "(8200 ft, 600 psi, 2 7/8\" tubing) — never spell numbers out "
        "in words.\n"
        "  - Normal sentences: capital letter at the start, period at "
        "the end of each fragment.\n"
        "  - Cover everything in the row — long rows get longer "
        "translations, never dropped detail.\n"
        "  - Say problems and lost time bluntly ('swivel broke, lost "
        "4 hours').\n"
        "  - Do NOT invent anything not in the row."
    )
    try:
        result = extract_with_schema(
            prompt,
            LLMDDRTranslations,
            client=cli,
            system=_SYSTEM_PROMPT,
            model=model,
            num_ctx=_NARRATIVE_NUM_CTX,
        )
    except Exception as exc:
        if len(chunk) > 1:
            mid = len(chunk) // 2
            log.info("ddr.llm.narrative_split", size=len(chunk), error=str(exc)[:120])
            return _translate_chunk(
                record, chunk[:mid], cli, comment_chars, by_index, model=model
            ) + _translate_chunk(
                record, chunk[mid:], cli, comment_chars, by_index, model=model
            )
        log.warning(
            "ddr.llm.narrative_entry_failed",
            row=chunk[0].index,
            error=str(exc)[:200],
        )
        return 0
    translated = 0
    for item in result.items:
        e = by_index.get(item.row)
        text = (item.text or "").strip()
        if e is not None and text:
            e.plain_english = text
            translated += 1
    return translated


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


