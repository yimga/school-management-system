#!/usr/bin/env python3
"""Audit the shared tenant/operator Django admin form-intelligence contract.

This is a read-only release gate.  It resolves the add and change form class for
every registered model on both real AdminSite instances and proves that field
classification, tenant ownership, evidence ownership and preference metadata
remain complete and disjoint.

It also covers INLINE formsets, which are attached as a class attribute rather
than registered and were therefore proven by nothing until 2026-08-21: 30 inline
classes were attached across the two sites and none carried any of the policy, so
system-evidence fields were editable there and tenant ownership was posted from
the client.  A regression that reaches only the inlines now turns this gate red.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.admin.utils import flatten_fieldsets  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.messages.middleware import MessageMiddleware  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.schools.models import School  # noqa: E402
from apps.siteconfig.admin_form_intelligence import (  # noqa: E402
    SYSTEM_EVIDENCE_FIELDS,
    build_admin_field_contract,
)
from config.admin import platform_admin_site, tenant_admin_site  # noqa: E402


def _source_contract_findings() -> list[str]:
    checks = {
        "templates/unfold/helpers/fieldset_row.html": (
            "data-rmc-admin-field-name",
            "data-rmc-field-required",
        ),
        "templates/admin/includes/admin_field_visibility.html": (
            "Recommended fields",
            "Show all",
            "Reset",
        ),
        "static/js/rmc-admin-field-preferences-v1.js": (
            "data-rmc-recommended-badge",
            "localStorage.removeItem(pendingKey)",
            "credentials: \"same-origin\"",
        ),
        "templates/admin/base_site.html": (
            "rmc-admin-field-preferences-v1.js",
        ),
    }
    findings: list[str] = []
    for relative_path, needles in checks.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                findings.append(f"source:{relative_path}:missing:{needle}")
    return findings


def _audit_site(
    *,
    label: str,
    site,
    host: str,
    urlconf: str,
    host_kind: str,
    school,
    user,
) -> tuple[dict[str, Any], list[str]]:
    request = RequestFactory().get("/admin/", HTTP_HOST=host)
    request.user = user
    request.school = school
    request.public_host_kind = host_kind
    request.urlconf = urlconf
    # A small set of specialized ModelAdmins consult the session/message
    # context while constructing forms.  Mirror the real middleware contract
    # so this gate audits the production form path instead of a partial request.
    SessionMiddleware(lambda _request: None).process_request(request)
    MessageMiddleware(lambda _request: None).process_request(request)

    findings: list[str] = []
    metrics: dict[str, Any] = {
        "registered_models": 0,
        "add_forms_resolved": 0,
        "change_forms_resolved": 0,
        "required_editable_fields": 0,
        "optional_editable_fields": 0,
        "recommended_editable_fields": 0,
        "system_hidden_fields": 0,
        "models_with_school": 0,
        "school_fields_exposed": 0,
        "inline_classes": 0,
        "inline_classes_automated": 0,
        "inline_school_fields_exposed": 0,
        "inferred_hidden_fields": 0,
    }

    for model, model_admin in site._registry.items():
        model_label = model._meta.label_lower
        metrics["registered_models"] += 1
        if not getattr(model_admin, "_rmc_admin_form_automation", False):
            findings.append(f"{label}:{model_label}:shared-mixin-missing")

        readonly = set(model_admin.get_readonly_fields(request, None))
        expected_evidence = {
            name for name in SYSTEM_EVIDENCE_FIELDS if hasattr(model, name)
        }
        missing_readonly = expected_evidence - readonly
        if missing_readonly:
            findings.append(
                f"{label}:{model_label}:system-evidence-editable:"
                + ",".join(sorted(missing_readonly))
            )

        has_school = any(field.name == "school" for field in model._meta.fields)
        if has_school:
            metrics["models_with_school"] += 1

        # Inlines are where bulk entry happens and they are attached as a class
        # attribute, not registered — so nothing else proves they are covered.
        for inline_class in getattr(model_admin, "inlines", ()) or ():
            metrics["inline_classes"] += 1
            inline_label = getattr(
                getattr(inline_class, "model", None), "_meta", None
            )
            inline_name = (
                inline_label.label_lower if inline_label else inline_class.__name__
            )
            if not getattr(inline_class, "_rmc_admin_inline_automation", False):
                findings.append(
                    f"{label}:{model_label}:inline:{inline_name}:automation-missing"
                )
                continue
            metrics["inline_classes_automated"] += 1
            try:
                inline = inline_class(model, site)
                inline_excluded = set(inline.get_exclude(request, None) or ())
                inline_readonly = set(inline.get_readonly_fields(request, None) or ())
            except Exception as exc:  # pragma: no cover - release ledger
                findings.append(
                    f"{label}:{model_label}:inline:{inline_name}:"
                    f"error:{type(exc).__name__}:{exc}"
                )
                continue
            inline_model = inline_class.model
            if (
                label == "tenant"
                and any(f.name == "school" for f in inline_model._meta.fields)
                and "school" not in inline_excluded
            ):
                metrics["inline_school_fields_exposed"] += 1
                findings.append(
                    f"{label}:{model_label}:inline:{inline_name}:school-editable"
                )
            inline_evidence = {
                name for name in SYSTEM_EVIDENCE_FIELDS if hasattr(inline_model, name)
            }
            inline_gap = inline_evidence - inline_readonly - inline_excluded
            if inline_gap:
                findings.append(
                    f"{label}:{model_label}:inline:{inline_name}:"
                    "system-evidence-editable:" + ",".join(sorted(inline_gap))
                )

        for mode in ("add", "change"):
            try:
                form_class = model_admin.get_form(
                    request,
                    obj=None,
                    change=mode == "change",
                )
                contract = build_admin_field_contract(
                    model_admin,
                    request,
                    obj=None,
                    mode=mode,
                )
            except Exception as exc:  # pragma: no cover - release ledger
                findings.append(
                    f"{label}:{model_label}:{mode}-form-error:"
                    f"{type(exc).__name__}:{exc}"
                )
                continue

            metrics[f"{mode}_forms_resolved"] += 1
            declared_form_names = set(form_class.base_fields)
            rendered_form_names = set(
                flatten_fieldsets(model_admin.get_fieldsets(request, None))
            )
            # A reusable ModelForm may intentionally declare fields that this
            # specialized ModelAdmin does not render.  Audit the active
            # fieldset allowlist so the release gate detects the same surface
            # the browser receives instead of requiring phantom controls.
            form_names = declared_form_names & rendered_form_names
            required = set(contract.required_fields)
            optional = {item["name"] for item in contract.optional_fields}
            recommended = set(contract.recommended_fields)
            system_hidden = set(contract.system_hidden_fields)
            readonly = set(model_admin.get_readonly_fields(request, None))

            if required & optional:
                findings.append(f"{label}:{model_label}:{mode}:classification-overlap")
            unclassified = form_names - required - optional - readonly - system_hidden
            if unclassified:
                findings.append(
                    f"{label}:{model_label}:{mode}:unclassified:"
                    + ",".join(sorted(unclassified))
                )
            if recommended - required - optional:
                findings.append(
                    f"{label}:{model_label}:{mode}:recommended-not-editable:"
                    + ",".join(sorted(recommended - required - optional))
                )
            if required & set(contract.hidden_fields):
                findings.append(f"{label}:{model_label}:{mode}:required-hidden")
            if system_hidden & optional:
                findings.append(f"{label}:{model_label}:{mode}:system-optional")
            if has_school and label == "tenant" and "school" in declared_form_names:
                metrics["school_fields_exposed"] += 1
                findings.append(f"{label}:{model_label}:{mode}:school-editable")
            if not contract.endpoint:
                findings.append(f"{label}:{model_label}:{mode}:endpoint-missing")

            # Usage-derived hiding must obey the same rules as chosen hiding: only
            # optional fields, and every inferred name must also be in `hidden`.
            inferred = set(getattr(contract, "inferred_hidden_fields", ()) or ())
            if inferred - optional:
                findings.append(
                    f"{label}:{model_label}:{mode}:inferred-not-optional:"
                    + ",".join(sorted(inferred - optional))
                )
            if inferred - set(contract.hidden_fields):
                findings.append(
                    f"{label}:{model_label}:{mode}:inferred-not-hidden:"
                    + ",".join(sorted(inferred - set(contract.hidden_fields)))
                )
            if mode == "add":
                metrics["inferred_hidden_fields"] += len(inferred)

            if mode == "add":
                metrics["required_editable_fields"] += len(required)
                metrics["optional_editable_fields"] += len(optional)
                metrics["recommended_editable_fields"] += len(recommended)
                metrics["system_hidden_fields"] += len(system_hidden)

    return metrics, findings


def run() -> dict[str, Any]:
    User = get_user_model()
    user = User.objects.filter(is_superuser=True, is_active=True).first()
    school = School.objects.filter(is_active=True).order_by("created_at").first()
    findings = _source_contract_findings()
    if user is None:
        findings.append("environment:no-active-superuser-for-read-only-form-resolution")
    if school is None:
        findings.append("environment:no-active-school-for-tenant-form-resolution")

    sites: dict[str, Any] = {}
    if user is not None and school is not None:
        tenant_metrics, tenant_findings = _audit_site(
            label="tenant",
            site=tenant_admin_site,
            host=f"{school.slug}.runmycampus.com",
            urlconf="config.tenant_urls",
            host_kind="tenant",
            school=school,
            user=user,
        )
        operator_metrics, operator_findings = _audit_site(
            label="operator",
            site=platform_admin_site,
            host="manager.runmycampus.com",
            urlconf="config.manager_urls",
            host_kind="manager",
            school=None,
            user=user,
        )
        sites = {"tenant": tenant_metrics, "operator": operator_metrics}
        findings.extend(tenant_findings)
        findings.extend(operator_findings)

    return {
        "contract_satisfied": not findings,
        "sites": sites,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    payload = run()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.report:
        path = args.report if args.report.is_absolute() else ROOT / args.report
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if payload["contract_satisfied"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
