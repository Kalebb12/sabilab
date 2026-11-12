"""Rubric definition loader, validator, and prompt generator."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_RUBRIC_PATH = Path(__file__).resolve().parent.parent / "rubric.json"
_CACHED_RUBRIC: Optional[Dict[str, Any]] = None


def get_rubric() -> Dict[str, Any]:
    """Load rubric definition from rubric.json."""
    global _CACHED_RUBRIC
    if _CACHED_RUBRIC is None:
        with open(_RUBRIC_PATH, "r", encoding="utf-8") as f:
            _CACHED_RUBRIC = json.load(f)
    return _CACHED_RUBRIC


def get_criteria_map() -> Dict[str, Dict[str, Any]]:
    """Return map of criterion_id -> details with dimension and levels."""
    rubric = get_rubric()
    cmap = {}
    for dim_name, dim_data in rubric.get("dimensions", {}).items():
        for crit in dim_data.get("criteria", []):
            cmap[crit["id"]] = {
                "id": crit["id"],
                "name": crit["name"],
                "dimension": dim_name,
                "levels": crit.get("levels", {}),
            }
    return cmap


def get_criterion_ids() -> List[str]:
    """Return criterion IDs in rubric display order."""
    return list(get_criteria_map())


def get_level_keys() -> List[str]:
    """Return level keys in ascending scoring order, with insufficient evidence last."""
    levels = get_rubric().get("levels", {})
    return sorted(
        levels,
        key=lambda key: (
            levels[key].get("order", 0) == 0,
            levels[key].get("order", 0),
        ),
    )


def normalize_criterion_id(cid: str) -> Optional[str]:
    """Map criterion identifier to canonical ID (e.g. C1, C1 Clarity -> C1)."""
    if not cid or not isinstance(cid, str):
        return None
    cleaned = cid.strip()
    cmap = get_criteria_map()
    if cleaned in cmap:
        return cleaned
    parts = cleaned.split()
    if parts and parts[0].upper() in cmap:
        return parts[0].upper()
    for k, v in cmap.items():
        if v["name"].lower() == cleaned.lower():
            return k
    return None


def is_valid_criterion(cid: str) -> bool:
    """Check if criterion id exists in rubric."""
    return normalize_criterion_id(cid) is not None


def normalize_level(lvl: str) -> Optional[str]:
    """Map any accepted representation to canonical level key."""
    if not lvl or not isinstance(lvl, str):
        return None
    key = lvl.strip().lower().replace(" ", "_")
    mapping = {
        "insufficient": "insufficient_evidence",
        "not_enough_evidence": "insufficient_evidence",
    }
    canonical = mapping.get(key, key)
    return canonical if canonical in get_rubric().get("levels", {}) else None


def get_level_display(lvl: str) -> str:
    """Return human display string for level (e.g. 'Needs practice')."""
    canon = normalize_level(lvl)
    if not canon:
        return lvl
    rubric = get_rubric()
    return rubric.get("levels", {}).get(canon, {}).get("display", lvl)


def is_valid_level(lvl: str) -> bool:
    """Check if level is valid in rubric."""
    return normalize_level(lvl) is not None


def get_compact_rubric_prompt() -> str:
    """Generate compact one-line-per-criterion rubric text for prompt."""
    rubric = get_rubric()
    lines = [f"Valid levels: {', '.join(get_level_keys())}."]
    for dim_name, dim_data in rubric.get("dimensions", {}).items():
        lines.append(f"[{dim_name}]")
        for crit in dim_data.get("criteria", []):
            cid = crit["id"]
            name = crit["name"]
            lvls = crit.get("levels", {})
            np_desc = lvls.get("needs_practice", "")
            f_desc = lvls.get("foundation", "")
            p_desc = lvls.get("proficient", "")
            lines.append(f"- {cid} {name}: NP: {np_desc} | F: {f_desc} | P: {p_desc}")
    return "\n".join(lines)
