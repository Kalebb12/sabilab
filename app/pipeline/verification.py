"""Verification checks in code to enforce rubric constraints and exact evidence quotes."""

from typing import Any, Dict, List, Tuple

ALLOWED_LEVELS = {"Needs practice", "Foundation", "Proficient", "insufficient_evidence", "Insufficient evidence"}


def verify_scoring_output(scoring_data: Dict[str, Any], student_messages_map: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Validate schema, exact substring quotes, student message ownership, and level caps."""
    errors = []

    if not isinstance(scoring_data, dict):
        return False, ["Scoring output is not a JSON object."]

    scores = scoring_data.get("scores")
    if not isinstance(scores, list) or len(scores) == 0:
        return False, ["Missing or empty 'scores' array."]

    for s in scores:
        crit = s.get("criterion", "Unknown")
        lvl = s.get("level", "")
        if lvl not in ALLOWED_LEVELS:
            errors.append(f"Criterion '{crit}': Level '{lvl}' exceeds cap or is invalid. Max level is Proficient.")

        # If scored, evidence must be an exact quote from the student's message
        if lvl not in {"insufficient_evidence", "Insufficient evidence"}:
            quote = s.get("evidence", "")
            mid = s.get("evidence_message_id", "")
            if not quote:
                errors.append(f"Criterion '{crit}': Missing evidence quote for level '{lvl}'.")
            elif mid not in student_messages_map:
                errors.append(f"Criterion '{crit}': Cited message '{mid}' does not belong to the student.")
            elif quote not in student_messages_map[mid]:
                errors.append(f"Criterion '{crit}': Evidence quote '{quote}' is not an exact substring of message {mid}.")

        # Verify counter-evidence quote if present
        counter = s.get("counter_evidence")
        if counter and isinstance(counter, str):
            if not any(counter in raw_text for raw_text in student_messages_map.values()):
                errors.append(f"Criterion '{crit}': Counter-evidence '{counter}' is not a substring of any student message.")

    # Verify feedback strength quote
    strength_quote = scoring_data.get("feedback", {}).get("strength", {}).get("quote")
    if strength_quote and isinstance(strength_quote, str):
        if not any(strength_quote in raw_text for raw_text in student_messages_map.values()):
            errors.append(f"Feedback strength quote '{strength_quote}' is not a substring of any student message.")

    return len(errors) == 0, errors
