#!/usr/bin/env python3
"""
Extract static {% url 'namespace:name' %} tags from templates; try reverse() with no args.

Run from repo root:
  python scripts/audit_template_url_names.py
  python scripts/audit_template_url_names.py --urlconf config.tenant_urls

"No args" failures are normal for paths that require ids. Cross-check remaining
names against urlpatterns when hunting dead links.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

URL_TAG_RE = re.compile(
    r"{%\s*url\s+['\"]([a-zA-Z0-9_:]+)['\"]\s*%}", re.MULTILINE
)


def collect_url_names() -> set[str]:
    names: set[str] = set()
    if not TEMPLATES.is_dir():
        return names
    for p in TEMPLATES.rglob("*.html"):
        if "node_modules" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in URL_TAG_RE.finditer(text):
            names.add(m.group(1))
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--urlconf",
        action="append",
        default=[],
        metavar="MODULE",
        help="Also try this urlconf (repeatable). Always includes ROOT_URLCONF first.",
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.urls import NoReverseMatch, clear_url_caches, reverse

    names = sorted(collect_url_names())
    urlconfs: list[str | None] = [None]
    for uc in args.urlconf:
        if uc not in urlconfs:
            urlconfs.append(uc)

    lines: list[str] = []
    lines.append(f"# Static template `{{% url %}}` name audit ({len(names)} unique)\n\n")

    for uc in urlconfs:
        label = uc or "(ROOT_URLCONF)"
        lines.append(f"## {label}\n\n")
        clear_url_caches()
        ok: list[str] = []
        bad: list[str] = []
        for name in names:
            try:
                reverse(name, urlconf=uc)
                ok.append(name)
            except NoReverseMatch:
                bad.append(name)
        lines.append(f"- **{len(ok)}** reverse with no arguments\n")
        lines.append(f"- **{len(bad)}** need arguments or missing on this urlconf\n\n")
        if bad:
            lines.append("<details><summary>Names not reverse()-able without args</summary>\n\n")
            for n in bad:
                lines.append(f"- `{n}`\n")
            lines.append("\n</details>\n\n")

    report = "".join(lines)
    print(report)
    out = ROOT / "docs" / "phase_audit" / "PHASE_3_4_URL_NAME_AUDIT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
