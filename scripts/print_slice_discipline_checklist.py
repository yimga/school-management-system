#!/usr/bin/env python3
"""
Print §11.4 anti-drag slice checklist to stdout.

Canonical rules: docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md (§11.4).
Does not run gates; use before opening a PR or when a slice feels unbounded.
"""

from __future__ import annotations

LINES = (
    "RunMyCampus 11.4 slice checklist (anti-drag)",
    "",
    "  [ ] Single theme: one 11.4 queue row or named sub-bullet for this change set",
    "  [ ] DONE criteria: tests or script exits agreed before / during implementation",
    "  [ ] A-F log row in docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md for this slice",
    "  [ ] 11.4 queue row updated (DONE / PARTIAL / QUEUED / BLOCKED + owner if blocked)",
    "  [ ] migrations: python manage.py makemigrations --check (if models touched)",
    "  [ ] merge: bash scripts/pre_deploy_gate.sh (or fix the first failing step)",
    "",
)


def main() -> None:
    print("\n".join(LINES))


if __name__ == "__main__":
    main()
