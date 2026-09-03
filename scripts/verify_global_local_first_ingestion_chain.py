#!/usr/bin/env python
"""End-to-end chain gate: country pack -> ingestion lexicon -> offline surfaces.

Proves the local-first ingestion path is wired across:
* 249 ISO countries compile offline ingestion manifests (default + TVET profile)
* Tenant offline manifest carries ``operational_context.ingestion_lexicon``
* Portal SMS_OFFLINE_CONFIG emits ``ingestionManifest``
* Client JS + IndexedDB + offline upload preflight

Needs Django for the tenant-manifest slice only; country coverage is deps-free.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _static_wiring_failures() -> list[str]:
    failures: list[str] = []
    surface = (REPO_ROOT / "apps/siteconfig/platform_surface_config.py").read_text(
        encoding="utf-8"
    )
    if "ingestionManifest" not in surface:
        failures.append("platform_surface_config missing ingestionManifest")
    resolver = (REPO_ROOT / "apps/sync_engine/tenant_manifest_resolver.py").read_text(
        encoding="utf-8"
    )
    if "ingestion_lexicon" not in resolver:
        failures.append("tenant_manifest_resolver missing ingestion_lexicon in operational_context")
    if "compile_offline_ingestion_manifest_for_school" not in resolver:
        failures.append("tenant_manifest_resolver missing compile_offline_ingestion_manifest_for_school")

    js = REPO_ROOT / "static/js/rmc-offline-ingestion-lexicon.js"
    if not js.is_file():
        failures.append("missing rmc-offline-ingestion-lexicon.js")
    else:
        body = js.read_text(encoding="utf-8")
        if "resolveIngestionManifest" not in body:
            failures.append("rmc-offline-ingestion-lexicon.js missing resolveIngestionManifest fallback")

    portal = (REPO_ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "rmc-offline-ingestion-lexicon.js" not in portal:
        failures.append("portal_base.html does not load ingestion lexicon JS")

    offline_db = (REPO_ROOT / "static/js/offline-db.js").read_text(encoding="utf-8")
    if "ingestion_lexicon" not in offline_db:
        failures.append("offline-db.js missing ingestion_lexicon store")

    forms = (REPO_ROOT / "static/js/rmc-offline-portal-forms.js").read_text(encoding="utf-8")
    if "ingestion_preflight" not in forms:
        failures.append("rmc-offline-portal-forms.js missing ingestion_preflight payload")
    return failures


def _country_manifest_failures() -> list[str]:
    import pytz

    from apps.migration_cloud.ingestion_lexicon import compile_offline_ingestion_manifest

    required = frozenset(
        {
            "version",
            "country_code",
            "institution_profile",
            "grading_scale",
            "weight_type",
            "lexicon_mappings",
            "default_coefficients",
        }
    )
    failures: list[str] = []
    for code in sorted(pytz.country_names.keys()):
        for profile in ("default", "technical_vocational"):
            manifest = compile_offline_ingestion_manifest(code, institution_profile=profile)
            missing = required - set(manifest.keys())
            if missing:
                failures.append(f"{code}/{profile}: missing {sorted(missing)}")
    return failures


def _tenant_manifest_failures() -> list[str]:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from apps.sync_engine.tenant_manifest_resolver import school_offline_manifest_dict

    failures: list[str] = []
    for cc in ("CM", "KE", "US", "FR", "NG"):
        school = SimpleNamespace(
            id=1,
            schema_name=f"tenant_{cc.lower()}",
            country_code=cc,
            default_language="",
        )
        manifest = school_offline_manifest_dict(school)
        ops = manifest.get("operational_context") or {}
        lex = ops.get("ingestion_lexicon")
        if not isinstance(lex, dict):
            failures.append(f"{cc}: operational_context.ingestion_lexicon missing")
            continue
        if not lex.get("country_code"):
            failures.append(f"{cc}: ingestion_lexicon.country_code blank")
        if not lex.get("lexicon_mappings"):
            failures.append(f"{cc}: ingestion_lexicon.lexicon_mappings empty")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-django",
        action="store_true",
        help="Skip tenant-manifest slice (static + country coverage only)",
    )
    args = parser.parse_args()

    failures = _static_wiring_failures()
    failures.extend(_country_manifest_failures())

    if not args.skip_django:
        try:
            failures.extend(_tenant_manifest_failures())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"tenant manifest slice failed: {exc}")

    if failures:
        print("GLOBAL_LOCAL_FIRST_INGESTION_CHAIN_FAIL")
        for f in failures[:40]:
            print(f"  {f}")
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1

    print("GLOBAL_LOCAL_FIRST_INGESTION_CHAIN_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
