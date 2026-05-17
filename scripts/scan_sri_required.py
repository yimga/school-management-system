#!/usr/bin/env python
"""Subresource Integrity (SRI) requirement scanner.

12-pillar audit P1 follow-up. Third-party `<script src="https://...">` or
`<link rel="stylesheet" href="https://...">` tags without an
``integrity=`` attribute let a compromised CDN ship arbitrary code to
every RunMyCampus user. SRI hashes are the standard mitigation.

Scope: `templates/**/*.html`. Looks for HTTPS-loaded assets from origins
OTHER than the platform's own (`runmycampus.com`, `cdn.runmycampus.com`,
relative paths, `{% static %}` template tags). Same-origin assets are
served from WhiteNoise and don't need SRI.

Allowlist marker: `<!-- sri-allow: <reason> -->` on the same line as
the tag. Use for legitimate cases where SRI is intentionally omitted
(e.g. a vendor URL that doesn't publish stable hashes).

Output mirrors the boundary scanner CLI:

    python scripts/scan_sri_required.py             # write baseline
    python scripts/scan_sri_required.py --compare   # diff vs baseline (CI)
    python scripts/scan_sri_required.py --json      # JSON to stdout
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIRS = (REPO_ROOT / "templates",)
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-sri-required.json"

# Trusted same-origin hosts that don't need SRI.
SAME_ORIGIN_HOSTS = (
    "runmycampus.com",
    "cdn.runmycampus.com",
    "manager.runmycampus.com",
)

# Match a <script src=...> or <link rel=stylesheet href=...> tag.
_SCRIPT_RE = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)
_LINK_RE = re.compile(
    r"<link\b[^>]*\brel\s*=\s*['\"]stylesheet['\"][^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)
_INTEGRITY_RE = re.compile(r"\bintegrity\s*=\s*['\"]sha[0-9]+-[A-Za-z0-9+/=]+['\"]", re.IGNORECASE)
_ALLOW_RE = re.compile(r"<!--\s*sri-allow:", re.IGNORECASE)


def _is_third_party_https(url: str) -> bool:
    """Return True when the URL is HTTPS and not on a same-origin host."""
    if not url.lower().startswith(("http://", "https://")):
        return False
    for host in SAME_ORIGIN_HOSTS:
        if f"//{host}" in url.lower():
            return False
    return True


def _scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        if _ALLOW_RE.search(line):
            continue
        for regex, kind in ((_SCRIPT_RE, "script"), (_LINK_RE, "link")):
            for match in regex.finditer(line):
                url = match.group(1)
                if not _is_third_party_https(url):
                    continue
                tag = match.group(0)
                if _INTEGRITY_RE.search(tag):
                    continue
                findings.append({
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "line": lineno,
                    "kind": kind,
                    "url": url[:200],
                })
    return findings


def _scan() -> list[dict]:
    findings: list[dict] = []
    for root in TEMPLATE_DIRS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.html")):
            findings.extend(_scan_file(path))
    findings.sort(key=lambda f: (f["path"], f["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "third-party <script src=>/<link rel=stylesheet href=> over HTTPS "
            "must carry an integrity= SRI hash"
        ),
        "same_origin_hosts": list(SAME_ORIGIN_HOSTS),
        "allow_marker": "<!-- sri-allow: <reason> -->",
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"SRI requirement scan: {len(findings)} third-party asset(s) without integrity=")
    for f in findings[:40]:
        print(f"  {f['path']}:{f['line']}  [{f['kind']}]  {f['url']}")
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {(item["path"], item["line"]) for item in baseline.get("findings", [])}
    current_set = {(item["path"], item["line"]) for item in findings}
    new = current_set - baseline_set
    _print_summary(findings)
    if new:
        print("\nNEW third-party asset(s) without SRI:")
        for path, line in sorted(new):
            print(f"  {path}:{line}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
