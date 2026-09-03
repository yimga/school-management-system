#!/usr/bin/env python3
"""Tenant preview → live adoption gate (batch 1727+).

Ensures design-preview HTML contracts are wired into live templates per wave.
Registry: scripts/generated/tenant_preview_to_live_registry.json
Prompt: docs/phase_checklists/TENANT_PREVIEW_TO_LIVE_ADOPTION.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "scripts/generated/tenant_preview_to_live_registry.json"

WAVE_NEEDLES: dict[str, list[tuple[str, str]]] = {
    "W0": [
        ("docs/phase_checklists/TENANT_PREVIEW_TO_LIVE_ADOPTION.md", "Tenant preview → live adoption program"),
        ("static/css/rmc-tenant-preview-live-bridge.css", "rmc-preview-live"),
        ("templates/portal_base.html", "rmc-tenant-preview-live-bridge.css"),
        ("templates/portal_base.html", "cockpit.ai_copilot_rail.default_state"),
        ("apps/siteconfig/cockpit_context.py", "_resolve_tenant_copilot_default_state"),
        ("var/design-previews/tenant-admin-workspace-preview.html", "STATIC DESIGN PREVIEW"),
        ("var/design-previews/full-width-sweep-browsable.html", "role-surface"),
    ],
    "W1": [
        ("templates/accounts/backend_dashboard.html", "data-rmc-preview-live-admin"),
        ("templates/accounts/backend_dashboard.html", "rmc-admin-onboarding-setup"),
        ("templates/accounts/backend_dashboard.html", "Setup Studio"),
        ("templates/accounts/backend_dashboard.html", "admin_workspace_zone_intro"),
        ("templates/partials/tenant/admin_workspace_zone_intro.html", "Operator cockpit"),
        ("templates/partials/tenant/admin_workspace_zone_intro.html", "Setup Studio"),
        ("templates/accounts/backend_dashboard.html", "At a glance"),
        ("static/css/rmc-backend-admin-bento.css", "rmc-admin-zone-intro"),
        ("var/design-previews/tenant-admin-workspace-preview.html", "Set up your school"),
    ],
    "W2": [
        ("templates/teacher/dashboard.html", "data-rmc-preview-live-teacher"),
        ("templates/teacher/dashboard.html", "rmc-teacher-cockpit"),
        ("templates/teacher/_rmc_dh_teacher_home.html", "rmc-preview-live-teacher"),
        ("templates/teacher/_rmc_dh_teacher_home.html", "rmc-teacher-attention"),
        ("templates/teacher/_rmc_dh_teacher_home.html", "rmc-preview-live-fw"),
        ("static/css/rmc-tenant-preview-live-bridge.css", "rmc-preview-live-class-grid"),
        ("var/design-previews/tenant-teacher-dashboard-preview.html", "Teaching"),
    ],
    "W3": [
        ("templates/parent/dashboard.html", "data-rmc-preview-live-parent"),
        ("templates/parent/dashboard.html", "rmc-parent-cockpit"),
        ("templates/parent/_rmc_dh_family_home.html", "rmc-preview-live-parent"),
        ("templates/parent/_rmc_dh_family_home.html", "rmc-parent-attention"),
        ("templates/parent/_rmc_dh_family_home.html", "Today snapshot"),
        ("static/css/rmc-tenant-preview-live-bridge.css", "rmc-preview-live-hero-actions"),
        ("var/design-previews/tenant-parent-dashboard-preview.html", "Family Home"),
    ],
    "W4": [
        ("templates/student/learning_home.html", "data-rmc-preview-live-student"),
        ("templates/student/learning_home.html", "rmc-student-cockpit"),
        ("templates/student/_rmc_dh_student_home.html", "rmc-preview-live-student"),
        ("templates/student/_rmc_dh_student_home.html", "rmc-student-today"),
        ("var/design-previews/tenant-student-dashboard-enrichment-100x.html", "Student"),
    ],
    "W5": [
        ("scripts/run_role_home_visual_sweep.mjs", "toolsTrayOpen"),
        ("scripts/run_role_home_visual_sweep.mjs", "preview-live"),
        ("var/design-previews/full-width-sweep-browsable.html", "sweep-tabs"),
    ],
    "W6": [
        ("templates/setup_studio/tenant_wizard.html", "review_mode"),
        ("templates/setup_studio/tenant_wizard.html", "rmc-wizard-step-assist"),
        ("var/design-previews/mfa-wizard-review-void-fix-preview.html", "MFA"),
        ("var/design-previews/wizard-step-assist-preview.html", "Assist"),
    ],
}


# --------------------------------------------------------------------------
# Behaviour checks
#
# A (path, substring) needle asserts a WORD. Two W1 needles outlived the words
# they named while the behaviour behind them survived intact, so this gate
# failed continuously and told nobody anything:
#
#   * "rmc-setup-surface__title" -- 84b7cf382 (2026-08-02) folded the setup
#     landing's scattered islands into ONE bounded cockpit card and renamed the
#     class to rmc-cockpit__title. The <h1> and its "Set up your <school>" copy
#     moved verbatim; only the class token changed.
#   * "minmax(220px" -- 159255257 (2026-08-01) replaced
#     repeat(auto-fill, minmax(220px, 1fr)) with
#     repeat(auto-fit, minmax(min(100%, 14.5rem), 1fr)): the same responsive
#     card grid, minus the bare fixed min track that overflows any container
#     narrower than itself.
#
# Both are asserted below as the behaviour they stood for, so a rename or a unit
# change no longer reads as a breach -- and, unlike the needles, deleting the
# heading or flattening the grid now does.
# --------------------------------------------------------------------------

SETUP_SURFACE_PARTIAL = "templates/partials/tenant/setup_command_surface.html"
SETUP_SURFACE_CSS = "static/css/rmc-setup-surface.css"

_H1_RE = re.compile(r"<h1(?:\s[^>]*)?>(.*?)</h1>", re.S | re.I)
_SURFACE_LABELLED_RE = re.compile(
    r'class="(?:[^"]*\s)?rmc-setup-surface(?:\s[^"]*)?"[^>]*aria-label='
)
_CARDS_RULE_RE = re.compile(r"\.rmc-setup-surface__cards\s*\{(.*?)\}", re.S)
_GRID_COLS_RE = re.compile(r"grid-template-columns\s*:\s*([^;]+);")
_REPEAT_MINMAX_RE = re.compile(
    r"repeat\(\s*(auto-fit|auto-fill)\s*,\s*minmax\(\s*(.+?)\s*,\s*1fr\s*\)\s*\)",
    re.S,
)


def _read_rel(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _check_setup_surface_heading() -> list[str]:
    """The setup command surface names itself with exactly one translatable <h1>."""
    body = _read_rel(SETUP_SURFACE_PARTIAL)
    if body is None:
        return [f"missing file: {SETUP_SURFACE_PARTIAL}"]
    findings: list[str] = []
    headings = _H1_RE.findall(body)
    if len(headings) != 1:
        findings.append(
            f"{SETUP_SURFACE_PARTIAL}: expected exactly one <h1> naming the setup "
            f"surface, found {len(headings)}"
        )
    inner = headings[0] if headings else ""
    if headings and not ("{% blocktrans" in inner or "{% trans" in inner):
        findings.append(
            f"{SETUP_SURFACE_PARTIAL}: the setup surface <h1> must be translatable "
            f"(trans / blocktrans), not raw copy"
        )
    if headings and "Set up your" not in inner:
        findings.append(
            f"{SETUP_SURFACE_PARTIAL}: the setup surface <h1> must carry the approved "
            f"preview title 'Set up your <school>' (see the W1 design-preview needle)"
        )
    if not _SURFACE_LABELLED_RE.search(body):
        findings.append(
            f"{SETUP_SURFACE_PARTIAL}: the .rmc-setup-surface region must carry an "
            f"aria-label so the landmark has an accessible name"
        )
    return findings


def _check_setup_surface_card_grid() -> list[str]:
    """Step cards stay a responsive grid that cannot overflow its container."""
    body = _read_rel(SETUP_SURFACE_CSS)
    if body is None:
        return [f"missing file: {SETUP_SURFACE_CSS}"]
    rule = _CARDS_RULE_RE.search(body)
    if not rule:
        return [f"{SETUP_SURFACE_CSS}: no .rmc-setup-surface__cards rule"]
    cols = _GRID_COLS_RE.search(rule.group(1))
    if not cols:
        return [
            f"{SETUP_SURFACE_CSS}: .rmc-setup-surface__cards must set "
            f"grid-template-columns -- the step cards stop reflowing without it"
        ]
    value = cols.group(1).strip()
    match = _REPEAT_MINMAX_RE.search(value)
    if not match:
        return [
            f"{SETUP_SURFACE_CSS}: .rmc-setup-surface__cards must lay out as "
            f"repeat(auto-fit|auto-fill, minmax(<min>, 1fr)) so step cards reflow by "
            f"available width; found {value!r}"
        ]
    minimum = match.group(2)
    if "min(" not in minimum and "%" not in minimum:
        return [
            f"{SETUP_SURFACE_CSS}: .rmc-setup-surface__cards minmax minimum {minimum!r} "
            f"is a bare fixed length -- it overflows any container narrower than itself; "
            f"clamp it (min(100%, <len>)) the way 159255257 did"
        ]
    return []


WAVE_BEHAVIOURS = {
    "W1": (_check_setup_surface_heading, _check_setup_surface_card_grid),
}


def _load_registry() -> dict:
    if not REGISTRY.is_file():
        return {}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _check_needles(wave: str) -> list[str]:
    findings: list[str] = []
    for rel, needle in WAVE_NEEDLES.get(wave, []):
        path = ROOT / rel.replace("/", "\\") if "\\" in str(ROOT) else ROOT / rel
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing file: {rel}")
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if needle not in body:
            findings.append(f"{rel}: missing needle {needle!r}")
    return findings


def _check_registry_integrity(reg: dict) -> list[str]:
    findings: list[str] = []
    if not reg:
        return ["registry missing or empty"]
    for key in ("hub_html", "prompt_doc", "bridge_css"):
        rel = reg.get(key, "")
        if not rel or not (ROOT / rel).is_file():
            findings.append(f"registry {key} not found: {rel}")
    for role in reg.get("roles", []):
        prev = role.get("preview", "")
        if prev and not (ROOT / prev).is_file():
            findings.append(f"role preview missing: {prev}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", default="", help="Check only this wave (W0–W6)")
    args = parser.parse_args()

    reg = _load_registry()
    findings = _check_registry_integrity(reg)

    waves = [args.wave.upper()] if args.wave else list(WAVE_NEEDLES.keys())
    for wave in waves:
        if wave not in WAVE_NEEDLES:
            findings.append(f"unknown wave: {wave}")
            continue
        findings.extend(_check_needles(wave))
        for behaviour in WAVE_BEHAVIOURS.get(wave, ()):
            findings.extend(behaviour())

    if findings:
        print("TENANT_PREVIEW_TO_LIVE_FAIL")
        for item in findings:
            print(f"  - {item}")
        return 1

    token = f"TENANT_PREVIEW_TO_LIVE_{args.wave.upper()}_PASS" if args.wave else "TENANT_PREVIEW_TO_LIVE_PASS"
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
