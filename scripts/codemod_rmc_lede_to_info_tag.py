#!/usr/bin/env python3
"""
Convert educational <p class="rmc-lede"> walls into rmc_info_tag (Core vs Context).

Keeps:
- alert / warn ledes (role=alert, rmc-lede--warn)
- live-data shells (data-mc-preview-*, data-rmc-dlq-row-count)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

LEDE_RE = re.compile(
    r"<p\b([^>]*\bclass=[\"'][^\"']*\brmc-lede\b[^\"']*[\"'][^>]*)>(.*?)</p>",
    re.S | re.I,
)
H1_RE = re.compile(r"(<h1\b[^>]*>)(.*?)(</h1>)", re.S | re.I)
LOAD_RE = re.compile(r"(\{% load\s+)([^%]+?)(\s*%\})")


def should_keep(attrs: str, body: str) -> str | None:
    if "rmc-lede--warn" in attrs or 'role="alert"' in attrs:
        return "alert"
    if "data-mc-preview" in attrs or "data-rmc-dlq-row-count" in attrs:
        return "live-data"
    if not re.sub(r"\s+", "", body) and "data-" in attrs:
        return "live-data"
    return None


def ensure_load(text: str) -> str:
    if "rmc_explain_tags" in text:
        return text
    m = LOAD_RE.search(text)
    if not m:
        em = re.search(r"(\{% extends[^%]*%\}\s*)", text)
        if em:
            return (
                text[: em.end()]
                + "{% load i18n rmc_explain_tags %}\n"
                + text[em.end() :]
            )
        return "{% load i18n rmc_explain_tags %}\n" + text
    loads = m.group(2).split()
    if "rmc_explain_tags" not in loads:
        loads.append("rmc_explain_tags")
        if "i18n" not in loads:
            loads.insert(0, "i18n")
        return (
            text[: m.start()]
            + m.group(1)
            + " ".join(loads)
            + m.group(3)
            + text[m.end() :]
        )
    return text


def extract_tip_asvar(body: str, var_name: str) -> tuple[str, str]:
    body = body.strip()
    m = re.fullmatch(
        r'\{%\s*trans\s+("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')\s*%\}',
        body,
        re.S,
    )
    if m:
        return f"{{% trans {m.group(1)} as {var_name} %}}", var_name

    m = re.fullmatch(
        r"\{%\s*blocktrans(\s+[^%]*)?%\}(.*?)\{%\s*endblocktrans\s*%\}",
        body,
        re.S,
    )
    if m:
        opts = (m.group(1) or "").strip()
        inner = m.group(2)
        if "asvar" in opts:
            # already asvar — reuse existing var if present
            am = re.search(r"asvar\s+(\w+)", opts)
            if am:
                return body, am.group(1)
        opts2 = (opts + f" asvar {var_name}").strip()
        return f"{{% blocktrans {opts2} %}}{inner}{{% endblocktrans %}}", var_name

    if "{%" not in body and "{{" not in body:
        return (
            f"{{% blocktrans asvar {var_name} %}}{body}{{% endblocktrans %}}",
            var_name,
        )
    return "", ""


def wrap_h1_with_tip(h1_full: str, asvar: str, tip_var: str, surface: str) -> str:
    tip = (
        '{% rmc_info_tag title=_("About this page") '
        f'body={tip_var} surface="{surface}" placement="bottom" %}}'
    )
    return (
        '<div class="rmc-page__title-row d-flex align-items-center gap-2 min-w-0">\n'
        f"      {h1_full}\n"
        f"      {asvar}\n"
        f"      {tip}\n"
        "    </div>"
    )


def details_block(asvar: str, tip_var: str) -> str:
    return (
        f"{asvar}\n"
        '    <details class="rmc-help-details mb-2" data-rmc-core-context="1">\n'
        '      <summary class="small fw-semibold">{% trans "About this page" %}</summary>\n'
        f'      <div class="small text-muted pt-1">{{{{ {tip_var} }}}}</div>\n'
        "    </details>"
    )


def infer_surface(path: Path) -> str:
    s = path.as_posix()
    if "/operator/" in s or "/super/" in s:
        return "operator"
    if "migration_cloud" in s:
        return "migration-cloud"
    return "tenant"


def convert_file(path: Path, *, dry_run: bool) -> tuple[str, int]:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"\brmc-lede\b", text):
        return "skip", 0

    surface = infer_surface(path)
    matches = list(LEDE_RE.finditer(text))
    if not matches:
        return "skip", 0

    # Build left-to-right so offsets stay coherent via piece list
    out: list[str] = []
    cursor = 0
    converted = 0
    kept = 0
    failed = 0
    tip_i = 0

    for m in matches:
        attrs, body = m.group(1), m.group(2)
        keep = should_keep(attrs, body)
        if keep:
            kept += 1
            out.append(text[cursor : m.end()])
            cursor = m.end()
            continue

        tip_i += 1
        var_name = f"page_tip_{tip_i}"
        asvar, tip_var = extract_tip_asvar(body.strip(), var_name)
        if not asvar:
            failed += 1
            # Fallback: collapse raw body into details (still Core vs Context)
            summary = '{% trans "About this page" %}'
            replacement = (
                '<details class="rmc-help-details mb-2" data-rmc-core-context="1">\n'
                f'      <summary class="small fw-semibold">{summary}</summary>\n'
                f'      <div class="small text-muted pt-1">{body.strip()}</div>\n'
                "    </details>"
            )
            # Prefer attaching after nearest h1 in the segment before this lede
            segment = text[cursor : m.start()]
            h1m = None
            for hm in H1_RE.finditer(segment):
                h1m = hm
            if h1m and (len(segment) - h1m.end()) < 500:
                out.append(segment[: h1m.end()])
                out.append("\n    ")
                out.append(replacement)
                out.append(segment[h1m.end() :])
                # drop the lede
                cursor = m.end()
                converted += 1
                continue
            out.append(text[cursor : m.start()])
            out.append(replacement)
            cursor = m.end()
            converted += 1
            continue

        segment = text[cursor : m.start()]
        h1m = None
        for hm in H1_RE.finditer(segment):
            h1m = hm

        if h1m and (len(segment) - h1m.end()) < 500:
            # Wrap h1 + tip; omit lede
            out.append(segment[: h1m.start()])
            h1_full = h1m.group(0)
            out.append(wrap_h1_with_tip(h1_full, asvar, tip_var, surface))
            out.append(segment[h1m.end() :])
            cursor = m.end()
            converted += 1
        else:
            out.append(segment)
            out.append(details_block(asvar, tip_var))
            cursor = m.end()
            converted += 1

    out.append(text[cursor:])
    new = "".join(out)

    if converted and new != text:
        new = ensure_load(new)
        if "data-rmc-core-context" not in new and re.search(r"<main\b", new):
            new = re.sub(
                r"(<main\b[^>]*)(>)",
                r'\1 data-rmc-core-context="1"\2',
                new,
                count=1,
            )
        if not dry_run:
            path.write_text(new, encoding="utf-8")
        return "changed", converted

    if kept and not converted:
        return "kept-only", 0
    return "noop", 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed_files = 0
    total_conv = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        status, n = convert_file(path, dry_run=args.dry_run)
        if status == "changed":
            changed_files += 1
            total_conv += n
            print(f"CHANGED {path.relative_to(ROOT)} (+{n})")
    print(f"SUMMARY files={changed_files} ledes_converted={total_conv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
