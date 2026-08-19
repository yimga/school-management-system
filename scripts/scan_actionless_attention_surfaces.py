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


def _include_pattern(component: str) -> re.Pattern[str]:
    # {% include "<component>" with ... %} — non-greedy up to the closing tag.
    return re.compile(
        r"\{%\s*include\s+['\"]" + re.escape(component) + r"['\"](?P<args>[^%]*?)%\}",
        re.S,
    )


def scan() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for component, param in ATTENTION_COMPONENTS.items():
            for match in _include_pattern(component).finditer(text):
                args = match.group("args")
                if param in args or EXEMPTION_PARAM in args:
                    continue
                findings.append(
                    {
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "line": text[: match.start()].count("\n") + 1,
                        "component": Path(component).stem,
                        "missing": param,
                    }
                )
    return findings


def _key(finding: dict[str, object]) -> str:
    """Line-insensitive: editing a template above a finding must not re-flag it."""
    return f"{finding['path']}::{finding['component']}"


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
