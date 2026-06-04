#!/usr/bin/env python3
"""Record GitHub repo visibility for canonical SDK metadata vs workspace origin.

Unauthenticated GitHub API returns 200 for public repos and 404 for private or
missing repos (same status). Use --require-public in release prep only when an
operator has confirmed visibility out-of-band.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DEFAULT = "yimga/school-management-system"
_SDK_REPO_PATTERNS = (
    re.compile(r'Repository\s*=\s*"https://github\.com/([^/]+/[^/"]+)"'),
    re.compile(r"<https://github\.com/([^/]+/[^/>]+)/issues>"),
)


def _discover_canonical_repos() -> list[str]:
    repos: set[str] = {CANONICAL_DEFAULT}
    scan_roots = (
        ROOT / "packages" / "runmycampus-webhook-verifier-py" / "pyproject.toml",
        ROOT / "packages" / "runmycampus-webhook-verifier-js" / "package.json",
        ROOT / "sdk" / "pyproject.toml",
    )
    for path in scan_roots:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _SDK_REPO_PATTERNS:
            for match in pattern.finditer(text):
                repos.add(match.group(1).rstrip("/"))
    return sorted(repos)


def _git_origin_repo() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", out)
    return m.group(1) if m else None


def _github_api_status(repo: str) -> dict[str, object]:
    url = f"https://api.github.com/repos/{repo}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "runmycampus-open-source-visibility-verifier",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {
                "http_status": resp.status,
                "visibility": "public" if not body.get("private") else "private",
                "full_name": body.get("full_name"),
                "html_url": body.get("html_url"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "http_status": exc.code,
            "visibility": "not_found_or_private",
            "note": "GitHub API 404 means private or repo does not exist (unauthenticated).",
        }
    except urllib.error.URLError as exc:
        return {"http_status": 0, "visibility": "error", "error": str(exc.reason)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-public",
        action="store_true",
        help="Exit 1 unless every checked repo returns HTTP 200 and visibility public",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write docs/generated/open_source_github_repo_visibility.json",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Additional owner/repo to check (repeatable)",
    )
    args = parser.parse_args()

    repos = sorted(
        set(_discover_canonical_repos())
        | set(args.repo)
        | ({_git_origin_repo()} if _git_origin_repo() else set())
    )
    checks = {repo: _github_api_status(repo) for repo in repos}
    origin = _git_origin_repo()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_sdk_default": CANONICAL_DEFAULT,
        "workspace_origin": origin,
        "issue_template_urls_use": origin or "see .github/ISSUE_TEMPLATE/config.yml",
        "repos": checks,
    }

    if args.write:
        out = ROOT / "docs" / "generated" / "open_source_github_repo_visibility.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")

    failures: list[str] = []
    for repo, info in checks.items():
        status = info.get("http_status")
        vis = info.get("visibility")
        print(f"{repo}: HTTP {status} ({vis})")
        if args.require_public and (status != 200 or vis != "public"):
            failures.append(repo)

    if failures:
        print(
            "FAIL: --require-public: not public or missing: "
            + ", ".join(failures),
            file=sys.stderr,
        )
        print(
            "Operator: confirm canonical org repo in GitHub Settings → "
            "Change visibility, or update SDK pyproject Repository URLs.",
            file=sys.stderr,
        )
        return 1

    print("OPEN_SOURCE_GITHUB_REPO_VISIBILITY_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
