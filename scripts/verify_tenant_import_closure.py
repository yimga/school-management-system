#!/usr/bin/env python
"""Verify tenant import graph closure (import → teachers → classrooms → grades).

Operator acceptance gate — not "gates green", but "the school graph is wired".

Usage::

    python scripts/verify_tenant_import_closure.py --school gilead-tech
    python scripts/verify_tenant_import_closure.py --school gilead-tech --bundle-id 86 --strict
    python scripts/verify_tenant_import_closure.py --school gilead-tech --classroom-probe "Form One" --json

Requires Django (run on production/staging with DATABASE_URL set).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _bootstrap_django() -> None:
    import django

    django.setup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--school", required=True, help="School slug/subdomain/pk")
    parser.add_argument("--bundle-id", type=int, default=None)
    parser.add_argument(
        "--classroom-probe",
        default="",
        help='Optional classroom name substring (e.g. "Form One")',
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any import-graph layer is not OK",
    )
    args = parser.parse_args()

    _bootstrap_django()

    from apps.migration_cloud.closure_status import (
        build_import_graph_health_report,
        evaluate_import_closure_findings,
    )
    from apps.migration_cloud.management.commands.remediate_teaching_graph_closure import (
        _tenant_schema,
    )
    from apps.migration_cloud.management.school_resolution import resolve_school_or_error
    from apps.migration_cloud.models import MigrationBundle

    school = resolve_school_or_error(args.school)
    bundle = None
    if args.bundle_id is not None:
        bundle = MigrationBundle.objects.filter(pk=args.bundle_id, school=school).first()
        if bundle is None:
            print(
                f"TENANT_IMPORT_CLOSURE_FAIL: bundle #{args.bundle_id} "
                f"not found for school {school.slug}",
                file=sys.stderr,
            )
            return 1

    with _tenant_schema(school):
        report = build_import_graph_health_report(
            school,
            bundle=bundle,
            classroom_probe=args.classroom_probe,
        )
        findings = evaluate_import_closure_findings(report)

    if args.as_json:
        payload = {**report, "findings": findings}
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(f"School: {report['school']}")
        print(f"Import graph ready: {report.get('import_graph_ready')}")
        print(f"Playbook ready: {report.get('playbook_ready')}")
        layers = report.get("import_graph_layers") or {}
        for name, layer in layers.items():
            if not isinstance(layer, dict):
                continue
            status = "OK" if layer.get("ok", True) else "GAP"
            print(f"  [{status}] {name}: {layer}")
        probe = layers.get("classroom_probe") or {}
        if probe.get("sample_classroom_name"):
            print(
                f"  Classroom probe {probe.get('sample_classroom_name')!r}: "
                f"{probe.get('sample_roster', 0)} student(s) on roster"
            )
        if findings:
            print("\nFindings:")
            for item in findings:
                print(f"  - {item}")

    if args.strict and findings:
        print("\nTENANT_IMPORT_CLOSURE_FAIL", file=sys.stderr)
        return 1
    if not args.as_json:
        print("\nTENANT_IMPORT_CLOSURE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
