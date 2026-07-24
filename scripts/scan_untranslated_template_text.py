#!/usr/bin/env python3
"""Ratchet gate: hardcoded (untranslated) text in label-bearing template elements.

The M21 audit found ~19% of templates carry user-facing English that was never
wrapped in ``{% trans %}`` / ``{% blocktrans %}`` — invisible to a real translation
and to the pseudo-locale QA build. This is the static, CI-native companion to the
``en_XA`` pseudo-locale (``scripts/verify_pseudo_locale.py``): it freezes the current
backlog and fails only when a NEW hardcoded string lands, so the count can only go
down.

**Scope is deliberately narrow to stay low-false-positive** (the codebase's own
lesson: "a gate that rejects true statements is worse than none"). It inspects only
the DIRECT text of elements that almost always carry a user-facing label —
``button, a, label, th, h1..h6, option, legend, summary, figcaption, caption`` — and
flags that text only when, after stripping nested tags, ``{{ }}`` / ``{% %}``
fragments, entities, digits and punctuation, a real word remains (a translated label
renders its text from inside ``{% trans %}``, i.e. inside ``{% %}``, so it strips to
nothing and is never flagged). It is false-negative biased: prose paragraphs, alt
text, titles, and every non-label element are intentionally out of scope for v1.

Opt a reviewed site out with ``{# i18n-allow: <reason> #}`` on the element's line or
the line above, or a whole file with ``{# i18n-allow-file: <reason> #}`` anywhere in
it (brand names, code samples, a template that is itself an email body, etc.).

Usage:
  python scripts/scan_untranslated_template_text.py            # write/update baseline
  python scripts/scan_untranslated_template_text.py --compare  # gate (fail on NEW)
  python scripts/scan_untranslated_template_text.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-untranslated-template-text.json"

# Directories that hold Django templates.
_TEMPLATE_GLOBS = ("templates/**/*.html", "apps/*/templates/**/*.html")

# Label-bearing elements: their direct text is reliably a user-facing UI string.
_LABEL_TAGS = ("button", "a", "label", "th", "h1", "h2", "h3", "h4", "h5", "h6",
               "option", "legend", "summary", "figcaption", "caption")
_ELEMENT_RE = re.compile(
    r"<(" + "|".join(_LABEL_TAGS) + r")(?:\s[^>]*)?>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)

# Blocks whose inner text must be ignored entirely.
_SKIP_BLOCK_RE = re.compile(
    r"<(script|style|pre|code|textarea)\b.*?</\1>"
    r"|<!--.*?-->"
    r"|{%\s*comment\s*%}.*?{%\s*endcomment\s*%}"
    r"|{%\s*(?:blocktrans|blocktranslate)\b.*?{%\s*(?:endblocktrans|endblocktranslate)\s*%}"
    r"|{%\s*verbatim\s*%}.*?{%\s*endverbatim\s*%}",
    re.IGNORECASE | re.DOTALL,
)


def _blank(segment: str) -> str:
    """Same-length blank that preserves newlines so line numbers stay accurate."""
    return re.sub(r"[^\n]", " ", segment)

_NESTED_TAG_RE = re.compile(r"<[^>]+>")
_DJANGO_VAR_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)
_ENTITY_RE = re.compile(r"&[#0-9a-zA-Z]+;")
_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_VOWEL_RE = re.compile(r"[AaEeIiOoUuYy]")

_ALLOW_LINE_RE = re.compile(r"{#\s*i18n-allow\s*:")
_ALLOW_FILE_RE = re.compile(r"{#\s*i18n-allow-file\s*:")


def _looks_like_language(text: str) -> bool:
    """True if the cleaned label text contains at least one natural-language word.

    A "word" is >=3 letters and contains a vowel — filters out acronyms (PDF, CSV,
    ID), single glyphs, numbers, and pure punctuation without dragging prose in.
    """
    words = _WORD_RE.findall(text)
    return any(len(w) >= 3 and _VOWEL_RE.search(w) for w in words)


def _clean_label(inner: str) -> str:
    inner = _NESTED_TAG_RE.sub(" ", inner)
    inner = _DJANGO_VAR_RE.sub(" ", inner)
    inner = _ENTITY_RE.sub(" ", inner)
    return inner.strip()


def _line_of(offset: int, newline_offsets: list[int]) -> int:
    # binary-search the 1-indexed line for a character offset
    import bisect

    return bisect.bisect_right(newline_offsets, offset) + 1


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_template_files() -> list[Path]:
    seen: set[Path] = set()
    for pattern in _TEMPLATE_GLOBS:
        for p in REPO_ROOT.glob(pattern):
            if p.is_file():
                seen.add(p)
    return sorted(seen)


def scan_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if _ALLOW_FILE_RE.search(text):
        return []
    # Blank out skip-blocks then every {{ }} / {% %} fragment (newline-preserving so
    # line numbers stay accurate). Masking template tags BEFORE element matching stops
    # a `>` inside `{% if a > b %}` in an attribute from breaking element boundaries,
    # and makes a translated label (text inside {% trans %}) strip to nothing.
    masked = _SKIP_BLOCK_RE.sub(lambda m: _blank(m.group(0)), text)
    masked = _DJANGO_VAR_RE.sub(lambda m: _blank(m.group(0)), masked)
    lines = masked.splitlines(keepends=True)
    newline_offsets: list[int] = []
    off = 0
    for ln in lines:
        off += len(ln)
        newline_offsets.append(off)
    raw_lines = text.splitlines()

    findings: list[dict] = []
    for m in _ELEMENT_RE.finditer(masked):
        inner = m.group(2)
        cleaned = _clean_label(inner)
        if not cleaned or not _looks_like_language(cleaned):
            continue
        line = _line_of(m.start(), newline_offsets)
        # Line-level allow marker (this line or the line above).
        idx = line - 1
        window = " ".join(raw_lines[max(0, idx - 1): idx + 1])
        if _ALLOW_LINE_RE.search(window):
            continue
        snippet = re.sub(r"\s+", " ", cleaned)[:60]
        findings.append(
            {
                "path": _rel(path),
                "tag": m.group(1).lower(),
                "text": snippet,
            }
        )
    return findings


def scan(files: list[Path] | None = None) -> list[dict]:
    files = files if files is not None else _iter_template_files()
    out: list[dict] = []
    for f in files:
        out.extend(scan_file(f))
    return out


def _key(f: dict) -> tuple[str, str, str]:
    return (f["path"], f["tag"], f["text"])


def _payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Hardcoded user-facing text in label-bearing template elements "
            f"({', '.join(_LABEL_TAGS)}). Ratchet: NEW findings fail --compare; "
            "existing are the burndown backlog. Wrap in {% trans %}/{% blocktrans %} "
            "or mark {# i18n-allow: <reason> #}."
        ),
        "label_tags": list(_LABEL_TAGS),
        "finding_count": len(findings),
        "findings": sorted(findings, key=_key),
    }


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_payload(findings), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)} ({len(findings)} findings)")


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", action="store_true", help="fail on NEW findings vs baseline")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    args = ap.parse_args()

    findings = scan()
    print(f"untranslated-template-text scan: {len(findings)} label(s) flagged")

    if args.json:
        print(json.dumps(_payload(findings), indent=2, ensure_ascii=False))
        return 0

    if not args.compare:
        _write_baseline(findings)
        return 0

    baseline = _load_baseline()
    if baseline is None:
        print("\nNo baseline on disk. Run without --compare to write one.", file=sys.stderr)
        return 1
    baseline_counts = Counter(_key(f) for f in baseline.get("findings", []))
    current_counts = Counter(_key(f) for f in findings)
    new = current_counts - baseline_counts
    if new:
        print(f"\nFAIL: {sum(new.values())} NEW hardcoded label(s) not in the baseline:", file=sys.stderr)
        for (path, tag, text), n in sorted(new.items()):
            print(f"  {path}: <{tag}> {text!r}", file=sys.stderr)
        print(
            "\nWrap the text in {% trans %}/{% blocktrans %}, or mark a reviewed site "
            "{# i18n-allow: <reason> #}. Do not add it to the baseline.",
            file=sys.stderr,
        )
        return 1
    removed = baseline_counts - current_counts
    if removed:
        print(f"  {sum(removed.values())} label(s) burned down since baseline (update it when ready).")
    print("OK: no new hardcoded labels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
