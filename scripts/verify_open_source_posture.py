#!/usr/bin/env python3
"""Composite gate: open-source posture (SH-4 hook, public repo, governance, SDK URLs)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_REPO_SLUG = "yimga/school-management-system"
CANONICAL_REPO_URL = f"https://github.com/{CANONICAL_REPO_SLUG}"

GOVERNANCE_FILES = (
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    "docs/GOVERNANCE_OPERATOR_CONTACTS.md",
    "docs/OPEN_SOURCE_POSTURE_AUDIT_2026_06_03.md",
)

SDK_METADATA_PATHS = (
    "packages/runmycampus-webhook-verifier-py/pyproject.toml",
    "packages/runmycampus-webhook-verifier-js/package.json",
    "sdk/pyproject.toml",
    "sdk/js/package.json",
)

LEGACY_REPO_MARKERS = (
    "github.com/runmycampus/runmycampus",
    "github.com/runmycampus/school-management-system",
)


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-github-network",
        action="store_true",
        help="Skip --require-public (offline CI only)",
    )
    args = parser.parse_args()
    errors: list[str] = []
    py = sys.executable

    for rel in GOVERNANCE_FILES:
        if not (ROOT / rel).is_file():
            errors.append(f"missing governance artifact: {rel}")

    for rel in SDK_METADATA_PATHS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing SDK metadata: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if CANONICAL_REPO_URL not in text:
            errors.append(f"{rel}: must reference {CANONICAL_REPO_URL}")
        for marker in LEGACY_REPO_MARKERS:
            if marker in text:
                errors.append(f"{rel}: stale repo URL {marker}")

    dev_surface = ROOT / "apps/schools/developer_surface.py"
    if dev_surface.is_file():
        ds = dev_surface.read_text(encoding="utf-8")
        if "github.com/yimga/school-management-system" not in ds:
            errors.append("apps/schools/developer_surface.py: sdk_repo must point at public repo")
        if "github.com/runmycampus/runmycampus" in ds or "github.com/runmycampus/sdk" in ds:
            errors.append("apps/schools/developer_surface.py: stale sdk_repo URL")

    if _run([py, str(ROOT / "scripts/verify_media_storage_self_host_hook.py")]) != 0:
        errors.append("verify_media_storage_self_host_hook.py failed")

    gh_args = [
        py,
        str(ROOT / "scripts/verify_open_source_github_repo_visibility.py"),
        "--write",
    ]
    if not args.skip_github_network:
        gh_args.append("--require-public")
    if _run(gh_args) != 0:
        errors.append("verify_open_source_github_repo_visibility.py failed")

    readme = ROOT / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        for needle in ("CODE_OF_CONDUCT.md", "SECURITY.md", "CONTRIBUTING.md"):
            if needle not in text:
                errors.append(f"README.md missing link to {needle}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print("OPEN_SOURCE_POSTURE_FAIL", file=sys.stderr)
        return 1

    print("OPEN_SOURCE_POSTURE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
