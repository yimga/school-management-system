#!/usr/bin/env python3
"""Repair templates broken by greedy row-form disclosure wrapping."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BROKEN_START = re.compile(
    r"(<tr[^>]*>\s*)<td>\s*<details class=\"rmc-row-disclosure\">"
    r"[\s\S]*?<div class=\"rmc-row-disclosure__body mt-1\">\s*"
    r"(\{\{[^}]+\}\})</td>",
    re.IGNORECASE,
)
ORPHAN_CLOSE = re.compile(
    r"\s*</div>\s*</details></td>(\s*</tr>)",
    re.IGNORECASE,
)
FORM_TD = re.compile(
    r"(<td\b[^>]*>)((?:(?!<td\b|<tr\b).)*?<form\b(?:(?!<td\b|<tr\b).)*?)</td>",
    re.IGNORECASE | re.DOTALL,
)
ALREADY_DISCLOSED = re.compile(r"<details class=\"rmc-row-disclosure\">", re.IGNORECASE)


def repair_text(text: str) -> str:
    while True:
        match = BROKEN_START.search(text)
        if not match:
            break
        text = text[: match.start()] + match.group(1) + f"<td>{match.group(2)}</td>" + text[match.end() :]

    text = ORPHAN_CLOSE.sub(r"</td>\1", text)

    def wrap_form_td(match: re.Match[str]) -> str:
        open_td, body = match.group(1), match.group(2)
        if ALREADY_DISCLOSED.search(body):
            return match.group(0)
        return (
            f"{open_td}\n"
            '          <details class="rmc-row-disclosure">\n'
            '            <summary class="btn btn-sm btn-outline-secondary">{% trans "Actions" %}</summary>\n'
            '            <div class="rmc-row-disclosure__body mt-1">\n'
            f"{body.strip()}\n"
            "            </div>\n"
            "          </details></td>"
        )

    return FORM_TD.sub(wrap_form_td, text)


def main() -> int:
    broken = []
    for path in Path(ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "rmc-row-disclosure__body" in text and BROKEN_START.search(text):
            repaired = repair_text(text)
            if repaired != text:
                path.write_text(repaired, encoding="utf-8")
                broken.append(path.relative_to(ROOT).as_posix())
                print(f"repaired {path.relative_to(ROOT).as_posix()}")
    print(f"repaired {len(broken)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
