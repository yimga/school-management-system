"""Shared assertions for experience_control closure HTTP/template proofs."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def repo_templates_glob_marketing_html() -> list[Path]:
    """Marketing / public chrome templates most linked from validate_marketing_urls smoke."""
    out: list[Path] = []
    for base in (
        _REPO_ROOT / "templates" / "schools",
        _REPO_ROOT / "templates" / "marketing",
    ):
        if not base.is_dir():
            continue
        out.extend(p for p in base.rglob("*.html") if p.is_file())
    return sorted(set(out))


def marketing_templates_avoid_href_hash_dummy(
    *,
    allow_js_handlers: bool = True,
) -> list[tuple[str, str]]:
    """
    Returns list of (path, line_snippet) violations: bare href=\"#\" on anchors
    (dummy navigation). Allows javascript: when allow_js_handlers.
    """
    violations: list[tuple[str, str]] = []
    href_hash = re.compile(r"""href\s*=\s*['"]#['"]""", re.I)
    for path in repo_templates_glob_marketing_html():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if not href_hash.search(line):
                continue
            if "javascript:" in line.lower():
                continue
            # Skip documented in-page anchors that include name= fragment targets (rare)
            violations.append((f"{path.relative_to(_REPO_ROOT)}:{i}", line.strip()[:200]))
    return violations


def count_strict_primary_backend_markers(html: str) -> int:
    return html.count('data-rmc-backend-role-home-primary="1"')


def count_founder_toolbar_primary(html: str) -> int:
    return html.count('data-rmc-founder-primary-toolbar="1"')


def body_has_strict_attribute(html: str) -> bool:
    return 'data-rmc-conversion-strict="1"' in html
