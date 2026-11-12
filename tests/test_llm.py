"""Tests for the OpenAI-compatible LLM adapter."""

from types import SimpleNamespace
from threading import Lock, Thread
import time
import pytest
import openai
import config
import app.pipeline.llm as llm


class FakeCompletions:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=output))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        )


def setup_client(monkeypatch, outputs):
    completions = FakeCompletions(outputs)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_TEST_LLM_HANDLER", None)
    return completions


def test_call_llm_json_parses_fenced_json(monkeypatch):
    completions = setup_client(monkeypatch, ['```json\n{"ok": true}\n```'])
    assert llm.call_llm_json("system", "prompt") == {"ok": True}
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    ("call_type", "model", "cap", "effort"),
    [("reading", "fast", 800, "low"), ("persona", "fast", 150, "low"),
     ("scoring", "scoring", 1500, "low"), ("scoring_retry", "scoring", 1500, "low")],
)
def test_call_llm_json_uses_pass_settings(monkeypatch, call_type, model, cap, effort):
    completions = setup_client(monkeypatch, ['{"ok": true}'])
    monkeypatch.setattr(config, "LLM_MODEL_FAST", "fast")
    monkeypatch.setattr(config, "LLM_MODEL_SCORING", "scoring")

    llm.call_llm_json("system", "prompt", call_type=call_type)

    request = completions.calls[0]
    assert request["model"] == model
    assert request["max_tokens"] == cap
    assert request.get("reasoning_effort") == effort


def test_call_llm_json_retries_invalid_json(monkeypatch):
    completions = setup_client(monkeypatch, ["not json", '{"ok": true}'])
    assert llm.call_llm_json("system", "prompt") == {"ok": True}
    assert len(completions.calls) == 2


def test_call_llm_json_retries_rate_limit(monkeypatch):
    rate_limit = RuntimeError("Rate limit reached. Please try again in 1.9425s.")
    rate_limit.status_code = 429
    completions = setup_client(monkeypatch, [rate_limit, '{"ok": true}'])
    waits = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    assert llm.call_llm_json("system", "prompt") == {"ok": True}
    assert waits == [pytest.approx(2.9425)]


def test_call_llm_json_falls_back_without_json_mode(monkeypatch):
    failed_json = RuntimeError("Failed to generate JSON. See failed_generation for details.")
    failed_json.status_code = 400
    completions = setup_client(monkeypatch, [failed_json, '{"ok": true}'])
    assert llm.call_llm_json("system", "prompt") == {"ok": True}
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]


def test_call_llm_json_switches_provider_after_rate_limit_retries(monkeypatch):
    rate_limits = [RuntimeError("try again in 0.1s") for _ in range(3)]
    for error in rate_limits:
        error.status_code = 429
    primary = FakeCompletions(rate_limits)
    fallback = FakeCompletions(['{"ok": true}'])
    clients = iter([primary, fallback])
    client_options = []

    def create_client(**kwargs):
        client_options.append(kwargs)
        completions = next(clients)
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    monkeypatch.setattr(openai, "OpenAI", create_client)
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "FALLBACK_BASE_URL", "https://fallback.example/v1")
    monkeypatch.setattr(config, "FALLBACK_API_KEY", "fallback-key")
    monkeypatch.setattr(config, "FALLBACK_MODEL", "fallback-model")
    monkeypatch.setattr(llm, "_TEST_LLM_HANDLER", None)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)

    assert llm.call_llm_json("system", "prompt", call_type="reading") == {"ok": True}
    assert len(primary.calls) == 3
    assert fallback.calls[0]["model"] == "fallback-model"
    assert client_options[1]["base_url"] == "https://fallback.example/v1"


def test_call_llm_json_serializes_concurrent_calls(monkeypatch):
    state_lock = Lock()
    active = 0
    peak_active = 0

    def handler(system_instruction, prompt):
        nonlocal active, peak_active
        with state_lock:
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.02)
        with state_lock:
            active -= 1
        return {"ok": True}

    monkeypatch.setattr(llm, "_TEST_LLM_HANDLER", handler)
    threads = [Thread(target=llm.call_llm_json, args=("system", "prompt")) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak_active == 1
