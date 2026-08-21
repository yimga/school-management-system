"""
Deploy freshness metadata for post-deploy cache busting.

Exposes git commit + service-worker CACHE_VERSION to templates and the SW asset
manifest so the browser can detect stale shells after Render deploys.

Resolution order for the commit, most authoritative first:

1. A deploy environment variable (``RENDER_GIT_COMMIT`` and friends). Render sets
   this for free; a CI pipeline can set it explicitly.
2. ``.build-stamp.json`` at the repo root, written at image build time by
   ``scripts/write_build_stamp.py``. This is what lets a self-hosted Docker
   appliance say what it is running.
3. ``.git/HEAD``, read as plain files -- no ``git`` binary, no subprocess. Covers
   a plain checkout (dev, bare-metal deploy) and an image whose build context
   still carried ``.git``.

An env var that is SET but malformed stops the chain at ``unknown`` instead of
falling through. Falling through would answer a different question from the one
asked: the deployer explicitly declared a commit, and quietly substituting the
SHA of whatever source happens to sit on disk turns a visible config error into a
confident wrong answer. Post-deploy smoke compares this value against the commit
it *meant* to ship, so a wrong answer is worse than no answer.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SW_PATH = _REPO_ROOT / "static" / "js" / "service-worker.js"
_CACHE_VERSION_RE = re.compile(
    r'const\s+CACHE_VERSION\s*=\s*"(?P<value>[^"]+)"\s*;'
)
#: Public so the build-time stamper reads the same keys in the same order.
COMMIT_ENV_KEYS = (
    "RENDER_GIT_COMMIT",
    "GIT_COMMIT",
    "SOURCE_VERSION",
    "COMMIT_SHA",
)
_BUILD_TIME_ENV_KEYS = (
    "BUILD_TIME",
    "BUILD_TIMESTAMP",
    "RENDER_CREATED_AT",
)
_ENVIRONMENT_ENV_KEYS = (
    "RENDER_SERVICE_NAME",
    "RMC_ENVIRONMENT",
    "DJANGO_ENV",
    "ENVIRONMENT",
)

BUILD_STAMP_FILENAME = ".build-stamp.json"

UNKNOWN = "unknown"

_SHA_RE = re.compile(r"[0-9a-fA-F]{7,64}")
_FULL_SHA_RE = re.compile(r"[0-9a-fA-F]{40,64}")

#: Values are echoed into an HTTP response and a ``<meta>`` tag, so cap them --
#: a hostile or accidental multi-kilobyte env var must not become the payload.
_MAX_VALUE_CHARS = 128


def _env_value(keys: tuple[str, ...]) -> str:
    """First non-empty value among ``keys``, or the empty string."""
    for key in keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw[:_MAX_VALUE_CHARS]
    return ""


def build_stamp_path() -> Path:
    override = (os.environ.get("RMC_BUILD_STAMP_PATH") or "").strip()
    return Path(override) if override else _REPO_ROOT / BUILD_STAMP_FILENAME


@lru_cache(maxsize=1)
def read_build_stamp() -> dict[str, str]:
    """Parse the build stamp baked into the image, or ``{}``.

    Never raises. A missing, unreadable, non-JSON or non-object stamp is simply
    an absent stamp -- a stamp is a convenience, never a boot requirement.
    """
    try:
        raw = build_stamp_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): str(value)[:_MAX_VALUE_CHARS]
        for key, value in data.items()
        if isinstance(value, (str, int, float))
    }


def _resolve_git_dir() -> Path | None:
    """The real ``.git`` directory for this checkout, following a worktree file."""
    candidate = _REPO_ROOT / ".git"
    try:
        if candidate.is_dir():
            return candidate
        if not candidate.is_file():
            return None
        # A linked worktree stores "gitdir: <path to .git/worktrees/<name>>".
        text = candidate.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    pointed = Path(text.split(":", 1)[1].strip())
    if not pointed.is_absolute():
        pointed = _REPO_ROOT / pointed
    try:
        return pointed if pointed.is_dir() else None
    except OSError:
        return None


def _ref_search_dirs(git_dir: Path) -> list[Path]:
    """``git_dir`` plus its common dir -- packed-refs lives in the latter."""
    dirs = [git_dir]
    try:
        rel = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return dirs
    if not rel:
        return dirs
    common = Path(rel)
    if not common.is_absolute():
        common = git_dir / common
    try:
        common = common.resolve()
    except OSError:
        return dirs
    if common != git_dir:
        dirs.append(common)
    return dirs


def _read_sha_for_ref(git_dir: Path, ref: str) -> str:
    search_dirs = _ref_search_dirs(git_dir)
    for base in search_dirs:
        try:
            value = (base / ref).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if _FULL_SHA_RE.fullmatch(value):
            return value
    for base in search_dirs:
        try:
            packed = (base / "packed-refs").read_text(encoding="utf-8")
        except OSError:
            continue
        for line in packed.splitlines():
            line = line.strip()
            # "#" is the header; "^<sha>" annotates the preceding tag.
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref and _FULL_SHA_RE.fullmatch(sha):
                return sha
    return ""


@lru_cache(maxsize=1)
def read_git_head_sha() -> str:
    """The checked-out commit read straight from ``.git``, or the empty string.

    Plain file reads on purpose. ``git rev-parse`` would need the binary present
    and a subprocess on a request path, and the runtime image is not guaranteed
    to carry git.
    """
    git_dir = _resolve_git_dir()
    if git_dir is None:
        return ""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not head.startswith("ref:"):
        return head if _FULL_SHA_RE.fullmatch(head) else ""
    return _read_sha_for_ref(git_dir, head.split(":", 1)[1].strip())


def resolve_deploy_commit_sha(*, short: bool = False) -> str:
    """Return the active deploy commit or ``unknown``.

    See the module docstring for the resolution order, and for why a malformed
    env var deliberately does NOT fall through to the next source.
    """
    declared = _env_value(COMMIT_ENV_KEYS)
    if declared:
        if not _SHA_RE.fullmatch(declared):
            return UNKNOWN
        return declared[:12] if short else declared

    for candidate in (
        (read_build_stamp().get("commit_sha") or "").strip(),
        read_git_head_sha(),
    ):
        if candidate and _SHA_RE.fullmatch(candidate):
            return candidate[:12] if short else candidate
    return UNKNOWN


def resolve_build_time() -> str:
    """Return when this build was produced, or ``unknown``."""
    declared = _env_value(_BUILD_TIME_ENV_KEYS)
    if declared:
        return declared
    stamped = (read_build_stamp().get("build_time") or "").strip()
    return stamped[:_MAX_VALUE_CHARS] if stamped else UNKNOWN


def resolve_deploy_environment() -> str:
    """Return the deploy tier / service label, or ``unknown``.

    ``ENVIRONMENT`` is the label a self-hosted box should set. Deliberately NOT
    ``DJANGO_ENV``: ``config/settings.py`` feeds that one into
    ``_IS_CLOUD_DEPLOYED``, so an operator labelling their appliance
    ``DJANGO_ENV=production`` would flip the box into hosted-cloud posture --
    losing its local Ollama tier and switching on hosted conversion / paid-install
    enforcement. A display label must not be able to change routing.
    """
    declared = _env_value(_ENVIRONMENT_ENV_KEYS)
    if declared:
        return declared
    stamped = (read_build_stamp().get("environment") or "").strip()
    return stamped[:_MAX_VALUE_CHARS] if stamped else UNKNOWN


@lru_cache(maxsize=1)
def read_service_worker_cache_version() -> str:
    """Parse CACHE_VERSION from the canonical service worker source file."""
    try:
        text = _SW_PATH.read_text(encoding="utf-8")
    except OSError:
        return UNKNOWN
    match = _CACHE_VERSION_RE.search(text)
    return match.group("value") if match else UNKNOWN


def reset_deploy_meta_caches() -> None:
    """Drop every cached file read. For tests; production files never change."""
    read_build_stamp.cache_clear()
    read_git_head_sha.cache_clear()
    read_service_worker_cache_version.cache_clear()


def build_deploy_freshness_context() -> dict[str, str]:
    return {
        "rmc_deploy_commit_sha": resolve_deploy_commit_sha(),
        "rmc_sw_cache_version": read_service_worker_cache_version(),
    }
