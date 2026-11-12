"""Owner persona replies for the huddle."""

import json
import logging
import re
import time
from typing import Any, Dict, List

from app.loader import load_scenario, render_scenario_text, scenario_fact_values
from app.pipeline.llm import call_llm_json
from db import get_connection

logger = logging.getLogger("sabilab.persona")
PERSONA_TIMEOUT_SECONDS = 6.0
_ADVICE_PATTERN = re.compile(
    r"\b(?:you|we)\s+(?:should|must|need to|have to|ought to)\b"
    r"|\b(?:you|we)\s+(?:can|could|will|would)\s+(?:pay|offer|decline|accept|reject|settle|approve)\b"
    r"|\b(?:i|we)\s+(?:will|would|can|could)\s+(?:pay|offer|decline|accept|reject|settle|approve)\b"
    r"|\b(?:i|we)\s+(?:recommend|suggest|propose)\b"
    r"|\b(?:cannot|can['’]t|will not|won['’]t)\s+(?:meet|grant|accept|approve)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_CLAIM_PATTERN = re.compile(
    r"\b(?:limit(?:s|ed)?|restrict(?:s|ed)?|prevent(?:s|ed)?|unable|ability|"
    r"afford|enough|insufficient|shortfall|reserve)\b",
    re.IGNORECASE,
)


def _session_context(session_id: str, sender: str) -> tuple[Dict[str, Any], str, List[str]]:
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT scenario_id, variant FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")
        student = conn.execute(
            "SELECT display_name FROM participants WHERE session_id = ? AND kind = 'student'",
            (session_id,),
        ).fetchone()
        student_name = student["display_name"] if student else sender
        rows = conn.execute(
            "SELECT text FROM messages WHERE session_id = ? AND sender = ? "
            "AND phase = 'huddle' ORDER BY sequence_number DESC LIMIT 2",
            (session_id, student_name),
        ).fetchall()
    finally:
        conn.close()
    return load_scenario(session["scenario_id"]), session["variant"], [
        row["text"] for row in reversed(rows)
    ]


def _persona_facts(scenario: Dict[str, Any], variant: str) -> Dict[str, str]:
    facts = scenario_fact_values(scenario, variant)
    facts.pop("cash_remaining_if_paid_in_full", None)
    return facts


def _contains_answer_key_amount(reply: str, scenario: Dict[str, Any], variant: str) -> bool:
    checks = (
        scenario.get("variant_b", {}).get("checks", scenario["checks"])
        if variant == "B"
        else scenario["checks"]
    )
    protected_patterns = []
    for check in checks:
        if check["id"] in {"K3", "K5"}:
            protected_patterns.extend(check["patterns"])
    protected_values = set()
    for pattern in protected_patterns:
        normalized = pattern.lower()
        if normalized.endswith("k"):
            normalized = normalized[:-1] + "000"
        protected_values.add(re.sub(r"\D", "", normalized))
    mentioned_values = []
    for match in re.finditer(r"(?<!\d)\d[\d,]*(?:\s*[kK])?(?!\w)", reply):
        value = re.sub(r"\D", "", match.group())
        if match.group().strip().lower().endswith("k"):
            value += "000"
        mentioned_values.append(value)
    return bool(protected_values.intersection(mentioned_values))


def _contains_unlisted_number(reply: str, facts: Dict[str, str]) -> bool:
    def normalized_numbers(text: str) -> set[str]:
        values = set()
        for match in re.finditer(r"(?<!\d)\d[\d,]*(?:\s*[kK])?(?!\w)", text):
            value = re.sub(r"\D", "", match.group())
            if match.group().strip().lower().endswith("k"):
                value += "000"
            values.add(value)
        return values

    allowed = set().union(*(normalized_numbers(value) for value in facts.values()))
    return not normalized_numbers(reply).issubset(allowed)


def generate_owner_reply(
    session_id: str,
    sender: str,
    twist_active: bool,
) -> str:
    """React to the two latest student messages or return the beat's scripted line."""
    scenario, variant, recent_messages = _session_context(session_id, sender)
    beat = "after_twist" if twist_active else "before_twist"
    fallback_key = "after_twist" if twist_active else "follow_up"
    fallback = render_scenario_text(
        scenario["owner"]["scripted_lines"][fallback_key], scenario, variant
    )
    started = time.monotonic()
    try:
        fact_context = json.dumps(_persona_facts(scenario, variant), ensure_ascii=False)
        prompt = (
            f"Current beat: {beat}.\n"
            f"Student's last two messages: {json.dumps(recent_messages, ensure_ascii=False)}\n"
            f"Scenario facts you may use: {fact_context}\n"
            "As Adaeze, briefly acknowledge the student's latest proposal or question, then state one "
            "relevant need or constraint exactly as stated in the facts. Do not infer a new constraint, "
            "advise the student, make a decision, calculate, or invent any fact, amount, or deadline. "
            "Do not mention scoring or "
            "answer-key amounts. Use no numeric value unless it appears in the listed facts. Reply in "
            '40 words or fewer as exactly this JSON shape: {"reply":"..."}'
        )
        result = call_llm_json(
            "You are Adaeze, the practical owner of Adaeze's Fabrics, focused on cash flow and business survival. "
            "Stay professional, concise, and in character. State needs and constraints without giving advice.",
            prompt,
            session_id=session_id,
            call_type="persona",
            timeout_seconds=PERSONA_TIMEOUT_SECONDS,
        )
        if time.monotonic() - started > PERSONA_TIMEOUT_SECONDS:
            raise TimeoutError("Owner persona call exceeded six seconds.")
        reply = result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Owner persona returned no reply.")
        reply = reply.strip()
        if len(reply.split()) > 40:
            raise ValueError("Owner persona reply exceeded 40 words.")
        if set(result) != {"reply"}:
            raise ValueError("Owner persona returned an unexpected response shape.")
        if _ADVICE_PATTERN.search(reply):
            raise ValueError("Owner persona reply included a recommendation or decision.")
        if _UNSUPPORTED_CLAIM_PATTERN.search(reply):
            raise ValueError("Owner persona reply inferred an unsupported constraint.")
        if _contains_unlisted_number(reply, _persona_facts(scenario, variant)):
            raise ValueError("Owner persona reply included an unlisted number.")
        if _contains_answer_key_amount(reply, scenario, variant):
            raise ValueError("Owner persona reply included an answer-key amount.")
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.warning(
            "owner_persona session_id=%s path=scripted_fallback beat=%s elapsed_seconds=%.2f error=%s",
            session_id,
            beat,
            elapsed,
            type(exc).__name__,
        )
        return fallback

    elapsed = time.monotonic() - started
    logger.info(
        "owner_persona session_id=%s path=model beat=%s elapsed_seconds=%.2f",
        session_id,
        beat,
        elapsed,
    )
    return reply
