"""Scenario loader and check verification for SabiLab."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List
import config


def list_scenarios() -> List[Dict[str, str]]:
    """Return a summary list of all available scenarios."""
    scenarios = []
    for filepath in config.SCENARIOS_DIR.glob("*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            scenarios.append({
                "id": data["id"],
                "title": data["title"],
                "status": data["status"],
                "student_role": data["student_role"],
            })
    return scenarios


def load_scenario(scenario_id: str) -> Dict[str, Any]:
    """Load a single scenario by ID and return its full configuration."""
    filepath = config.SCENARIOS_DIR / f"{scenario_id}.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Scenario '{scenario_id}' not found.")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    _validate_scenario(data)
    return data


def _validate_scenario(data: Dict[str, Any]) -> None:
    """Ensure all required fields exist in the scenario data."""
    required_fields = [
        "id", "title", "status", "student_role", "roster",
        "owner", "client", "facts", "timeline", "twist",
        "task", "checks", "approaches", "register", "variant_b"
    ]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field in scenario: {field}")


def normalize_text_for_checks(text: str) -> str:
    """Normalize text by expanding 'k' to thousands and stripping commas, spaces, and naira signs."""
    # Convert trailing 'k' on numbers to '000' (e.g. 350k -> 350000)
    expanded = re.sub(r'(\d+)[kK]\b', r'\g<1>000', text)
    # Remove commas, spaces, and currency symbols
    cleaned = re.sub(r'[₦\s,]', '', expanded)
    return cleaned.lower()


def run_checks(task_text: str, checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Report which check patterns appear in the task text."""
    normalized_task = normalize_text_for_checks(task_text)
    results = []
    for check in checks:
        matched = False
        for pattern in check.get("patterns", []):
            normalized_pattern = normalize_text_for_checks(pattern)
            if normalized_pattern and normalized_pattern in normalized_task:
                matched = True
                break
        results.append({
            "id": check["id"],
            "label": check["label"],
            "matched": matched,
        })
    return results
