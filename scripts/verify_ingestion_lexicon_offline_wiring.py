#!/usr/bin/env python
"""Verify ingestion lexicon is wired into offline client config (local-first).

Checks:
* ``resolve_sms_offline_config`` emits ``ingestionManifest`` key
* ``compile_offline_ingestion_manifest_for_school`` symbol exists
* Client JS module + portal shell script tag
* IndexedDB schema includes ``ingestion_lexicon`` store
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures: list[str] = []

    surface = (REPO_ROOT / "apps/siteconfig/platform_surface_config.py").read_text(encoding="utf-8")
    if "ingestionManifest" not in surface:
        failures.append("platform_surface_config.py missing ingestionManifest")
    if "_ingestion_manifest_for_request" not in surface:
        failures.append("platform_surface_config.py missing _ingestion_manifest_for_request")

    lexicon = (REPO_ROOT / "apps/migration_cloud/ingestion_lexicon.py").read_text(encoding="utf-8")
    if "compile_offline_ingestion_manifest_for_school" not in lexicon:
        failures.append("ingestion_lexicon.py missing compile_offline_ingestion_manifest_for_school")

    resolver = (REPO_ROOT / "apps/sync_engine/tenant_manifest_resolver.py").read_text(encoding="utf-8")
    if "ingestion_lexicon" not in resolver:
        failures.append("tenant_manifest_resolver.py missing operational_context.ingestion_lexicon")

    js = REPO_ROOT / "static/js/rmc-offline-ingestion-lexicon.js"
    if not js.is_file():
        failures.append("missing static/js/rmc-offline-ingestion-lexicon.js")
    else:
        body = js.read_text(encoding="utf-8")
        if "rmcOfflineIngestionLexicon" not in body:
            failures.append("rmc-offline-ingestion-lexicon.js missing global export")
        if "resolveIngestionManifest" not in body:
            failures.append("rmc-offline-ingestion-lexicon.js missing tenant-manifest fallback")
        if "ensureManifestReady" not in body or "loadManifestFromIndexedDB" not in body:
            failures.append("rmc-offline-ingestion-lexicon.js missing IndexedDB read path")

    portal = (REPO_ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    auth_open = portal.find("{% if request.user.is_authenticated %}")
    if auth_open < 0 or portal.find("rmc-offline-ingestion-lexicon.js") < auth_open:
        failures.append("portal_base.html does not load lexicon for authenticated users")

    offline_db = (REPO_ROOT / "static/js/offline-db.js").read_text(encoding="utf-8")
    if "ingestion_lexicon" not in offline_db:
        failures.append("offline-db.js missing ingestion_lexicon store")

    forms = (REPO_ROOT / "static/js/rmc-offline-portal-forms.js").read_text(encoding="utf-8")
    if "ingestion_preflight" not in forms:
        failures.append("rmc-offline-portal-forms.js missing ingestion_preflight payload")

    if failures:
        print("INGESTION_LEXICON_OFFLINE_WIRING_FAIL")
        for f in failures:
            print(f"  {f}")
        return 1

    print("INGESTION_LEXICON_OFFLINE_WIRING_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
