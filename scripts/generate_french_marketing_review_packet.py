#!/usr/bin/env python3
"""Generate French native-review packet (AI draft + blank correction column).

Unlike yo/ha/sw/pid blank packets, French ships AI-drafted msgstr in django.po;
this packet is for a native speaker to verify/correct before production deploy.

Usage:
    python scripts/generate_french_marketing_review_packet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.generate_translation_request_packets import (  # noqa: E402
    SOURCE_MSGIDS,
    SURFACE_HINTS,
    surface,
)
from scripts.seed_french_marketing_translations import (  # noqa: E402
    FR_PO,
    TRANSLATIONS,
    _parse_po_blocks,
)

OUT = REPO / "docs" / "i18n" / "translation_requests" / "fr.md"


def _current_fr_msgstr(po_text: str, msgid: str) -> str:
    blocks = _parse_po_blocks(po_text)
    for block in blocks:
        if block["msgid"] != msgid:
            continue
        start = block["msgstr_start"]
        end = block["msgstr_end"]
        lines = po_text.splitlines(keepends=True)[start:end]
        if not lines:
            return ""
        first = lines[0]
        if first.startswith("msgstr "):
            value = first[7:].strip().strip('"')
        else:
            value = ""
        for cont in lines[1:]:
            value += cont.strip().strip('"')
        return value
    return ""


def main() -> int:
    if not FR_PO.is_file():
        print(f"generate_french_marketing_review_packet: missing {FR_PO}", file=sys.stderr)
        return 1

    po_text = FR_PO.read_text(encoding="utf-8")
    lines: list[str] = [
        "# Native review packet: French (`fr`) — marketing chrome",
        "",
        "**Purpose:** verify or correct AI-drafted French marketing strings before production deploy.",
        "",
        "**Source:** English (`en`)  ·  **Locale:** `fr`  ·  **Strings:** "
        f"{len(SOURCE_MSGIDS)} (111-string marketing set; anchors seeded via `seed_marketing_site`)",
        "",
        "**Brand voice:** editorial / quiet-luxury — see [MARKETING_VOICE.md](../../MARKETING_VOICE.md).",
        "",
        "**Locale notes:** French formal copy uses non-breaking space before `: ; ! ?`. "
        "School-domain terms (bursar → *intendant*, report card → *bulletin*) should match "
        "Francophone Africa + France operator expectations.",
        "",
        "## Instructions for the native reviewer",
        "",
        "1. Read the **AI draft** column (from `locale/fr/LC_MESSAGES/django.po` + seed script).",
        "2. If correct, leave **Corrected** blank or copy the draft unchanged.",
        "3. If wrong, write the corrected French in **Corrected**.",
        "4. Sign off at the bottom.",
        "5. Operator applies corrections to `locale/fr/LC_MESSAGES/django.po`, runs "
        "`python manage.py sync_i18n_catalog --compile`, then:",
        "",
        "   `python manage.py i18n_review_status --mark-reviewed fr --reviewer \"<your-name>\"`",
        "",
        "**Production gate:** `python scripts/verify_marketing_i18n_production_gate.py --production` "
        "blocks deploy until `fr` (and `es`, `pt-br`) are `production-ready` in "
        "`var/i18n-review-status.json`.",
        "",
        "## String table",
        "",
        "| # | Surface | English (source) | AI draft | Corrected (if changed) |",
        "|---|---|---|---|---|",
    ]

    for n, msgid in enumerate(SOURCE_MSGIDS, 1):
        safe_mid = msgid.replace("|", "\\|")
        draft = TRANSLATIONS.get(msgid) or _current_fr_msgstr(po_text, msgid) or "_—_"
        draft = draft.replace("|", "\\|")
        lines.append(
            f"| {n} | `{surface(msgid)}` | {safe_mid} | {draft} | _—_ |"
        )

    lines.extend(
        [
            "",
            "## Sign-off",
            "",
            "- **Reviewer name:** _—_",
            "- **Date completed:** _—_",
            "- **Native-speaker affirmation (Y/N):** _—_",
            "- **Notes** (terms left in English, register choices): _—_",
            "",
            "---",
            "",
            "Regenerate this packet after `seed_french_marketing_translations.py` changes: "
            "`python scripts/generate_french_marketing_review_packet.py`",
            "",
        ]
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"generate_french_marketing_review_packet: wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
