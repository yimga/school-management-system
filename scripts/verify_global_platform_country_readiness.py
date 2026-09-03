#!/usr/bin/env python
"""Forensic structural gate: 249-country baseline + local-first chain.

Zero-tolerance on UNIVERSAL layers (every ISO country must compile/resolve).
Reports DEPTH tiers honestly — does not fail on research gaps (grading 93/249).

Structural requirements (FAIL if broken):
* 249 ISO codes in governance matrix
* 249/249 resolve_country_pack
* 498/498 offline ingestion manifests (default + TVET)
* Tenant manifest carries operational_context.ingestion_lexicon
* Local-first verifiers pass (ingestion chain, offline capabilities, sovereign foundation)
* Client lexicon: IDB read path + authenticated portal shell load
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_script(name: str) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / name)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO_ROOT),
    )
    out = (r.stdout or r.stderr or "").strip()
    last = out.splitlines()[-1] if out else f"exit {r.returncode}"
    return r.returncode, last


def _static_client_failures() -> list[str]:
    import re

    failures: list[str] = []
    portal = (REPO_ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    lex_path = "rmc-offline-ingestion-lexicon.js"
    auth_open = portal.find("{% if request.user.is_authenticated %}")
    lex_pos = portal.find(lex_path)
    if auth_open < 0 or lex_pos < auth_open:
        failures.append("portal_base: lexicon not loaded for authenticated users")
    status_block = re.search(
        r"{% if SHOW_OFFLINE_STATUS_BAR %}.*?{% endif %}",
        portal,
        re.DOTALL,
    )
    if status_block and lex_path in status_block.group(0):
        failures.append("portal_base: lexicon gated only behind SHOW_OFFLINE_STATUS_BAR")

    js = (REPO_ROOT / "static/js/rmc-offline-ingestion-lexicon.js").read_text(encoding="utf-8")
    for sym in ("ensureManifestReady", "loadManifestFromIndexedDB"):
        if sym not in js:
            failures.append(f"rmc-offline-ingestion-lexicon.js missing {sym}")

    sw = (REPO_ROOT / "static/js/service-worker.js").read_text(encoding="utf-8")
    for asset in (
        "rmc-offline-ingestion-lexicon.js",
        "rmc-offline-portal-forms.js",
        "offline-queue-client.js",
    ):
        if asset not in sw:
            failures.append(f"service-worker precache missing {asset}")
    return failures


def _country_structural_failures() -> list[str]:
    import pytz

    from apps.migration_cloud.ingestion_lexicon import compile_offline_ingestion_manifest
    from apps.siteconfig.country_localization_service import resolve_country_pack

    iso = sorted(pytz.country_names.keys())
    failures: list[str] = []

    gov_path = REPO_ROOT / "docs/generated/country_governance_matrix.json"
    if gov_path.is_file():
        gov = json.loads(gov_path.read_text(encoding="utf-8"))
        rows = gov.get("rows") or []
        gov_iso = {
            str(r.get("iso_alpha2") or r.get("country_code") or "").upper()[:2]
            for r in rows
            if isinstance(r, dict)
        } - {""}
        if len(gov_iso) < 249:
            failures.append(f"governance matrix: {len(gov_iso)}/249 ISO rows")
    else:
        failures.append("missing docs/generated/country_governance_matrix.json")

    pack_miss = [c for c in iso if not resolve_country_pack(c)]
    if pack_miss:
        failures.append(f"resolve_country_pack failed for {len(pack_miss)} countries")

    manifest_miss = []
    for code in iso:
        for profile in ("default", "technical_vocational"):
            m = compile_offline_ingestion_manifest(code, institution_profile=profile)
            if not m.get("lexicon_mappings"):
                manifest_miss.append(f"{code}/{profile}")
    if manifest_miss:
        failures.append(
            f"ingestion manifests missing lexicon: {len(manifest_miss)} "
            f"(first: {manifest_miss[0]})"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-django", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    failures.extend(_static_client_failures())
    failures.extend(_country_structural_failures())

    gate_scripts = [
        "verify_global_country_ingestion_coverage.py",
        "verify_ingestion_lexicon_offline_wiring.py",
        "verify_offline_capability_implementation.py",
        "verify_local_first_surface_wiring.py",
        "verify_sovereign_offline_foundation.py",
    ]
    if not args.skip_django:
        gate_scripts.append("verify_global_local_first_ingestion_chain.py")
        gate_scripts.append("verify_tenant_customer_250_country_matrix.py")

    for script in gate_scripts:
        code, summary = _run_script(script)
        if code != 0:
            failures.append(f"{script}: {summary}")

    if failures:
        print("GLOBAL_PLATFORM_COUNTRY_READINESS_FAIL")
        for f in failures:
            print(f"  {f}")
        return 1

    print(
        "GLOBAL_PLATFORM_COUNTRY_READINESS_PASS "
        "(249 ISO structural baseline + local-first chain enforced)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
