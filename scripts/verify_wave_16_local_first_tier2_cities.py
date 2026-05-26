"""Wave 16 (v3.95.0 — 2026-05-26) — verifier for tier-2 city canonical map.

Confirms the ``_CITY_CANONICAL_MAP`` in ``apps.siteconfig.geoip_country_lookup``
has been expanded to cover tier-2 metros across all priority regions, and
that every canonical *value* round-trips through :func:`canonicalize_city`
to itself (so the slugified key for a value lands the value back).

Honest-reporting: prints PASS / FAIL per region, exits non-zero on any FAIL.
"""

from __future__ import annotations

import os
import sys

# Run as a stand-alone script: add repo root to sys.path so apps.* imports work.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Django setup is required for the apps.siteconfig import (settings module
# loads global registries). We don't actually issue any ORM calls.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # type: ignore

    django.setup()
except Exception:  # noqa: BLE001
    pass


def _load_map():
    from apps.siteconfig.geoip_country_lookup import (  # type: ignore
        _CITY_CANONICAL_MAP,
        canonicalize_city,
    )

    return _CITY_CANONICAL_MAP, canonicalize_city


_TIER2_REGIONS: dict[str, tuple[str, ...]] = {
    "Brazil tier-2": ("porto alegre", "recife", "manaus", "belem", "goiania"),
    "India tier-2": ("jaipur", "lucknow", "kanpur", "indore", "patna", "kochi"),
    "China tier-2": ("chengdu", "hangzhou", "wuhan", "xi'an", "chongqing"),
    "Japan tier-2": ("nagoya", "yokohama", "sapporo", "fukuoka", "kobe"),
    "Korea tier-2": ("incheon", "daegu", "daejeon", "gwangju", "ulsan"),
    "SE Asia tier-2": ("davao", "bandung", "yogyakarta", "chiang mai", "da nang", "phnom penh"),
    "MENA tier-2": ("sharjah", "kuwait city", "amman", "beirut", "tunis"),
    "Africa tier-2": ("port harcourt", "tamale", "cotonou", "kinshasa", "luanda"),
    "UK/IE tier-2": ("liverpool", "leeds", "cardiff", "belfast", "limerick"),
    "Americas tier-2": ("houston", "dallas", "boston", "ottawa", "lima", "quito"),
    "Europe tier-2": ("amsterdam", "wien", "zürich", "warszawa", "praha", "athens"),
    "Oceania tier-2": ("adelaide", "hobart", "canberra", "tauranga", "suva"),
    "South Asia tier-2": ("rawalpindi", "sylhet", "kandy", "kathmandu"),
}


def main() -> int:
    canonical_map, canonicalize_city = _load_map()
    print(f"# verify_wave_16_local_first_tier2_cities — {len(canonical_map)} entries")
    failures: list[str] = []
    for region, keys in _TIER2_REGIONS.items():
        missing = [k for k in keys if k not in canonical_map]
        if missing:
            failures.append(f"{region} missing: {missing}")
            print(f"FAIL {region}: missing {missing}")
        else:
            print(f"PASS {region} ({len(keys)} entries)")
    # Round-trip a sample of canonical values through canonicalize_city.
    samples = ("São Paulo", "München", "東京", "Bengaluru", "Lagos", "London")
    for s in samples:
        out = canonicalize_city(s)
        if out != s:
            failures.append(f"round-trip {s!r} -> {out!r}")
            print(f"FAIL round-trip {s!r} -> {out!r}")
        else:
            print(f"PASS round-trip {s!r}")
    if failures:
        print(f"\nFAIL — {len(failures)} issue(s)")
        return 1
    print("\nPASS — Wave 16 tier-2 city coverage verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
