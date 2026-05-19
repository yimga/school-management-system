#!/usr/bin/env python3
"""
1052: Classify security-sensitive API usage (visibility, not auto-remediation).

Each hit also receives ``governance_tier`` for enterprise reporting:
``safe`` | ``controlled`` | ``needs_review`` | ``violation`` (default script exit remains 0).

Patterns:
- ``@csrf_exempt`` (and ``csrf_exempt(``)
- ``AllowAny`` (DRF permission class)
- ``.cursor.execute(`` (raw SQL)
- ``subprocess.`` calls
- **Auth / DRF hints (positive controls, still review in context):** ``@login_required``,
  ``@staff_member_required``, ``permission_classes`` assignment, ``@require_POST`` / ``@require_http_methods``
- **Note:** mutating **POST** routes are not fully resolved from static text; use Django URLconf review for write endpoints.

Per hit: file, line, pattern kind, bucket: ``tests`` | ``product`` | ``scripts`` | ``vendor_skip``.

``vendor_skip`` is unused here; migrations are ``product`` but flagged ``needs_review`` for raw SQL.
Writes ``docs/generated/security_surface_audit.json`` (+ ``.md``).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "docs" / "generated" / "security_surface_audit.json"
OUT_MD = REPO / "docs" / "generated" / "security_surface_audit.md"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("csrf_exempt", re.compile(r"@csrf_exempt\b|csrf_exempt\s*\(")),
    ("allow_any", re.compile(r"\bAllowAny\b")),
    ("cursor_execute", re.compile(r"\.cursor\.execute\s*\(")),
    ("subprocess", re.compile(r"\bsubprocess\.")),
    ("login_required", re.compile(r"@login_required\b|login_required\s*\(")),
    ("staff_member_required", re.compile(r"@staff_member_required\b")),
    ("permission_classes", re.compile(r"\bpermission_classes\s*=")),
    ("require_http_methods", re.compile(r"@require_POST\b|@require_http_methods\b")),
]

# Webhooks / provider callbacks: CSRF cannot be used; token/HMAC is the real gate.
# Source of truth: scripts/allowlists/csrf_exempt_allowlist.json (keys under "files").
_CSRF_ALLOWLIST_PATH = REPO / "scripts" / "allowlists" / "csrf_exempt_allowlist.json"


def _load_known_csrf_exempt_product_paths() -> frozenset[str]:
    fallback = {
        "apps/accounts/views_saml.py",
        "apps/api/scim_views.py",
        "apps/api/oneroster_roster_webhook.py",
        "apps/billing/api_views.py",
        "apps/finance/views_payments.py",
        "apps/portal/views_office.py",
        "apps/platform_runtime/views_rum.py",
        "apps/schools/section8_views.py",
    }
    try:
        data = json.loads(_CSRF_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        files = data.get("files") or {}
        if isinstance(files, dict) and files:
            return frozenset(str(k) for k in files.keys())
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return frozenset(fallback)


KNOWN_CSRF_EXEMPT_PRODUCT_PATHS: frozenset[str] = _load_known_csrf_exempt_product_paths()


SKIP_PREFIXES = (
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".django_test_dbs",
)


def _bucket(rel: str) -> str:
    if "/tests/" in rel or rel.startswith("apps/") and "test_" in Path(rel).name:
        return "tests"
    if rel.startswith("scripts/"):
        return "scripts"
    return "product"


_POSITIVE_SECURITY_PATTERNS = frozenset(
    {
        "login_required",
        "staff_member_required",
        "permission_classes",
        "require_http_methods",
    }
)


def _classification(pattern: str, rel: str, bucket: str) -> str:
    if bucket == "tests":
        return "allowed"
    if pattern in _POSITIVE_SECURITY_PATTERNS:
        return "allowed"
    if pattern == "csrf_exempt" and rel in KNOWN_CSRF_EXEMPT_PRODUCT_PATHS:
        return "allowed"
    if pattern == "csrf_exempt":
        return "unsafe"
    if pattern == "allow_any":
        return "needs_review"
    if pattern == "cursor_execute" and "/migrations/" in rel:
        return "needs_review"
    if pattern == "cursor_execute":
        return "unsafe"
    if pattern == "subprocess":
        return "needs_review"
    return "needs_review"


def _governance_tier(pattern: str, legacy_cls: str, bucket: str, rel: str) -> str:
    """
    Map legacy classification + path to SOC2-style governance buckets.
    Does not change enforcement defaults elsewhere (informational for ledgers).
    """
    if bucket == "tests":
        return "safe"
    if legacy_cls == "allowed":
        return "safe"
    if pattern == "csrf_exempt" and legacy_cls == "unsafe":
        return "violation"
    if pattern == "cursor_execute" and "/migrations/" in rel:
        return "controlled"
    if pattern == "subprocess" and rel.startswith("scripts/"):
        return "controlled"
    if pattern == "subprocess" and "/management/commands/" in rel:
        return "controlled"
    if legacy_cls == "unsafe":
        return "needs_review"
    return "needs_review"


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for root in (REPO / "apps", REPO / "scripts", REPO / "config"):
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            rel = p.relative_to(REPO).as_posix()
            if any(sp in rel for sp in SKIP_PREFIXES):
                continue
            out.append(p)
    return sorted(out)


def main() -> int:
    by_kind: dict[str, list[dict[str, str]]] = defaultdict(list)
    counts = defaultdict(int)

    for path in _iter_py_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        b = _bucket(rel)
        for i, line in enumerate(lines, start=1):
            for name, pat in PATTERNS:
                if pat.search(line):
                    cls = _classification(name, rel, b)
                    rec = {
                        "file": rel,
                        "line": str(i),
                        "pattern": name,
                        "bucket": b,
                        "classification": cls,
                        "governance_tier": _governance_tier(name, cls, b, rel),
                    }
                    by_kind[name].append(rec)
                    counts[name] += 1

    unified = []
    for name in sorted(by_kind.keys()):
        unified.extend(sorted(by_kind[name], key=lambda r: (r["file"], int(r["line"]))))

    by_class: dict[str, int] = defaultdict(int)
    for r in unified:
        by_class[str(r.get("classification", "needs_review"))] += 1

    by_tier: dict[str, int] = defaultdict(int)
    for r in unified:
        by_tier[str(r.get("governance_tier", "needs_review"))] += 1

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {k: counts[k] for k in sorted(counts.keys())},
        "summary_by_classification": dict(sorted(by_class.items())),
        "summary_by_governance_tier": dict(sorted(by_tier.items())),
        "totals": {"hits": len(unified)},
        "by_pattern": {k: v for k, v in by_kind.items()},
        "unified": unified,
        "known_csrf_exempt_product_paths": sorted(KNOWN_CSRF_EXEMPT_PRODUCT_PATHS),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Security surface audit (generated)",
        "",
        f"**UTC** `{payload['generated_at']}`  ",
        "",
        "Counts are **visibility only**; review classifications in JSON.",
        "",
        "| Pattern | Count |",
        "| --- | --- |",
    ]
    for k in sorted(counts.keys()):
        lines.append(f"| {k} | {counts[k]} |")
    lines.extend(["", f"**Total hits:** {len(unified)}", ""])
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("audit_security_surface: OK")
    print(f"  written: {OUT_JSON.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
