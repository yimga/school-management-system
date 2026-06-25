#!/usr/bin/env python3
"""Operator proof: Parent preset + CM country → score band + country bonus on command strip."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounts.models import User
from apps.portal.tenant_experience_command import build_tenant_experience_command
from apps.siteconfig.config_service import get_effective_site_settings
from apps.siteconfig.tenant_experience_policy import (
    persist_tenant_experience_policy,
    resolve_tenant_experience_policy,
)
from apps.siteconfig.tenant_experience_presets import PRESET_PARENT_PORTAL, apply_experience_preset


def main() -> int:
    from apps.schools.models import School

    school = School.objects.filter(slug="demo-school").first()
    if school is None:
        print("OPERATOR_PROOF_FAIL: demo-school not found")
        return 1

    site = get_effective_site_settings(school=school)
    if site is None:
        print("OPERATOR_PROOF_FAIL: site settings missing")
        return 1

    school.country_code = "CM"
    school.save(update_fields=["country_code", "updated_at"])

    policy = apply_experience_preset(PRESET_PARENT_PORTAL)
    policy["role_experience_presets"] = {"PARENT": PRESET_PARENT_PORTAL}
    persist_tenant_experience_policy(site, policy)

    parent = get_user_model().objects.filter(username="demo.parent").first()
    if parent is None:
        parent = get_user_model().objects.filter(role=User.Role.PARENT).first()
    if parent is None:
        print("OPERATOR_PROOF_FAIL: parent user missing")
        return 1

    request = RequestFactory().get("/portal/parent/")
    request.school = school
    request.site_settings = site
    request.SITE = site
    request.user = parent

    resolved = resolve_tenant_experience_policy(request, role=User.Role.PARENT)
    payload = build_tenant_experience_command(request, User.Role.PARENT)

    failures: list[str] = []
    if resolved.get("effective_experience_preset") != PRESET_PARENT_PORTAL:
        failures.append("effective_experience_preset != parent_portal_focus")
    if payload.get("score_band") not in {"ready", "progress", "attention"}:
        failures.append("score_band missing")
    if int(payload.get("country_auto_bonus") or 0) <= 0:
        failures.append("country_auto_bonus not applied for CM")
    if payload.get("local_experience_depth") not in {"deep", "derived", "baseline"}:
        failures.append("local_experience_depth not configured for CM")

    if failures:
        print("OPERATOR_PROOF_FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print(
        "OPERATOR_PROOF_PASS "
        f"band={payload['score_band']} "
        f"bonus={payload['country_auto_bonus']} "
        f"depth={payload['local_experience_depth']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
