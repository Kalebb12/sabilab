"""Gemini API client wrapper for structured JSON generation and token cost tracking."""

import json
import logging
import re
from typing import Any, Dict, Optional
import config
from app.cost import log_llm_cost

_TEST_LLM_HANDLER = None
logger = logging.getLogger("sabilab.pipeline.llm")
LLM_TIMEOUT_MS = 30_000


def set_test_llm_handler(handler) -> None:
    """Set an optional mock LLM handler for testing."""
    global _TEST_LLM_HANDLER
    _TEST_LLM_HANDLER = handler


def clean_json_response(text: str) -> str:
    """Strip markdown code fence blocks from an LLM response string."""
    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


def call_gemini_json(
    system_instruction: str,
    prompt: str,
    session_id: Optional[str] = None,
    call_type: str = "general",
) -> Dict[str, Any]:
    """Invoke Gemini API or test handler, log token usage and cost, and return parsed JSON."""
    if _TEST_LLM_HANDLER:
        result = _TEST_LLM_HANDLER(system_instruction, prompt)
        if session_id:
            in_tok = max(1, len(system_instruction + prompt) // 4)
            out_tok = max(1, len(json.dumps(result)) // 4)
            log_llm_cost(session_id, call_type, in_tok, out_tok, config.GEMINI_MODEL)
        return result

    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured in .env.")

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=LLM_TIMEOUT_MS),
    )
    generation_options: Dict[str, Any] = {
        "system_instruction": system_instruction,
        "response_mime_type": "application/json",
        "temperature": 0.1,
    }
    thinking_config_type = getattr(types, "ThinkingConfig", None)
    if thinking_config_type and config.GEMINI_MODEL.lower().startswith("gemini-3"):
        thinking_level_type = getattr(types, "ThinkingLevel", None)
        low_level = getattr(thinking_level_type, "LOW", None)
        if low_level is not None:
            generation_options["thinking_config"] = thinking_config_type(
                thinking_level=low_level
            )
    elif thinking_config_type and config.GEMINI_MODEL.lower().startswith("gemini-2.5"):
        generation_options["thinking_config"] = thinking_config_type(thinking_budget=0)

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(**generation_options),
        )
        raw_text = clean_json_response(response.text or "{}")
        result = json.loads(raw_text)
    except Exception as exc:
        status = getattr(exc, "code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if str(status) == "429":
            logger.exception("Gemini API rate limited this request (HTTP 429).")
        elif str(status) == "503" or "UNAVAILABLE" in str(exc):
            logger.exception(
                "Gemini API is temporarily unavailable (HTTP 503); the model may "
                "be experiencing high demand."
            )
        elif str(status) == "504" or "DEADLINE_EXCEEDED" in str(exc):
            logger.exception(
                "Gemini API deadline exceeded (HTTP 504); the provider did not "
                "complete this request before its deadline."
            )
        elif isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            logger.exception("Gemini API request timed out after 30 seconds.")
        else:
            logger.exception("Gemini API request or response parsing failed.")
        raise

    if session_id:
        usage = getattr(response, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", None) or max(1, len(system_instruction + prompt) // 4)
        out_tok = getattr(usage, "candidates_token_count", None) or max(1, len(raw_text) // 4)
        log_llm_cost(session_id, call_type, in_tok, out_tok, config.GEMINI_MODEL)

    return result
