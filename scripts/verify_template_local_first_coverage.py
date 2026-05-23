"""Verifier — local-first template coverage for priority markets.

Asserts at least 25 priority markets have a dedicated local-first template
mapped to a real LocalExperienceProfile.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PRIORITY_MARKETS = {
    "CM", "NG", "GH", "KE", "ZA", "CI", "SN", "MA",
    "IN", "PK", "BD",
    "JP", "KR", "CN",
    "PH", "MY", "ID",
    "US", "GB", "AU",
    "AE", "MX", "BR",
    "CA", "IE", "NZ",
    "SG", "HK", "TH", "VN", "LK", "NP",
    "TZ", "UG", "RW", "ET", "EG",
    "SA", "QA", "TR",
    "ES", "FR", "DE", "NL", "PT",
    "CL", "CO", "PE",
}


def _bootstrap() -> None:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    _bootstrap()
    from apps.brand_experience import experience_templates as et
    from apps.siteconfig import local_experience_profiles as lep

    by_country: dict[str, list[str]] = {}
    for o in et.OVERLAYS:
        if o.category != "local-first":
            continue
        for cc in o.supported_countries:
            by_country.setdefault(cc, []).append(o.key)

    missing = sorted(PRIORITY_MARKETS - by_country.keys())
    if missing:
        print(f"FAIL: {len(missing)} priority markets without a local-first template: {missing}")
        return 1

    profile_keys = set(lep.profile_keys())
    orphan_refs = [
        o.key
        for o in et.OVERLAYS
        if o.category == "local-first" and o.local_profile_ref not in profile_keys
    ]
    if orphan_refs:
        print(f"FAIL: {len(orphan_refs)} local-first templates reference unknown profiles: {orphan_refs[:3]}")
        return 1

    if len(lep.PROFILES) != 50:
        print(f"FAIL: expected 50 LocalExperienceProfile entries, found {len(lep.PROFILES)}")
        return 1

    print(
        f"TEMPLATE_LOCAL_FIRST_COVERAGE_PASS "
        f"(markets covered: {len(by_country)}/{len(PRIORITY_MARKETS)}, "
        f"templates: {sum(len(v) for v in by_country.values())}, "
        f"profiles: {len(profile_keys)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
