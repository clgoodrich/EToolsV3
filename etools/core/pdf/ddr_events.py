"""Extract typed DDRKeyEvents from a DDRRecord's time log.

The operator's daily comments hold ground-truth events the rest of the
WCR only hints at — explicit KOP/EOC MDs, casing-run dates, cement-job
sacks, FIT pressures, perforation depths, frac-stage rates, NPT
descriptions. Each event we recognise gets a strongly-typed
``DDRKeyEvent`` with the MD/TVD/timestamp/source-row breadcrumb so
downstream consumers (WCR pipeline, UI) can prefer the driller's
reported value over heuristic detection.

Rules-only — the LLM categorization layer adds the events these heuristics
miss (see ``ddr_llm_events.py``).
"""

from __future__ import annotations

import re

from etools.logging_setup import get_logger
from etools.models import DDRKeyEvent, DDRRecord, DDRTimeLogEntry

log = get_logger(__name__)


def extract_events(record: DDRRecord) -> list[DDRKeyEvent]:
    """Walk the record's entries and produce typed key events.

    Also stamps ``entry.trouble`` on every entry as a side effect, so
    problem flags are available wherever the record travels (UI, exports).
    """
    events: list[DDRKeyEvent] = []
    for entry in record.entries:
        entry.trouble = detect_trouble(entry)
        for ev in _events_from_entry(entry):
            events.append(ev)
    # De-duplicate. For events with an MD, dedup on (type, md). For events
    # without MD (FracStage, NPT, BHA, Fish, …), dedup on (type, stage|src_index)
    # so repeated stages are preserved.
    seen: set = set()
    unique: list[DDRKeyEvent] = []
    for e in events:
        if e.md_ft is not None:
            key = (e.event_type, round(e.md_ft, 1))
        else:
            stage = e.extra.get("stage") if e.extra else None
            key = (e.event_type, stage if stage is not None else e.source_index)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    log.info(
        "ddr.events.extracted",
        job=record.job_category,
        rows=len(record.entries),
        events=len(unique),
    )
    return unique


# ---------------------------------------------------------------------------
# Trouble detection — "what went wrong" flags
# ---------------------------------------------------------------------------
#
# Rules-based scan of the comment text for operational problems. Unlike
# the typed extractors below, this works on every appendix layout —
# daily-block and report-row DDRs have no PT/NPT column or code2 tags,
# so the comment text is the only signal.

_TROUBLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "stuck pipe": re.compile(
        r"\bstuck\b|\bdifferential(?:ly)?\s+st[iu]ck|\bwork(?:ing|ed)?\s+(?:pipe|string|tools?)\s+free"
        r"|\bjarring\b|\bjar(?:red)?\s+(?:on|free|loose)\b",
        re.I,
    ),
    "fishing": re.compile(
        r"\bfish(?:ing)?\b|\bovershot\b|\bjunk\s+basket\b|\bleft\s+in\s+hole\b",
        re.I,
    ),
    "twist-off / parted": re.compile(
        r"\btwist(?:ed)?\s*off\b|\bparted\b|\bback(?:ed)?\s*off\b",
        re.I,
    ),
    "bit problem": re.compile(
        r"\blost\s+(?:a\s+)?cone\b|\bbit\s+fail(?:ed|ure)?\b|\bbroke(?:n)?\s+bit\b"
        r"|\bbit\s+balled\b|\br[iu]ng(?:ed)?\s*out\b|\bdull(?:ed)?\s+bit\b",
        re.I,
    ),
    "equipment failure": re.compile(
        r"\bfail(?:ed|ure)\b|\bbroke(?:n)?\b(?!\s*down\s+(?:pressure|of))|\brepair(?:ed|ing|s)?\b"
        r"|\bmalfunction\w*\b|\blos(?:ing|t)\s+torque\b|\bdid\s+not\s+(?:stroke|set|fire|test)\b"
        r"|\bwould\s+not\b|\bnot\s+functioning\b|\bre-?set\s+(?:the\s+)?plug\b",
        re.I,
    ),
    "leak": re.compile(r"\bleak(?:s|ed|ing)?\b", re.I),
    "washout": re.compile(r"\bwash(?:ed)?\s*out\b", re.I),
    # NB: a bare "LCM" mention is routine (preventive sweeps/pills every N
    # strokes) — only actual loss events flag.
    "lost circulation": re.compile(
        r"\b(?:lost|losing)\s+(?:\d{1,3}%\s+)?(?:full\s+|partial\s+|total\s+)?"
        r"(?:circulation|returns)\b"
        r"|\bloss(?:es)?\s+of\s+returns\b|\bmud\s+loss(?:es)?\b|\btaking\s+losses\b",
        re.I,
    ),
    "well control": re.compile(
        r"\b(?:took|taking)\s+a\s+kick\b|\bgas\s+kick\b|\bwell\s+control\b"
        r"|\bflow\s+check\s+positive\b|\bsurging\b|\bkill\s+(?:plug|well|fluid)\b"
        r"|\bkilled\s+(?:the\s+)?well\b|\bh2s\s+(?:detected|present|alarm)\b",
        re.I,
    ),
    "screen-out": re.compile(r"\bscreen(?:ed)?[-\s]?out\b|\bsand(?:ed)?\s+off\b", re.I),
    "waiting": re.compile(
        r"\bwait(?:ing)?\s+on\s+(?:weather|orders|parts|repairs?|equipment|daylight)\b|\bwow\b",
        re.I,
    ),
}

# A match doesn't count when it's negated just before ("no leaks",
# "none detected", "without losses").
_NEGATION_RE = re.compile(r"\b(?:no|none|without|w/o|never)\b[^.;:!\n]{0,16}$", re.I)


def detect_trouble(entry: DDRTimeLogEntry) -> list[str]:
    """Return the problem categories present in this entry (rules-only)."""
    text = " ".join(
        x for x in (entry.phase, entry.code1, entry.comment) if x
    )
    flags: list[str] = []
    if entry.ops_category == "NPT":
        flags.append("NPT")
    if not text:
        return flags
    for label, pat in _TROUBLE_PATTERNS.items():
        for m in pat.finditer(text):
            if _NEGATION_RE.search(text[: m.start()]):
                continue  # negated — keep looking for a real one
            flags.append(label)
            break
    return flags


def trouble_excerpt(entry: DDRTimeLogEntry, width: int = 90) -> str:
    """A short comment excerpt around the first trouble match, for display."""
    text = entry.comment or entry.phase or ""
    first: int | None = None
    for label in entry.trouble:
        pat = _TROUBLE_PATTERNS.get(label)
        if pat is None:
            continue
        for m in pat.finditer(text):
            if _NEGATION_RE.search(text[: m.start()]):
                continue
            if first is None or m.start() < first:
                first = m.start()
            break
    if first is None:
        return text[: width * 2].strip()
    lo = max(0, first - width)
    hi = min(len(text), first + width)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return ("…" if lo > 0 else "") + snippet + ("…" if hi < len(text) else "")


# ---------------------------------------------------------------------------
# Per-entry dispatcher
# ---------------------------------------------------------------------------


def _events_from_entry(entry: DDRTimeLogEntry):
    comment = (entry.comment or "").upper()
    if not comment:
        return
    for fn in _EXTRACTORS:
        yield from fn(entry, comment)


# ---------------------------------------------------------------------------
# KOP — "ORIENT TOOL FACE T/ <azi>° AZM DRILLED CURVE. SLIDE DRILL F/<md>"
# Or: "BEGIN BUILDING ANGLE @ <md>"
# Or: phase change Vertical → Curve at this row's start_depth_ftkb
# ---------------------------------------------------------------------------


_KOP_PHRASES = (
    re.compile(r"ORIENT\s+TOOL\s+FACE.*?\bSLIDE\s+DRILL\s+F/\s*(\d{2,5}(?:,\d{3})*)", re.S),
    re.compile(r"\bKICKOFF\s*@\s*(\d{2,5}(?:,\d{3})*)", re.I),
    re.compile(r"\bKOP\s*@?\s*(\d{2,5}(?:,\d{3})*)", re.I),
    re.compile(r"\bBUILD(?:ING)?\s+CURVE\s*F/\s*(\d{2,5}(?:,\d{3})*)", re.I),
)


def _extract_kop(entry: DDRTimeLogEntry, c: str):
    for pat in _KOP_PHRASES:
        m = pat.search(c)
        if m:
            md = _to_float(m.group(1))
            if md and 100 < md < 30000:
                yield DDRKeyEvent(
                    event_type="KOP",
                    md_ft=md,
                    timestamp=entry.start_time,
                    description=f"Kickoff @ MD {md:.0f} (operator note)",
                    source_index=entry.index,
                    confidence=1.0,
                )
                return
    # Phase-change fallback: first row whose phase contains "Drill Curve"
    if entry.phase and "DRILL CURVE" in entry.phase.upper() and entry.start_depth_ftkb:
        yield DDRKeyEvent(
            event_type="KOP",
            md_ft=entry.start_depth_ftkb,
            timestamp=entry.start_time,
            description=f"Kickoff @ MD {entry.start_depth_ftkb:.0f} (phase change to curve)",
            source_index=entry.index,
            confidence=0.7,
        )


# ---------------------------------------------------------------------------
# EOC — "EOC <md>' MD <inc>° INC <tvd>' TVD <vs> VS."
# ---------------------------------------------------------------------------


_EOC_RE = re.compile(
    r"\bEOC\s+(\d{2,5}(?:,\d{3})*)\'?\s*MD\s+([\d.]+)°?\s*INC\s+(\d{2,5}(?:,\d{3})*)\'?\s*TVD",
    re.I,
)


def _extract_eoc(entry: DDRTimeLogEntry, c: str):
    m = _EOC_RE.search(c)
    if not m:
        return
    md = _to_float(m.group(1))
    tvd = _to_float(m.group(3))
    inc = _to_float(m.group(2))
    yield DDRKeyEvent(
        event_type="EOC",
        md_ft=md,
        tvd_ft=tvd,
        timestamp=entry.start_time,
        description=f"End-of-curve @ MD {md:.0f} ({inc:.1f}° inc, TVD {tvd:.0f})",
        source_index=entry.index,
        confidence=1.0,
        extra={"inclination_deg": inc},
    )


# ---------------------------------------------------------------------------
# Landing — "LANDED @ <md>" or "PTB <bur>° BRN T/ LAND <inc>°" style notes
# ---------------------------------------------------------------------------


_LAND_PHRASES = (
    re.compile(r"\bLAND(?:ED|ING)?\s+(?:CSG|CASING|LINER|F/S)\s*@\s*(\d{2,5}(?:,\d{3})*)", re.I),
    re.compile(r"\bLANDED\s*@\s*(\d{2,5}(?:,\d{3})*)", re.I),
)


def _extract_landing(entry: DDRTimeLogEntry, c: str):
    for pat in _LAND_PHRASES:
        m = pat.search(c)
        if m:
            md = _to_float(m.group(1))
            if md and 100 < md < 30000:
                yield DDRKeyEvent(
                    event_type="Landing",
                    md_ft=md,
                    timestamp=entry.start_time,
                    description=f"Landed @ MD {md:.0f}",
                    source_index=entry.index,
                    confidence=1.0,
                )
                return


# ---------------------------------------------------------------------------
# Casing run — phase code RUNCAS with shoe / float / collar depths
# ---------------------------------------------------------------------------


_CSG_SHOE_RE = re.compile(
    r"(?:CASING|CSG)\s+(?:LANDED|TO|@)\s*(\d{2,5}(?:,\d{3})*)\'?", re.I
)
_FLOAT_SHOE_RE = re.compile(
    r"(?:FLOAT|SHOE|F\.E\.\s*CMT)\s*@\s*(\d{2,5}(?:,\d{3})*)", re.I
)


def _extract_casing_run(entry: DDRTimeLogEntry, c: str):
    if entry.code2 not in {"RUNCAS"}:
        return
    # Pull every depth referenced in the comment — shoe / float / collar.
    depths = []
    for pat in (_CSG_SHOE_RE, _FLOAT_SHOE_RE, re.compile(r"@\s*(\d{2,5}(?:,\d{3})*)\'", re.I)):
        for m in pat.finditer(c):
            d = _to_float(m.group(1))
            if d and 100 < d < 30000:
                depths.append(d)
    if not depths:
        return
    deepest = max(depths)
    yield DDRKeyEvent(
        event_type="CasingRun",
        md_ft=deepest,
        timestamp=entry.start_time,
        description=f"Casing run, deepest depth {deepest:.0f} ft",
        source_index=entry.index,
        confidence=0.9,
        extra={"all_depths_ft": sorted(set(depths))},
    )


# ---------------------------------------------------------------------------
# Cement job — phase code PRIMCEM. Pull sacks/yield/weight per stage.
# ---------------------------------------------------------------------------


_CEMENT_LEAD_RE = re.compile(
    r"(\d{2,5})\s*SACKS.*?(\d+(?:\.\d+)?)\s*(?:PPG|LB)\s*LEAD",
    re.I | re.S,
)
_CEMENT_TAIL_RE = re.compile(
    r"(\d{2,5})\s*SACKS.*?(\d+(?:\.\d+)?)\s*(?:PPG|LB)\s*TAIL",
    re.I | re.S,
)


def _extract_cement_job(entry: DDRTimeLogEntry, c: str):
    if entry.code2 != "PRIMCEM":
        return
    lead = _CEMENT_LEAD_RE.search(c)
    tail = _CEMENT_TAIL_RE.search(c)
    bits = []
    extra: dict = {}
    if lead:
        extra["lead_sacks"] = int(lead.group(1))
        extra["lead_weight_ppg"] = float(lead.group(2))
        bits.append(f"{extra['lead_sacks']}sx lead @ {extra['lead_weight_ppg']:.1f} ppg")
    if tail:
        extra["tail_sacks"] = int(tail.group(1))
        extra["tail_weight_ppg"] = float(tail.group(2))
        bits.append(f"{extra['tail_sacks']}sx tail @ {extra['tail_weight_ppg']:.1f} ppg")
    yield DDRKeyEvent(
        event_type="CementJob",
        md_ft=entry.start_depth_ftkb,
        timestamp=entry.start_time,
        description="Primary cement job" + (" — " + "; ".join(bits) if bits else ""),
        source_index=entry.index,
        confidence=0.9 if bits else 0.6,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# FIT — "FIT TEST T/ <ppg> PPG MWE TVD <tvd>"
# ---------------------------------------------------------------------------


_FIT_RE = re.compile(
    r"FIT(?:\s+TEST)?\s+T/\s*(\d+(?:\.\d+)?)\s*(?:PPG|LB)\s*(?:MAMW|MWE|EMW)?\s*TVD\s+(\d{2,5}(?:,\d{3})*)",
    re.I,
)


def _extract_fit(entry: DDRTimeLogEntry, c: str):
    m = _FIT_RE.search(c)
    if not m:
        return
    ppg = float(m.group(1))
    tvd = _to_float(m.group(2))
    yield DDRKeyEvent(
        event_type="FIT",
        md_ft=entry.start_depth_ftkb,
        tvd_ft=tvd,
        timestamp=entry.start_time,
        description=f"FIT to {ppg:.1f} ppg @ TVD {tvd:.0f}",
        source_index=entry.index,
        confidence=1.0,
        extra={"test_emw_ppg": ppg},
    )


# ---------------------------------------------------------------------------
# Perforation guns — completion phase with "Plug Depth: X / Perf Depths: Y (Top) Z (Bottom)"
# ---------------------------------------------------------------------------


_PERF_RE = re.compile(
    r"Stage:\s*(\d+).*?Plug\s+Depth:\s*\"?([\d,]+)\'?\s*MD.*?Perf\s+Depths?:\s*([\d,]+)\'?\s*\(Top\)\s+([\d,]+)\'?\s*\(Bottom\)",
    re.I | re.S,
)


def _extract_perf_event(entry: DDRTimeLogEntry, c: str):
    if entry.code2 not in {"PFRT"}:
        return
    m = _PERF_RE.search(c)
    if not m:
        return
    stage = int(m.group(1))
    plug = _to_float(m.group(2))
    top = _to_float(m.group(3))
    bot = _to_float(m.group(4))
    yield DDRKeyEvent(
        event_type="PerforationGuns",
        md_ft=top,
        depth_top_ft=top,
        depth_bottom_ft=bot,
        timestamp=entry.start_time,
        description=f"Stage {stage} perfs {top:.0f}–{bot:.0f} (plug @ {plug:.0f})",
        source_index=entry.index,
        confidence=1.0,
        extra={"stage": stage, "plug_depth_ft": plug},
    )


# ---------------------------------------------------------------------------
# Frac stage — code2 == FRAC with Avg/Max RT, psi, BBL, sand totals.
# ---------------------------------------------------------------------------


# Each field is independent so a stage with one missing value still parses.
_FRAC_STAGE_RE = re.compile(r"Stage\s*(\d+)", re.I)
_FRAC_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "avg_rate_bpm": re.compile(r"Avg\s*RT\s*[-:]?\s*([\d.]+)\s*bpm", re.I),
    "max_rate_bpm": re.compile(r"Max\s*RT\s*[-:]?\s*([\d.]+)\s*bpm", re.I),
    "avg_psi": re.compile(r"Avg\s*psi\s*[-:]?\s*([\d,]+)", re.I),
    "max_psi": re.compile(r"Max\s*psi\s*[-:]?\s*([\d,]+)", re.I),
    "clean_bbl": re.compile(r"Clean\s*total\s*[-:]?\s*([\d,]+)\s*bbl", re.I),
    "slurry_bbl": re.compile(r"Slurry\s*total\s*[-:]?\s*([\d,]+)\s*bbl", re.I),
    "sand_lbs": re.compile(r"Total\s*sand\s*[-:]?\s*([\d,]+)\s*lbs", re.I),
    "open_well_psi": re.compile(r"O(?:W|pen\s*Well)\s*[:#]?\s*([\d,]+)\s*psi", re.I),
    "fg": re.compile(r"F\.?\s*G\.?\s*([\d.]+)", re.I),
}


def _extract_frac_stage(entry: DDRTimeLogEntry, c: str):
    if entry.code2 != "FRAC":
        return
    stage_match = _FRAC_STAGE_RE.search(c)
    extra: dict = {}
    if stage_match:
        extra["stage"] = int(stage_match.group(1))
    for field, pat in _FRAC_FIELD_PATTERNS.items():
        m = pat.search(c)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        try:
            extra[field] = float(raw) if "." in raw or field == "fg" else int(raw)
        except ValueError:
            continue
    if not extra:
        # Couldn't pull any structured fields — still emit a placeholder.
        yield DDRKeyEvent(
            event_type="FracStage",
            timestamp=entry.start_time,
            description=(entry.comment or "Frac stage (details not parsed)")[:160],
            source_index=entry.index,
            confidence=0.5,
        )
        return

    bits: list[str] = []
    if "stage" in extra:
        bits.append(f"Stage {extra['stage']}")
    if "avg_rate_bpm" in extra and "avg_psi" in extra:
        bits.append(f"avg {extra['avg_rate_bpm']:.0f} bpm @ {extra['avg_psi']:,} psi")
    if "sand_lbs" in extra:
        bits.append(f"{extra['sand_lbs']:,} lbs sand")
    if "clean_bbl" in extra:
        bits.append(f"{extra['clean_bbl']:,} bbl clean")
    if "fg" in extra:
        bits.append(f"FG {extra['fg']:.2f}")
    description = ", ".join(bits) or "Frac stage"
    yield DDRKeyEvent(
        event_type="FracStage",
        timestamp=entry.start_time,
        description=description,
        source_index=entry.index,
        confidence=0.95 if "stage" in extra else 0.7,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# NPT — any row tagged ops_category=NPT
# ---------------------------------------------------------------------------


def _extract_npt(entry: DDRTimeLogEntry, c: str):
    if entry.ops_category != "NPT":
        return
    yield DDRKeyEvent(
        event_type="NPT",
        md_ft=entry.start_depth_ftkb,
        timestamp=entry.start_time,
        description=(
            f"NPT {entry.duration_hr or 0:.1f}h — {entry.code1 or 'unspec'}: "
            f"{(entry.comment or '')[:120]}"
        ).strip(),
        source_index=entry.index,
        confidence=1.0,
        extra={"duration_hr": entry.duration_hr},
    )


# ---------------------------------------------------------------------------
# BHA changes — code2 == PULDSTR (pick up / lay down drill string)
# ---------------------------------------------------------------------------


def _extract_bha(entry: DDRTimeLogEntry, c: str):
    if entry.code2 != "PULDSTR":
        return
    yield DDRKeyEvent(
        event_type="BHA",
        md_ft=entry.start_depth_ftkb,
        timestamp=entry.start_time,
        description=f"BHA change @ {entry.start_depth_ftkb or 0:.0f}",
        source_index=entry.index,
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# Fishing — code2 == FISH
# ---------------------------------------------------------------------------


def _extract_fish(entry: DDRTimeLogEntry, c: str):
    if entry.code2 != "FISH":
        return
    yield DDRKeyEvent(
        event_type="Fish",
        md_ft=entry.start_depth_ftkb,
        timestamp=entry.start_time,
        description=f"Fishing op @ {entry.start_depth_ftkb or 0:.0f} — {(entry.comment or '')[:80]}",
        source_index=entry.index,
        confidence=1.0,
    )


_EXTRACTORS = (
    _extract_kop,
    _extract_eoc,
    _extract_landing,
    _extract_casing_run,
    _extract_cement_job,
    _extract_fit,
    _extract_perf_event,
    _extract_frac_stage,
    _extract_npt,
    _extract_bha,
    _extract_fish,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None
