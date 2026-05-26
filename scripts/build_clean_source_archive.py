"""Build a clean release-source archive that excludes evidence sludge.

Why this exists
---------------
The brutal no-mercy audit (2026-05-25) found that the repo zip shipped
with ~3 GB of evidence sludge: visual-QA screenshots, runserver error
logs, joblib model candidates, click-repro logs, pre_deploy_gate_run.txt
(37 MB), etc. The working tree may legitimately hold these (scanners
read some, runtime verifiers read others), but a *release-source*
archive must not. This script enforces that.

Two modes
---------
* ``build``  - produce ``dist/<name>.tar.gz`` walking the worktree,
               skipping every path matching the deny rules below, and
               failing if any banned glob still survived.
* ``check``  - audit-only. Walk the worktree, report what *would* be
               excluded, and exit 1 if any banned path is staged where
               it would land in a release archive.

The exclusion set mirrors ``.gitattributes export-ignore`` so the two
stay in lockstep; ``.gitattributes`` is the authority when ``git
archive`` is used, this script is the authority when a tarball is
built directly from the worktree (this repo is not always a git tree).

Hard constraints
----------------
* Stdlib only - ``tarfile`` / ``argparse`` / ``fnmatch`` / ``pathlib``.
* Reproducible: ``mtime=0`` on every TarInfo, sorted filename ordering,
  fixed uid/gid/uname/gname, fixed mode bits.
* Never contains: .env, .pem, .key, *.sqlite3, *.log, screenshots,
  visual-qa, click-repro logs, joblib model candidates, autonomous
  execution log, pre_deploy_gate_run.txt (full), or anything under
  artifacts-evidence/.
* Exit 1 the moment a banned path slips through.

CLI
---
::

    python scripts/build_clean_source_archive.py --mode check
    python scripts/build_clean_source_archive.py --mode build \\
        --out dist/runmycampus-clean-source.tar.gz

Self-test
---------
``--mode check`` MUST exit 0 on a clean tree. ``--mode build`` MUST
re-open the produced tarball and re-verify the banned patterns are
absent before declaring success.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Banned globs match against the path RELATIVE to ROOT, using forward
# slashes. A trailing "/**" recurses into the directory. A trailing "/"
# matches the directory itself (no children needed). Patterns without
# wildcards match exactly.
BANNED_PATTERNS: tuple[str, ...] = (
    # secrets / credentials / databases
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.sqlite3",
    "*.sqlite3-journal",
    "*.sqlite3.malformed",
    "*.sqlite3.corrupted",
    # runtime / OS / IDE
    "__pycache__/**",
    ".pytest_cache/**",
    ".django_test_dbs/**",
    ".tmp_test_artifacts/**",
    ".tmp_test_raw_sql_usage/**",
    ".idea/**",
    ".vscode/**",
    ".cursor/**",
    "node_modules/**",
    "staticfiles/**",
    "tmp/**",
    "logs/**",
    "test-results/**",
    "backups/**",
    "*.pid",
    "*.swp",
    "*.swo",
    "*.bak",
    "Thumbs.db",
    ".DS_Store",
    # evidence sludge (batch 1507 cleanup)
    "artifacts-evidence/**",
    "artifacts/db_snapshots/**",
    "artifacts/visual-qa/**",
    "artifacts/apple-class/**",
    "artifacts/theme-experience-dual-plane/**",
    "artifacts/manager-surface-parity/**",
    "artifacts/live_browser_ux_certification/**",
    "artifacts/marketing-snapshots/**",
    "artifacts/preview-shell-lane2/**",
    "artifacts/tenant-portal-lane2/**",
    "artifacts/admin-platform-proof/**",
    "artifacts/runtime/**",
    "artifacts/security/**",
    "artifacts/*.png",
    "artifacts/*.pid",
    "artifacts/manager-playwright-auth.json",
    "var/evidence/click-repro/**",
    "var/cand.joblib",
    "var/at_risk_v2_2026q2.joblib",
    "var/at_risk/**",
    "var/help-*",
    "var/feedback-*",
    "var/all-hc-*",
    "var/audit-1310-*",
    "var/single-staff-*",
    "var/last-test-*",
    "var/verify-interaction-*",
    "var/pytest-cache-files-*/**",
    "var/tmp/**",
    "*.log",
    "*.webm",
    "*.mp4",
)

# Marketing media is intentionally shipped; whitelist before the *.mp4 rule
# would otherwise strip it.
ALLOWLIST_PATTERNS: tuple[str, ...] = (
    "static/marketing/video/hero-home.mp4",
    "static/marketing/img/hero-home-poster.svg",
    "static/marketing/fonts/**/*.woff2",
    "static/marketing/css/marketing-critical.min.css",
    "static/marketing/css/marketing-enhanced.min.css",
    "static/marketing/css/marketing-bundles.manifest.json",
)


def _path_matches(rel_posix: str, pattern: str) -> bool:
    """Return True if ``rel_posix`` is excluded by ``pattern``.

    ``pattern`` is gitignore-flavored: ``**`` recurses into directories,
    trailing ``/`` indicates a directory. We translate to fnmatch
    semantics by handling ``**`` explicitly.
    """
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        if rel_posix == prefix:
            return True
        if rel_posix.startswith(prefix + "/"):
            return True
        return False
    if "/**/" in pattern:
        left, _, right = pattern.partition("/**/")
        return rel_posix.startswith(left + "/") and fnmatch.fnmatch(rel_posix, "*/" + right)
    if pattern.endswith("/"):
        prefix = pattern[:-1]
        return rel_posix == prefix or rel_posix.startswith(prefix + "/")
    # Direct fnmatch handles single-segment globs (`*.log`, `*.sqlite3`,
    # `var/help-*`) and exact matches.
    return fnmatch.fnmatch(rel_posix, pattern) or any(
        fnmatch.fnmatch(seg, pattern) for seg in rel_posix.split("/")
    )


def is_banned(rel_posix: str) -> bool:
    """Return True if ``rel_posix`` should be excluded from the archive."""
    for pattern in ALLOWLIST_PATTERNS:
        if _path_matches(rel_posix, pattern):
            return False
    for pattern in BANNED_PATTERNS:
        if _path_matches(rel_posix, pattern):
            return True
    return False


def iter_repo_files(root: Path) -> list[Path]:
    """Walk ``root`` and return every regular file, sorted, sans .git."""
    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == ".git":
            continue
        out.append(path)
    out.sort()
    return out


def audit_tree(root: Path) -> tuple[list[str], list[str]]:
    """Return (included_paths, banned_paths_found_in_worktree)."""
    included: list[str] = []
    banned_present: list[str] = []
    for path in iter_repo_files(root):
        rel_posix = path.relative_to(root).as_posix()
        if is_banned(rel_posix):
            banned_present.append(rel_posix)
        else:
            included.append(rel_posix)
    return included, banned_present


def _normalize_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip uid/gid/mtime for reproducibility."""
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.mode = info.mode & 0o755 if info.isdir() else info.mode & 0o644
    return info


def build_archive(root: Path, out_path: Path) -> tuple[int, int]:
    """Build a tar.gz at ``out_path`` and return (files_in, files_skipped)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = iter_repo_files(root)
    included = 0
    skipped = 0
    with tarfile.open(out_path, "w:gz") as tar:
        for path in files:
            rel_posix = path.relative_to(root).as_posix()
            if is_banned(rel_posix):
                skipped += 1
                continue
            tar.add(
                str(path),
                arcname=rel_posix,
                filter=_normalize_tarinfo,
            )
            included += 1
    return included, skipped


def verify_archive(out_path: Path) -> list[str]:
    """Re-open the built tarball and return any banned paths that slipped in."""
    leaks: list[str] = []
    with tarfile.open(out_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isdir():
                continue
            if is_banned(member.name):
                leaks.append(member.name)
    return leaks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a clean release-source archive (release hygiene gate).",
    )
    parser.add_argument(
        "--mode",
        choices=("check", "build"),
        default="check",
        help="check = audit-only; build = produce dist/<name>.tar.gz",
    )
    parser.add_argument(
        "--out",
        default="dist/runmycampus-clean-source.tar.gz",
        help="Output tarball path (build mode only).",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Print every excluded path (verbose).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="In check mode, exit 1 if any banned path is present in the worktree.",
    )
    args = parser.parse_args(argv)

    included, banned = audit_tree(ROOT)
    print(
        f"[build_clean_source_archive] worktree files={len(included) + len(banned)} "
        f"included={len(included)} banned-present={len(banned)}",
        file=sys.stderr,
    )
    if args.show_skipped:
        for rel in banned:
            print(f"  skip: {rel}")

    if args.mode == "check":
        if args.strict and banned:
            print(
                f"[build_clean_source_archive] STRICT mode: {len(banned)} banned "
                "path(s) present in worktree. .gitattributes/.gitignore will strip "
                "them at archive time but a clean tree is preferred.",
                file=sys.stderr,
            )
            return 1
        return 0

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    in_count, skip_count = build_archive(ROOT, out_path)
    print(
        f"[build_clean_source_archive] built {out_path} files_in={in_count} "
        f"files_skipped={skip_count} size_bytes={out_path.stat().st_size}",
        file=sys.stderr,
    )

    leaks = verify_archive(out_path)
    if leaks:
        print(
            f"[build_clean_source_archive] FAIL: {len(leaks)} banned path(s) "
            "survived into the tarball:",
            file=sys.stderr,
        )
        for leak in leaks[:20]:
            print(f"  leak: {leak}", file=sys.stderr)
        return 1

    print("[build_clean_source_archive] OK: archive is clean.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
