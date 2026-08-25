"""Ollama transport guards: bad bodies and truncated responses."""
from __future__ import annotations

import json

import pytest

from etools.core.llm.ollama_client import OllamaClient, OllamaUnavailableError


class _Resp:
    def __init__(self, status=200, payload=None, text="", raise_json=False):
        self.status_code = status
        self._payload = payload
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise json.JSONDecodeError("Expecting value", "<html>", 0)
        return self._payload

    def raise_for_status(self):
        return None


def test_non_json_body_becomes_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _Resp(raise_json=True, text="<html>bad gateway</html>"),
    )
    with pytest.raises(OllamaUnavailableError) as ei:
        OllamaClient().chat_json("hi")
    assert "json" in str(ei.value).lower()


def test_truncated_response_is_detected(monkeypatch):
    payload = {
        "message": {"content": '{"partial": tru'},
        "done_reason": "length",
        "eval_count": 2048,
    }
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(payload=payload))
    with pytest.raises(OllamaUnavailableError) as ei:
        OllamaClient().chat_json("hi")
    assert "truncat" in str(ei.value).lower()


def test_a_complete_response_is_returned(monkeypatch):
    payload = {
        "message": {"content": '{"ok": true}'},
        "done_reason": "stop",
        "eval_count": 12,
    }
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(payload=payload))
    assert OllamaClient().chat_json("hi") == '{"ok": true}'


def test_a_response_without_done_reason_is_not_treated_as_truncated(monkeypatch):
    # Older Ollama builds omit done_reason entirely; that must not be read
    # as a truncation.
    payload = {"message": {"content": '{"ok": true}'}, "eval_count": 12}
    monkeypatch.setattr("httpx.post", lambda *a, **k: _Resp(payload=payload))
    assert OllamaClient().chat_json("hi") == '{"ok": true}'


def test_has_model_returns_false_on_a_non_json_body(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(raise_json=True))
    assert OllamaClient().has_model("anything") is False


def test_has_model_still_works_on_a_good_body(monkeypatch):
    payload = {"models": [{"name": "qwen3.5:9b"}]}
    monkeypatch.setattr("httpx.get", lambda *a, **k: _Resp(payload=payload))
    cli = OllamaClient()
    assert cli.has_model("qwen3.5:9b") is True
    assert cli.has_model("nope:1b") is False
