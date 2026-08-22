#!/usr/bin/env python3
"""Cross-wave Admin OS audit: approval board vs live tree (Waves 0–4 / I1–I12)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import admin_build_lock  # sibling helper; scripts/ is sys.path[0] when run directly
errors: list[str] = []
warns: list[str] = []
oks: list[str] = []


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def must(path: str, label: str, *needles: str) -> None:
    text = read(path)
    missing = [n for n in needles if n not in text]
    if missing:
        errors.append(f"FAIL {label}: {path} missing {missing[:4]}")
    else:
        oks.append(f"OK {label}")


def ban(path: str, label: str, *needles: str) -> None:
    text = read(path)
    hit = [n for n in needles if n in text]
    if hit:
        errors.append(f"FAIL {label}: {path} still has {hit[:4]}")
    else:
        oks.append(f"OK ban {label}")


def main() -> int:
    # --- Wave 0 OS contracts ---
    must(
        "templates/admin/submit_line.html",
        "W0 Save compact",
        "data-rmc-save-compact",
        "rmc-django-save-split",
    )
    must(
        "templates/admin/base_site.html",
        "W0 CSS+JS owner",
        "rmc-admin-emergency-full-canvas-v17.css",
        "rmc-admin-os-innovations.js",
        "rmc-admin-model-policy.js",
        "rmc-admin-workspace.js",
    )
    must(
        "templates/admin/index_superadmin.html",
        "W0 op host voice",
        "Platform Backoffice",
        'data-rmc-admin-archetype="discover"',
    )
    must(
        "templates/admin/index_tenant.html",
        "W0 ten host voice",
        "This school only",
        "Configuration &amp; records",
        'data-rmc-admin-archetype="discover"',
    )

    # --- Wave 1 archetypes ---
    archetypes = {
        "templates/admin/index_superadmin.html": "discover",
        "templates/admin/index_tenant.html": "discover",
        "templates/admin/change_list.html": "scan",
        "templates/admin/change_form.html": "edit",
        "templates/admin/object_history.html": "audit",
        "templates/admin/delete_confirmation.html": "decide",
        "templates/admin/delete_selected_confirmation.html": "decide",
        "templates/admin/app_index.html": "dossier",
    }
    for path, arch in archetypes.items():
        must(path, f"W1 archetype {arch}", f'data-rmc-admin-archetype="{arch}"')

    ban(
        "templates/admin/change_form.html",
        "W1 no metrics/Form-Audit on form",
        "admin_workspace_metrics_strip.html",
        "admin_change_form_mode_panels.html",
        "rmc-django-view-toggle",
    )
    ban(
        "templates/admin/change_list.html",
        "W1 no metrics on list",
        "admin_workspace_metrics_strip.html",
    )
    ban(
        "templates/admin/index_superadmin.html",
        "W1 no legacy steering op",
        "cp-steering",
    )
    ban(
        "templates/admin/index_tenant.html",
        "W1 no legacy steering ten",
        "cp-steering",
    )
    must("templates/admin/index_superadmin.html", "W1 approved index rail op", "admin_index_context_rail.html")
    must("templates/admin/index_superadmin.html", "W1 approved index tools op", "admin_workspace_tools.html")
    must("templates/admin/index_tenant.html", "W1 approved index rail ten", "admin_index_context_rail.html")
    must("templates/admin/index_tenant.html", "W1 approved index tools ten", "admin_workspace_tools.html")
    ban(
        "templates/admin/base.html",
        "W1 no decision banner",
        "tenant_admin_decision_banner.html",
    )
    ban(
        "templates/admin/object_history.html",
        "W1 audit no tools",
        "admin_workspace_tools.html",
    )
    ban(
        "templates/admin/delete_confirmation.html",
        "W1 decide no tools",
        "admin_workspace_tools.html",
    )

    must("static/js/rmc-admin-workspace.js", "I6 M2M disclosure class", "rmc-admin-disclosure")
    must("templates/admin/index_superadmin.html", "I6 catalog disclosure", "rmc-admin-disclosure")
    must("templates/admin/delete_confirmation.html", "I6 delete disclosure", "rmc-admin-disclosure")

    must(
        "templates/admin/includes/admin_page_aware_rail_cards.html",
        "I9 live marker",
        "data-rmc-django-rail-live",
    )
    ban(
        "templates/admin/includes/admin_page_aware_rail_cards.html",
        "I9 no boundary manifesto card",
        'data-rmc-django-rail-page="1"',
    )
    rail_py = read("apps/siteconfig/admin_page_aware_rail.py")
    if '"guided": []' not in rail_py and "'guided': []" not in rail_py:
        warns.append("WARN I9: change-form/list guided=[] not obvious in rail builder")
    else:
        oks.append("OK I9 empty guided on CRUD rails")

    for path in (
        "templates/admin/change_form.html",
        "templates/admin/change_list.html",
        "templates/admin/index_superadmin.html",
        "templates/admin/index_tenant.html",
        "templates/admin/object_history.html",
        "templates/admin/delete_confirmation.html",
        "templates/admin/app_index.html",
    ):
        must(path, f"info-tag on {Path(path).name}", "rmc_info_tag")

    tools = read("templates/admin/includes/admin_workspace_tools.html")
    if 'data-rmc-tools-kill-matrix="v15"' not in tools:
        errors.append("FAIL kill matrix marker missing on tools")
    else:
        oks.append("OK kill matrix marker")
    must(
        "templates/admin/includes/admin_workspace_tools.html",
        "I8 keymap on tools",
        'data-rmc-admin-keymap-open="1"',
    )
    if 'data-rmc-command-bar-trigger="1"' in tools:
        errors.append("FAIL tools ? still opens command palette (must be keymap only)")
    else:
        oks.append("OK tools ? is keymap-only")

    # --- Wave 2 ---
    innov = read("static/js/rmc-admin-os-innovations.js")
    must(
        "templates/admin/change_list.html",
        "I1 marker",
        'data-rmc-admin-selection-gravity="1"',
    )
    if "Save ·" not in innov and "is-dirty" not in innov:
        errors.append("FAIL I3 dirty Save logic missing from innovations.js")
    else:
        oks.append("OK I3 dirty Save present")
    if "openSheet" not in innov or "keymap" not in innov.lower():
        errors.append("FAIL I8 keymap sheet missing")
    else:
        oks.append("OK I8 keymap present")
    must(
        "templates/admin/index_superadmin.html",
        "I8 discover keymap op",
        'data-rmc-admin-keymap-open="1"',
    )
    must(
        "templates/admin/index_tenant.html",
        "I8 discover keymap ten",
        'data-rmc-admin-keymap-open="1"',
    )

    # --- Wave 3 ---
    must("templates/admin/change_list.html", "I2 peek marker", "data-rmc-admin-row-peek")
    must(
        "templates/admin/change_form.html",
        "I4 radar",
        'data-rmc-admin-section-radar="1"',
    )
    must(
        "templates/admin/change_form.html",
        "I5 focus root",
        'data-rmc-admin-focus-root="1"',
    )
    css = read("static/css/rmc-admin-approval-surface-v15.css")
    terminal_css = read("static/css/rmc-admin-emergency-full-canvas-v17.css")
    if '@import url("./rmc-admin-approval-surface-v15.css")' not in terminal_css:
        errors.append("FAIL terminal v17 owner does not import the approved v15 foundation")
    else:
        oks.append("OK terminal v17 owner imports the approved v15 foundation")
    for needle, label in (
        ("section-radar", "I4"),
        ("admin-focus", "I5"),
        ("peek", "I2"),
        ("Selection gravity", "I1"),
        ("Host accent", "I10"),
        ("pins-row", "I7"),
    ):
        if needle not in innov and needle not in css:
            errors.append(f"FAIL {label} ({needle}) not in innovations.js or v15 CSS")
        else:
            oks.append(f"OK {label} in JS/CSS")
    if "rowHeaderLabels" not in innov and "thead" not in innov:
        errors.append("FAIL I2 peek missing thead header labels")
    else:
        oks.append("OK I2 peek thead labels")

    # --- Wave 4 ---
    must("templates/admin/index_superadmin.html", "I7 pins op", 'data-rmc-admin-pins="1"')
    must("templates/admin/index_tenant.html", "I7 pins ten", 'data-rmc-admin-pins="1"')
    must(
        "static/js/rmc-admin-model-policy.js",
        "I11 policy",
        "accounts.user",
        "siteconfig.sitesettings",
        "schools.school",
    )
    must(
        "scripts/verify_admin_os_three_click_sla.py",
        "I12 verifier",
        "THREE_CLICK",
        "admin_url",
    )
    if "I10" not in css and "Host accent" not in css:
        errors.append("FAIL I10 host accent CSS missing")
    else:
        oks.append("OK I10 host accent CSS")

    op = read("templates/admin/index_superadmin.html")
    ten = read("templates/admin/index_tenant.html")
    if "New school" not in op:
        errors.append("FAIL op index missing New school primary")
    else:
        oks.append("OK op New school primary")
    if "Invite a school" in ten:
        errors.append("FAIL tenant index must not have fleet Invite CTA")
    else:
        oks.append("OK tenant has no Invite CTA")
    if "Config center" not in ten:
        errors.append("FAIL tenant index missing Config center primary")
    else:
        oks.append("OK tenant Config primary")
    if "feature_control_panel" not in ten:
        errors.append("FAIL tenant index missing Feature control CTA")
    else:
        oks.append("OK tenant Feature control")
    if "admin_v1_index_surface_previews.html" not in op:
        errors.append("FAIL op index missing restored surface sections")
    else:
        oks.append("OK op surface sections")

    # Build lock consistency
    lock = json.loads(read("var/admin-approval-build-lock.json"))
    bs = read("templates/admin/base_site.html")
    sw = read("static/js/service-worker.js")
    for key in ("build_id", "cache_bust", "sw_version", "seal"):
        if not lock.get(key):
            errors.append(f"FAIL lock missing {key}")
    if lock["build_id"] not in bs:
        errors.append(f"FAIL base_site missing build_id {lock['build_id']}")
    else:
        oks.append(f"OK build_id in base_site: {lock['build_id']}")
    if f"?v={lock['cache_bust']}" not in bs:
        errors.append(f"FAIL base_site cache bust mismatch want {lock['cache_bust']}")
    else:
        oks.append(f"OK cache bust {lock['cache_bust']}")
    sw_ok, sw_why = admin_build_lock.sw_at_least(lock["sw_version"], sw)
    if not sw_ok:
        errors.append(f"FAIL {sw_why}")
    else:
        oks.append(f"OK {sw_why}")
    # A seal documents the contract a rule set implements, so it lives WITH those
    # rules. The v22 build is a tenant-SIDEBAR build; looking only in the terminal
    # canvas sheet asks the wrong file.
    seal_ok, seal_where = admin_build_lock.seal_present(lock["seal"])
    if not seal_ok:
        errors.append(
            f"FAIL CSS seal missing {lock['seal']} "
            f"(searched {len(admin_build_lock.SEAL_SEARCH_PATHS)} admin stylesheets)"
        )
    else:
        oks.append(f"OK CSS seal {lock['seal']} in {seal_where}")

    for path, host in (
        ("templates/admin/index_superadmin.html", "op"),
        ("templates/admin/index_tenant.html", "ten"),
    ):
        text = read(path)
        if "rmc-admin-approval-build-chip" not in text or lock["build_id"] not in text:
            errors.append(f"FAIL {host} chip missing for {lock['build_id']}")
        else:
            oks.append(f"OK {host} visible chip")

    for marker in (
        'data-rmc-admin-discover="1"',
        "rmc-admin-discover-canvas",
        "data-rmc-admin-catalog-search",
    ):
        if marker not in op:
            errors.append(f"FAIL op missing {marker}")
        if marker not in ten:
            errors.append(f"FAIL ten missing {marker}")
    oks.append("OK op/ten discover geometry markers")

    # Guided forms still page-aware
    for guided in (
        "templates/admin/schools/school/delete_guided.html",
        "templates/admin/schools/school/waive_subscription_form.html",
    ):
        must(guided, f"guided rail {Path(guided).name}", "admin_guided_surface_rail.html")

    # Scan/Edit and approved Discover surfaces keep page-aware tools.
    must("templates/admin/change_list.html", "scan tools", "admin_workspace_tools.html")
    must("templates/admin/change_form.html", "edit tools", "admin_workspace_tools.html")
    must("templates/admin/app_index.html", "dossier tools", "admin_workspace_tools.html")

    # Mechanical gates
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.setdefault("DEBUG", "1")
    env.setdefault("SECRET_KEY", "admin-os-cross-wave-audit-local-only")
    gate_cmds = [
        ["python", "scripts/verify_admin_os_three_click_sla.py"],
        ["python", "scripts/verify_admin_os_sections_restore.py"],
        ["python", "scripts/verify_admin_os_empty_space.py"],
        ["python", "scripts/verify_surface_preview_interactivity.py"],
        ["python", "scripts/verify_django_admin_preview_parity.py"],
        ["python", "scripts/audit_django_admin_canvas_contract.py"],
        ["python", "scripts/audit_django_admin_miss_nothing.py"],
        ["python", "scripts/verify_service_worker_version.py", "--check-monotonic"],
        ["python", "scripts/verify_tenant_admin_sidebar_v2.py"],
        ["python", "scripts/verify_operator_admin_sidebar_v2.py"],
        ["python", "scripts/verify_user_account_center.py"],
        ["python", "scripts/verify_approved_tenant_dashboard_sidebar_contracts.py"],
        ["python", "scripts/verify_approved_ui_deploy_artifacts.py"],
        ["python", "scripts/verify_governed_outcome_surfaces.py"],
        ["python", "scripts/verify_launch_readiness_contract.py"],
        ["python", "scripts/verify_template_compiles.py"],
    ]
    gate_results: list[tuple[str, int]] = []
    for cmd in gate_cmds:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        name = Path(cmd[1]).name
        gate_results.append((name, proc.returncode))
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
            errors.append(f"FAIL gate {name} exit={proc.returncode}: " + " | ".join(tail))
        else:
            oks.append(f"OK gate {name}")

    # Page-aware unit tests
    proc = subprocess.run(
        [
            "python",
            "scripts/run_sqlite_memory_tests.py",
            "apps.siteconfig.tests.test_admin_page_aware_rail",
            "--verbosity=0",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        errors.append("FAIL page-aware rail tests")
        warns.append((proc.stderr or proc.stdout or "")[-500:])
    else:
        oks.append("OK page-aware rail tests")

    print("=== ADMIN OS CROSS-WAVE AUDIT ===")
    print(f"OK={len(oks)} WARN={len(warns)} FAIL={len(errors)}")
    print("--- gates ---")
    for name, code in gate_results:
        print(f"  {name}: {'PASS' if code == 0 else 'FAIL'}")
    for w in warns:
        print(w)
    for e in errors:
        print(e)
    if not errors:
        print("ADMIN_OS_CROSS_WAVE_AUDIT_PASS")
    else:
        print("ADMIN_OS_CROSS_WAVE_AUDIT_FAIL")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
