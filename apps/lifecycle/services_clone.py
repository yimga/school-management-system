"""Clone-from-template school service.

Operators can spin up a new school whose settings/branding/blueprint
mirror an existing 'template' school. Common case: an org running 10
similar campuses wants the 11th to look like #1 from day 0 without
re-doing the wizard's brand pass.

Public API:
    clone_school(source, *, new_name, new_slug, actor=None, overrides=None)
        -> ClonedSchool

Fields cloned (when present on source):
- branding & brand_payload (primary_color, accent_color, theme_choice, theme_pack_id, branding_metadata)
- locale (sub_system, default_language, default_region_id, timezone)
- sector & education profile (primary_sector, school_type, education_levels)
- workflow defaults (default_workflow_slug, default_dashboard_slug, report_platform_bundle_slug)
- settings dict (excluding 'offboarding' state — see _SETTINGS_EXCLUDE)

Never cloned:
- id, slug, name, subdomain (must be new)
- is_active, is_approved, is_frozen (clones start gated)
- last_activity, custom_domain*, trial_end_date (status — not template)
- settings['offboarding'] (incoming clone is not in offboarding)
- impersonation_consent_* (per-tenant consent, not template-shareable)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from apps.schools.models import School

from .services import record_stage

logger = logging.getLogger(__name__)


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")

# Settings keys NEVER copied — these are state about the source school,
# not template traits.
#
# The first three were the original list. The rest were found being cloned:
# ``migration_intent`` is read by the School post_save receiver, which calls
# ensure_draft_migration_bundle and gave a brand-new empty tenant a real
# MigrationBundle labelled with the SOURCE's label plus a MIGRATING lifecycle
# stage on day 0 (and, because the receiver records that before clone_school's
# own REQUESTED, a timeline whose current stage disagreed with its history).
# ``customersuccess`` carries the source's helpcenter_sources ledger — its
# registered help URLs and uploaded filenames — and its nudges_sent log;
# ``lifecycle`` carries creation_path/creation_path_set_at; ``provisioning``
# carries the source's phase flags; ``rmc_public_onboarding`` carries the
# source's signup/migration record, which also flips get_creation_path().
#
# Deliberately still a deny-list, not the allow-list the model side uses for
# direct fields: settings holds open-ended per-feature template traits
# (localization, blueprint and workflow defaults, branding extras) that an
# allow-list would silently stop cloning. What must never travel is STATE, and
# state is enumerable. Add to this list when a feature starts storing state
# under settings.
_SETTINGS_EXCLUDE = frozenset(
    {
        "offboarding",  # offboarding state machine for the source
        "incident_log",  # source-specific operational history
        "billing_state",  # source-specific reconciliation cache
        "migration_intent",  # auto-drafts a MigrationBundle for the clone
        "customersuccess",  # helpcenter ledger + nudge log, source-specific
        "lifecycle",  # creation_path and its timestamp
        "provisioning",  # the source's provisioning phase flags
        "rmc_public_onboarding",  # the source's signup / migration record
    }
)

# Direct fields on School that ARE part of the template ("trait" fields).
# Listed explicitly so we never accidentally clone status / privacy
# fields. Update this list when adding new School fields that should
# participate in templating.
_TEMPLATE_FIELDS = (
    "sub_system",
    "default_region_id",
    "country_code",
    "data_region",
    "subdivision_id",
    "timezone",
    "default_language",
    "features",
    "logo_url",
    "wallpaper_url",
    "primary_color",
    "accent_color",
    "theme_choice",
    "theme_pack_id",
    "plan_id",
    "default_workflow_slug",
    "default_dashboard_slug",
    "addons",
    "report_platform_bundle_slug",
    "school_type",
    "billing_type",
    "compliance_region",
    "branding_metadata",
    "primary_sector",
    "regional_cluster",
)


@dataclass
class ClonedSchool:
    source_id: str
    new_id: str
    new_slug: str
    new_name: str
    fields_copied: int
    settings_keys_copied: int


def _copy_settings(src: dict) -> dict:
    if not isinstance(src, dict):
        return {}
    out: dict = {}
    for key, value in src.items():
        if not isinstance(key, str):
            continue
        if key in _SETTINGS_EXCLUDE:
            continue
        out[key] = value
    return out


def clone_school(
    source: School,
    *,
    new_name: str,
    new_slug: str,
    actor=None,
    new_subdomain: Optional[str] = None,
    overrides: Optional[dict] = None,
) -> ClonedSchool:
    """Create a new School row mirroring `source`'s template traits."""
    if not source or not getattr(source, "id", None):
        raise ValueError("source must be a saved School instance")
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("new_name is required")
    new_slug = (new_slug or "").strip().lower()
    if not _SLUG_RE.match(new_slug):
        raise ValueError("new_slug must be lowercase alnum+hyphens, 3-120 chars")
    sub = (new_subdomain or new_slug).strip().lower()
    if not _SLUG_RE.match(sub):
        raise ValueError("new_subdomain must be lowercase alnum+hyphens, 3-120 chars")
    overrides = overrides or {}

    fields_copied = 0
    template_payload: dict = {}
    for field_name in _TEMPLATE_FIELDS:
        if not hasattr(source, field_name):
            continue
        value = getattr(source, field_name)
        if value in (None, ""):
            continue
        template_payload[field_name] = value
        fields_copied += 1
    settings_copy = _copy_settings(getattr(source, "settings", {}) or {})
    settings_keys_copied = len(settings_copy)
    template_payload.update(overrides)

    with transaction.atomic():
        clone = School.objects.create(
            name=new_name,
            slug=new_slug,
            subdomain=sub,
            is_active=False,
            settings=settings_copy,
            **template_payload,
        )
        record_stage(
            clone,
            "REQUESTED",
            actor=actor,
            note=f"Cloned from {source.slug}",
            payload={
                "source": "clone_school",
                "source_school_id": str(source.id),
                "source_slug": source.slug,
                "fields_copied": fields_copied,
                "settings_keys_copied": settings_keys_copied,
            },
        )

    return ClonedSchool(
        source_id=str(source.id),
        new_id=str(clone.id),
        new_slug=clone.slug,
        new_name=clone.name,
        fields_copied=fields_copied,
        settings_keys_copied=settings_keys_copied,
    )
