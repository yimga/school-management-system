#!/usr/bin/env python3
"""Verify operator surfaces only expose earned-stable maturity labels."""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=str(ROOT), help="Repository root to inspect.")
    return parser.parse_args()


def main() -> int:
    base = Path(parse_args().base).resolve()
    if not base.is_dir():
        print(f"verify_operator_surface_maturity: missing base {base}", file=sys.stderr)
        return 1
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(base))

    import django

    django.setup()

    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    from apps.siteconfig.control_outcome_center import (
        STABLE_OPERATOR_SURFACE,
        build_ccc_staging_publish_links_for_request,
        build_feature_control_operator_quick_links,
        build_operator_control_model_for_request,
        build_outcome_groups_for_request,
        validate_operator_surface_maturity_proofs,
    )

    findings = validate_operator_surface_maturity_proofs()
    request = RequestFactory().get("/")
    request.urlconf = "config.manager_urls"
    request.public_host_kind = "manager"
    request.user = AnonymousUser()

    for group in build_outcome_groups_for_request(request):
        for link in group["links"]:
            if link.get("stability") != STABLE_OPERATOR_SURFACE:
                findings.append(
                    f"outcome:{group['id']}:{link['label']} exposes {link.get('stability')!r}"
                )

    for link in build_feature_control_operator_quick_links(request):
        if link.get("stability") != STABLE_OPERATOR_SURFACE:
            findings.append(f"quick-link:{link['label']} exposes {link.get('stability')!r}")

    for link in build_ccc_staging_publish_links_for_request(request):
        if link.get("stability") != STABLE_OPERATOR_SURFACE:
            findings.append(f"staging-link:{link['label']} exposes {link.get('stability')!r}")

    for step in build_operator_control_model_for_request(request):
        if step["primary"].get("stability") != STABLE_OPERATOR_SURFACE:
            findings.append(
                f"operator-model:{step['id']}:primary exposes {step['primary'].get('stability')!r}"
            )
        for related in step.get("related") or ():
            if related.get("stability") != STABLE_OPERATOR_SURFACE:
                findings.append(
                    f"operator-model:{step['id']}:{related['label']} exposes {related.get('stability')!r}"
                )

    if findings:
        print(f"verify_operator_surface_maturity: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("verify_operator_surface_maturity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
