#!/usr/bin/env python3
"""
Master-prompt vector 4 gate: required platform subsystems exist and are importable.

Does not claim product maturity — verifies code paths are present for audit traceability.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if os.environ.get("DJANGO_SETTINGS_MODULE") is None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

VECTORS = (
    {
        "name": "studio_os_onboarding",
        "modules": (
            "apps.studio_os.views",
            "apps.siteconfig.views_school_onboarding",
        ),
        "paths": (
            "apps/studio_os/urls.py",
            "templates/studio_os/shell_control_plane.html",
        ),
    },
    {
        "name": "curriculum_region_runtime",
        "modules": (
            "apps.siteconfig.tenant_config",
            "apps.siteconfig.views",
        ),
        "paths": (
            "apps/siteconfig/urls.py",
        ),
        "url_snippets": ("region_grading_scales", "region_validation"),
    },
    {
        "name": "workflow_canvas",
        "modules": ("apps.automation.views_visual_workflow",),
        "paths": (
            "apps/automation/urls.py",
            "templates/automation/visual_workflow_designer.html",
        ),
        "url_snippets": ("visual_workflow_designer",),
    },
    {
        "name": "marketplace_sis",
        "modules": ("apps.migration_cloud.services.legacy_hash_intake",),
        "paths": (
            "apps/marketplace/urls_developer_platform.py",
            "apps/migration_cloud/companion_receiver.py",
        ),
    },
    {
        "name": "billing_ledger_telemetry",
        "modules": (
            "apps.finance.payment_orchestration",
            "apps.observability.tracing",
        ),
        "paths": (
            "apps/finance/models.py",
            "apps/observability/slo.py",
        ),
    },
    {
        "name": "trust_compliance_audit",
        "modules": ("apps.compliance.models_audit",),
        "paths": (
            "apps/compliance/models_audit.py",
            "scripts/verify_audit_log_append_only.py",
        ),
    },
)


def main() -> int:
    failures: list[str] = []
    for spec in VECTORS:
        for mod in spec.get("modules", ()):
            try:
                importlib.import_module(mod)
            except Exception as exc:
                failures.append(f"{spec['name']}: import {mod}: {exc}")
        for rel in spec.get("paths", ()):
            if not (REPO_ROOT / rel).is_file() and not (REPO_ROOT / rel).is_dir():
                failures.append(f"{spec['name']}: missing path {rel}")
        text_blob = ""
        for rel in spec.get("paths", ()):
            p = REPO_ROOT / rel
            if p.is_file():
                text_blob += p.read_text(encoding="utf-8", errors="replace")
        for snippet in spec.get("url_snippets", ()):
            if snippet not in text_blob:
                failures.append(f"{spec['name']}: url snippet {snippet!r} not in paths")

    if failures:
        print("verify_tenant_platform_vectors: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"verify_tenant_platform_vectors: PASS ({len(VECTORS)} vectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
