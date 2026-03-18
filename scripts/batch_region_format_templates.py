#!/usr/bin/env python3
"""Batch add region_format and replace |date: / |floatformat: in templates."""

import re
from pathlib import Path


def main():
    templates_dir = Path("templates")
    updated = []
    for html in templates_dir.rglob("*.html"):
        try:
            text = html.read_text(encoding="utf-8")
        except Exception:
            continue
        if "|date:" not in text and "|floatformat:" not in text:
            continue
        orig = text
        if "region_format" not in text and (
            "|date:" in text or "|floatformat:" in text
        ):
            if "{% load " in text and "{% load region_format %}" not in text:
                text = re.sub(
                    r"(\{% load [^%]+%\})",
                    r"\1\n{% load region_format %}",
                    text,
                    count=1,
                )
            elif "{% extends " in text:
                text = re.sub(
                    r"({% extends [^%]+%}\s*\n)",
                    r"\1{% load region_format %}\n",
                    text,
                    count=1,
                )
        # ${{ x|floatformat:2 }} -> {{ x|format_currency }}
        text = re.sub(
            r"\$\{\{\s*([^|]+)\|floatformat:2\s*\}\}", r"{{ \1|format_currency }}", text
        )
        text = re.sub(
            r"\$\{\{\s*([^|]+)\|floatformat:0\s*\}\}", r"{{ \1|format_currency }}", text
        )
        # {{ x|floatformat:N }} -> format_number:N
        text = re.sub(
            r"\{\{\s*([^|]+)\|floatformat:2\s*\}\}(?!\s*\|)",
            r"{{ \1|format_number:2 }}",
            text,
        )
        text = re.sub(
            r"\{\{\s*([^|]+)\|floatformat:1\s*\}\}", r"{{ \1|format_number:1 }}", text
        )
        text = re.sub(
            r"\{\{\s*([^|]+)\|floatformat:0\s*\}\}(?!\s*\|)",
            r"{{ \1|format_number:0 }}",
            text,
        )
        # |date:"Y-m-d" or |date:'Y-m-d' -> |format_date:"YYYY-MM-DD"
        text = re.sub(
            r"\|\s*date\s*:\s*['\"]Y-m-d['\"]", '|format_date:"YYYY-MM-DD"', text
        )
        if text != orig:
            html.write_text(text, encoding="utf-8")
            updated.append(str(html))
    print("Updated", len(updated), "templates")
    for u in updated[:30]:
        print(" ", u)
    if len(updated) > 30:
        print(" ... and", len(updated) - 30, "more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
