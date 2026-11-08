"""Reading pass implementation to assess message clarity, language, and tone."""

import json
from typing import Any, Dict, List
from db import get_connection
from app.pipeline.llm import call_gemini_json
from app.pipeline.prompts import READING_SYSTEM_PROMPT


def build_reading_prompt(transcript: List[Dict[str, Any]], scenario: Dict[str, Any]) -> str:
    """Construct the user prompt for the reading pass enclosing transcript as data."""
    transcript_text = "\n".join(
        f"[{m['message_id']}] ({m['role']}) {m['sender']}: {m['text']}"
        for m in transcript
    )
    register_text = json.dumps(scenario.get("register", {}), indent=2)
    facts_text = json.dumps([f"{f['key']}: {f['value']}" for f in scenario.get("facts", [])], indent=2)

    return f"""<audience_and_register>
{register_text}
</audience_and_register>

<scenario_facts>
{facts_text}
</scenario_facts>

<transcript>
{transcript_text}
</transcript>

Analyze each message where sender is 'Student'. Return JSON matching schema."""


def execute_reading_pass(session_id: str, transcript: List[Dict[str, Any]], scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Execute reading pass via LLM and save results in readings table."""
    user_prompt = build_reading_prompt(transcript, scenario)
    result = call_gemini_json(READING_SYSTEM_PROMPT, user_prompt, session_id=session_id, call_type="reading")

    # Persist readings into database
    conn = get_connection()
    try:
        raw_id_map = {m["message_id"]: m["raw_id"] for m in transcript}
        for r in result.get("readings", []):
            msg_id = raw_id_map.get(r.get("message_id"), r.get("message_id", "unknown"))
            conn.execute(
                "INSERT INTO readings (session_id, message_id, language, intent, clarity, ambiguity, tone, tone_flags, register_fit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    msg_id,
                    r.get("language", "en"),
                    r.get("intent", ""),
                    r.get("clarity", "clear"),
                    r.get("ambiguity") or "",
                    r.get("tone", "neutral"),
                    json.dumps(r.get("tone_flags", [])),
                    r.get("register_fit", "fit"),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return result
