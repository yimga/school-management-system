"""Derived 200+ country experience baselines.

The rich ``LocalExperienceProfile`` registry holds premium deep profiles for
priority markets. This module gives every country in the finance regional
payment catalog a tenant-experience baseline so onboarding, templates, and
setup copy can resolve a local currency/payment posture even before a deep
profile exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Any


_APPS_ROOT = Path(__file__).resolve().parents[1]
_PAYMENT_PROFILE_PATH = _APPS_ROOT / "finance" / "data" / "regional_payment_profiles.json"


@dataclass(frozen=True)
class CountryExperienceBaseline:
    country_code: str
    label: str
    currency: str
    primary_rail: str
    backup_rail: str
    manual_fallback: bool
    offline_receipt_allowed: bool
    provider_setup_status: str
    locale_status: str
    template_depth: str
    setup_posture: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _load_payment_profiles() -> dict[str, dict[str, Any]]:
    with _PAYMENT_PROFILE_PATH.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, dict):
        raise ValueError("regional_payment_profiles.json must be an object keyed by ISO2")
    return rows


@lru_cache(maxsize=1)
def list_country_experience_baselines() -> list[CountryExperienceBaseline]:
    out: list[CountryExperienceBaseline] = []
    for code, row in sorted(_load_payment_profiles().items()):
        cc = str(row.get("country_code") or code).strip().upper()
        currency = str(row.get("currency") or "").strip().upper()
        primary = str(row.get("primary_rail") or "").strip().upper()
        backup = str(row.get("backup_rail") or "").strip().upper()
        if len(cc) != 2 or len(currency) != 3:
            continue
        out.append(
            CountryExperienceBaseline(
                country_code=cc,
                label=str(row.get("label") or cc).strip(),
                currency=currency,
                primary_rail=primary or "BANK",
                backup_rail=backup or "CASH",
                manual_fallback=bool(row.get("manual_fallback", True)),
                offline_receipt_allowed=bool(row.get("offline_receipt_allowed", True)),
                provider_setup_status=str(row.get("provider_setup_status") or "external_required"),
                locale_status="baseline",
                template_depth="baseline_country_native",
                setup_posture="country_currency_payment_baseline",
            )
        )
    return out


@lru_cache(maxsize=1)
def baseline_index() -> dict[str, CountryExperienceBaseline]:
    return {row.country_code: row for row in list_country_experience_baselines()}


def assert_country_baseline_invariants(min_count: int = 200) -> None:
    rows = list_country_experience_baselines()
    if len(rows) < min_count:
        raise AssertionError(f"Expected at least {min_count} country baselines, got {len(rows)}")
    codes = [row.country_code for row in rows]
    if len(codes) != len(set(codes)):
        raise AssertionError("Duplicate country experience baseline codes detected")
    for row in rows:
        if not row.currency or len(row.currency) != 3:
            raise AssertionError(f"{row.country_code}: missing ISO-4217 currency")
        if not row.primary_rail:
            raise AssertionError(f"{row.country_code}: missing primary rail")
        if not row.backup_rail:
            raise AssertionError(f"{row.country_code}: missing backup rail")
