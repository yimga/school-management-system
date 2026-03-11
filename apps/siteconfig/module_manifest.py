"""
World Engine: single source for active module set by school type.
Loads apps/siteconfig/data/module_manifest.json; get_school_type_config merges inherits.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_manifest_cache: dict | None = None


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "module_manifest.json"


def get_manifest() -> dict:
    """Load and cache module_manifest.json. Returns dict keyed by school type."""
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    path = _manifest_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            _manifest_cache = json.load(f)
        return _manifest_cache
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Failed to load module_manifest.json: %s", e)
        _manifest_cache = {}
        return _manifest_cache


def get_school_type_config(school_type: str) -> dict:
    """
    Return merged config for school_type. Merges inherits (required_apps from base types).
    """
    manifest = get_manifest()
    if not school_type or school_type not in manifest:
        return manifest.get("BASE_SCHOOL", {}).copy() or {}
    cfg = dict(manifest[school_type])
    required = list(cfg.get("required_apps") or [])
    for base in (cfg.get("inherits") or [])[:10]:
        base_cfg = manifest.get(base)
        if base_cfg and isinstance(base_cfg.get("required_apps"), list):
            for app in base_cfg["required_apps"]:
                if app and app not in required:
                    required.append(app)
    cfg["required_apps"] = required
    return cfg
