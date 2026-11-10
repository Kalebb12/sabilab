"""LLM cost calculation, event logging, and session summaries for SabiLab."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import config
from db import get_connection


def log_llm_cost(
    session_id: str,
    call_type: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = config.LLM_MODEL,
    current_time: Optional[datetime] = None,
    response: Any = None,
) -> float:
    """Calculate and log LLM usage event for a session into the events table."""
    usage = getattr(response, "usage", None)
    if usage is not None:
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
    now = current_time or datetime.now(timezone.utc)
    input_price, output_price = config.LLM_MODEL_PRICES_PER_M.get(model, (0.0, 0.0))
    in_cost = (input_tokens / 1_000_000.0) * input_price
    out_cost = (output_tokens / 1_000_000.0) * output_price
    cost_usd = round(in_cost + out_cost, 6)

    details = json.dumps({
        "call_type": call_type,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    })

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO events (session_id, type, time, details) VALUES (?, ?, ?, ?)",
            (session_id, "llm_cost", now.isoformat(), details),
        )
        conn.commit()
    finally:
        conn.close()

    return cost_usd


def get_cost_summary(session_id: str) -> Dict[str, Any]:
    """Compile token usage and cost summary across all LLM calls for a session."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT time, details FROM events WHERE session_id = ? AND type = 'llm_cost' ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()

    calls = []
    total_in = 0
    total_out = 0
    total_cost = 0.0

    for r in rows:
        d = json.loads(r["details"] or "{}")
        calls.append({
            "time": r["time"],
            "call_type": d.get("call_type", "unknown"),
            "model": d.get("model", config.LLM_MODEL),
            "input_tokens": d.get("input_tokens", 0),
            "output_tokens": d.get("output_tokens", 0),
            "cost_usd": d.get("cost_usd", 0.0),
        })
        total_in += d.get("input_tokens", 0)
        total_out += d.get("output_tokens", 0)
        total_cost += d.get("cost_usd", 0.0)

    return {
        "session_id": session_id,
        "total_calls": len(calls),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_cost_usd": round(total_cost, 6),
        "calls": calls,
    }
