from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib import error, parse, request

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone as django_timezone

from apps.siteconfig.brand_registry import (
    BASELINE_ISCED_LEVELS,
    DEFAULT_COMPLIANCE_CONFIG,
    DEFAULT_LABELS_MAP,
    DEFAULT_UI_CONFIG,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import GlobalBrandRegistry


UNESCO_TIMEOUT_SECONDS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_default_registry_row(country_alpha2: str, country_alpha3: str) -> dict:
    defaults = GlobalGeoCatalog.country_defaults(country_alpha3 or country_alpha2)
    language = (defaults.get("default_language") or "en").split("-", 1)[0].lower()
    return {
        "country_name": defaults.get("country_name") or country_alpha2,
        "primary_language": language or "en",
        "academic_config": {
            "isced_levels": BASELINE_ISCED_LEVELS,
            "source": "baseline",
            "seeded_at": _now_iso(),
        },
        "labels_map": dict(DEFAULT_LABELS_MAP),
        "compliance_config": dict(DEFAULT_COMPLIANCE_CONFIG),
        "seo_config": {
            "headline": f"Global School Platform for {defaults.get('country_name') or country_alpha2}",
            "subheadline": "Localized operations, secure tenancy, and modern campus workflows.",
        },
        "ui_config": {
            **DEFAULT_UI_CONFIG,
            "timezone": defaults.get("timezone") or "UTC",
            "locale": language or "en",
        },
        "currency_code": (defaults.get("currency") or "USD").upper(),
        "is_active": True,
        "source_name": "global_catalog",
        "source_synced_at": django_timezone.now(),
    }


def _parse_uis_isced_payload(payload: dict) -> dict | None:
    """
    Best-effort parser for UIS-like responses.
    """
    if not isinstance(payload, dict):
        return None
    levels = payload.get("isced_levels")
    if isinstance(levels, dict) and levels:
        return levels
    data = payload.get("data")
    if isinstance(data, dict):
        levels = data.get("isced_levels")
        if isinstance(levels, dict) and levels:
            return levels
    if isinstance(data, list):
        out = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            level = str(row.get("level") or row.get("isced") or "").strip()
            label = str(row.get("label") or row.get("name") or "").strip()
            if level and label:
                out[level] = label
        if out:
            return out
    return None


def _fetch_unesco_isced(country_alpha2: str) -> dict | None:
    """
    UNESCO UIS endpoints change over time; this function tries candidate URLs.
    Returns {"isced_levels": {...}, "source_name": "..."} or None.
    """
    candidates = [
        f"https://api.uis.unesco.org/api/public/v1/isced?country={parse.quote(country_alpha2)}",
        f"https://api.uis.unesco.org/v1/isced/{parse.quote(country_alpha2)}",
    ]
    for url in candidates:
        try:
            req = request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "runmycampus-seeder/1.0",
                },
            )
            with request.urlopen(req, timeout=UNESCO_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(body)
            levels = _parse_uis_isced_payload(payload)
            if levels:
                return {
                    "isced_levels": levels,
                    "source_name": "unesco_uis",
                }
        except (
            error.URLError,
            error.HTTPError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
        ):
            continue
    return None


class Command(BaseCommand):
    help = "Seed GlobalBrandRegistry for all countries (with best-effort UNESCO ISCED enrichment)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--country",
            default="",
            help="Optional ISO alpha-2 or alpha-3 to seed only one country.",
        )
        parser.add_argument(
            "--skip-unesco",
            action="store_true",
            help="Do not call UNESCO endpoints; use local baseline only.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        country_arg = (options.get("country") or "").strip()
        skip_unesco = bool(options.get("skip_unesco"))

        if country_arg:
            alpha3 = GlobalGeoCatalog.normalize_country_code(country_arg)
            alpha2 = GlobalGeoCatalog.alpha2_for_country(alpha3)
            countries = (
                [
                    {
                        "code": alpha3,
                        "code_alpha2": alpha2,
                        "name": GlobalGeoCatalog.country_name(alpha3),
                    }
                ]
                if alpha3 and alpha2
                else []
            )
        else:
            countries = GlobalGeoCatalog.list_countries()

        if not countries:
            self.stdout.write(
                self.style.ERROR("No countries resolved from GlobalGeoCatalog.")
            )
            return

        created = 0
        updated = 0
        unesco_hits = 0
        fallback_hits = 0

        for country in countries:
            alpha3 = str(country.get("code") or "").upper()
            alpha2 = str(
                country.get("code_alpha2")
                or GlobalGeoCatalog.alpha2_for_country(alpha3)
            ).upper()
            if not alpha2:
                continue

            defaults = _build_default_registry_row(alpha2, alpha3)
            unesco_payload = None if skip_unesco else _fetch_unesco_isced(alpha2)
            if unesco_payload:
                defaults["academic_config"] = {
                    "isced_levels": unesco_payload["isced_levels"],
                    "source": "unesco_uis",
                    "seeded_at": _now_iso(),
                }
                defaults["source_name"] = unesco_payload["source_name"]
                unesco_hits += 1
            else:
                fallback_hits += 1

            _, was_created = GlobalBrandRegistry.objects.update_or_create(
                iso_code=alpha2,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Global brand registry seed complete. "
                f"Countries={len(countries)} Created={created} Updated={updated} "
                f"UNESCO={unesco_hits} Fallback={fallback_hits}"
            )
        )
