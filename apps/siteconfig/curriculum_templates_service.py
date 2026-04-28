"""
North Star SLICE 3 — curriculum template registry (registry-first, file-backed).

Templates are reference data for operators; applying them to a live tenant is a
separate guided flow (not implemented here).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator


_REG_FILENAME = "curriculum_templates_registry.json"


def _registry_path() -> Path:
    base = Path(__file__).resolve().parent / "data" / _REG_FILENAME
    if base.exists():
        return base
    # Fallback for unusual layouts
    return Path(__file__).resolve().parent / _REG_FILENAME


@lru_cache(maxsize=1)
def _load_registry_raw() -> dict[str, Any]:
    path = _registry_path()
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("curriculum_templates_registry.json must be a JSON object")
    return data


def curriculum_template_keys() -> list[str]:
    """Stable sorted list of template keys."""
    return sorted(_load_registry_raw().keys())


def get_curriculum_template(template_key: str) -> dict[str, Any] | None:
    """Return one template dict or None."""
    key = (template_key or "").strip()
    if not key:
        return None
    raw = _load_registry_raw()
    entry = raw.get(key)
    return dict(entry) if isinstance(entry, dict) else None


def iter_curriculum_templates() -> Iterator[dict[str, Any]]:
    """Yield template dicts sorted by label."""
    raw = _load_registry_raw()
    items = [dict(v) for k, v in raw.items() if isinstance(v, dict)]
    items.sort(key=lambda x: (str(x.get("label") or x.get("template_key") or "")).lower())
    yield from items


def get_template_terminology(template_key: str) -> dict[str, str]:
    t = get_curriculum_template(template_key) or {}
    m = t.get("terminology_map") or {}
    if not isinstance(m, dict):
        return {}
    return {str(k): str(v) for k, v in m.items()}


def get_template_term_labels(template_key: str) -> list[str]:
    t = get_curriculum_template(template_key) or {}
    labels = t.get("term_labels") or []
    if not isinstance(labels, list):
        return []
    return [str(x) for x in labels]


def get_template_subject_seed(template_key: str) -> list[dict[str, Any]]:
    t = get_curriculum_template(template_key) or {}
    seed = t.get("subject_seed") or []
    if not isinstance(seed, list):
        return []
    out: list[dict[str, Any]] = []
    for row in seed:
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def reload_curriculum_templates_cache() -> None:
    """Tests / management commands may call after mutating the JSON file."""
    _load_registry_raw.cache_clear()


__all__ = [
    "curriculum_template_keys",
    "get_curriculum_template",
    "get_template_subject_seed",
    "get_template_term_labels",
    "get_template_terminology",
    "iter_curriculum_templates",
    "reload_curriculum_templates_cache",
]
