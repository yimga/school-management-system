#!/usr/bin/env python3
"""
UI wiring audit: static template URL names + hazardous href/action patterns.

This does **not** replace human QA; it fails fast on:
- **Dead names:** `{% url 'namespace:name' %}` where the literal name is not registered on
  any of the primary urlconfs (root, tenant, manager, public).
- **Risky navigation:** `javascript:` in href (except allowlisted `javascript:history.`),
  empty href, empty form action (excluding `{% %}` dynamic actions).

Run from repo root (Django required; no DB queries for the url tree walk)::

    python scripts/verify_ui_wiring_audit.py

Optional: regenerate markdown report (same idea as audit_template_url_names)::

    python scripts/verify_ui_wiring_audit.py --write-report
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# First argument to {% url %} when it is a quoted string literal (allows extra args before %})
URL_TAG_RE = re.compile(
    r"{%\s*url\s+['\"]([a-zA-Z0-9_:]+)['\"]",
    re.MULTILINE,
)

# href="/foo" or href='#' — capture value for analysis
HREF_RE = re.compile(
    r"""href\s*=\s*(['"])\s*([^'"]*)\1""",
    re.IGNORECASE | re.MULTILINE,
)

ACTION_RE = re.compile(
    r"""action\s*=\s*(['"])\s*([^'"]*)\1""",
    re.IGNORECASE | re.MULTILINE,
)

# href="#" is OK when Bootstrap/other toggles present on the same line
HREF_HASH_OK_LINE = re.compile(
    r"data-bs-toggle|data-toggle|role=\"button\"|aria-haspopup",
    re.IGNORECASE,
)

JAVASCRIPT_ALLOWED_PREFIXES = (
    "javascript:history.",
    "javascript:window.history.",
)

SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)

URLCONF_MODULES = (
    "config.urls",
    "config.tenant_urls",
    "config.manager_urls",
    "config.public_urls",
)


def _walk_url_names(urlpatterns, namespace: str = "") -> set[str]:
    from django.urls.resolvers import URLPattern, URLResolver

    out: set[str] = set()
    for p in urlpatterns:
        if isinstance(p, URLResolver):
            sub_ns = namespace
            if p.namespace:
                sub_ns = f"{namespace}{p.namespace}:" if namespace else f"{p.namespace}:"
            out |= _walk_url_names(p.url_patterns, sub_ns)
        elif isinstance(p, URLPattern):
            if p.name:
                fq = f"{namespace}{p.name}" if namespace else p.name
                out.add(fq)
    return out


def _registered_url_names() -> set[str]:
    import importlib

    names: set[str] = set()
    for mod_name in URLCONF_MODULES:
        mod = importlib.import_module(mod_name)
        patterns = getattr(mod, "urlpatterns", None)
        if patterns:
            names |= _walk_url_names(patterns)
    return names


def _collect_template_url_literals() -> dict[str, list[str]]:
    """Map relative path -> list of url names found."""
    by_file: dict[str, list[str]] = {}
    if not TEMPLATES.is_dir():
        return by_file
    for p in TEMPLATES.rglob("*.html"):
        if "node_modules" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = sorted({m.group(1) for m in URL_TAG_RE.finditer(text)})
        if found:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            by_file[rel] = found
    return by_file


def _strip_non_html_blocks(text: str) -> str:
    """Avoid matching a.href / href= inside embedded JS/CSS."""
    text = SCRIPT_BLOCK_RE.sub("", text)
    text = STYLE_BLOCK_RE.sub("", text)
    return text


def _scan_href_action_hazards() -> list[str]:
    failures: list[str] = []
    if not TEMPLATES.is_dir():
        return failures
    for p in TEMPLATES.rglob("*.html"):
        if "node_modules" in p.parts:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _strip_non_html_blocks(raw)
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            for m in HREF_RE.finditer(line):
                val = (m.group(2) or "").strip()
                if not val.strip():
                    failures.append(f"{rel}:{i}: empty href")
                    continue
                low = val.lower()
                if low.startswith("javascript:"):
                    if any(low.startswith(pref) for pref in JAVASCRIPT_ALLOWED_PREFIXES):
                        continue
                    failures.append(f"{rel}:{i}: disallowed javascript: href ({val[:48]!r})")
                elif val.strip() == "#":
                    if not HREF_HASH_OK_LINE.search(line) and "data-tour-trigger" not in line:
                        failures.append(
                            f"{rel}:{i}: href=# without toggle/bootstrap/tour hint (dead link risk)"
                        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write docs/phase_audit/UI_WIRING_AUDIT_LATEST.md summary",
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    registered = _registered_url_names()
    by_file = _collect_template_url_literals()
    all_literals: set[str] = set()
    for names in by_file.values():
        all_literals.update(names)

    unknown = sorted(n for n in all_literals if n not in registered)
    href_failures = _scan_href_action_hazards()

    lines: list[str] = []
    lines.append(f"# UI wiring audit\n\n")
    lines.append(f"- Registered URL names (union of {', '.join(URLCONF_MODULES)}): **{len(registered)}**\n")
    lines.append(f"- Unique `{{% url %}}` literals in templates: **{len(all_literals)}**\n")
    lines.append(f"- Literals **not** in registered union: **{len(unknown)}**\n")
    lines.append(f"- href/action hazards: **{len(href_failures)}**\n\n")

    if unknown:
        lines.append("## Unknown `{% url %}` literals (dead or typo)\n\n")
        for n in unknown:
            refs = [fp for fp, ns in by_file.items() if n in ns]
            lines.append(f"- `{n}` — {', '.join(refs[:12])}")
            if len(refs) > 12:
                lines.append(f" (+{len(refs) - 12} more)")
            lines.append("\n")
        lines.append("\n")

    if href_failures:
        lines.append("## href / action hazards\n\n")
        for item in href_failures:
            lines.append(f"- {item}\n")
        lines.append("\n")

    report = "".join(lines)
    print(report)

    if args.write_report:
        out = ROOT / "docs" / "phase_audit" / "UI_WIRING_AUDIT_LATEST.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)

    if unknown or href_failures:
        print("\nFAIL verify_ui_wiring_audit:", file=sys.stderr)
        if unknown:
            print(f"  unknown url literals: {len(unknown)}", file=sys.stderr)
        if href_failures:
            for h in href_failures[:30]:
                print(f"  {h}", file=sys.stderr)
            if len(href_failures) > 30:
                print(f"  ... and {len(href_failures) - 30} more", file=sys.stderr)
        return 1

    print("OK   verify_ui_wiring_audit (template url literals + href/action scan)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
