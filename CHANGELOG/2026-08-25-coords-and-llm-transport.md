# Coordinate guards and Ollama transport failures

- **Date:** 2026-08-25
- **Author:** Colton Goodrich
- **Commit(s):** a122bf0, (ollama commit)

## What changed

"Reprocess with new SHL" no longer does nothing when you swap latitude and
longitude — it now tells you the coordinate could not be projected. And three
Ollama failure modes that used to be reported as the wrong thing (or not at all)
now name themselves.

## Why

Audit findings 7.C2, 7.C3 and 7.C5, plus break case §6/E2.

**E2** was real: typing the longitude into the easting box killed the
`reprocess_shl` handler with no dialog and no notification, so the user clicked
again. **The mechanism I originally gave for it was wrong** — see Notes.

`ollama_client.py` called `r.json()` unguarded in two places. A 200 response with
a non-JSON body (a proxy's HTML error page) raised `json.JSONDecodeError`, which
is a `ValueError` and therefore slipped past `has_model`'s
`except (httpx.HTTPError, KeyError)`. It surfaced several frames up as
"LLM extraction failed", pointing at the wrong component. Separately, truncation
at the `num_predict: 2048` cap was never detected at all — Ollama reports
`done_reason == "length"` and the code never read it, so a truncated response was
indistinguishable from any other malformed one.

## What was added

- **`tests/test_coordinate_guards.py`** (7), including an AST-based test that
  asserts `utm_to_latlon` stays *inside* `reprocess_shl`'s try block.
- **`tests/test_ollama_client_guards.py`** (6).

## What was changed / removed

- **`etools/ui/tabs/survey_tab.py`** — the coordinate conversion moved inside the
  existing `try`, so the existing `except ValueError` actually covers it.
- **`etools/core/coordinates/converter.py`** — `utm_to_latlon` coerces its inputs
  and normalises failures to `ValueError`.
- **`etools/core/llm/ollama_client.py`** — `r.json()` guarded in `chat_json` and
  `has_model`; `done_reason == "length"` raises `OllamaUnavailableError`, which
  every caller already handles as a named warning.

## Verification

- New tests: 13 passed, each verified failing first.
- Full suite: **194 passed** in 8:14, exit 0.
- Confirmed a truncated response reaches `extract_with_schema`'s caller as
  `OllamaUnavailableError: Ollama response was truncated at the num_predict
  limit (2048 tokens)` rather than as an empty field.

## Notes / follow-ups

- **Correction to audit finding 7.C2.** I stated twice that
  `utm.error.OutOfRangeError` "is NOT a `ValueError`" and built the E2
  explanation on it. It **is** a `ValueError` subclass —
  `['OutOfRangeError', 'ValueError', 'Exception', ...]`. I inferred it from the
  exception name in a traceback without checking the MRO. The break case is
  real; the stated cause was not. The actual cause is placement: the call sat
  below the `except` clause.
- The converter guard still earns its place for the gaps that are real: a string
  reaches numpy and raises `UFuncTypeError`, `None` raises `TypeError` — neither
  is a `ValueError`. NaN already raised `OutOfRangeError`, so that part of the
  finding was also overstated.
- **No retries were added**, deliberately. `ddr_llm.py:485-499`'s chunk-splitting
  remains the only retry in the codebase and is a better response to a truncation
  than blind repetition.
- Part of the failure-path hardening effort planned in
  `docs/superpowers/plans/2026-08-19-failure-path-hardening.md`.
