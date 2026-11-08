"""Text normalization and factual check pattern matching for SabiLab."""

import re
from typing import Any, Dict, List

# Word representations of common figures in scenarios (stretch goal)
NUMBER_WORDS = {
    "four hundred and eighty thousand": "480000",
    "four hundred eighty thousand": "480000",
    "three hundred and fifty thousand": "350000",
    "three hundred fifty thousand": "350000",
    "one hundred and thirty thousand": "130000",
    "one hundred thirty thousand": "130000",
    "one hundred and fifty thousand": "150000",
    "one hundred fifty thousand": "150000",
    "two hundred thousand": "200000",
    "one hundred thousand": "100000",
    "twenty percent": "20%",
    "ten percent": "10%",
    "five percent": "5%",
    "fifteen percent": "15%",
}


def normalize_text(text: str) -> str:
    """Normalize text by expanding number words and 'k', then removing commas, spaces, and naira signs."""
    lowered = text.lower()
    for words, num in NUMBER_WORDS.items():
        lowered = lowered.replace(words, num)

    # Convert trailing 'k' on numbers to '000' (e.g. 350k -> 350000)
    expanded = re.sub(r'(\d+)[kK]\b', r'\g<1>000', lowered)
    # Remove commas, spaces, and currency symbols (₦ and N)
    cleaned = re.sub(r'[₦n\s,]', '', expanded)
    return cleaned


def report_checks(task_text: str, checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Report which check figures appear in the task text without judging correctness."""
    normalized_task = normalize_text(task_text)
    results = []
    for check in checks:
        matched = False
        for pattern in check.get("patterns", []):
            norm_pattern = normalize_text(pattern)
            if norm_pattern and norm_pattern in normalized_task:
                matched = True
                break
        results.append({
            "id": check["id"],
            "label": check["label"],
            "matched": matched,
        })
    return results


# Backward compatibility alias
run_checks = report_checks
