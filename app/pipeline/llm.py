"""Gemini API client wrapper for structured JSON generation."""

import json
import re
from typing import Any, Dict
import config

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


def call_gemini_json(system_instruction: str, prompt: str) -> Dict[str, Any]:
    """Invoke Gemini API using the official client with JSON mode and return parsed dictionary."""
    if _TEST_LLM_HANDLER:
        return _TEST_LLM_HANDLER(system_instruction, prompt)

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
    return json.loads(raw_text)
