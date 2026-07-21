#!/usr/bin/env python
"""Metric #21 — critical msgid msgstr depth (repo-contained).

Bulk catalog msgstr will stay thin for years; A+ for i18n means the *critical*
operator/parent/counselor/booking strings are translated in beachhead locales
(fr/es/pt), not that all ~14k msgids are filled.

Exit 0 = CRITICAL_MSGID_DEPTH_PASS.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Keep this list short and load-bearing — strings shipped on A+ Wave 21–23 surfaces.
CRITICAL_MSGIDS = (
    "Intervention contact logged.",
    "Could not log contact.",
    "Select a valid student.",
    "Student not found in this school.",
    "No open incidents to update for this student.",
    "Booking confirmed.",
    "That time slot conflicts with an existing booking.",
    "Booking not found.",
    "Booking cancelled.",
    "Resource name is required.",
    "Bookable resource added.",
    "A resource with that name already exists.",
    "Resource and start/end times are required.",
    "Select a hostel room from this school.",
    "Placement removed from the draft.",
    "Sold out",
    "Band",
    "Registration recorded.",
    "MTSS tier updated to %(tier)s (%(count)s open incident(s)).",
)

# The catalogs that Django can actually activate. This checked "pt" until
# 2026-07-21, which was green and meaningless: 'pt' is not in settings.LANGUAGES,
# so Django resolves Portuguese to pt_BR and never loads locale/pt. locale/pt held
# exactly these 19 msgids and nothing else -- a catalog whose only purpose was to
# satisfy this gate -- while locale/pt_BR, the one that ships, had 0 of 19
# translated. Every Portuguese-speaking user saw English on all 19 strings while
# CI reported CRITICAL_MSGID_DEPTH_PASS.
#
# A locale listed here must be one settings.LANGUAGES actually serves; otherwise
# this gate proves nothing about what a user sees.
LOCALES = ("fr", "es", "pt_BR")


def _unescape_po(s: str) -> str:
    return (
        s.replace("\\\\", "\0")
        .replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\0", "\\")
    )


def _parse_po_entries(text: str) -> dict[str, str]:
    """Map msgid -> msgstr for simple (non-plural) entries.

    Accepts both single-line ``msgstr "…"`` and gettext multi-line form::

        msgstr ""
        "continued…"
    """
    entries: dict[str, str] = {}
    blocks = re.split(r"\n\n+", text)
    for block in blocks:
        mid = re.search(r'^msgid "(.*)"\s*$', block, re.M)
        if not mid:
            continue
        msgid = _unescape_po(mid.group(1))
        if msgid == "":
            continue
        chunks: list[str] | None = None
        for line in block.splitlines():
            if chunks is None:
                opened = re.match(r'^msgstr "(.*)"\s*$', line)
                if opened:
                    chunks = [opened.group(1)]
                continue
            cont = re.match(r'^"(.*)"\s*$', line)
            if cont:
                chunks.append(cont.group(1))
            else:
                break
        if chunks is not None:
            entries[msgid] = _unescape_po("".join(chunks))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locales",
        default=",".join(LOCALES),
        help="Comma-separated locale codes under locale/",
    )
    args = parser.parse_args()
    locales = [x.strip() for x in args.locales.split(",") if x.strip()]

    failures: list[str] = []
    checked = 0
    for loc in locales:
        po_path = ROOT / "locale" / loc / "LC_MESSAGES" / "django.po"
        if not po_path.is_file():
            failures.append(f"{loc}: missing django.po")
            continue
        entries = _parse_po_entries(po_path.read_text(encoding="utf-8"))
        for msgid in CRITICAL_MSGIDS:
            checked += 1
            msgstr = entries.get(msgid)
            if msgstr is None:
                failures.append(f"{loc}: missing msgid {msgid!r}")
            elif not msgstr.strip():
                failures.append(f"{loc}: empty msgstr for {msgid!r}")

    if failures:
        print("CRITICAL_MSGID_DEPTH_FAIL", file=sys.stderr)
        for f in failures[:40]:
            print(f"  - {f}", file=sys.stderr)
        if len(failures) > 40:
            print(f"  … +{len(failures) - 40} more", file=sys.stderr)
        return 1

    print(
        f"CRITICAL_MSGID_DEPTH_PASS (locales={len(locales)}, "
        f"msgids={len(CRITICAL_MSGIDS)}, checked={checked})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
