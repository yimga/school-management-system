"""Isomorphic IAM display — invariant codes with tenant-local labels (cockpit_payload)."""

from __future__ import annotations

from typing import Any



def _school_settings(school) -> Any | None:
    if school is None:
        return None
    try:
        from apps.siteconfig.config_service import get_effective_site_settings

        # config-resolver-allow: namespace object returned to callers (helper contract)
        return get_effective_site_settings(school)
    except Exception:
        return None


def load_iam_localization(school) -> dict[str, Any]:
    """Read `iam_localization` from site settings cockpit_payload (tenant-defined)."""
    site = _school_settings(school)
    if site is None:
        return {}
    payload = getattr(site, "cockpit_payload", None) or {}
    if not isinstance(payload, dict):
        return {}
    block = payload.get("iam_localization") or {}
    return block if isinstance(block, dict) else {}


def localized_role_label(role_code: str, school=None, *, fallback: str | None = None) -> str:
    """Map internal role code (e.g. ADMIN) to tenant display name."""
    code = (role_code or "").strip().upper()
    if not code:
        return fallback or ""
    block = load_iam_localization(school)
    mappings = block.get("role_mappings") or {}
    entry = mappings.get(code) or mappings.get(f"ROLE_{code}")
    if isinstance(entry, dict):
        label = (entry.get("local_display_name") or entry.get("display") or "").strip()
        if label:
            return label
    if fallback:
        return fallback
    return code.replace("_", " ").title()


def localized_permission_label(permission_code: str, school=None) -> str:
    """Map invariant permission code to tenant-facing action label."""
    code = (permission_code or "").strip()
    if not code:
        return ""
    block = load_iam_localization(school)
    actions = block.get("action_labels") or block.get("actions") or {}
    if isinstance(actions, dict) and code in actions:
        val = actions[code]
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            return (val.get("display") or val.get("label") or code).strip()
    return code.replace(".", " · ").replace("_", " ")


def localized_government_body_label(school, default: str = "") -> str:
    block = load_iam_localization(school)
    return (block.get("government_body_label") or default or "").strip() or default
