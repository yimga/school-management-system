"""What code and which assets a deployment is made of — one hash the far side can compare.

THE GAP THIS CLOSES. A box can already say which *migrations* it is on
(:mod:`apps.sync_engine.schema_guard`) and which *commit* it was built from
(:mod:`apps.siteconfig.deploy_meta`). Neither answers the question an upgrade needs:
"which FILES differ between us, and which of them may I safely fetch?" A commit sha is
opaque — two boxes on the same sha can still differ if one of them failed a
``collectstatic`` — and a migration head says nothing at all about a template or a
JS bundle.

So this module produces a ``system_manifest.json``: every shippable file mapped to its
SHA-256, a category, its size, and the migration index it belongs to. The manifest's own
hash is a single value that two deployments can exchange in one HTTP header, and a
mismatch is not merely a signal that *something* changed — the two manifests subtract to
give the exact file list.

DETERMINISM IS THE WHOLE CONTRACT. The manifest hash is computed over the canonical JSON
of the file map plus the migration heads, and deliberately NOT over ``generated_at`` or
the absolute root path. Two builds of identical source therefore produce an identical
hash, which is what makes "we are in parity" a fact rather than a guess. Anything that
would make the hash time-varying belongs outside :func:`SystemManifestGenerator.digest`.

WHAT IS DELIBERATELY NOT IN IT. Databases, media, ``.git``, virtualenvs, caches,
collected ``staticfiles/`` output (it is a *product* of ``static/``, and shipping both
would double every asset), and the test suite. A manifest is the shippable surface of a
deployment, not a backup of the checkout.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone as _tz
from pathlib import Path
from typing import Iterable, Iterator

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "system_manifest.json"
MANIFEST_FORMAT_VERSION = 1

# ── Categories ───────────────────────────────────────────────────────────────
# The category is what lets an edge box apply HALF an upgrade safely: templates and
# static assets can be swapped under a running worker, a migration cannot. Rollout
# policy keys off this and nothing else, so the classifier stays small and total.
APP_CORE = "APP_CORE"          # importable python that defines behaviour
UI_TEMPLATE = "UI_TEMPLATE"    # django templates — swappable without a code reload
STATIC_ASSET = "STATIC_ASSET"  # js/css/img/font — swappable, then collectstatic
MIGRATION = "MIGRATION"        # schema changes — the only category that touches the DB
CONFIG = "CONFIG"              # settings, urls, requirements, deploy descriptors
LOCALE = "LOCALE"              # gettext catalogues

CATEGORIES = (APP_CORE, UI_TEMPLATE, STATIC_ASSET, MIGRATION, CONFIG, LOCALE)

# Categories an edge box may apply WITHOUT reloading the python interpreter. Used by the
# rollout manager's "assets" mode, which is the safe default for a school appliance.
ASSET_CATEGORIES = frozenset({UI_TEMPLATE, STATIC_ASSET, LOCALE})

_HASH_READ_BYTES = 1024 * 1024  # magic-number-allow: 1 MiB hashing read size

# Directory names pruned wholesale during the crawl. Pruned by NAME at every depth, so a
# nested ``__pycache__`` or ``node_modules`` costs nothing to skip.
DEFAULT_EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "staticfiles",          # collectstatic OUTPUT — a product of static/, never shipped
    "media",                # tenant uploads — moves on the file channel, not here
    "backups", "artifacts", "logs",
    ".rmc_ota_staging",     # our own staging root; a manifest must never describe itself
    ".rmc_sync_staging",
    "htmlcov", ".idea", ".vscode",
})

# Suffixes never shipped. Databases and their sidecars are the important ones: a box
# whose db_*.sqlite3 landed in a manifest would fetch another deployment's data.
DEFAULT_EXCLUDE_SUFFIXES = frozenset({
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".db",
    ".log", ".tmp", ".swp", ".orig", ".rej",
    ".mo",                  # compiled catalogues are rebuilt from .po at apply time
})

DEFAULT_EXCLUDE_GLOBS = (
    "db_*.sqlite3*",
    "*.egg-info/*",
    ".env*",
    "system_manifest.json",  # the manifest never describes itself
    ".build-stamp.json",     # build identity is resolved separately, per deployment
)

# Tests are code, but they are not shippable surface: an appliance never runs them and
# they are ~40% of the file count. Opt back in with ``include_tests=True``.
_TEST_DIR_NAMES = frozenset({"tests", "test"})
_TEST_FILE_RE = re.compile(r"^(test_.*|.*_test)\.py$")

_MIGRATION_INDEX_RE = re.compile(r"^(\d{4})_")


def _sha256_file(path: Path) -> tuple[str, int]:
    """``(hexdigest, size_bytes)`` for one file, read in bounded chunks."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_READ_BYTES)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def canonical_json_bytes(payload) -> bytes:
    """Stable bytes for hashing: sorted keys, no incidental whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class ManifestEntry:
    path: str
    sha256: str
    bytes: int
    category: str
    app_label: str = ""
    migration_index: str = ""

    def as_dict(self) -> dict:
        out = {
            "sha256": self.sha256,
            "bytes": self.bytes,
            "category": self.category,
        }
        if self.app_label:
            out["app_label"] = self.app_label
        if self.migration_index:
            out["migration_index"] = self.migration_index
        return out


@dataclass
class SystemManifestGenerator:
    """Crawl a deployment root and emit an immutable, versioned manifest.

    ``root`` defaults to ``settings.BASE_DIR``. Nothing here imports Django models or
    touches a database — the generator runs at image-build time, in CI, and inside a
    management command with equal validity, and must not require a live app registry.
    """

    root: Path
    include_tests: bool = False
    exclude_dirs: frozenset = DEFAULT_EXCLUDE_DIRS
    exclude_suffixes: frozenset = DEFAULT_EXCLUDE_SUFFIXES
    exclude_globs: tuple = DEFAULT_EXCLUDE_GLOBS
    version_label: str = ""
    channel: str = "stable"
    _entries: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.root = Path(self.root).resolve()

    # ── classification ───────────────────────────────────────────────────────
    @staticmethod
    def categorise(relative_path: str) -> str:
        """Category for one repo-relative POSIX path. Total: every path gets one."""
        parts = relative_path.split("/")
        name = parts[-1]
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""

        if "migrations" in parts and suffix == ".py" and name != "__init__.py":
            return MIGRATION
        if "templates" in parts or suffix in (".html", ".htm", ".jinja", ".jinja2"):
            return UI_TEMPLATE
        if "locale" in parts or suffix in (".po", ".pot"):
            return LOCALE
        if "static" in parts or suffix in (
            ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".map",
            ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif",
            ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ):
            return STATIC_ASSET
        if parts[0] in ("config", "deploy", "scripts") or name in (
            "requirements.txt", "package.json", "package-lock.json", "render.yaml",
            "manage.py", "build.sh", "deploy.sh", "Dockerfile", "docker-compose.yml",
        ):
            return CONFIG
        if suffix == ".py":
            return APP_CORE
        # Anything else that survived the exclusions is data the app reads at runtime
        # (json catalogues, .txt fixtures). APP_CORE is the conservative bucket: it is
        # the one the rollout manager refuses to hot-swap.
        return APP_CORE

    @staticmethod
    def app_label_for(relative_path: str) -> str:
        """``apps/finance/models.py`` -> ``finance``; anything else -> ``""``."""
        parts = relative_path.split("/")
        if len(parts) >= 2 and parts[0] == "apps":
            return parts[1]
        return ""

    @staticmethod
    def migration_index_for(relative_path: str) -> str:
        """``0094_ledger_split.py`` -> ``0094``. Empty when not a migration."""
        parts = relative_path.split("/")
        if "migrations" not in parts:
            return ""
        match = _MIGRATION_INDEX_RE.match(parts[-1])
        return match.group(1) if match else ""

    # ── crawl ────────────────────────────────────────────────────────────────
    def _excluded_by_glob(self, relative_path: str) -> bool:
        from fnmatch import fnmatch

        return any(fnmatch(relative_path, pattern) for pattern in self.exclude_globs)

    def iter_files(self) -> Iterator[str]:
        """Yield repo-relative POSIX paths, in no particular order."""
        root = str(self.root)
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune in place so os.walk never descends. Sorted for a stable walk order,
            # which keeps a partial run's log readable even though the manifest is
            # sorted again at build time.
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in self.exclude_dirs
                and not (not self.include_tests and d in _TEST_DIR_NAMES)
            )
            for filename in sorted(filenames):
                if not self.include_tests and _TEST_FILE_RE.match(filename):
                    continue
                suffix = os.path.splitext(filename)[1].lower()
                if suffix in self.exclude_suffixes:
                    continue
                absolute = os.path.join(dirpath, filename)
                relative = os.path.relpath(absolute, root).replace(os.sep, "/")
                if self._excluded_by_glob(relative):
                    continue
                yield relative

    def _entry(self, relative_path: str) -> ManifestEntry | None:
        absolute = self.root / relative_path
        try:
            sha, size = _sha256_file(absolute)
        except OSError as exc:  # a file that vanished mid-crawl is not worth a failure
            logger.warning("system manifest: skipping unreadable %s (%s)", relative_path, exc)
            return None
        return ManifestEntry(
            path=relative_path,
            sha256=sha,
            bytes=size,
            category=self.categorise(relative_path),
            app_label=self.app_label_for(relative_path),
            migration_index=self.migration_index_for(relative_path),
        )

    # ── build ────────────────────────────────────────────────────────────────
    def entries(self) -> dict[str, ManifestEntry]:
        if not self._entries:
            built: dict[str, ManifestEntry] = {}
            for relative in self.iter_files():
                entry = self._entry(relative)
                if entry is not None:
                    built[relative] = entry
            self._entries = dict(sorted(built.items()))
        return self._entries

    def migration_heads(self) -> dict[str, str]:
        """Highest migration index per app, read from the FILES rather than the database.

        Deliberately not ``schema_guard.local_migration_heads``: that answers "what has
        this database applied", which is a different question and needs a live
        connection. A manifest describes a code tree, and must be buildable in a Docker
        layer with no database in existence.
        """
        heads: dict[str, str] = {}
        for entry in self.entries().values():
            if entry.category != MIGRATION or not entry.app_label or not entry.migration_index:
                continue
            current = heads.get(entry.app_label, "")
            if entry.migration_index > current:
                heads[entry.app_label] = entry.migration_index
        return dict(sorted(heads.items()))

    def digest(self) -> str:
        """The manifest hash — over content only, never over time or location."""
        payload = {
            "format": MANIFEST_FORMAT_VERSION,
            "files": {path: entry.as_dict() for path, entry in self.entries().items()},
            "migration_heads": self.migration_heads(),
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    def build(self) -> dict:
        entries = self.entries()
        by_category: dict[str, int] = {}
        total_bytes = 0
        for entry in entries.values():
            by_category[entry.category] = by_category.get(entry.category, 0) + 1
            total_bytes += entry.bytes
        return {
            "format": MANIFEST_FORMAT_VERSION,
            "manifest_hash": self.digest(),
            "version_label": self.version_label or _default_version_label(),
            "channel": self.channel,
            "generated_at": datetime.now(_tz.utc).isoformat(timespec="seconds"),
            "engine_commit": _engine_commit(),
            "file_count": len(entries),
            "total_bytes": total_bytes,
            "counts_by_category": dict(sorted(by_category.items())),
            "migration_heads": self.migration_heads(),
            "files": {path: entry.as_dict() for path, entry in entries.items()},
        }

    def write(self, destination: str | os.PathLike | None = None) -> Path:
        """Write ``system_manifest.json`` and return the path written."""
        target = Path(destination) if destination else (self.root / MANIFEST_FILENAME)
        payload = self.build()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def _default_version_label() -> str:
    return datetime.now(_tz.utc).strftime("%Y.%m.%d")


def _engine_commit() -> str:
    """The deploy commit, when it is resolvable. Advisory only — never hashed."""
    try:
        from apps.siteconfig.deploy_meta import resolve_deploy_commit_sha

        return resolve_deploy_commit_sha()
    except Exception:  # noqa: BLE001 - a manifest must build without Django configured
        return ""


# ── reading a manifest back ──────────────────────────────────────────────────
def manifest_path(root: str | os.PathLike | None = None) -> Path:
    """Where this deployment's manifest lives.

    ``RMC_OTA_MANIFEST_PATH`` overrides, so a read-only image can keep its manifest on a
    writable volume without the rest of the code caring.
    """
    from django.conf import settings

    override = str(getattr(settings, "RMC_OTA_MANIFEST_PATH", "") or "").strip()
    if override:
        return Path(override)
    base = Path(root) if root else Path(getattr(settings, "BASE_DIR", "."))
    return base / MANIFEST_FILENAME


def load_manifest(path: str | os.PathLike | None = None) -> dict:
    """Read a manifest from disk. ``{}`` when absent or unreadable — never raises.

    Absence is an ordinary state, not an error: a deployment that has never generated a
    manifest simply declares nothing and the far side treats it exactly as it treated
    every box before this feature existed.
    """
    target = Path(path) if path else manifest_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        loaded = json.loads(raw)
    except ValueError:
        logger.warning("system manifest at %s is not valid JSON; ignoring", target)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def local_manifest_hash(path: str | os.PathLike | None = None) -> str:
    """This deployment's manifest hash, or ``""`` when it has none."""
    return str(load_manifest(path).get("manifest_hash") or "")


def verify_tree(manifest: dict, root: str | os.PathLike, *, paths: Iterable[str] | None = None) -> dict:
    """Re-hash files under ``root`` against ``manifest`` and report every disagreement.

    Returns ``{"ok": bool, "checked": int, "mismatched": [...], "missing": [...]}``.

    This is the gate the rollout manager runs on a STAGED tree before anything is
    promoted, and it is the reason a truncated download cannot reach a running box: the
    bytes are on disk but they are not the bytes the manifest names, and a promotion that
    trusted the transfer's own success report would never find that out.
    """
    files = manifest.get("files") or {}
    wanted = list(paths) if paths is not None else list(files)
    base = Path(root)
    mismatched: list[str] = []
    missing: list[str] = []
    checked = 0
    for relative in wanted:
        declared = (files.get(relative) or {}).get("sha256") or ""
        if not declared:
            continue
        candidate = base / relative
        if not candidate.is_file():
            missing.append(relative)
            continue
        try:
            actual, _size = _sha256_file(candidate)
        except OSError:
            missing.append(relative)
            continue
        checked += 1
        if actual != declared:
            mismatched.append(relative)
    return {
        "ok": not mismatched and not missing,
        "checked": checked,
        "mismatched": sorted(mismatched),
        "missing": sorted(missing),
    }


__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_FORMAT_VERSION",
    "APP_CORE",
    "UI_TEMPLATE",
    "STATIC_ASSET",
    "MIGRATION",
    "CONFIG",
    "LOCALE",
    "CATEGORIES",
    "ASSET_CATEGORIES",
    "ManifestEntry",
    "SystemManifestGenerator",
    "canonical_json_bytes",
    "manifest_path",
    "load_manifest",
    "local_manifest_hash",
    "verify_tree",
]
