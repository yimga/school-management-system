#!/usr/bin/env python3
"""Glocal adoption — row-detail drawer on every operational rmc-data-table."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shell_css_contract as css_contract  # noqa: E402  (repo-local helper)

EXCLUDE_REL = frozenset(
    {
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/admin/base_site.html",
        "templates/base.html",
        "templates/customersuccess/guided_onboarding.html",
        "templates/siteconfig/partials/reportcard_style_preview_body.html",
        "templates/admin/partials/admin_v1_index_surface_previews.html",
        "templates/partials/cockpit/_churn_scorecard.html",
        "templates/components/rmc_skeleton.html",
    }
)

CONFLICT_CARD_TARGETS: tuple[tuple[str, str], ...] = (
    ("templates/portal/offline_sync_conflicts.html", "offline_sync_conflicts"),
)

# Explicitly wired surfaces (manual title/meta) — must keep data-rmc-row-detail rows.
EXPLICIT_ROW_DETAIL_TARGETS: frozenset[str] = frozenset(
    {
        "templates/teacher/marks_entry.html",
        "templates/teacher/marks_list.html",
        "templates/teacher/attendance.html",
        "templates/teacher/pay_history.html",
        "templates/teacher/leave.html",
        "templates/teacher/timetable.html",
        "templates/parent/finance.html",
        "templates/parent/results.html",
        "templates/parent/attendance_discipline.html",
        "templates/parent/wallet.html",
        "templates/portal/roll_call_student.html",
        "templates/portal/roll_call_teacher.html",
        "templates/portal/cahier_list.html",
        "templates/portal/cahier_verify_list.html",
        "templates/portal/office_document_list.html",
        "templates/portal/partials/document_library_manage_inner.html",
        "templates/portal/user_contributions.html",
        "templates/portal/offline_sync_queue.html",
        "templates/portal/signature_requests_manage.html",
        "templates/portal/at_risk_labeling/queue.html",
        "templates/portal/configure/lexicon_settings.html",
        "templates/people/backend_student_list.html",
        "templates/people/backend_guardian_list.html",
        "templates/people/backend_teacher_list.html",
        "templates/people/backend_applicant_list.html",
        "templates/people/backend_classroom_list.html",
        "templates/accounts/tenant_identity_roster.html",
        "templates/finance/invoices.html",
        "templates/finance/global_payment_command_center.html",
        "templates/finance/offline_payment_intent_queue.html",
        "templates/finance/requests.html",
    }
)

#: Role homes that ship the tenant workspace-canvas grammar.
#:
#: The scroll policy is NOT theirs to declare.  templates/portal_base.html owns
#: `{% block body_scroll_policy %}` and resolves it to `canvas` under the v3
#: tenant shell, `document` otherwise.  Both of these pages DID hard-declare
#: `{% block body_scroll_policy %}canvas{% endblock %}` until a7d2b6758 removed
#: it: canvas mode depended on `--rmc-portal-header-offset`, which never
#: resolved, so the inner pane was clipped and users lost vertical scroll on the
#: parent and teacher dashboards entirely.  That token no longer exists anywhere
#: in the tree, so putting the override back would reinstate the regression --
#: which is exactly what the old form of this check ("the file must contain
#: body_scroll_policy and canvas") was asking for.  The check now guards the fix
#: instead: the canvas stylesheet and body class must stay, and neither page may
#: re-declare the block.
CANVAS_ROLE_HOMES: tuple[tuple[str, str], ...] = (
    ("templates/teacher/dashboard.html", "dashboard-page-teacher"),
    ("templates/parent/dashboard.html", "dashboard-page-parent"),
)

#: A page re-declaring the shell's scroll-policy block (the a7d2b6758 regression).
BODY_SCROLL_OVERRIDE = re.compile(r"\{%\s*block\s+body_scroll_policy\s*%\}")
#: portal_base's own declaration, captured so its contents can be asserted.
PORTAL_SCROLL_BLOCK = re.compile(
    r"\{%\s*block\s+body_scroll_policy\s*%\}(.*?)\{%\s*endblock\s*%\}", re.S
)

ROLE_LITERAL = re.compile(
    r">\s*(Administrator|Headteacher|Teacher|Parent|Student)\s*<",
    re.IGNORECASE,
)

DRAWER_JS_MARKERS = (
    "portal_row_detail_drawer",
    "portal_row_detail_drawer_bundle",
    "rmc-portal-row-detail-drawer.js",
)

SHELL_EXTENDS_MARKERS = (
    'extends "base.html"',
    "extends 'base.html'",
    'extends "portal_base',
    "extends 'portal_base",
    'extends "control_plane_base',
    "extends 'control_plane_base",
    'extends "control_plane_skeleton',
    "extends 'control_plane_skeleton",
    'extends "backend_base',
    "extends 'backend_base",
    'extends "migration_cloud/connector/_wizard_base',
    "extends 'migration_cloud/connector/_wizard_base",
    'extends "marketing/base_marketing',
    "extends 'marketing/base_marketing",
)

IAM_LEXICON_MARKERS = (
    "glocal_token",
    "localized_role",
    "trans_term",
    '{% term "',
)

#: apps/platform_runtime/templatetags/glocal_tags.py registers exactly ONE
#: tag.  Using it without loading the library is a TemplateSyntaxError; the
#: {% load %} line on its own does nothing at all.
GLOCAL_TAG_USE = re.compile(r"\{%\s*glocal_token\b")
GLOCAL_TAG_LOAD = re.compile(r"\{%\s*load\b[^%]*\bglocal_tags\b")

#: `{% extends some_var %}` -- a shell chain that cannot be walked statically.
_DYNAMIC_EXTENDS = re.compile(r"\{%\s*extends\s+(?![\x22\x27])")

#: A template that extends nothing is an include/fragment, never a page.
_EXTENDS_RE = re.compile(r"\{%\s*extends\s")


TABLE_WITH_RMC_RE = re.compile(r"<table\b[^>]*\brmc-data-table\b", re.IGNORECASE)


def _discover_drawer_targets() -> tuple[tuple[str, str], ...]:
    targets: list[tuple[str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDE_REL:
            continue
        text = path.read_text(encoding="utf-8")
        if not TABLE_WITH_RMC_RE.search(text):
            continue
        label = path.stem
        targets.append((rel, label))
    return tuple(targets)


def _inherits_shell_drawer(text: str, rel: str = "") -> bool:
    """True when this page's shell already ships the row-detail drawer bundle.

    A raw `'extends "portal_base' in text` test only sees the FIRST hop.  Real
    pages are two deep -- templates/accounts/owner_console/role_groups.html
    extends `_console_base.html`, which extends `portal_base.html`; the /super/
    wedges extend `_surface_base.html`, which extends `control_plane_base.html`
    (itself extending `control_plane_skeleton.html`, where the bundle is) -- so
    both were reported as missing a bundle their shell had loaded all along.
    Given *rel*, the whole {% extends %} chain is resolved with
    shell_css_contract and asked whether ANY template in it loads the bundle;
    the first-hop marker list stays as the answer for a raw-text caller.
    """
    if rel:
        chain = css_contract.reachable_templates(rel)
        if any(
            marker in css_contract.reachable_text(target)
            for target in chain
            for marker in DRAWER_JS_MARKERS
        ):
            return True
        # A RESOLVED chain is the answer -- if the shell stopped shipping the
        # bundle, its pages have stopped receiving it, whatever they name.
        # A chain that passes through a DYNAMIC {% extends var %} cannot be
        # followed statically (templates/backend_base.html routes through
        # rmc_backend_extends|default:"backend_base_tenant.html", which does
        # reach portal_base and its bundle), so 147 pages would be accused of
        # missing a bundle they receive.  There, the shell-name list stays the
        # answer: better to under-report than to name a page that is fine.
        if not any(
            _DYNAMIC_EXTENDS.search(css_contract.reachable_text(target))
            for target in [rel, *chain]
        ):
            return False
    return any(marker in text for marker in SHELL_EXTENDS_MARKERS)


def _is_include_only(text: str) -> bool:
    """True for a partial/fragment: it extends nothing, so it is never a page.

    `"/partials/" in rel` misses the two other names this repo gives the same
    thing -- `templates/marketing/components/_product_tour.html` and
    `templates/schools/super_support_queue_fragment.html` are both rendered
    INTO a page that already loads the drawer bundle, and neither can carry a
    shell of its own.  Asking whether the file extends anything answers the
    question the path convention was standing in for.
    """
    return _EXTENDS_RE.search(text) is None


def _has_drawer_bundle(text: str, rel: str = "") -> bool:
    return any(marker in text for marker in DRAWER_JS_MARKERS) or _inherits_shell_drawer(
        text, rel
    )


def _table_row_detail_ok(text: str, rel: str) -> bool:
    if "data-rmc-row-detail-table" not in text:
        return False
    if rel in EXPLICIT_ROW_DETAIL_TARGETS:
        return 'data-rmc-row-detail="1"' in text or "data-rmc-row-detail='1'" in text
    return (
        'data-rmc-row-detail="1"' in text
        or "data-rmc-row-detail='1'" in text
        or 'data-rmc-row-detail-auto="1"' in text
    )


def _check_drawer_targets(targets: tuple[tuple[str, str], ...]) -> list[str]:
    findings: list[str] = []
    for rel, _label in targets:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        # Findings name the PATH, not path.stem: two different files both
        # reported as "index" and neither could be acted on.
        is_partial = "/partials/" in rel or _is_include_only(text)
        if not is_partial and not _has_drawer_bundle(text, rel):
            findings.append(f"{rel}: missing row-detail drawer bundle")
        if not _table_row_detail_ok(text, rel):
            findings.append(f"{rel}: rmc-data-table missing row-detail wiring")
    return findings


def _check_conflict_card_targets() -> list[str]:
    findings: list[str] = []
    for rel, label in CONFLICT_CARD_TARGETS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_drawer_bundle(text, rel):
            findings.append(f"{label}: missing row-detail drawer bundle")
        if 'data-rmc-row-detail-cards="1"' not in text:
            findings.append(f"{label}: missing data-rmc-row-detail-cards surface")
        if 'data-rmc-row-detail="1"' not in text:
            findings.append(f"{label}: missing data-rmc-row-detail cards")
    return findings


def _check_iam_targets(targets: tuple[tuple[str, str], ...]) -> list[str]:
    findings: list[str] = []
    vocab = ROOT / "apps/platform_runtime/glocal_vocabulary.py"
    tags = ROOT / "apps/platform_runtime/templatetags/glocal_tags.py"
    if not vocab.is_file() or not tags.is_file():
        findings.append("glocal vocabulary kernel missing")
    for rel, _label in targets:
        if "/partials/" in rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if GLOCAL_TAG_USE.search(text) and not GLOCAL_TAG_LOAD.search(text):
            findings.append(
                f"{rel}: uses {{% glocal_token %}} without {{% load glocal_tags %}} "
                "-- TemplateSyntaxError, the page 500s"
            )
        if ROLE_LITERAL.search(text) and not any(
            marker in text for marker in IAM_LEXICON_MARKERS
        ):
            findings.append(f"{rel}: hardcoded role label without glocal_token")
    return findings


def _glocal_adoption() -> tuple[int, int]:
    """(templates calling glocal_token, templates loading it without calling it).

    Printed on every run so nobody reads this gate's PASS as evidence of glocal
    adoption.  It is currently (0, 102): apps/platform_runtime/templatetags/
    glocal_tags.py registers exactly one tag and no template in the repo calls
    it.  That is precisely why requiring the {% load %} line was worthless.
    """
    used = dead = 0
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        calls = bool(GLOCAL_TAG_USE.search(text))
        loads = bool(GLOCAL_TAG_LOAD.search(text))
        if calls:
            used += 1
        elif loads:
            dead += 1
    return used, dead


def _check_canvas_role_homes() -> list[str]:
    findings: list[str] = []
    css = ROOT / "static/css/rmc-tenant-workspace-canvas.css"
    if not css.is_file():
        findings.append("missing rmc-tenant-workspace-canvas.css")
    for rel, body_class in CANVAS_ROLE_HOMES:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if body_class not in text:
            findings.append(f"{rel}: missing {body_class}")
        if "rmc-tenant-workspace-canvas.css" not in text:
            findings.append(f"{rel}: missing workspace canvas stylesheet")
        if BODY_SCROLL_OVERRIDE.search(text):
            findings.append(
                f"{rel}: re-declares the body_scroll_policy block -- a7d2b6758 "
                "deleted that override because canvas mode clipped the inner pane "
                "and killed vertical scroll on this page; the shell decides the "
                "policy"
            )
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    block = PORTAL_SCROLL_BLOCK.search(portal)
    if block is None:
        findings.append("portal_base missing body_scroll_policy block")
    else:
        body = block.group(1)
        if "tp_v3_tenant_shell" not in body or "canvas" not in body:
            findings.append(
                "portal_base body_scroll_policy no longer resolves to canvas under "
                "tp_v3_tenant_shell -- the role homes would silently lose the "
                "workspace-canvas grammar they ship the stylesheet for"
            )
    return findings


def main() -> int:
    drawer_targets = _discover_drawer_targets()
    used, dead_loads = _glocal_adoption()
    # Printed on PASS and FAIL alike: this gate is named "glocal adoption",
    # and the honest number is the one nobody was being shown.
    print(
        f"glocal lexicon adoption: {used} template(s) call "
        f"{{% glocal_token %}}, {dead_loads} carry a load they never use"
    )
    findings: list[str] = []
    findings.extend(_check_drawer_targets(drawer_targets))
    findings.extend(_check_conflict_card_targets())
    findings.extend(_check_iam_targets(drawer_targets))
    findings.extend(_check_canvas_role_homes())

    if findings:
        print("verify_glocal_adoption_tranche: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_glocal_adoption_tranche: GLOCAL_ADOPTION_TRANCHE_PASS "
        f"({len(drawer_targets)} drawer tables, {len(CONFLICT_CARD_TARGETS)} card surfaces)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
