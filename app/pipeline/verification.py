"""Verification checks enforcing rubric criteria, valid levels, and exact evidence quotes."""

from typing import Any, Dict, List, Tuple
from pydantic import ValidationError
from app.rubric import (
    is_valid_criterion,
    is_valid_level,
    normalize_criterion_id,
    normalize_level,
)
from app.schemas import ScoringRubricFields


def verify_scoring_output(
    scoring_data: Dict[str, Any], student_messages_map: Dict[str, str]
) -> Tuple[bool, List[str]]:
    """Validate schema, rubric criterion IDs, valid levels, quote lengths, and substrings."""
    errors = []
    if not isinstance(scoring_data, dict):
        return False, ["Scoring output is not a JSON object."]

    scores = scoring_data.get("scores")
    if not isinstance(scores, list) or len(scores) == 0:
        return False, ["Missing or empty 'scores' array."]

    for index, s in enumerate(scores):
        if not isinstance(s, dict):
            errors.append(f"Score at index {index} is not a JSON object.")
            continue
        try:
            validated = ScoringRubricFields.model_validate(s)
        except ValidationError:
            validated = None
        crit = validated.criterion if validated else s.get("criterion", "Unknown")
        lvl = validated.level if validated else s.get("level", "")

        if not is_valid_criterion(crit):
            errors.append(f"Criterion '{crit}' is not recognized in rubric.json.")

        if not is_valid_level(lvl):
            errors.append(f"Criterion '{crit}': Level '{lvl}' is not in rubric.json.")
        else:
            canon_lvl = normalize_level(lvl)
            if canon_lvl != "insufficient_evidence":
                quote = (s.get("evidence") or "").strip()
                mid = s.get("evidence_message_id", "")
                if not quote:
                    errors.append(f"Criterion '{crit}': Missing evidence quote for level '{lvl}'.")
                elif len(quote) < 8:
                    errors.append(f"Criterion '{crit}': Evidence quote '{quote}' shorter than 8 characters.")
                elif len(quote.split()) < 2:
                    errors.append(f"Criterion '{crit}': Evidence quote '{quote}' has under 2 words.")
                elif mid not in student_messages_map:
                    errors.append(f"Criterion '{crit}': Cited message '{mid}' does not belong to the student.")
                elif quote not in student_messages_map[mid]:
                    errors.append(f"Criterion '{crit}': Evidence quote '{quote}' is not an exact substring of message {mid}.")

        counter = s.get("counter_evidence")
        if counter and isinstance(counter, str):
            if not any(counter in raw_text for raw_text in student_messages_map.values()):
                errors.append(f"Criterion '{crit}': Counter-evidence '{counter}' is not a substring of any student message.")

    strength_quote = scoring_data.get("feedback", {}).get("strength", {}).get("quote")
    if strength_quote and isinstance(strength_quote, str):
        if not any(strength_quote in raw_text for raw_text in student_messages_map.values()):
            errors.append(f"Feedback strength quote '{strength_quote}' is not a substring of any student message.")

    return len(errors) == 0, errors


def sanitize_unverified_scores(
    scoring_data: Dict[str, Any], student_messages_map: Dict[str, str]
) -> Dict[str, Any]:
    """Withhold invalid scores and remove any evidence that could not be verified."""
    sanitized = dict(scoring_data)
    safe_scores = []
    for score in scoring_data.get("scores", []):
        if not isinstance(score, dict):
            continue
        criterion = normalize_criterion_id(score.get("criterion", ""))
        level = normalize_level(score.get("level", ""))
        if not criterion or not level:
            continue

        item = dict(score)
        item["criterion"] = criterion
        if level == "insufficient_evidence":
            item["level"] = "insufficient_evidence"
            item["evidence"] = ""
            item["evidence_message_id"] = ""
        else:
            is_valid, _ = verify_scoring_output(
                {"scores": [item]}, student_messages_map
            )
            if not is_valid:
                item["level"] = "insufficient_evidence"
                item["evidence"] = ""
                item["evidence_message_id"] = ""
                item["reason"] = "Evidence could not be verified; score withheld for human review."

        counter = item.get("counter_evidence")
        if isinstance(counter, str) and counter and not any(
            counter in message for message in student_messages_map.values()
        ):
            item["counter_evidence"] = ""
        safe_scores.append(item)

    sanitized["scores"] = safe_scores
    feedback = sanitized.get("feedback")
    if isinstance(feedback, dict):
        strength = feedback.get("strength")
        if isinstance(strength, dict):
            quote = strength.get("quote")
            if isinstance(quote, str) and quote and not any(
                quote in message for message in student_messages_map.values()
            ):
                feedback = dict(feedback)
                feedback["strength"] = {**strength, "quote": ""}
                sanitized["feedback"] = feedback
    return sanitized
