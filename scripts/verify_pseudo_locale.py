#!/usr/bin/env python3
"""CI gate: the pseudo-locale transform is interpolation-safe across the whole catalog.

Pseudo-localization (see ``scripts/pseudo_locale_transform.py``) is only safe to run
for QA if it never corrupts an interpolation or markup token — a ``%(name)s`` turned
into ``%(námé)s`` would raise ``KeyError`` the moment Django formats it, silently
breaking the very QA build it powers. This gate proves that invariant holds against
EVERY real source string, not a hand-picked sample: it parses
``locale/en/LC_MESSAGES/django.po`` (the source catalog every locale falls back to),
runs the transform over each ``msgid`` / ``msgid_plural``, and asserts the pseudo
output carries the identical token multiset.

Zero-tolerance, no baseline (like ``audit_template_render_safety``): a single
token-corrupting string fails the gate. Stdlib-only so it runs in the deps-free
architectural-boundaries job.

Usage:
  python scripts/verify_pseudo_locale.py            # gate (exit 1 on any failure)
  python scripts/verify_pseudo_locale.py --sample 8 # print example transforms
  python scripts/verify_pseudo_locale.py --json     # machine-readable summary
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pseudo_locale_transform import format_tokens, pseudofy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
EN_PO = REPO_ROOT / "locale" / "en" / "LC_MESSAGES" / "django.po"

_MSGID_RE = re.compile(r'^(?:msgid|msgid_plural)\s+"(.*)"$')
_CONT_RE = re.compile(r'^"(.*)"$')
_C_ESCAPE = re.compile(r'\\(.)')


def _unescape(value: str) -> str:
    """Decode the small set of PO C-escapes that affect token detection."""
    return _C_ESCAPE.sub(lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(m.group(1), m.group(1)), value)


def iter_source_strings(po_path: Path):
    """Yield every non-empty source string (msgid + msgid_plural) in a PO file.

    Handles multi-line continuation blocks. Skips the header entry (``msgid ""``).
    """
    if not po_path.exists():
        return
    lines = po_path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = _MSGID_RE.match(lines[i].strip())
        if m is None:
            i += 1
            continue
        value = m.group(1)
        j = i + 1
        while j < n and (cont := _CONT_RE.match(lines[j].strip())):
            value += cont.group(1)
            j += 1
        i = j
        if value:
            yield _unescape(value)


def _rel(po_path: Path) -> str:
    try:
        return po_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(po_path)


def scan(po_path: Path = EN_PO) -> dict:
    checked = 0
    failures: list[dict] = []
    transformed = 0
    for src in iter_source_strings(po_path):
        checked += 1
        src_tokens = format_tokens(src)
        pseudo = pseudofy(src)
        if format_tokens(pseudo) != src_tokens:
            failures.append(
                {
                    "source": src[:120],
                    "source_tokens": src_tokens,
                    "pseudo_tokens": format_tokens(pseudo),
                }
            )
        if pseudo != src:
            transformed += 1
    return {
        "po_path": _rel(po_path),
        "checked": checked,
        "transformed": transformed,
        "failures": failures,
        "failure_count": len(failures),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--sample", type=int, default=0, help="print N example transforms and exit 0")
    args = ap.parse_args()

    # Pseudo output carries non-Latin-1 glyphs (⟦ ⟧ · accents); force UTF-8 so a
    # legacy Windows console (cp1252) can't UnicodeEncodeError on --sample/--json.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if not EN_PO.exists():
        print(f"pseudo-locale gate: source catalog not found at {EN_PO} — nothing to check.")
        return 0

    if args.sample:
        shown = 0
        for src in iter_source_strings(EN_PO):
            if not any(ch.isalpha() for ch in src):
                continue
            print(f"  {src[:60]!r}\n    -> {pseudofy(src)[:80]!r}")
            shown += 1
            if shown >= args.sample:
                break
        return 0

    result = scan()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"pseudo-locale gate: checked {result['checked']} source string(s), "
            f"{result['transformed']} transformed, {result['failure_count']} token-corrupting."
        )
        for f in result["failures"][:20]:
            print(f"  TOKEN CORRUPTION: {f['source']!r}")
            print(f"    source tokens: {f['source_tokens']}")
            print(f"    pseudo tokens: {f['pseudo_tokens']}")

    if result["failure_count"]:
        print(
            f"\nFAIL: {result['failure_count']} source string(s) lose/alter an interpolation "
            f"token under pseudo-localization. Fix scripts/pseudo_locale_transform.py so the "
            f"protected-token set covers them — a corrupted %(x)s/{{x}}/<tag> would 500 the QA build.",
            file=sys.stderr,
        )
        return 1
    print("OK: pseudo-localization preserves every interpolation/markup token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
