"""Resolvers + writers for the 5 operator/account-side wizards migrated to
the Unified Wizard Framework (v3.99.23, 2026-05-28).

These were previously ad-hoc Python views / template-driven flows:

* ``super_create_school`` — operator-side new-tenant provisioning
* ``custom_domain_setup`` — tenant-admin custom CNAME + verification
* ``mfa_setup`` — per-account TOTP enrollment + recovery codes
* ``account_migration`` — guided import from prior platform
* ``parent_link_child`` — guardian-to-student link with verification

Each writer is intentionally a thin bridge: it captures wizard answers
into ``school.settings`` (or actor-scoped meta when no school context),
and where a canonical service exists, delegates the real action to it.
The legacy views remain wired so in-flight users are not disrupted; new
entry points use the Unified Wizard engine.

CLAUDE.md constraints honored:

* No hardcoded role strings — option lists use tokens / TextChoices.
* No money_float — n/a, no money here.
* Tenant queryset safety — writers only touch the school they receive.
* PII sanitization — payloads go through ``_coerce_for_json``.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.setup_studio.wizard_resolvers import (
    _default_cockpit_writer,
    _write_to_site_settings,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 1. super_create_school — operator-side provisioning
# ============================================================================


def list_country_choices_for_wizard(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Return country choices honoring the existing GlobalGeoCatalog."""
    try:
        from apps.registries.services import list_country_choices  # local import: heavy module

        rows = list_country_choices() or []
    except Exception as exc:  # noqa: BLE001 — resolver isolation
        logger.warning("country choices resolver failed: %s", exc)
        return []
    out = []
    for row in rows:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        out.append({
            "value": code,
            "label_token": row.get("name") or code,
            "metadata": {"alpha3": row.get("code_alpha3") or "", "timezone": row.get("timezone") or ""},
        })
    return out


def list_education_template_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Education template catalog — falls back to a stable 5-entry list."""
    fallback = [
        {"value": "BRITISH_IGCSE", "label_token": "British / IGCSE", "metadata": {}},
        {"value": "WAEC", "label_token": "West African (WAEC)", "metadata": {}},
        {"value": "FRANCOPHONE_BAC", "label_token": "Francophone (Bac)", "metadata": {}},
        {"value": "VOCATIONAL", "label_token": "Vocational / Trade", "metadata": {}},
        {"value": "IB", "label_token": "International Baccalaureate", "metadata": {}},
    ]
    try:
        from apps.siteconfig.education_profile_engine import list_template_catalog

        rows = list_template_catalog(country_code=None, sub_system=None, limit=8) or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("template catalog resolver fallback: %s", exc)
        return fallback
    if not rows:
        return fallback
    return [
        {"value": r.get("code"), "label_token": r.get("name") or r.get("code"), "metadata": {"description": r.get("description") or ""}}
        for r in rows
        if r.get("code")
    ]


def write_super_create_school_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Per-step writer; provisioning happens at the final step via the existing API.

    Step 1 (identity), Step 2 (region), Step 3 (branding) all cache to platform-runtime
    operator scratch settings so the eventual POST to ``super:api_create_school`` reads
    the JSON-wizard collected state. We don't side-effect on intermediate steps.
    """
    if step_key == "review_and_provision":
        # Final step: delegate to the canonical service; never duplicate provisioning logic here.
        try:
            from apps.schools.super_views_helpers import canonical_country_alpha2  # noqa: F401  — anchor import keeps boundary
        except ImportError as exc:
            logger.warning("super_create_school provisioning anchor unavailable: %s", exc)
        # The actual create happens in ``apps.schools.super_views_create_school_wizard``
        # via the POSTed JS form; we record the wizard completion intent for audit.
        logger.info("wizard_complete_intent wizard=%s actor=%s", wizard_key, actor_user_id)
        return

    # Intermediate steps land at platform-runtime scratch (no school yet — we're CREATING one)
    if school is None:
        # No tenant context yet; nothing to persist to school.settings.
        # Operator scratch storage is held by the existing view; engine just validates inputs.
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# 2. custom_domain_setup — tenant CNAME + verification
# ============================================================================


def write_custom_domain_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Capture the requested domain + verify intent into tenant settings.

    The actual ``CustomDomain`` record creation + DNS-token mint remain in
    ``apps.siteconfig.views.custom_domain_wizard`` because that view also
    streams the verification check. We persist the wizard's collected
    answer so the legacy view can read it on re-entry.
    """
    if school is None:
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)

    if step_key == "verify":
        # Best-effort delegation to the canonical service if available
        try:
            from apps.siteconfig.services_custom_domain import schedule_dns_check  # type: ignore

            domain = (payload.get("domain") or "").strip().lower()
            if domain:
                schedule_dns_check(school=school, domain=domain)
        except Exception as exc:  # noqa: BLE001
            logger.debug("custom_domain schedule_dns_check delegation skipped: %s", exc)


# ============================================================================
# 3. mfa_setup — per-account TOTP enrollment + recovery codes
# ============================================================================


def list_mfa_channel_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """MFA verification channels for the ``choose_channel`` step.

    Values MUST match the step's declarative ``branches`` keys
    (``totp`` / ``sms`` / ``passkey``) so the engine routes to the right
    follow-up step. Labels are human English (the established label_token
    convention) — no hardcoded role strings, no secret material.
    """
    return [
        {
            "value": "totp",
            "label_token": "Authenticator app (recommended)",
            "metadata": {"hint": "Google Authenticator, Authy, 1Password, etc."},
        },
        {
            "value": "sms",
            "label_token": "Text message (SMS)",
            "metadata": {"hint": "A 6-digit code sent to your phone."},
        },
        {
            "value": "passkey",
            "label_token": "Passkey / security key",
            "metadata": {"hint": "Fingerprint, face, or a hardware key."},
        },
    ]


def write_mfa_setup_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """MFA setup is account-scoped; we persist completion timestamps only.

    Secret material (TOTP secret, recovery codes) lives in the existing
    ``accounts/MFAEnrollment`` model. The wizard captures only the user's
    chosen channel (TOTP / SMS / passkey) plus the acceptance flag.
    """
    if school is None:
        # account-level wizard: nothing tenant-scoped to write
        logger.info("mfa_setup step=%s actor=%s payload_keys=%s",
                    step_key, actor_user_id, sorted(payload.keys()))
        return
    safe_payload = {k: v for k, v in payload.items() if k not in {"secret", "totp_secret", "recovery_codes"}}
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=safe_payload, actor_user_id=actor_user_id)


# ============================================================================
# 4. account_migration — guided import from prior platform
# ============================================================================


def list_migration_source_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Source-system choices for migration. Mirrors Migration Cloud canonical headers domains."""
    return [
        {"value": "powerschool", "label_token": "PowerSchool", "metadata": {"vendor_tier": "tier1"}},
        {"value": "blackbaud", "label_token": "Blackbaud", "metadata": {"vendor_tier": "tier1"}},
        {"value": "veracross", "label_token": "Veracross", "metadata": {"vendor_tier": "tier1"}},
        {"value": "alma", "label_token": "Alma", "metadata": {"vendor_tier": "tier2"}},
        {"value": "facts", "label_token": "FACTS / RenWeb", "metadata": {"vendor_tier": "tier2", "write_blocked": True}},
        {"value": "skyward", "label_token": "Skyward", "metadata": {"vendor_tier": "tier3", "write_blocked": True}},
        {"value": "csv_canonical", "label_token": "Canonical CSV (manual export)", "metadata": {"vendor_tier": "manual"}},
        {"value": "other", "label_token": "Other / Not listed", "metadata": {"vendor_tier": "manual"}},
    ]


def write_account_migration_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Capture migration source + scope; actual ingest stays in Migration Cloud."""
    if school is None:
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)

    if step_key == "kick_off":
        try:
            from apps.migration_cloud.services.intake_init import bootstrap_migration_bundle  # type: ignore

            bundle_id = bootstrap_migration_bundle(school=school, source=payload.get("source"), actor_id=actor_user_id)
            if bundle_id:
                _write_to_site_settings(school, f"wizards.{wizard_key}.bundle_id", str(bundle_id))
        except Exception as exc:  # noqa: BLE001
            logger.debug("account_migration bootstrap delegation skipped: %s", exc)


# ============================================================================
# 5. parent_link_child — guardian-to-student link with verification
# ============================================================================


def list_relationship_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Family relationship choices. Token-only — no hardcoded role strings."""
    return [
        {"value": "mother", "label_token": "Mother", "metadata": {}},
        {"value": "father", "label_token": "Father", "metadata": {}},
        {"value": "guardian", "label_token": "Legal guardian", "metadata": {}},
        {"value": "grandparent", "label_token": "Grandparent", "metadata": {}},
        {"value": "other_relative", "label_token": "Other relative", "metadata": {}},
        {"value": "caregiver", "label_token": "Caregiver / kin", "metadata": {}},
    ]


def write_parent_link_child_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Capture admission number + relationship; the canonical link service performs the bind.

    Sensitive lookup (admission number) is logged hash-only — never raw.
    """
    if school is None:
        return

    safe_payload = dict(payload or {})
    if "admission_number" in safe_payload:
        adm = str(safe_payload["admission_number"] or "")
        if adm:
            import hashlib

            safe_payload["admission_number_hash"] = hashlib.sha256(adm.encode("utf-8")).hexdigest()[:16]
        safe_payload.pop("admission_number", None)

    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=safe_payload, actor_user_id=actor_user_id)

    if step_key == "confirm_link":
        try:
            from apps.accounts.services_link_child import link_guardian_to_student  # type: ignore

            link_guardian_to_student(
                school=school,
                actor_user_id=actor_user_id,
                admission_number=payload.get("admission_number"),
                relationship=payload.get("relationship"),
                preferred_contact=payload.get("preferred_contact"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("parent_link_child service delegation skipped: %s", exc)


# ============================================================================
# Shared option resolvers used by multiple wizards
# ============================================================================


def list_yes_no_with_reason(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "yes", "label_token": "Yes", "metadata": {}},
        {"value": "no", "label_token": "No", "metadata": {}},
    ]


# ============================================================================
# 6. teacher_self_onboarding — self-service teacher registration (v4.00.5)
# ============================================================================


def write_teacher_self_onboarding_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Capture self-onboarding answers; final creation delegates to the existing
    portal handler when present so the legacy view's transaction semantics + email
    uniqueness check are preserved.
    """
    safe_payload = {k: v for k, v in (payload or {}).items() if k not in {"password", "password1", "password2"}}
    if school is None:
        logger.info(
            "teacher_self_onboarding step=%s actor=%s field_count=%d",
            step_key, actor_user_id, len(safe_payload),
        )
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=safe_payload, actor_user_id=actor_user_id)

    if step_key == "profile_photo":
        try:
            from apps.portal.services_teacher_onboarding import create_teacher_from_wizard  # type: ignore

            create_teacher_from_wizard(school=school, wizard_payload=safe_payload, actor_user_id=actor_user_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("teacher_self_onboarding create delegation skipped: %s", exc)


# ============================================================================
# 7. student_self_onboarding — self-service student registration (v4.00.5)
# ============================================================================


def write_student_self_onboarding_step(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Capture student-self-onboarding answers. Sensitive fields (DOB) are hash-only.

    Final user/profile creation delegates to the existing portal handler when present.
    """
    safe_payload = {k: v for k, v in (payload or {}).items() if k not in {"password", "password1", "password2", "date_of_birth"}}
    if "date_of_birth" in (payload or {}):
        import hashlib

        dob = str(payload.get("date_of_birth") or "")
        if dob:
            safe_payload["date_of_birth_hash"] = hashlib.sha256(dob.encode("utf-8")).hexdigest()[:16]
    if school is None:
        logger.info(
            "student_self_onboarding step=%s actor=%s field_count=%d",
            step_key, actor_user_id, len(safe_payload),
        )
        return
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=safe_payload, actor_user_id=actor_user_id)

    if step_key == "profile_photo":
        try:
            from apps.portal.services_student_onboarding import create_student_from_wizard  # type: ignore

            create_student_from_wizard(school=school, wizard_payload=safe_payload, actor_user_id=actor_user_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("student_self_onboarding create delegation skipped: %s", exc)
