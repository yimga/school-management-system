#!/usr/bin/env python
"""Attention surfaces must lead somewhere.

A tenant admin opened their dashboard and read:

    (!) What needs you
        6 access requests awaiting approval

...with no link, no button, nothing. The platform knew the work existed, knew
how many there were, knew exactly which screen resolves them — and made the
reader go find it. That is a DEAD END: a surface that reports a backlog and
offers no way to act on it.

It was never a one-off. ``components/dashboard/rmc_dh_attn_row.html`` has
accepted ``dh_go_href`` from the day it was written, and the invoice row two
lines above rendered a working "Chase" link. The approvals row simply omitted
the parameter, and nothing in the build noticed.

THE RULE
--------
Every include of an attention component must do one of two things:

  1. pass a destination  (``dh_go_href`` / ``dh_href``), or
  2. state why it has none, via ``dh_no_action_reason``.

The second branch is not a loophole; it is the point. A row reading "Queue
clear" reports the ABSENCE of work and correctly has nowhere to go. Forcing a
link onto it would make the surface worse, so the exemption lives in the
template where a reviewer reads it — never in a baseline file where it becomes
invisible.

Two components are in scope because their whole purpose is to say "this needs
you": ``rmc_dh_attn_row`` and ``rmc_dh_due_item``. Purely informational
components (``rmc_dh_lead_item`` for top performers, ``rmc_dh_badge``) are
deliberately NOT in scope — enforcing links there would flood the gate with
noise and get it switched off, which is how gates die.

Flags: ``--json``, ``--compare`` (exit 1 only on findings NOT in the baseline),
``--update-baseline``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
BASELINE = ROOT / "var" / "security-audit-baseline-actionless-attention-surfaces.json"

# component template path -> the parameter that carries its destination
ATTENTION_COMPONENTS: dict[str, str] = {
    "components/dashboard/rmc_dh_attn_row.html": "dh_go_href",
    "components/dashboard/rmc_dh_due_item.html": "dh_href",
}

# The documented, reviewer-visible way to say "this row has nothing to act on".
EXEMPTION_PARAM = "dh_no_action_reason"

# ---------------------------------------------------------------------------
# RULE B — counted backlogs outside the component vocabulary.
#
# Rule A only sees the two dashboard components. The same defect occurs in
# hand-written markup: "{{ n }} awaiting approval" rendered as bare text. This
# rule finds a COUNT plus actionable-state language with no affordance nearby.
#
# The count requirement is what makes it precise. "Pending approval" alone is a
# status label on one item; "Pending approval (7)" is a backlog. Dropping the
# count requirement took the finding set from 38 to 122, and every one of the
# extra 84 was a label, an empty state, or a page title — noise that would get
# the gate switched off.
#
# Four categories are NOT this defect, and each must say which it is:
#
#   resolver-surface  the count sits ON the page that clears it. "Failed: 3" on
#                     the import monitor is not a dead end — you are already there.
#   status-label      a badge on a single row, not a backlog.
#   empty-state       reports the ABSENCE of work ("No grants awaiting approval").
#   descriptive-copy  prose that happens to contain a number.
# ---------------------------------------------------------------------------

BACKLOG_STATE = re.compile(
    r"awaiting\s+(approval|review|action)|pending\s+(approval|review|invite)"
    r"|needs?\s+(attention|action|review)|action\s+required|requires\s+(approval|action)"
    r"|overdue|at[-\s]risk|unresolved|outstanding|expiring|failed",
    re.I,
)

# A number in the neighbourhood — what separates a backlog from a label.
COUNT_NEARBY = re.compile(
    r"\{\{\s*[\w.|:_]*count[\w.|:_]*\s*\}\}|\{%\s*blocktrans\s+count\b|\|length|\{\{\s*n\s*\}\}",
    re.I,
)

# An affordance is anything that lets the reader ACT. Plain <a>/<button>/<form>,
# the component destination params — and template tags that RENDER actions, which
# no amount of HTML matching would find. operator_queue_smart_links_banner.html
# looked actionless until `{% render_smart_links %}` on its last line was read.
AFFORDANCE = re.compile(
    r"<a\b[^>]*href=|<button\b|<form\b"
    r"|dh_go_href|dh_href|dh_more_href"
    r"|role=[\"']button"
    r"|\{%\s*render_smart_links\b|\{%\s*include\s+[\"'][^\"']*(action|cta|smart_link)"
    # A destination handed to a component is as real as an <a>: insight_card takes
    # action_url/action_label, and the operator row-detail cards take a JSON action
    # array that JS turns into buttons. Judging only raw HTML reported both as dead
    # ends while they were rendering perfectly good links.
    r"|\baction_url\s*=|\bprimary_url\s*=|data-rmc-row-actions",
    re.I,
)

# A tag that renders a whole action set serves the SURFACE, not one line, so it
# counts wherever it sits in the file. operator_queue_smart_links_banner.html
# reads as actionless for twenty lines and then calls {% render_smart_links %} on
# its last one; judging it by a line window would report a banner whose entire
# purpose is to offer actions.
FILE_LEVEL_AFFORDANCE = re.compile(r"\{%\s*render_smart_links\b", re.I)

# Shapes that are structurally incapable of being this defect.
NOT_A_BACKLOG = re.compile(
    r"\{%\s*block\s+title|\{#|\{%\s*comment|rmc_empty_state|empty_state"
    r"|\{%\s*(el)?if\s|visually-hidden|aria-label|legend|swatch|__sw\b"
    r"|msgid|placeholder=",
    re.I,
)

# A line that is nothing but a data-/aria- attribute is plumbing, not something a
# person reads. `data-server-failed="{{ server_failed }}"` carries the word
# "failed" and a value, and is neither a backlog nor a dead end.
ATTRIBUTE_ONLY_LINE = re.compile(r"^\s*(data|aria)-[\w-]+\s*=", re.I)

_ALLOW_CATEGORIES = frozenset(
    {"resolver-surface", "status-label", "empty-state", "descriptive-copy"}
)

# A fifth category exists only because this platform is host-split. accounts:
# backend_dashboard is routed on the manager and public URLconfs as well as the
# tenant one, but finance:/requests:/analytics: are registered ONLY on the tenant
# side. A template rendering on all three must therefore fall back to plain text
# on the hosts where its destination does not exist — a bare href="" would be a
# focusable link to nowhere, the same defect wearing a link.
#
# This one is CONSTRAINED so it cannot become the escape hatch the other four
# aren't: it is only honoured when the file actually attempts a destination with
# `{% url … as … %}`. Claiming it without trying to resolve anything is refused.
_HOST_ABSENT_CATEGORY = "no-destination-on-host"
_URL_AS_ATTEMPT = re.compile(r"\{%\s*url\s+[^%]*?\bas\b\s+\w+\s*%\}")
# {# attention-allow: resolver-surface — this page IS the review queue #}
_ALLOW_MARKER = re.compile(
    r"attention-allow:\s*(?P<category>[a-z-]+)", re.I
)

_WINDOW_BEFORE = 5
_WINDOW_AFTER = 6


def _include_pattern(component: str) -> re.Pattern[str]:
    # {% include "<component>" with ... %} — non-greedy up to the closing tag.
    return re.compile(
        r"\{%\s*include\s+['\"]" + re.escape(component) + r"['\"](?P<args>[^%]*?)%\}",
        re.S,
    )


def _scan_components(path: Path, text: str) -> list[dict[str, object]]:
    """Rule A — the two components whose whole purpose is "this needs you"."""
    out: list[dict[str, object]] = []
    for component, param in ATTENTION_COMPONENTS.items():
        for match in _include_pattern(component).finditer(text):
            args = match.group("args")
            if param in args or EXEMPTION_PARAM in args:
                continue
            out.append(
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": text[: match.start()].count("\n") + 1,
                    "component": Path(component).stem,
                    "missing": param,
                    "rule": "component",
                }
            )
    return out


def _scan_counted_backlogs(path: Path, text: str) -> list[dict[str, object]]:
    """Rule B — a counted backlog in hand-written markup with nothing to act on."""
    out: list[dict[str, object]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not BACKLOG_STATE.search(line) or NOT_A_BACKLOG.search(line):
            continue
        if ATTRIBUTE_ONLY_LINE.match(line):
            continue
        start = max(0, index - _WINDOW_BEFORE)
        window = "\n".join(lines[start : index + _WINDOW_AFTER])
        if not COUNT_NEARBY.search(window):
            continue
        if AFFORDANCE.search(window) or FILE_LEVEL_AFFORDANCE.search(text):
            continue
        marker = _ALLOW_MARKER.search(window)
        if marker:
            category = marker.group("category").lower()
            if category in _ALLOW_CATEGORIES:
                continue
            # Honoured only where a destination was genuinely attempted.
            if category == _HOST_ABSENT_CATEGORY and _URL_AS_ATTEMPT.search(text):
                continue
        out.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "line": index + 1,
                "component": "counted-backlog",
                "missing": "an affordance or an attention-allow category",
                "rule": "counted-backlog",
                "text": line.strip()[:90],
            }
        )
    return out


def scan() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(_scan_components(path, text))
        findings.extend(_scan_counted_backlogs(path, text))
    return findings


def _key(finding: dict[str, object]) -> str:
    """Line-insensitive: editing a template above a finding must not re-flag it."""
    return f"{finding['path']}::{finding['component']}::{finding.get('text', '')}"


def _load_baseline() -> list[str]:
    if not BASELINE.exists():
        return []
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("frozen", []))


def _write_baseline(findings: list[dict[str, object]]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps(
            {
                "rule": "attention surfaces must carry a destination or state why not",
                "frozen": sorted({_key(f) for f in findings}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()

    if args.update_baseline:
        _write_baseline(findings)
        print(f"actionless-attention-surfaces: baseline written ({len(findings)} frozen).")
        return 0

    if args.json:
        print(json.dumps(findings, indent=2))

    if args.compare:
        frozen = set(_load_baseline())
        fresh = [f for f in findings if _key(f) not in frozen]
        if not fresh:
            print(
                "actionless-attention-surfaces: no new dead ends "
                f"({len(findings)} total, {len(frozen)} frozen)."
            )
            return 0
        print(f"actionless-attention-surfaces: {len(fresh)} NEW dead end(s):", file=sys.stderr)
        for f in fresh:
            print(
                f"  {f['path']}:{f['line']}  {f['component']} has no {f['missing']}",
                file=sys.stderr,
            )
        print(
            "\nAn attention row states that something needs the reader. Give it the page\n"
            "that resolves it (pass the destination parameter), or — if it reports the\n"
            f"ABSENCE of work, like 'Queue clear' — say so with {EXEMPTION_PARAM}.",
            file=sys.stderr,
        )
        return 1

    if not args.json:
        if findings:
            for f in findings:
                print(f"  {f['path']}:{f['line']}  {f['component']} has no {f['missing']}")
        print(f"actionless-attention-surfaces: {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
