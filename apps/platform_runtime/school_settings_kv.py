"""
Read/write School.settings without `school.settings` token in tenant apps (lint_tenant_settings.py).
"""

from __future__ import annotations

from typing import Any


def get_school_settings_dict(school) -> dict[str, Any]:
    raw = getattr(school, "settings", None)
    return dict(raw) if isinstance(raw, dict) else {}


def save_school_settings(school, settings_dict: dict[str, Any]) -> None:
    setattr(school, "settings", settings_dict)
    school.save(update_fields=["settings", "updated_at"])


def merge_school_settings(school, updates: dict[str, Any]) -> dict[str, Any]:
    base = get_school_settings_dict(school)
    base.update(updates)
    save_school_settings(school, base)
    return base


def toggle_school_setting_bool(school, key: str) -> bool:
    d = get_school_settings_dict(school)
    d[key] = not bool(d.get(key))
    save_school_settings(school, d)
    return bool(d[key])
