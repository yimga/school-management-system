#!/usr/bin/env python3
"""Platform contract gate — Tier-1 academic/people fields end-to-end.

The Gilead ingest incident was not missing dynamic fields. It was a class of
**first-class column** failures across the stack:

* import mapping (ontology + landers)
* spreadsheet parsing (title-row headers)
* tenant verification UI (list/detail + nav)
* edge sync rail registration

This gate freezes that contract platform-wide so a fix in Migration Cloud cannot
drift from the surfaces schools and boxes rely on. It is stdlib-only (no Django)
and runs in the deps-free architectural-boundaries job.

Each contract row names a Tier-1 field and the surfaces that MUST stay wired.
A missing needle is a finding (exit 1). There is no baseline — regressions are
never absorbed silently.

Usage:
    python scripts/verify_tier1_academic_people_platform_contract.py
    python scripts/verify_tier1_academic_people_platform_contract.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (field_label, path_relative_to_repo, tuple_of_needles — ALL must appear)
_CONTRACT: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # --- Spreadsheet title-row detection (import path) ---
    (
        "spreadsheet_headers.module",
        "apps/migration_cloud/spreadsheet_headers.py",
        ("def pick_header_row_index", "def split_header_and_data_rows"),
    ),
    (
        "orchestrator.title_row_skip",
        "apps/migration_cloud/orchestrator.py",
        ("from .spreadsheet_headers import split_header_and_data_rows",),
    ),
    (
        "profiler.title_row_skip",
        "apps/migration_cloud/profiler.py",
        ("from .spreadsheet_headers import split_header_and_data_rows",),
    ),
    # --- Subject.category (Tier 1) ---
    (
        "Subject.category.lander",
        "apps/migration_cloud/landers/academics_lander.py",
        ("_resolve_subject_category", 'updates["category"]'),
    ),
    (
        "Subject.category.ontology",
        "apps/migration_cloud/ontology/catalog.py",
        ('"category"', "subject_category"),
    ),
    (
        "Subject.category.tenant_list_ui",
        "templates/people/backend_subject_list.html",
        ("get_category_display",),
    ),
    (
        "Subject.category.nav",
        "apps/platform_runtime/nav_engine.py",
        ('id="subjects"', "accounts:backend_subject_list"),
    ),
    (
        "Subject.category.portal_sidebar",
        "apps/siteconfig/portal_sidebar_items.py",
        ('("subjects"', "accounts:backend_subject_list"),
    ),
    (
        "Subject.category.sync_rail",
        "apps/api/sync_services.py",
        ('("subject", "academics", "Subject")',),
    ),
    (
        "Subject.category.companion_tauri_mirror",
        "companion-tauri/src-tauri/src/canonical_headers.json",
        ('"category"',),
    ),
    (
        "Subject.category.companion_docker_mirror",
        "companion-docker/app/canonical_headers.json",
        ('"category"',),
    ),
    # --- Teacher phone / role / department (Tier 1) ---
    (
        "TeacherProfile.phone.lander",
        "apps/migration_cloud/landers/staff_lander.py",
        ('"phone": _staff_field_from_row(row, "phone")',),
    ),
    (
        "TeacherProfile.department.lander",
        "apps/migration_cloud/landers/staff_lander.py",
        ('_staff_field_from_row(row, "department")', '"department": department'),
    ),
    (
        "User.role.lander",
        "apps/migration_cloud/landers/staff_lander.py",
        ("apply_imported_staff_role", "resolve_staff_role"),
    ),
    (
        "Staff.phone.ontology",
        "apps/migration_cloud/ontology/catalog.py",
        ("telephone_number",),
    ),
    (
        "Staff.role.ontology",
        "apps/migration_cloud/ontology/catalog.py",
        ("post_function_role", "function_role"),
    ),
    (
        "Staff.department.ontology",
        "apps/migration_cloud/ontology/catalog.py",
        ("specialty_name", '"specialty"'),
    ),
    (
        "TeacherProfile.phone.tenant_list_ui",
        "templates/people/backend_teacher_list.html",
        ("teacher.phone",),
    ),
    (
        "User.role.tenant_list_ui",
        "templates/people/backend_teacher_list.html",
        ("get_role_display",),
    ),
    (
        "TeacherProfile.phone.tenant_detail_ui",
        "templates/people/backend_teacher_detail.html",
        ("teacher.phone", "get_role_display"),
    ),
    (
        "TeacherProfile.phone.csv_export",
        "apps/people/views_backend.py",
        ('writer.writerow(["staff_id", "first_name", "last_name", "email", "phone", "role", "department"]',),
    ),
    (
        "TeacherProfile.sync_rail",
        "apps/api/sync_services.py",
        ('("teacher", "people", "TeacherProfile")', "phone"),
    ),
    # --- Specialty spine (Tier 1 catalog) ---
    (
        "Specialty.nav",
        "apps/platform_runtime/nav_engine.py",
        ('id="specialties"', "accounts:backend_specialty_list"),
    ),
    (
        "Specialty.sync_rail",
        "apps/api/sync_services.py",
        ('("specialty", "academics", "Specialty")',),
    ),
    # --- Tier-2 seed path (extras on classroom; subject recipe slot) ---
    (
        "Tier2.classroom_recipes",
        "apps/metadata/management/commands/seed_dynamic_field_recipes.py",
        ('"academics.classroom"',),
    ),
    (
        "Tier2.subject_recipes",
        "apps/metadata/management/commands/seed_dynamic_field_recipes.py",
        ('"academics.subject"',),
    ),
    # --- Migration Cloud review → tenant verification links ---
    (
        "MC.review.people_links",
        "templates/migration_cloud/connector/bundle_review.html",
        (
            "staff_identity_url",
            "subjects_url",
            "specialties_url",
            "teachers_url",
            "promote_staff_roles",
        ),
    ),
    # --- Cameroon TVET blueprint bridge (Specialty=Filière, Subject=Matière, coef) ---
    (
        "Ingestion.lexicon.module",
        "apps/migration_cloud/ingestion_lexicon.py",
        ("resolve_school_ingestion_lexicon", "compile_offline_ingestion_manifest"),
    ),
    (
        "Ingestion.catalog_shape.classifier",
        "apps/migration_cloud/classifiers/domain.py",
        ("apply_catalog_shape_adjustments",),
    ),
    (
        "SpecialtySubject.coef.lander",
        "apps/migration_cloud/landers/academics_lander.py",
        ("_link_subject_curriculum", "SpecialtySubject"),
    ),
    (
        "Specialty.lander.subject_guard",
        "apps/migration_cloud/landers/specialty_lander.py",
        ("row_looks_like_subject_catalog_entry",),
    ),
    (
        "Offline.ingestion_manifest.config",
        "apps/siteconfig/platform_surface_config.py",
        ("ingestionManifest", "_ingestion_manifest_for_request"),
    ),
    (
        "Offline.ingestion_lexicon.client",
        "static/js/rmc-offline-ingestion-lexicon.js",
        ("rmcOfflineIngestionLexicon", "ingestion_lexicon"),
    ),
    (
        "Staff.specialty.resolve",
        "apps/migration_cloud/landers/staff_lander.py",
        ("_resolve_staff_department", "imported_specialty"),
    ),
    (
        "SpecialtySubject.sync_rail",
        "apps/api/sync_services.py",
        ('("specialty_subject", "academics", "SpecialtySubject")',),
    ),
)


def scan() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for field_label, rel_path, needles in _CONTRACT:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            findings.append(
                {
                    "field": field_label,
                    "path": rel_path,
                    "reason": "file_missing",
                }
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                {
                    "field": field_label,
                    "path": rel_path,
                    "reason": f"unreadable:{exc}",
                }
            )
            continue
        for needle in needles:
            if needle not in text:
                findings.append(
                    {
                        "field": field_label,
                        "path": rel_path,
                        "reason": f"missing_needle:{needle!r}",
                    }
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    findings = scan()
    payload = {
        "rule": "Tier-1 academic/people fields must stay wired across import, UI, nav, and sync",
        "contract_rows": len(_CONTRACT),
        "finding_count": len(findings),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"Tier-1 platform contract: {len(_CONTRACT)} row(s), "
        f"{len(findings)} finding(s)"
    )
    for row in findings:
        print(f"  {row['field']} @ {row['path']}: {row['reason']}")
    if findings:
        print(
            "\nA Tier-1 field surface drifted. Re-wire the import/UI/sync path "
            "or update the contract deliberately (reviewed edit to this script)."
        )
        return 1
    print("TIER1_ACADEMIC_PEOPLE_PLATFORM_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
