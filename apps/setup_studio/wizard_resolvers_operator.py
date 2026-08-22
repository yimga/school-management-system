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

    # The domain may arrive on the entry step (value=) or the verify step (domain=).
    # schedule_dns_check is idempotent (get_or_create), so calling on either is safe.
    if step_key in ("domain_entry", "verify"):
        try:
            from apps.siteconfig.services_custom_domain import schedule_dns_check  # type: ignore

            domain = (payload.get("domain") or payload.get("value") or "").strip().lower()
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


def list_migration_scope_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """Canonical import domains for select_scope — platform-wide, not per-tenant."""
    from apps.setup_studio.migration_scope import build_migration_scope_choices

    return build_migration_scope_choices()


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

    if step_key == "select_source":
        source = payload.get("value") or payload.get("source")
        if source:
            _write_to_site_settings(school, "migration_cloud.wizard_source", str(source))
    elif step_key == "select_scope":
        raw = payload.get("value") or payload.get("values") or []
        if isinstance(raw, str):
            raw = [raw]
        domains = [str(v).strip() for v in raw if str(v).strip()]
        if domains:
            import json

            _write_to_site_settings(school, "migration_cloud.wizard_scope_domains", json.dumps(domains))
    elif step_key == "review_mapping":
        # Persist the field-vector mapping into the Migration Cloud bucket + bundle.
        from apps.migration_cloud.wizard_pipeline_kernel import apply_field_mapping

        apply_field_mapping(school=school, payload=payload, actor_user_id=actor_user_id)
    elif step_key == "kick_off":
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


# ============================================================================
# 8. academic_year_setup — create AcademicYear + terms (batch 1731)
# ============================================================================


def write_academic_year_setup(
    *,
    school: Any,
    wizard_key: str,
    step_key: str,
    payload: dict[str, Any],
    actor_user_id: int | None,
) -> None:
    """Create or update the school's active academic year and seed terms idempotently."""
    if school is None or step_key != "year_dates":
        return
    from datetime import date, timedelta

    from django.db import transaction

    from apps.academics.models import AcademicYear, Term

    data = payload or {}
    name = str(data.get("name") or "").strip()
    start_raw = data.get("start_date")
    end_raw = data.get("end_date")
    try:
        term_count = max(1, min(6, int(data.get("term_count") or 3)))
    except (TypeError, ValueError):
        term_count = 3
    if not name or not start_raw or not end_raw:
        logger.warning("academic_year_setup missing required fields school=%s", getattr(school, "pk", None))
        return
    if hasattr(start_raw, "isoformat"):
        start_date = start_raw
    else:
        start_date = date.fromisoformat(str(start_raw)[:10])
    if hasattr(end_raw, "isoformat"):
        end_date = end_raw
    else:
        end_date = date.fromisoformat(str(end_raw)[:10])

    # Checked here because the wizard engine validates fields one at a time and
    # has no way to express a rule spanning two of them. Without this the first
    # objection comes from the database as
    # "CHECK constraint failed: academicyear_end_after_start", which is true but
    # is not a sentence anyone should be shown.
    if end_date <= start_date:
        raise ValueError(
            f"Academic year end date ({end_date}) must fall after its start date "
            f"({start_date})."
        )

    with transaction.atomic():
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            name=name,
            defaults={
                "start_date": start_date,
                "end_date": end_date,
                "is_active": True,
            },
        )
        if ay.start_date != start_date or ay.end_date != end_date:
            ay.start_date = start_date
            ay.end_date = end_date
            ay.is_active = True
            ay.save(update_fields=["start_date", "end_date", "is_active"])
        AcademicYear.objects.filter(school=school).exclude(pk=ay.pk).update(is_active=False)

        months_per_term = 12 // term_count
        for i in range(term_count):
            t_start = date(
                start_date.year + ((start_date.month - 1 + i * months_per_term) // 12),
                ((start_date.month - 1 + i * months_per_term) % 12) + 1,
                1,
            )
            if i == term_count - 1:
                t_end = end_date
            else:
                next_month = ((start_date.month - 1 + (i + 1) * months_per_term) % 12) + 1
                next_year = start_date.year + ((start_date.month - 1 + (i + 1) * months_per_term) // 12)
                t_end = date(next_year, next_month, 1) - timedelta(days=1)
            Term.objects.get_or_create(
                academic_year=ay,
                name=f"Term {i + 1}",
                defaults={"start_date": t_start, "end_date": t_end},
            )


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
            # COPPA/children's-privacy classification at the ONE point raw DOB is
            # available. This is an operator/school-mediated flow, so the consent
            # basis is SCHOOL_AUTHORIZATION (16 CFR §312.5(a)(1) school-as-agent).
            # Only the coarse minor flag + age band + basis are forwarded — the
            # raw DOB is dropped from safe_payload above (data minimisation) and
            # is never persisted or logged.
            from apps.compliance.childrens_privacy import (
                ConsentBasis,
                derive_age,
                evaluate_coppa_gate,
            )

            _coppa = evaluate_coppa_gate(
                age=derive_age(dob),
                consent_basis=ConsentBasis.SCHOOL_AUTHORIZATION,
            )
            safe_payload["is_minor"] = bool(_coppa.is_minor)
            safe_payload["coppa_age_band"] = _coppa.age_band
            safe_payload["coppa_consent_basis"] = ConsentBasis.SCHOOL_AUTHORIZATION.value
            if _coppa.is_minor:
                logger.info(
                    "coppa.minor_account_provisioned school=%s actor=%s basis=%s band=%s",
                    getattr(school, "pk", None),
                    actor_user_id,
                    ConsentBasis.SCHOOL_AUTHORIZATION.value,
                    _coppa.age_band,
                )
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


# ============================================================================
# 6. edge_location_onboarding — turnkey sovereign box / edge site deployment
# ============================================================================
#
# A school that wants an on-premise box has to make about six decisions and then
# translate them into an .env, a terminator config and an ordered procedure. Done
# by hand, the translation is where the mistakes live -- a missing IP in the
# certificate, an origin left on http://, a certificate mode that no public CA
# can ever deliver for a LAN address.
#
# The wizard collects the decisions; ``apps.schools.edge_onboarding`` does the
# translation as a pure function. Nothing here invents a value: an address the
# school has not decided yet stays empty and the generated plan says so, because
# a plan that guesses at an address is worse than one that admits a gap.


def list_edge_tls_mode_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """The four certificate postures, with the trade-off stated in each label.

    Deliberately offers all four rather than hiding the ones that cannot work for
    this school's addresses: the options resolver does not receive earlier answers,
    so filtering here would have to guess. Instead the labels carry the constraint
    and ``build_edge_plan`` reports the combination as blocking, with the reason,
    on the review step -- where the school can see it next to everything else.
    """
    from apps.schools import edge_tls

    return [
        {
            "value": edge_tls.MODE_SELF_SIGNED,
            "label_token": "The box issues its own certificate",
            "metadata": {
                "hint": (
                    "No internet, domain or cost. Install the box CA once per device. "
                    "Works at a LAN address or an IP. This is the usual choice."
                ),
                "recommended": True,
            },
        },
        {
            "value": edge_tls.MODE_PROVIDED,
            "label_token": "We supply certificate files from our own CA",
            "metadata": {
                "hint": (
                    "For schools that already run an internal certificate authority. "
                    "No PUBLIC CA will issue for a .lan name or a private IP, so this "
                    "means your organisation's own CA, whose root still has to be on "
                    "every device."
                ),
            },
        },
        {
            "value": edge_tls.MODE_ACME,
            "label_token": "A public certificate authority, renewed automatically",
            "metadata": {
                "hint": (
                    "Needs a real public domain name pointing at the box and reachable "
                    "from the internet. Impossible for a box only reachable at a LAN "
                    "address -- and nothing to install on devices when it is possible."
                ),
            },
        },
        {
            "value": edge_tls.MODE_OFF,
            "label_token": "Plain HTTP for now",
            "metadata": {
                "hint": (
                    "Login works, but offline PIN / local mode cannot be enabled on ANY "
                    "browser: plain HTTP is not a secure context. Reversible at any time."
                ),
            },
        },
    ]


def list_edge_mobility_choices(*, request: Any, school: Any) -> list[dict[str, Any]]:
    """How likely is this box to move?

    This is not idle curiosity. It decides how loudly the plan talks about
    exporting the box CA, which is the single irreversible mistake available in
    this whole flow: lose it and every device that trusted the box must be
    physically revisited.
    """
    from apps.schools import edge_onboarding

    return [
        {
            "value": edge_onboarding.MOVE_NEVER,
            "label_token": "It stays where it is installed",
            "metadata": {"hint": "Still back up the box CA -- hardware fails too."},
        },
        {
            "value": edge_onboarding.MOVE_WITHIN_SITE,
            "label_token": "It may move room, or change IP",
            "metadata": {"hint": "A reissue covers this; devices are untouched."},
        },
        {
            "value": edge_onboarding.MOVE_BETWEEN_SITES,
            "label_token": "It may move between campuses",
            "metadata": {"hint": "Plan for the CA bundle to travel with it."},
        },
        {
            "value": edge_onboarding.MOVE_BETWEEN_COUNTRIES,
            "label_token": "It may move to another country",
            "metadata": {
                "hint": (
                    "Adds data-residency, timezone and clock steps -- a box whose RTC "
                    "dies in transit rejects its own certificate."
                )
            },
        },
    ]


#: Wizard step key -> the key ``build_edge_plan`` understands. Keeping the mapping
#: explicit means renaming a step cannot silently drop an answer out of the plan.
_EDGE_STEP_TO_ANSWER: dict[str, str] = {
    "tls_choice": "tls_mode",
    "acme_contact": "acme_email",
    "certificate_source": "provided_source",
    "mobility": "mobility",
}

#: The one structured_form step carries two answers at once, keyed by field name
#: rather than the usual "value". Kept separate so the single-value path below
#: stays a single, obvious rule.
_EDGE_FORM_FIELDS: tuple[str, ...] = ("site_name", "addresses")


def write_edge_location_onboarding_step(
    *,
    school: Any,
    wizard_key: str,
    step_key: str,
    payload: dict[str, Any],
    actor_user_id: int | None,
) -> None:
    """Capture the answer, and on review, build the deployable plan.

    The plan is NOT stored as a second copy of the answers. It is a pure function
    of them, so persisting it would create a way for the two to disagree -- and
    the stale one always wins an argument with an operator standing at the box.
    """
    _default_cockpit_writer(
        school=school,
        wizard_key=wizard_key,
        step_key=step_key,
        payload=payload,
        actor_user_id=actor_user_id,
    )

    if school is not None:
        if step_key == "site_and_addresses":
            for field_name in _EDGE_FORM_FIELDS:
                field_value = payload.get(field_name)
                if field_value not in (None, ""):
                    _write_to_site_settings(
                        school, f"edge_onboarding.{field_name}", field_value
                    )
        else:
            answer_key = _EDGE_STEP_TO_ANSWER.get(step_key)
            if answer_key:
                value = payload.get("value")
                if value is None:
                    value = payload.get(answer_key)
                if value is not None:
                    # Positional, and the dotted path NESTS: this lands at
                    # school.settings["edge_onboarding"][answer_key].
                    _write_to_site_settings(
                        school, f"edge_onboarding.{answer_key}", value
                    )

    if step_key != "review":
        return

    answers = _collect_edge_answers(school)
    from apps.setup_studio.wizard_resolvers import _try_domain_integration

    _try_domain_integration(
        "apps.schools.edge_onboarding",
        "record_edge_plan",
        school=school,
        answers=answers,
        actor_user_id=actor_user_id,
    )


def _collect_edge_answers(school: Any) -> dict[str, Any]:
    """Read back what the school answered, tolerating a partly-finished wizard.

    Returns only what was actually answered. A missing address stays missing so
    the generated plan can say "you have not decided this yet" rather than
    inventing something that will not match the box.
    """
    answers: dict[str, Any] = {}
    settings_blob = getattr(school, "settings", None) or {}
    if not isinstance(settings_blob, dict):
        return answers
    # _write_to_site_settings nests on dots, so the answers live in a sub-dict.
    bucket = settings_blob.get("edge_onboarding")
    if not isinstance(bucket, dict):
        return answers
    for answer_key in set(_EDGE_STEP_TO_ANSWER.values()) | set(_EDGE_FORM_FIELDS):
        stored = bucket.get(answer_key)
        if stored not in (None, ""):
            answers[answer_key] = stored
    return answers
