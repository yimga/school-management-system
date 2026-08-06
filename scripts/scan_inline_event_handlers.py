#!/usr/bin/env python3
"""Inline event-handler (``onclick=`` …) scanner — the M9 CSP-enforce seal.

The platform's ``script-src`` is ``'self'`` + a per-request ``'nonce-<n>'`` with
NO ``'unsafe-inline'`` (``apps/security/csp_middleware.py``). That is the directive
that actually stops XSS, so it is kept tight — but it also means an inline event
handler ATTRIBUTE (``onclick=``, ``onchange=``, ``onsubmit=`` …) is BLOCKED under
enforce: a nonce can authorize a ``<script>`` ELEMENT, never an ``on*`` attribute.
Until every such handler is retired, prod pins ``CSP_ENFORCE=0`` (Report-Only) in
``render.yaml``. This scanner is the ratchet that keeps the burndown at zero so the
enforce flip stays safe.

What it flags
-------------
Any inline ``on<event>="…"`` / ``on<event>='…'`` attribute on an HTML element in a
served template. The event name must be a real DOM event (curated list) so a
``data-onboarding=`` attribute or an ``once=`` prop never false-positives.

What it deliberately does NOT flag (masked before matching, so zero FPs)
-----------------------------------------------------------------------
* ``<script>…</script>`` / ``<style>…</style>`` block bodies — a JS property
  assignment ``el.onclick = fn`` or an ``addEventListener`` reference is fine under
  CSP (it runs inside an already-nonced/same-origin script), and a handler name
  inside a JS string is not an attribute.
* ``{% comment %}…{% endcomment %}``, ``{# … #}``, and ``<!-- … -->`` comments —
  usage examples in docstrings are not live handlers.

Scope
-----
Walks ``templates/**`` + ``apps/*/templates/**``. EXCLUDES ``**/admin/**``: the CSP
middleware's ``BYPASS_PREFIXES`` includes ``/admin/``, so the Django-admin surface
(Unfold + Alpine.js, which needs ``eval``) never receives the strict policy — its
inline handlers are out of scope for the enforce flip.

Zero-tolerance (baseline 0) post-burndown, like ``scan_inline_style_off_token``.
Mark a genuinely-unavoidable site with ``<!-- inline-handler-allow: <reason> -->``
on the same line or the line above.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = [ROOT / "templates", ROOT / "apps"]
BASELINE = ROOT / "var" / "security-audit-baseline-inline-event-handlers.json"

# Real DOM event-handler attribute names (without the leading "on"). A curated
# list keeps `onboarding`, `once`, `only`, etc. from ever matching.
_EVENTS = (
    "abort afterprint animationend animationiteration animationstart beforeprint "
    "beforeunload blur canplay canplaythrough change click contextmenu copy "
    "cuechange cut dblclick drag dragend dragenter dragleave dragover dragstart "
    "drop durationchange emptied ended error focus focusin focusout formdata "
    "hashchange input invalid keydown keypress keyup load loadeddata "
    "loadedmetadata loadstart message mousedown mouseenter mouseleave mousemove "
    "mouseout mouseover mouseup mousewheel offline online pagehide pageshow paste "
    "pause play playing popstate progress ratechange reset resize scroll search "
    "seeked seeking select show stalled storage submit suspend timeupdate toggle "
    "touchcancel touchend touchmove touchstart transitionend unload volumechange "
    "waiting wheel"
).split()

# An inline handler ATTRIBUTE: `on<event>=` not preceded by a word char or hyphen
# (so `data-onclick`/`my_onclick` never match), value opened by a quote.
HANDLER_RE = re.compile(
    r'(?<![\w-])on(' + "|".join(_EVENTS) + r')\s*=\s*["\']',
    re.IGNORECASE,
)

ALLOW_RE = re.compile(r"inline-handler-allow\s*:")

# Masking patterns — blank these regions (newlines preserved) before matching.
_MASK_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.IGNORECASE | re.DOTALL),
    re.compile(r"{#.*?#}", re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
]


def _blank_preserving_newlines(match: re.Match) -> str:
    """Replace a matched span with spaces, keeping newlines so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _mask(text: str) -> str:
    for pat in _MASK_PATTERNS:
        text = pat.sub(_blank_preserving_newlines, text)
    return text


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_text(text: str, rel_path: str) -> list[dict]:
    masked = _mask(text)
    raw_lines = text.splitlines()
    findings: list[dict] = []
    for m in HANDLER_RE.finditer(masked):
        line = _line_of(masked, m.start())
        # Allow-marker on the same line or the line directly above.
        same = raw_lines[line - 1] if 0 <= line - 1 < len(raw_lines) else ""
        prev = raw_lines[line - 2] if 0 <= line - 2 < len(raw_lines) else ""
        if ALLOW_RE.search(same) or ALLOW_RE.search(prev):
            continue
        findings.append(
            {
                "file": rel_path,
                "line": line,
                "event": "on" + m.group(1).lower(),
            }
        )
    return findings


def _iter_template_files():
    seen: set[Path] = set()
    for base in TEMPLATE_ROOTS:
        if not base.exists():
            continue
        for p in base.rglob("*.html"):
            # CSP bypasses /admin/ (see module docstring) — Django-admin surface
            # never receives the strict policy, so its handlers are out of scope.
            if "admin" in p.relative_to(ROOT).parts:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def collect() -> list[dict]:
    out: list[dict] = []
    for p in sorted(_iter_template_files()):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        out.extend(scan_text(text, p.relative_to(ROOT).as_posix()))
    return out


def fingerprint(findings: list[dict]) -> dict:
    by_event: dict[str, int] = defaultdict(int)
    for f in findings:
        by_event[f["event"]] += 1
    return {"finding_count": len(findings), "by_event": dict(by_event)}


def write_baseline(findings: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    fp = fingerprint(findings)
    payload = {
        "scanner": "inline-event-handlers",
        "finding_count": fp["finding_count"],
        "by_event": fp["by_event"],
        "findings": sorted(findings, key=lambda f: (f["file"], f["line"], f["event"])),
    }
    BASELINE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_baseline() -> dict:
    if not BASELINE.exists():
        return {"findings": [], "finding_count": 0}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _print_report(findings: list[dict]) -> None:
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_file[f["file"]].append(f)
    for path in sorted(by_file):
        for f in sorted(by_file[path], key=lambda x: x["line"]):
            print(f"  {f['file']}:{f['line']}  [{f['event']}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--compare", action="store_true", help="CI mode: fail on any finding above baseline (0)")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero when ANY finding exists")
    ap.add_argument("--write-baseline", action="store_true", help="Snapshot current findings as new baseline")
    ap.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = ap.parse_args()

    findings = collect()
    fp = fingerprint(findings)

    if args.write_baseline:
        write_baseline(findings)
        n_files = len({f["file"] for f in findings})
        print(f"Wrote baseline: {fp['finding_count']} finding(s) across {n_files} file(s)")
        return 0

    if args.json:
        print(json.dumps({"finding_count": fp["finding_count"], "findings": findings}, indent=2))
        return 0

    if args.compare:
        base = load_baseline()
        old = base.get("finding_count", len(base.get("findings", [])))
        new = fp["finding_count"]
        if new > old:
            print(f"FAIL: inline-event-handler findings grew by {new - old} ({old} -> {new})")
            base_keys = {(f["file"], f["line"], f["event"]) for f in base.get("findings", [])}
            for f in findings:
                if (f["file"], f["line"], f["event"]) not in base_keys:
                    print(f"  NEW: {f['file']}:{f['line']}  [{f['event']}]")
            print(
                "\nRetire the handler: move the behavior into a nonced <script> "
                "(addEventListener) or a data-attribute handled by "
                "static/js/rmc-csp-behaviors.js. Mark an unavoidable site with "
                "<!-- inline-handler-allow: <reason> -->."
            )
            return 1
        print(f"PASS: inline-event-handler findings {old} -> {new} (no growth)")
        return 0

    # Default: report.
    print(f"Inline event-handler findings: {fp['finding_count']}")
    if findings:
        _print_report(findings)
        for event, n in sorted(fp["by_event"].items()):
            print(f"    {event}: {n}")
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
