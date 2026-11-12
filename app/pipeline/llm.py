"""OpenAI-compatible client wrapper for JSON generation and token tracking."""

import json
import logging
import re
import time
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import config
from app.cost import log_llm_cost

_TEST_LLM_HANDLER = None
_LLM_LOCK = Lock()
logger = logging.getLogger("sabilab.pipeline.llm")
LLM_TIMEOUT_SECONDS = 30


def set_test_llm_handler(handler) -> None:
    """Set an optional mock LLM handler for testing."""
    global _TEST_LLM_HANDLER
    _TEST_LLM_HANDLER = handler


def clean_json_response(text: str) -> str:
    """Strip markdown code fence blocks from an LLM response string."""
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


def _rate_limit_delay(exc: Exception) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("retry-after")
    if retry_after is None:
        match = re.search(r"try again in\s+([0-9.]+)s", str(exc), re.IGNORECASE)
        retry_after = match.group(1) if match else None
    try:
        return float(retry_after) + 1.0 if retry_after else 2.0
    except (TypeError, ValueError):
        return 2.0


def _call_settings(call_type: str) -> tuple[str, Optional[int], Optional[str]]:
    if call_type == "reading":
        return config.LLM_MODEL_FAST, 800, "low"
    if call_type == "persona":
        return config.LLM_MODEL_FAST, 150, "low"
    if call_type.startswith("scoring"):
        return config.LLM_MODEL_SCORING, 1500, "low"
    return config.LLM_MODEL, None, None


def _create_completion(
    client: Any,
    messages: list[dict[str, str]],
    model: str,
    max_tokens: Optional[int],
    reasoning_effort: Optional[str],
    provider: str,
    allow_json_retry: bool = True,
) -> tuple[Any, float]:
    started = time.monotonic()
    options = {"model": model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0.1}
    if max_tokens is not None:
        options["max_tokens"] = max_tokens
    if reasoning_effort:
        options["reasoning_effort"] = reasoning_effort
    try:
        response = client.chat.completions.create(**options)
    except Exception as exc:
        message = str(exc).lower()
        json_mode_failure = any(term in message for term in (
            "response_format", "json_object", "failed to generate json", "failed_generation"
        ))
        if (
            not allow_json_retry
            or str(getattr(exc, "status_code", "")) != "400"
            or not json_mode_failure
        ):
            raise
        logger.warning("LLM provider=%s model=%s JSON mode failed; retrying without response_format",
                       provider, model)
        started = time.monotonic()
        options.pop("response_format")
        response = client.chat.completions.create(**options)
    return response, time.monotonic() - started


def _request_with_retries(client: Any, messages: list[dict[str, str]], model: str,
                          max_tokens: Optional[int], effort: Optional[str], provider: str,
                          timeout_seconds: Optional[float] = None) -> Any:
    attempts = 1 if timeout_seconds is not None else 3
    for retry in range(attempts):
        started = time.monotonic()
        try:
            response, elapsed = _create_completion(
                client,
                messages,
                model,
                max_tokens,
                effort,
                provider,
                allow_json_retry=timeout_seconds is None,
            )
            if timeout_seconds is not None and elapsed > timeout_seconds:
                raise TimeoutError("LLM call exceeded its timeout.")
            usage = getattr(response, "usage", None)
            logger.info("LLM provider=%s model=%s elapsed=%.2fs prompt_tokens=%d completion_tokens=%d",
                        provider, model, elapsed, getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0)
            return response
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.info("LLM provider=%s model=%s elapsed=%.2fs prompt_tokens=0 completion_tokens=0",
                        provider, model, time.monotonic() - started)
            if str(status) != "429" or retry == attempts - 1:
                raise
            delay = _rate_limit_delay(exc)
            logger.warning("LLM provider=%s model=%s rate limited; retry %d/2 in %.2fs",
                           provider, model, retry + 1, delay)
            time.sleep(delay)


def _status_code(exc: Exception) -> Any:
    return getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )


def _client(base_url: str, api_key: str, timeout_seconds: Optional[float] = None) -> Any:
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=base_url,
                  timeout=timeout_seconds or LLM_TIMEOUT_SECONDS, max_retries=0)


def _call_llm_json_unlocked(
    system_instruction: str,
    prompt: str,
    session_id: Optional[str] = None,
    call_type: str = "general",
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Call the configured OpenAI-compatible API and return a parsed JSON object."""
    model, max_tokens, effort = _call_settings(call_type)
    provider_url, api_key = config.LLM_BASE_URL, config.GROQ_API_KEY
    provider = urlparse(provider_url).netloc or "openai-compatible"
    prompt = prompt + "\nReturn a valid JSON object only."
    if _TEST_LLM_HANDLER:
        started = time.monotonic()
        result = _TEST_LLM_HANDLER(system_instruction, prompt)
        if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
            raise TimeoutError("LLM call exceeded its timeout.")
        input_tokens = max(1, len(system_instruction + prompt) // 4)
        output_tokens = max(1, len(json.dumps(result)) // 4)
        logger.info("LLM provider=%s model=%s elapsed=%.2fs prompt_tokens=%d completion_tokens=%d", provider, model, time.monotonic() - started, input_tokens, output_tokens)
        if session_id:
            log_llm_cost(session_id, call_type, input_tokens, output_tokens, model)
        return result

    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured in the environment.")
    client = _client(provider_url, api_key, timeout_seconds)
    fallback_configured = all((config.FALLBACK_BASE_URL, config.FALLBACK_API_KEY, config.FALLBACK_MODEL))
    fallback_used = False
    parse_attempts = 1 if timeout_seconds is not None else 2
    for parse_attempt in range(parse_attempts):
        if parse_attempt:
            prompt += f"\nThe previous response was invalid JSON. Return a valid JSON object only.\nPrevious response:\n{raw_text}"
        messages = [{"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}]
        try:
            response = _request_with_retries(
                client, messages, model, max_tokens, effort, provider, timeout_seconds
            )
        except Exception as exc:
            if (
                timeout_seconds is not None
                or str(_status_code(exc)) != "429"
                or not fallback_configured
                or fallback_used
            ):
                raise
            provider_url, api_key, model = (
                config.FALLBACK_BASE_URL, config.FALLBACK_API_KEY, config.FALLBACK_MODEL
            )
            provider = urlparse(provider_url).netloc or "fallback"
            client = _client(provider_url, api_key)
            fallback_used = True
            logger.warning("LLM rate limit retries exhausted; switching to fallback provider=%s model=%s",
                           provider, model)
            response = _request_with_retries(client, messages, model, max_tokens, effort, provider)
        if session_id:
            log_llm_cost(session_id, call_type, model=model, response=response)
        raw_text = clean_json_response(response.choices[0].message.content or "")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            if parse_attempt:
                raise ValueError("LLM returned invalid JSON after one retry.") from exc
    raise ValueError("LLM returned invalid JSON after one retry.")


def call_llm_json(
    system_instruction: str,
    prompt: str,
    session_id: Optional[str] = None,
    call_type: str = "general",
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Serialize LLM calls across this process and return parsed JSON."""
    if timeout_seconds is None:
        with _LLM_LOCK:
            return _call_llm_json_unlocked(system_instruction, prompt, session_id, call_type)

    started = time.monotonic()
    if not _LLM_LOCK.acquire(timeout=timeout_seconds):
        raise TimeoutError("Timed out waiting for the LLM client.")
    try:
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for the LLM client.")
        return _call_llm_json_unlocked(
            system_instruction,
            prompt,
            session_id,
            call_type,
            timeout_seconds=remaining,
        )
    finally:
        _LLM_LOCK.release()
