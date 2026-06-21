"""
Deploy freshness metadata for post-deploy cache busting.

Exposes git commit + service-worker CACHE_VERSION to templates and the SW asset
manifest so the browser can detect stale shells after Render deploys.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SW_PATH = _REPO_ROOT / "static" / "js" / "service-worker.js"
_CACHE_VERSION_RE = re.compile(
    r'const\s+CACHE_VERSION\s*=\s*"(?P<value>[^"]+)"\s*;'
)
_COMMIT_ENV_KEYS = (
    "RENDER_GIT_COMMIT",
    "GIT_COMMIT",
    "SOURCE_VERSION",
    "COMMIT_SHA",
)


def resolve_deploy_commit_sha(*, short: bool = False) -> str:
    """Return the active deploy commit or ``unknown`` when unset/invalid."""
    for key in _COMMIT_ENV_KEYS:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", raw):
            continue
        return raw[:12] if short else raw
    return "unknown"


@lru_cache(maxsize=1)
def read_service_worker_cache_version() -> str:
    """Parse CACHE_VERSION from the canonical service worker source file."""
    try:
        text = _SW_PATH.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = _CACHE_VERSION_RE.search(text)
    return match.group("value") if match else "unknown"


def build_deploy_freshness_context() -> dict[str, str]:
    return {
        "rmc_deploy_commit_sha": resolve_deploy_commit_sha(),
        "rmc_sw_cache_version": read_service_worker_cache_version(),
    }
