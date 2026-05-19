#!/usr/bin/env python
"""
Priority locale burndown (G-01): seed fr, es, pt_BR, de, ar msgstr from English
for msgids used in templates/people/* (English fallback until human translation).

Run: python scripts/burndown_glocal_priority_locales.py --write
Then: python manage.py compilemessages
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PEOPLE = REPO / "templates" / "people"
PRIORITY = ("fr", "es", "pt_BR", "de", "ar")
MSGID_RE = re.compile(r'msgid\s+"(.*)"')


def _collect_people_msgids() -> set[str]:
    msgids: set[str] = set()
    for path in PEOPLE.glob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'\{%\s*trans\s+"([^"]+)"\s*%\}', text):
            msgids.add(m.group(1))
        for m in re.finditer(r'_\("([^"]+)"\)', text):
            msgids.add(m.group(1))
    return msgids


def _parse_po(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    current_id = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = MSGID_RE.match(line.strip())
        if m and not line.strip().startswith("msgid_plural"):
            current_id = m.group(1)
            if current_id not in entries:
                entries[current_id] = ""
    return entries


def _fill_po(po_path: Path, en_map: dict[str, str], target_ids: set[str]) -> int:
    if not po_path.exists():
        return 0
    lines = po_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    filled = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.startswith('msgid "') and not line.startswith("msgid_plural"):
            mid = line.split('"')[1]
            if mid in target_ids and i + 1 < len(lines) and lines[i + 1].startswith('msgstr ""'):
                en_val = en_map.get(mid, mid)
                out[-1] = line
                out.append(f'msgstr "{en_val}"\n')
                filled += 1
                i += 2
                continue
        i += 1
    if filled:
        po_path.write_text("".join(out), encoding="utf-8")
    return filled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    people_ids = _collect_people_msgids()
    en_po = REPO / "locale" / "en" / "LC_MESSAGES" / "django.po"
    en_map = _parse_po(en_po)
    total = 0
    for loc in PRIORITY:
        po = REPO / "locale" / loc / "LC_MESSAGES" / "django.po"
        if args.write:
            n = _fill_po(po, en_map, people_ids)
            print(f"{loc}: filled {n}")
            total += n
        else:
            print(f"{loc}: would fill up to {len(people_ids)} people-template msgids (dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
