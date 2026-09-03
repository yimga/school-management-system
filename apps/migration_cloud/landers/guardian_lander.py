"""Guardian lander — persists canonical guardian rows + the student↔guardian link.

Completeness fix (2026-07-09): ``StudentGuardian.guardian_user`` is a REQUIRED
FK to the platform ``User`` — the old upsert never set it (and keyed on a
``last_name`` field the model doesn't have), so every guardian row from a
foreign-SIS import OR an inter-school transfer quarantined and parents lost
portal access at the target. The lander now RESOLVES the guardian's user:

1. ``guardian_user_ref`` (username) — internal transfers carry the guardian's
   platform identity, so the SAME account is re-linked at the target and the
   parent's portal access (scoped via ``StudentGuardian``) survives the move.
2. ``email`` — an existing platform user with that email is re-linked.
3. EXACT phone + matching name (Tier 1c dedup) — the same guardian
   re-appearing for a sibling under an absent/inconsistent email links to the
   account already carrying that phone, guardrailed by a name-score floor and
   a single-distinct-match rule so a shared household number never merges two
   people. School-scoped.
4. Provisioning — no matching user: a PARENT-role account is created with an
   UNUSABLE password (activation rides the existing guardian-invite /
   password-reset flow — the lander never mints a credential). When the row
   carries no email, a reserved, UNDELIVERABLE ``@unclaimed.invalid`` address
   is minted from a stable identity seed, so the guardian still reaches the
   Guardians directory attached to the right student instead of being lost,
   while remaining unable to log in or receive mail. That seed is resolved
   before provisioning, so a re-apply or a sibling row reuses the account.
5. No ref match, no phone match, no email AND no name → nothing identifies
   the person, so the row quarantines with a precise reason.

Canonical row shape::

    {
        "student_external_id": "PS-1029",
        "guardian_external_id": "g-42",
        "first_name": "Ama", "last_name": "Mensah",
        "email": "ama@example.com", "phone": "+233...",
        "relationship": "MOTHER" | "Mother",
        "is_primary": "true",
        "guardian_user_ref": "ama.mensah",   # internal transfers only
        # Consent / visibility / contact-preference (carried on transfer so
        # the target never resets them to model defaults). Booleans arrive as
        # "true"/"false"; an ABSENT column leaves the target value untouched.
        "receives_email": "false", "receives_sms": "true",
        "receives_whatsapp": "false",
        "can_view_results": "false", "can_view_finance": "true",
        "preferred_contact": "SMS", "whatsapp_number": "+233...",
        "address": "12 Independence Ave",
    }
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

from .base import Lander, LanderContext, LanderError, LanderResult, register
from ._helpers import normalize_canonical_row, record_row_error, student_name_from_row
from .reason_codes import INVALID_REF, LANDER_ERROR, MISSING_REQUIRED


class GuardianLander(Lander):
    domain = "guardians"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from django.contrib.auth import get_user_model

            from apps.people.models import StudentGuardian, StudentProfile
        except ImportError as exc:
            raise LanderError(
                f"GuardianLander could not import StudentGuardian / StudentProfile: {exc!s}"
            ) from exc
        User = get_user_model()

        result = LanderResult()
        guardian_model_fields = {f.name for f in StudentGuardian._meta.get_fields()}
        student_model_fields = {f.name for f in StudentProfile._meta.get_fields()}
        relationship_values = _relationship_values(StudentGuardian)

        for row in canonical_rows:
            row = normalize_canonical_row("guardians", row, ctx)
            student_external_id = (
                row.get("student_external_id") or row.get("external_id") or ""
            ).strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            user_ref = (row.get("guardian_user_ref") or "").strip()
            email = (row.get("email") or "").strip()
            if not (student_external_id or student_name_from_row(row)) or not (
                first_name or last_name or user_ref
            ):
                record_row_error(
                    result,
                    row,
                    f"Missing student_external_id or identity in guardian row {row!r}",
                    reason_code=MISSING_REQUIRED,
                )
                continue

            student_lookup_field = _student_lookup(student_model_fields)
            try:
                from ._helpers import resolve_student

                student = resolve_student(
                    ctx=ctx,
                    student_model=StudentProfile,
                    lookup_field=student_lookup_field,
                    external_id=student_external_id,
                    row=row,
                )
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"student lookup failed for {student_external_id}: {type(exc).__name__}",
                    reason_code=LANDER_ERROR,
                )
                continue
            if student is None:
                record_row_error(
                    result,
                    row,
                    f"No student with {student_lookup_field}={student_external_id!r} for guardian",
                    reason_code=INVALID_REF,
                )
                continue

            guardian_user, provision_reason = _resolve_or_provision_user(
                User=User,
                user_ref=user_ref,
                email=email,
                phone=(row.get("phone") or "").strip(),
                first_name=first_name,
                last_name=last_name,
                school=ctx.school,
                dry_run=ctx.dry_run,
            )
            if guardian_user is None and not (ctx.dry_run and provision_reason == ""):
                record_row_error(
                    result,
                    row,
                    f"guardian for {student_external_id}: {provision_reason or 'no linkable user'}",
                    reason_code=INVALID_REF,
                )
                continue

            relationship = (row.get("relationship") or "").strip().upper()
            defaults = {
                "email": email,
                "phone": (row.get("phone") or "").strip(),
                "relationship": relationship if relationship in relationship_values else "",
                "is_primary": _truthy(row.get("is_primary")),
            }
            defaults = {
                k: v
                for k, v in defaults.items()
                if k in guardian_model_fields and v not in (None, "")
            }

            # Consent / visibility / contact-preference fidelity: carry the
            # source values so a transfer/import never resets an opted-out
            # parent's channels, a restricted guardian's results access, or a
            # granted finance view to the model default. A present column with
            # an explicit false MUST persist False — distinct from an ABSENT
            # column, which leaves the target value untouched. Applied AFTER
            # the drop-empty filter above so a legitimate False is not dropped.
            for bool_field in (
                "receives_email",
                "receives_sms",
                "receives_whatsapp",
                "can_view_results",
                "can_view_finance",
            ):
                raw = row.get(bool_field)
                if bool_field in guardian_model_fields and raw not in (None, ""):
                    defaults[bool_field] = _truthy(raw)
            preferred = (row.get("preferred_contact") or "").strip().upper()
            if (
                "preferred_contact" in guardian_model_fields
                and preferred in _preferred_contact_values(StudentGuardian)
            ):
                defaults["preferred_contact"] = preferred
            for text_field in ("whatsapp_number", "address"):
                text_val = (row.get(text_field) or "").strip()
                if text_field in guardian_model_fields and text_val:
                    defaults[text_field] = text_val

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                from ._helpers import (
    record_id_mapping,
                    upsert_with_conflict_detection,
                )
                legacy_id = f"{student_external_id}:{user_ref or email}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="guardians", model=StudentGuardian,
                    lookup={
                        "student": student,
                        "guardian_user": guardian_user,
                    },
                    defaults=defaults,
                    legacy_id=legacy_id,
                )
                if preserved:
                    # Operator resolved this guardian-link conflict as PRESERVE —
                    # keep the existing relationship/contact, don't overwrite.
                    result.skipped += 1
                    record_id_mapping(
                        ctx=ctx, legacy_id=legacy_id,
                        canonical_obj=obj, domain="guardians",
                    )
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx, legacy_id=legacy_id,
                    canonical_obj=obj, domain="guardians",
                )
                try:
                    from apps.migration_cloud.guardian_directory import (
                        ensure_school_membership,
                    )

                    parent_role = User.Role.PARENT
                    ensure_school_membership(
                        user=guardian_user,
                        school=ctx.school,
                        role=parent_role,
                    )
                except Exception:  # noqa: BLE001 — membership is additive; link already landed
                    pass
            except Exception as exc:  # noqa: BLE001
                record_row_error(
                    result,
                    row,
                    f"guardian upsert failed: {type(exc).__name__}: {exc}",
                    reason_code=LANDER_ERROR,
                )
        return result


def _resolve_or_provision_user(
    *, User, user_ref: str, email: str, phone: str = "",
    first_name: str, last_name: str, school: Any = None, dry_run: bool,
):
    """Return ``(user, reason)`` — reason is set only when user is None.

    Resolution order: platform identity (username, internal transfers) →
    email → PHONE + name (phone-first dedup) → provision-with-unusable-password
    (email required). Existing users are NEVER mutated (role, names, credentials
    stay theirs).

    The email rung is school-scoped, like the phone rung below it: ``User`` is a
    SHARED public-schema table, so an unscoped email match let a bundle uploaded
    by school A bind school B's account to an A guardian row (and, via
    ``ensure_school_membership``, into A's parent directory). A match belonging
    only to another tenant now HOLDS the row for a human instead.
    """
    from ._helpers import FOREIGN_SCHOOL_MATCH_REASON, user_is_linkable_to_school

    if user_ref:
        user = User.objects.filter(username=user_ref).first()
        if user is not None:
            return user, ""
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            if not user_is_linkable_to_school(user, school):
                return None, FOREIGN_SCHOOL_MATCH_REASON.format(email=email)
            return user, ""
    # Phone-first dedup: many regions this platform serves are phone-primary and
    # email-rare, so the SAME guardian re-appearing for a sibling under an
    # inconsistent / absent email would otherwise be re-provisioned as a
    # DUPLICATE account (or, with no email, quarantined and lost). Link to the
    # existing guardian account carrying this EXACT phone + a matching name
    # instead. Guardrailed (name-score floor + single distinct match) so a
    # shared household phone can never merge two different guardians.
    matched = _match_guardian_user_by_phone(phone, first_name, last_name, school)
    if matched is not None:
        return matched, ""
    if not email:
        if not (first_name or last_name):
            return None, (
                "no guardian_user_ref / phone match and no email or name to "
                "resolve or provision a user"
            )
        from apps.accounts.email_delivery_policy import synthetic_unclaimed_email

        school_pk = getattr(school, "pk", "") or ""
        seed = (
            f"{school_pk}|{(phone or '').strip().lower()}|"
            f"{(first_name or '').casefold()}|{(last_name or '').casefold()}"
        )
        email = synthetic_unclaimed_email(seed)
        # The seed is identity-derived (school + phone + name), so the SAME
        # guardian always mints the SAME address. Resolve that address before
        # provisioning: without this lookup a re-apply of the same bundle, or a
        # second SIBLING row for the same guardian, mints a DUPLICATE unclaimed
        # account (identical email, _free_username merely suffixing the
        # username) plus a second StudentGuardian link -- the very duplicate
        # this rung's stable seed exists to prevent. School-safe without a
        # linkability check: the school pk is IN the seed, so a hit can only be
        # an account this lander minted for THIS school.
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            return existing, ""
    if dry_run:
        return None, ""  # would provision — preview counts it as landable
    username = _free_username(User, email)
    # Savepoint-wrap provisioning: under the forced-atomic finance apply a raw
    # create_user IntegrityError (concurrent apply racing the same email-derived
    # username) would mark the WHOLE connection needs_rollback, aborting the
    # entire finance-bearing bundle instead of quarantining this one guardian.
    from ._helpers import row_savepoint

    with row_savepoint():
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        if hasattr(user, "role") and hasattr(User, "Role"):
            user.role = User.Role.PARENT
        user.set_unusable_password()
        user.save()
    return user, ""


def _match_guardian_user_by_phone(phone: str, first_name: str, last_name: str, school: Any):
    """Phone-first guardian dedup: return the existing guardian ``User`` whose
    account already carries this EXACT ``phone`` on a ``StudentGuardian`` link
    AND whose name matches the incoming one, else ``None``.

    Safe against the shared-household-phone case (mum + dad on one number):
      * the incoming phone must be present AND matched exactly;
      * the deterministic name score must clear
        ``migration_cloud.dedup.autolink_min_score`` — so only the guardian
        whose NAME matches links, not everyone on that phone;
      * exactly ONE distinct user may clear the bar (a genuine name+phone
        collision → >1 → no auto-link, provision a fresh account instead).
    Scoped to the bundle's school so it never reaches across tenants.
    """
    phone = (phone or "").strip()
    if not phone or not (first_name or last_name):
        return None
    try:
        from apps.people.ai_dedup import deterministic_score
        from apps.people.models import StudentGuardian
    except Exception:  # noqa: BLE001 — dedup helper / model absent → no auto-link
        return None
    from apps.migration_cloud import defaults as mc_defaults

    try:
        min_score = float(mc_defaults.get("migration_cloud.dedup.autolink_min_score"))
    except Exception:  # noqa: BLE001 — unknown/blank key → conservative default
        min_score = 0.95
    scope: dict[str, Any] = {}
    if school is not None:
        scope["student__school"] = school
    links = StudentGuardian.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context; scoped by student__school
        phone=phone, **scope,
    ).select_related("guardian_user")[:25]
    matched: dict[Any, Any] = {}
    for link in links:
        u = getattr(link, "guardian_user", None)
        if u is None:
            continue
        score = deterministic_score(
            {"first_name": first_name, "last_name": last_name},
            {
                "first_name": getattr(u, "first_name", ""),
                "last_name": getattr(u, "last_name", ""),
            },
        )
        if score >= min_score:
            matched[u.pk] = u
    if len(matched) == 1:
        return next(iter(matched.values()))
    return None


def _free_username(User, email: str) -> str:
    base = (email.split("@", 1)[0] or "guardian")[:130]  # magic-number-allow: username-column-headroom-below-django-150-cap
    if not User.objects.filter(username=base).exists():
        return base
    digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"[:150]  # magic-number-allow: django-abstractuser-username-max-length


def _relationship_values(StudentGuardian) -> set[str]:
    try:
        field = StudentGuardian._meta.get_field("relationship")
        return {choice[0] for choice in (field.choices or ())}
    except Exception:  # noqa: BLE001 — alternate model shapes
        return set()


def _preferred_contact_values(StudentGuardian) -> set[str]:
    """Valid ``preferred_contact`` choice values, so a transfer/import never
    lands an out-of-vocabulary channel (mirrors :func:`_relationship_values`)."""
    try:
        field = StudentGuardian._meta.get_field("preferred_contact")
        return {choice[0] for choice in (field.choices or ())}
    except Exception:  # noqa: BLE001 — alternate model shapes
        return set()


def _student_lookup(available: set[str]) -> str:
    for c in ("external_id", "sis_external_id", "source_id", "admission_number"):
        if c in available:
            return c
    return "admission_number"


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t", "primary")


register("guardians", GuardianLander())
