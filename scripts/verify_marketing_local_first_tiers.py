#!/usr/bin/env python3
"""Verify marketing local-first tiers 2–3 ship required files, copy, and HTTP markers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FILES = (
    "apps/schools/security_packet_country_annex.py",
    "templates/marketing/partials/security_packet_country_annex.html",
    "templates/marketing/partials/case_study_cards_honest.html",
    "templates/marketing/pages/type_resources_case_studies.html",
    "config/marketing_content/resources-case-studies.json",
    "config/marketing_content/platform-marketplace.json",
    "static/marketing/js/mkt-security-packet-annex.js",
)

REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "templates/marketing/partials/security_packet_country_annex.html": (
        "data-mkt-security-country-annex",
    ),
    "templates/marketing/security_packet_request.html": (
        "security_packet_country_annex.html",
        "Which jurisdiction governs your student records",
        "compliance_jurisdiction",
        "mkt-security-packet-annex.js",
    ),
    "templates/marketing/components/_marketing_demo_form.html": (
        "Which jurisdiction governs your student records",
        "compliance_jurisdiction",
    ),
    "config/marketing_content/resources-case-studies.json": (
        "case_cards",
        "Cameroon",
        "Illustrative",
    ),
    "config/marketing_content/pricing.json": (
        "governance layer",
    ),
    "config/marketing_content/platform-marketplace.json": (
        "activate per campus",
    ),
    "apps/schools/marketing_views.py": (
        "MARKETING_SCALE_SCHOOL_COUNT",
        "Many campuses, one governance layer",
        "country_annex",
    ),
    "templates/schools/marketing_landing_v2.html": (
        "marketing_scale_school_count",
        "Illustrative scale signal",
    ),
}

FORBIDDEN_SUBSTRINGS = (
    '"School A"',
    ">School A<",
    "School A Academy",
)

HTTP_ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "/security-packet/?jurisdiction=ndpr-ng",
        ("data-mkt-security-country-annex", "Nigeria"),
    ),
    (
        "/resources/case-studies/",
        ("data-mkt-case-studies-honest", "Cameroon"),
    ),
    ("/demo/", ("Which jurisdiction governs your student records",)),
    ("/pricing/", ("governance layer",)),
    ("/grow/marketplace/", ("activate per campus",)),
    ("/marketing/", ("mkt-scale-signal", "Illustrative scale signal")),
)


def _read(rel: str) -> str:
    path = ROOT / rel.replace("/", os.sep)
    if not path.is_file():
        raise FileNotFoundError(rel)
    return path.read_text(encoding="utf-8")


def verify_files() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel.replace("/", os.sep)).is_file():
            errors.append(f"missing file: {rel}")
    return errors


def verify_markers() -> list[str]:
    errors: list[str] = []
    for rel, needles in REQUIRED_MARKERS.items():
        try:
            text = _read(rel)
        except FileNotFoundError as exc:
            errors.append(str(exc))
            continue
        for needle in needles:
            if needle not in text:
                errors.append(f"{rel}: missing marker {needle!r}")
    for rel in ("config/marketing_content/resources-case-studies.json",):
        try:
            text = _read(rel)
        except FileNotFoundError:
            continue
        for bad in FORBIDDEN_SUBSTRINGS:
            if bad in text:
                errors.append(f"{rel}: forbidden marker {bad!r}")
    return errors


def verify_annex_module() -> list[str]:
    errors: list[str] = []
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
        from apps.schools.security_packet_country_annex import (
            build_country_annex,
            country_code_for_jurisdiction,
            jurisdiction_choices,
        )

        if country_code_for_jurisdiction("ndpr-ng") != "NG":
            errors.append("country_code_for_jurisdiction(ndpr-ng) != NG")
        annex = build_country_annex(country_code="NG")
        if annex.get("country_code") != "NG":
            errors.append("build_country_annex(NG) country_code mismatch")
        if len(jurisdiction_choices()) < 8:
            errors.append("jurisdiction_choices() too short")
    except Exception as exc:  # noqa: BLE001 — verifier surfaces import/setup failures
        errors.append(f"annex module: {exc}")
    return errors


def verify_http(host: str) -> list[str]:
    errors: list[str] = []
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
        from django.test import Client
    except Exception as exc:  # noqa: BLE001
        errors.append(f"django setup: {exc}")
        return errors

    client = Client(HTTP_HOST=host)
    for path, needles in HTTP_ROUTES:
        resp = client.get(path, HTTP_HOST=host)
        if resp.status_code != 200:
            errors.append(f"GET {path}: status {resp.status_code}")
            continue
        body = resp.content.decode(errors="replace")
        for needle in needles:
            if needle.lower() not in body.lower():
                errors.append(f"GET {path}: missing {needle!r}")
        if path.startswith("/resources/case-studies"):
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in body:
                    errors.append(f"GET {path}: contains forbidden {bad!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--http", action="store_true", help="Live Django client smoke")
    parser.add_argument("--host", default="runmycampus.com")
    args = parser.parse_args()

    errors: list[str] = []
    errors.extend(verify_files())
    errors.extend(verify_markers())
    errors.extend(verify_annex_module())
    if args.http:
        errors.extend(verify_http(args.host))

    payload = {"ok": not errors, "errors": errors}
    if args.json:
        print(json.dumps(payload, indent=2))
    elif errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
    else:
        print("OK: marketing local-first tiers 2–3 verified")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
