"""Gemini API client wrapper for structured JSON generation and token cost tracking."""

import json
import re
from typing import Any, Dict, Optional
import config
from app.cost import log_llm_cost

_TEST_LLM_HANDLER = None


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

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    raw_text = clean_json_response(response.text or "{}")

    if session_id:
        usage = getattr(response, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", None) or max(1, len(system_instruction + prompt) // 4)
        out_tok = getattr(usage, "candidates_token_count", None) or max(1, len(raw_text) // 4)
        log_llm_cost(session_id, call_type, in_tok, out_tok, config.GEMINI_MODEL)

    return json.loads(raw_text)
