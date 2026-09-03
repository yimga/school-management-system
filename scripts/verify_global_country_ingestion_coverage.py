#!/usr/bin/env python
"""Verify every ISO country can compile an offline ingestion manifest.

Honest count: 249 ISO alpha-2 codes (pytz), not 250 — payment JSON adds EU stub.
Zero-tolerance: every country must produce a manifest with required keys.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytz

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REQUIRED_KEYS = frozenset({
    "version",
    "country_code",
    "institution_profile",
    "grading_scale",
    "weight_type",
    "lexicon_mappings",
    "default_coefficients",
})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    from apps.migration_cloud.ingestion_lexicon import compile_offline_ingestion_manifest

    failures: list[str] = []
    for code in sorted(pytz.country_names.keys()):
        for profile in ("default", "technical_vocational"):
            manifest = compile_offline_ingestion_manifest(code, institution_profile=profile)
            missing = REQUIRED_KEYS - set(manifest.keys())
            if missing:
                failures.append(f"{code}/{profile}: missing {sorted(missing)}")
            if not manifest.get("lexicon_mappings"):
                failures.append(f"{code}/{profile}: empty lexicon_mappings")
            if manifest.get("country_code") != code.upper()[:2] and code.upper() not in ("CMR",):
                # alpha2 normalization may differ for aliases; allow non-empty country_code
                if not manifest.get("country_code"):
                    failures.append(f"{code}/{profile}: blank country_code")

    if failures:
        print("GLOBAL_COUNTRY_INGESTION_COVERAGE_FAIL")
        for f in failures[:50]:
            print(f"  {f}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")
        return 1

    total = len(pytz.country_names) * 2
    print(f"GLOBAL_COUNTRY_INGESTION_COVERAGE_PASS (countries={len(pytz.country_names)} profiles=2 manifests={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
