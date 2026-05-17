"""Thin Ollama client + structured-output extraction helper.

Ollama exposes a JSON-schema constrained mode via ``format=<schema>`` on
``/api/chat``. We use that to get validated Pydantic objects out, no
post-hoc JSON repair needed.

Vision-capable models accept image bytes via the ``images`` array on each
message — base64-encoded PNG/JPEG. We hand a rendered PDF page in for OCR
fallback.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from etools.config import settings
from etools.logging_setup import get_logger

log = get_logger(__name__)


_DEBUG_DIR = Path("output") / "llm_debug"


def _dump_raw(prefix: str, content: str, *, body: dict | None = None) -> Path | None:
    """Write the raw LLM response (plus optional request body) to disk.

    One file per call, timestamped, under ``output/llm_debug/``. Returns the
    path written so callers can log it.
    """
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = _DEBUG_DIR / f"{ts}_{prefix}.json"
        with path.open("w", encoding="utf-8") as fh:
            if body is not None:
                # Strip image bytes from the dump — they're huge and not useful.
                body_safe = json.loads(json.dumps(body, default=str))
                for m in body_safe.get("messages", []):
                    if "images" in m:
                        m["images"] = [f"<{len(s)} b64 chars>" for s in m["images"]]
                fh.write("=== REQUEST ===\n")
                fh.write(json.dumps(body_safe, indent=2))
                fh.write("\n\n=== RAW RESPONSE ===\n")
            fh.write(content)
        return path
    except Exception as exc:  # pragma: no cover — debug only
        log.warning("llm.debug_dump.failed", error=str(exc))
        return None

T = TypeVar("T", bound=BaseModel)


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama isn't reachable. Caller should fall back to rules."""


class OllamaClient:
    """Synchronous client. Ollama is local, latency is fine for blocking calls."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm.base_url).rstrip("/")
        self.model = model or settings.llm.model
        self.vision_model = vision_model or settings.llm.vision_model
        self.timeout_s = timeout_s or settings.llm.timeout_s

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/version", timeout=2.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def has_model(self, model: str | None = None) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=4.0)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return (model or self.model) in names
        except (httpx.HTTPError, KeyError):
            return False

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def chat_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        system: str | None = None,
        images: list[bytes] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        thinking: bool = False,
    ) -> str:
        """Call ``/api/chat`` with structured output. Returns the raw JSON string.

        ``schema`` is a JSON-schema dict (Pydantic's ``model_json_schema()``).
        When provided, Ollama enforces it; otherwise it just sets ``format=json``.
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        msg: dict = {"role": "user", "content": prompt}
        if images:
            msg["images"] = [base64.b64encode(b).decode("ascii") for b in images]
        messages.append(msg)

        body: dict[str, Any] = {
            "model": model or (self.vision_model if images else self.model),
            "messages": messages,
            "stream": False,
            "format": schema if schema else "json",
            "options": {
                "temperature": temperature if temperature is not None else settings.llm.request_temperature,
                # Ollama's default num_predict is 128 — far too small for a
                # 100-row survey table (each row is ~40 JSON tokens). -1 lets
                # the model run until the schema is satisfied.
                # We expect metadata + (at most) a short survey listing.
                # Cap at 2048 — 100-row transcription is delegated to the
                # markdown regex path, not the LLM, since CPU inference of
                # 4k+ JSON tokens takes 10+ minutes.
                "num_predict": 2048,
                # Default num_ctx is 2048 on most models. Bump so a 16 KB
                # trimmed markdown actually fits.
                "num_ctx": 16384,
            },
            # Disable thinking by default — we want fast structured output, not chain-of-thought.
            "think": thinking,
        }

        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json=body,
                timeout=self.timeout_s,
            )
        except httpx.ConnectError as e:
            raise OllamaUnavailableError(f"Cannot reach Ollama at {self.base_url}: {e}") from e
        except httpx.HTTPError as e:
            raise OllamaUnavailableError(f"Ollama request failed: {e}") from e

        if r.status_code != 200:
            raise OllamaUnavailableError(
                f"Ollama returned HTTP {r.status_code}: {r.text[:300]}"
            )

        data = r.json()
        content = data.get("message", {}).get("content", "")
        has_images = bool(images)
        dump_path = _dump_raw(
            "vision" if has_images else "text",
            content,
            body=body,
        )
        log.info(
            "llm.chat",
            model=body["model"],
            tokens=data.get("eval_count"),
            duration_s=round(data.get("total_duration", 0) / 1e9, 2),
            response_chars=len(content),
            response_preview=content[:300],
            debug_dump=str(dump_path) if dump_path else None,
        )
        return content


def extract_with_schema(
    prompt: str,
    schema_model: Type[T],
    *,
    client: OllamaClient | None = None,
    system: str | None = None,
    images: list[bytes] | None = None,
) -> T:
    """One-shot: send prompt, validate response against ``schema_model``.

    Even though Ollama supports schema-constrained output via the ``format``
    parameter, real-world models still wander unless the schema is also
    repeated in the prompt as explicit guidance. We do both — belt + suspenders.
    """
    cli = client or OllamaClient()
    schema = schema_model.model_json_schema()
    full_prompt = (
        f"{prompt}\n\n"
        f"Respond with a single JSON object that conforms to this schema. "
        f"Use exactly the field names shown — do not rename or add extra fields.\n\n"
        f"Schema:\n```json\n{json.dumps(schema, indent=2)}\n```\n\n"
        f"Output only the JSON object. No prose, no code fences."
    )
    raw = cli.chat_json(
        full_prompt,
        schema=schema,
        system=system,
        images=images,
    )
    cleaned = _strip_code_fences(raw).strip()
    try:
        return schema_model.model_validate_json(cleaned)
    except ValidationError as e:
        log.warning("llm.validation.failed", error=str(e), raw=cleaned[:300])
        raise


def _strip_code_fences(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` even with structured-output mode.

    Strip a leading ```json (or ```) and a trailing ``` if present.
    """
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line.
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()
