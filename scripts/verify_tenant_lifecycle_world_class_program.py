#!/usr/bin/env python3

"""Verify world-class tenant journey program (batches 1732–1742, Pillar E offline-first)."""



from __future__ import annotations



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent





def main() -> int:

    errors: list[str] = []

    required = [

        "static/js/rmc-school-readiness-cache.js",

        "static/js/rmc-journey-offline-mirror.js",

        "static/js/rmc-discipline-refer.js",

        "static/js/offline-db.js",

        "apps/schools/launch_playbook.py",

        "apps/schools/year_close_checklist.py",

        "apps/schools/offline_workflow_handlers.py",

        "apps/academics/views_discipline_api.py",

        "apps/academics/migrations/0059_incident_mtss_tier_parent_notified.py",

        "templates/partials/tenant/launch_playbook_strip.html",

        "templates/partials/tenant/operational_lifecycle_strip.html",

        "templates/partials/tenant/academic_year_close_checklist.html",

        "templates/partials/tenant/provisioning_partial_failure_banner.html",

        "docs/phase_checklists/PILLAR_E_OFFLINE_CI_MATRIX.md",

        "tests/e2e/tenant-readiness-offline.spec.js",

        "var/design-previews/world-class-tenant-journey-hub-browsable.html",

        "var/design-previews/provisioning-offline-edge-lab-browsable.html",

        "var/design-previews/workflow-flight-deck-zero-fail-browsable.html",

        "var/design-previews/tenant-lifecycle-os-browsable.html",

        "var/design-previews/academic-year-close-open-browsable.html",

        "var/design-previews/disciplinary-excellence-lab-browsable.html",

    ]

    for rel in required:

        if not (ROOT / rel).is_file():

            errors.append(f"missing {rel}")



    readiness = (ROOT / "apps/schools/school_readiness.py").read_text(encoding="utf-8")

    for needle in ("cached_at", "offline_hint", '"key": "migrate"'):

        if needle not in readiness:

            errors.append(f"school_readiness.py missing {needle}")



    sw = (ROOT / "static/js/service-worker.js").read_text(encoding="utf-8")

    if "/api/discipline/" not in sw:

        errors.append("service-worker missing /api/discipline/ queue path")



    tenant_urls = (ROOT / "config/tenant_urls.py").read_text(encoding="utf-8")

    if "api_discipline_incidents" not in tenant_urls:

        errors.append("tenant_urls missing api_discipline_incidents")



    tasks = (ROOT / "apps/platform_runtime/tasks.py").read_text(encoding="utf-8")

    if "workflow_failed_provision_auto_requeue_sweep" not in tasks:

        errors.append("tasks.py missing failed provision auto-requeue sweep")



    js_poll = (ROOT / "static/js/rmc-setup-surface-readiness.js").read_text(encoding="utf-8")

    if "RMCSchoolReadinessCache" not in js_poll:

        errors.append("rmc-setup-surface-readiness.js missing cache integration")



    offline_db = (ROOT / "static/js/offline-db.js").read_text(encoding="utf-8")

    for store in ("school_readiness", "discipline_incidents", "operational_lifecycle"):

        if store not in offline_db:

            errors.append(f"offline-db.js missing store {store}")



    handlers = (ROOT / "apps/schools/offline_workflow_handlers.py").read_text(encoding="utf-8")

    for wf in ("discipline_refer", "launch_playbook_ack", "year_close_ack"):

        if wf not in handlers:

            errors.append(f"offline_workflow_handlers missing {wf}")



    flight = (ROOT / "apps/platform_runtime/workflow_flight_deck_actions.py").read_text(

        encoding="utf-8"

    )

    if "requires_network" not in flight:

        errors.append("workflow_flight_deck_actions missing requires_network metadata")



    launch = (ROOT / "templates/partials/tenant/launch_playbook_strip.html").read_text(

        encoding="utf-8"

    )

    if 'data-rmc-offline-workflow="launch_playbook_ack"' not in launch:

        errors.append("launch_playbook_strip missing offline ack form")



    year_close = (

        ROOT / "templates/partials/tenant/academic_year_close_checklist.html"

    ).read_text(encoding="utf-8")

    if 'data-rmc-offline-workflow="year_close_ack"' not in year_close:

        errors.append("year_close_checklist missing offline ack form")



    hub = (ROOT / "var/design-previews/world-class-tenant-journey-hub-browsable.html").read_text(

        encoding="utf-8"

    )

    if 'data-conn="offline"' not in hub or "Outbox" not in hub:

        errors.append("world-class hub missing offline/edge chrome")



    for preview in (

        "provisioning-offline-edge-lab-browsable.html",

        "workflow-flight-deck-zero-fail-browsable.html",

        "tenant-lifecycle-os-browsable.html",

        "academic-year-close-open-browsable.html",

        "disciplinary-excellence-lab-browsable.html",

    ):

        text = (ROOT / "var/design-previews" / preview).read_text(encoding="utf-8")

        if 'class="conn"' not in text and 'data-conn=' not in text:

            errors.append(f"{preview} missing connection pill chrome")



    setup = (ROOT / "templates/partials/tenant/setup_command_surface.html").read_text(
        encoding="utf-8"
    )
    for needle in ("provisioning_partial_failure_banner", "rmc-journey-offline-mirror.js"):
        if needle not in setup:
            errors.append(f"setup_command_surface missing {needle}")

    if errors:

        print("verify_tenant_lifecycle_world_class_program: FAIL")

        for err in errors:

            print(f"  - {err}")

        return 1



    print("verify_tenant_lifecycle_world_class_program: TENANT_LIFECYCLE_WORLD_CLASS_PROGRAM_PASS")

    return 0





if __name__ == "__main__":

    sys.exit(main())

