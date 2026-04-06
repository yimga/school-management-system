"""
Suggest next RuntimeDefaults first-class candidates from domain_ownership.

This command intentionally filters to short, non-FK/non-media string keys so we keep
shrinking the slim tenant site-settings payload without duplicating PlatformGlobalBranding media/FKs.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.runtime_defaults_first_class import (
    RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
)
from apps.siteconfig.domain_ownership import EXACT_FIELD_OWNERS
from apps.siteconfig.domain_ownership_storage import VIRTUAL_ONLY_EXACT_FIELDS

ALLOWED_OWNERS = {
    "brand_experience",
    "runtime_blueprints",
    "global_registries",
    "marketplace_integrations",
}
PREFERRED_ORDER = (
    "company_name",
    "company_email",
    "company_phone",
    "company_address",
    "company_slug",
    "ministry_registration_code",
    "country",
    "region",
    "ministry",
    "default_region",
    "default_grading_scale",
)
BLOCKLIST_SUBSTRINGS = ("theme", "logo", "background", "video", "svg", "report_style")


def collect_candidate_fields(
    *,
    exact_field_owners: dict[str, str],
    existing: set[str],
    virtual_only_exact: frozenset[str],
) -> list[str]:
    candidates: list[str] = []
    for field, owner in exact_field_owners.items():
        if owner not in ALLOWED_OWNERS:
            continue
        if field in existing:
            continue
        if field in virtual_only_exact:
            continue
        if any(part in field for part in BLOCKLIST_SUBSTRINGS):
            continue
        if field.endswith("_id") or field.endswith("_pack"):
            continue
        candidates.append(field)

    preferred = [f for f in PREFERRED_ORDER if f in candidates]
    remaining = sorted([f for f in candidates if f not in preferred])
    return preferred + remaining


class Command(BaseCommand):
    help = (
        "Suggest next RuntimeDefaults first-class field names from siteconfig "
        "domain ownership map (string-only, no FK/media style keys)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of candidate fields to print.",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 5))
        ordered = collect_candidate_fields(
            exact_field_owners=dict(EXACT_FIELD_OWNERS),
            existing=set(RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES),
            virtual_only_exact=VIRTUAL_ONLY_EXACT_FIELDS,
        )[:limit]
        if not ordered:
            self.stdout.write(self.style.WARNING("No candidates found."))
            return
        self.stdout.write("Suggested next RuntimeDefaults first-class fields:")
        for name in ordered:
            self.stdout.write(f"- {name} ({EXACT_FIELD_OWNERS.get(name)})")
