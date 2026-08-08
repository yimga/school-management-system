"""Staff lander — persists canonical staff rows into ``apps.people.TeacherProfile``.

Completeness fix (2026-07-11): the old lander wrote ``first_name``/``last_name``/
``email``/``role`` straight onto ``TeacherProfile`` (those live on ``User``, not
the profile), keyed the upsert on ``staff_external_id`` (not a real field →
``FieldError``), and NEVER set the REQUIRED ``TeacherProfile.user`` OneToOne
(→ ``IntegrityError``). Every staff/teacher row therefore quarantined and the
imported count was pinned to 0 — the same class already fixed for guardians.

The lander now RESOLVES-or-PROVISIONS the teacher's ``User`` (role TEACHER,
unusable password — activation rides the normal invite/reset flow, no credential
is minted) exactly as ``guardian_lander`` does, then creates the
``TeacherProfile(user=…, school=…, staff_id=external_id)`` keyed on the OneToOne
user. Real profile fields (``staff_id``/``position_title``/``phone``/
``department`` FK) are written; source-only columns (``hire_date``, the raw
``role`` string) land on the DynamicFieldValue engine so nothing is lost.

Canonical row shape::

    {
        "staff_external_id": "EMP-021",
        "first_name": "Jane", "last_name": "Doe",
        "email": "jane@example.com",
        "staff_user_ref": "jane.doe",     # internal transfers only
        "role": "Teacher", "department": "Science",
        "phone": "+233...", "hire_date": "2020-09-01",
    }
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    detect_and_register_assets,
    get_or_create_named,
    mint_scoped_code,
    model_field_names,
    persist_dfv_extras,
    record_id_mapping,
    resolve_or_provision_user,
    upsert_with_conflict_detection,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register

# Canonical role SOT (Django-free module, so it is safe to import at module level
# unlike the ORM imports below). The bare "TEACHER" literal must not be inlined:
# scan_role_strings.py enforces that the token comes from here or User.Role.
from apps.platform_runtime.role_registry import ROLE_TEACHER

# OneRoster/SIS role tokens that must NEVER be provisioned as teachers.
_NON_STAFF_ROLES = {"student", "guardian", "parent", "relative"}


class StaffLander(Lander):
    domain = "staff"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from django.contrib.auth import get_user_model

            from apps.academics.models import Department
            from apps.people.models import TeacherProfile
        except ImportError as exc:
            raise LanderError(f"StaffLander could not import TeacherProfile: {exc!s}") from exc
        User = get_user_model()

        result = LanderResult()
        model_fields = model_field_names(TeacherProfile)
        # Prefer the ORM-layer SOT (User.Role TextChoices); fall back to the
        # registry constant if a swapped user model has no Role enum. Mirrors
        # guardian_lander's hasattr idiom -- neither branch inlines the token.
        teacher_role = User.Role.TEACHER if hasattr(User, "Role") else ROLE_TEACHER

        for row in canonical_rows:
            external_id = (
                row.get("staff_external_id")
                or row.get("external_id")
                or row.get("employee_id")
                or ""
            ).strip()
            first_name = (row.get("first_name") or "").strip()
            last_name = (row.get("last_name") or "").strip()
            email = (row.get("email") or "").strip()
            user_ref = (row.get("staff_user_ref") or "").strip()
            if not external_id or not (first_name or last_name or user_ref or email):
                result.quarantined += 1
                result.errors.append(f"Missing required staff fields in row {row!r}")
                continue

            # Role gate: a combined OneRoster ``users.csv`` is pre-classified to
            # ``staff`` but carries every role. NEVER provision a student/parent/
            # guardian as a teacher — skip them here (they land via their own
            # domain). Blank/teacher/admin/aide/proctor roles fall through.
            role_raw = (row.get("role") or "").strip().lower()
            if role_raw in _NON_STAFF_ROLES:
                result.skipped += 1
                continue

            if ctx.dry_run:
                result.created += 1
                continue

            try:
                # Exact employee-number dedup (strongest signal, runs FIRST): a
                # TeacherProfile already carrying this staff_id in THIS school is
                # the same person, so reuse its user and let the upsert update in
                # place — instead of provisioning a DUPLICATE account when the
                # same staffer re-appears under a different / absent email.
                # staff_id is the source SIS's stable identity key (not an
                # ambiguous shared signal like a household phone), so an exact
                # single match is a safe auto-merge.
                teacher_user = _match_staff_user_by_staff_id(
                    TeacherProfile, ctx.school, external_id
                )
                if teacher_user is not None:
                    if not _resolution_would_reach(teacher_user, user_ref, email):
                        # The strong-key match linked a user that username/email
                        # would NOT have reached (a re-import under a different /
                        # absent email) — surface it so the auto-link is never
                        # silent.
                        _record_staff_dedup_link(ctx, teacher_user, external_id, email)
                else:
                    teacher_user, reason = resolve_or_provision_user(
                        User=User,
                        username_hint=user_ref,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        role=teacher_role,
                        dry_run=ctx.dry_run,
                    )
                    if teacher_user is None:
                        result.quarantined += 1
                        result.errors.append(f"staff {external_id}: {reason or 'no linkable user'}")
                        continue

                # Optional Department FK (SET_NULL) — reuse an existing one by
                # (school, name); mint a target-scoped code on create so we never
                # reuse the source's globally-unique department code.
                department = None
                dept_name = (row.get("department") or "").strip()
                if dept_name and "department" in model_fields:
                    department, _ = get_or_create_named(
                        model=Department,
                        school=ctx.school,
                        name=dept_name,
                        create_kwargs=lambda dn=dept_name: {
                            "code": mint_scoped_code(
                                prefix="DPT", name=dn, school=ctx.school, model=Department
                            )
                        },
                        result=result,
                    )

                defaults: dict[str, Any] = {
                    "staff_id": external_id,
                    "position_title": (row.get("role") or "").strip()[:120],  # magic-number-allow: position_title CharField max_length
                    "phone": (row.get("phone") or "").strip()[:50],
                    "department": department,
                }
                if "school" in model_fields and ctx.school is not None:
                    defaults["school"] = ctx.school
                defaults = {k: v for k, v in defaults.items() if k in model_fields and v not in (None, "")}

                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="staff", model=TeacherProfile,
                    lookup={"user": teacher_user}, defaults=defaults,
                    legacy_id=external_id,
                )
                if preserved:
                    # Operator resolved this staff conflict as PRESERVE.
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="staff")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                # Source-only columns with no TeacherProfile home → DFV (no data loss).
                persist_dfv_extras(
                    ctx=ctx, entity_type="staff", entity_id=obj.pk,
                    extras={"hire_date": (row.get("hire_date") or "").strip(),
                            "source_role": (row.get("role") or "").strip()},
                    result=result,
                )
                record_id_mapping(ctx=ctx, legacy_id=external_id, canonical_obj=obj, domain="staff")
                detect_and_register_assets(ctx=ctx, legacy_id=external_id, entity_kind="staff", row=row)
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(f"staff upsert failed for {external_id}: {type(exc).__name__}: {exc}")
        return result


def _match_staff_user_by_staff_id(TeacherProfile, school: Any, external_id: str):
    """Exact employee-number dedup: return the ``User`` of an existing
    ``TeacherProfile`` in THIS school carrying this ``staff_id``, else ``None``.

    ``staff_id`` is the source SIS's stable identity key for the record (not an
    ambiguous shared signal like a household phone), so an exact match is a safe
    auto-merge. Guardrailed so it can never wrong-merge:
      * ``staff_id`` must be present AND matched exactly;
      * scoped to the bundle's school (never reaches across tenants);
      * exactly ONE distinct user may match — legacy duplicate data (>1 profile
        sharing a staff_id) is ambiguous, so don't guess; fall through to the
        normal username/email resolution and let the merge engine reconcile.
    """
    external_id = (external_id or "").strip()
    if not external_id:
        return None
    scope: dict[str, Any] = {}
    if school is not None:
        scope["school"] = school
    profiles = TeacherProfile.objects.filter(  # tenant-isolation-allow: lander runs inside schema_context; scoped by school kwarg
        staff_id=external_id, **scope,
    ).select_related("user")[:5]
    matched: dict[Any, Any] = {}
    for tp in profiles:
        u = getattr(tp, "user", None)
        if u is not None:
            matched[u.pk] = u
    if len(matched) == 1:
        return next(iter(matched.values()))
    return None


def _resolution_would_reach(user, user_ref: str, email: str) -> bool:
    """True when the normal username/email resolution would have reached THIS
    user anyway — so the staff_id auto-link is only surfaced (as a dedup link)
    when it actually prevented a different / duplicate resolution."""
    if user_ref and getattr(user, "username", "") == user_ref:
        return True
    if email and (getattr(user, "email", "") or "").strip().lower() == email.strip().lower():
        return True
    return False


def _record_staff_dedup_link(ctx, user, external_id: str, email: str) -> None:
    """Note (for operator review) that an incoming staff row was linked to an
    existing teacher account by EXACT staff_id rather than by email/username —
    so the auto-link is never silent. Best-effort; never breaks the land."""
    bundle_id = getattr(ctx, "bundle_id", None)
    if bundle_id is None:
        return
    try:
        from apps.migration_cloud.models import MigrationBundle

        bundle = MigrationBundle.objects.filter(pk=bundle_id).first()  # tenant-isolation-allow: PK lookup by internal bundle id
    except Exception:  # noqa: BLE001
        return
    if bundle is None:
        return
    try:
        summary = dict(bundle.mapping_summary or {})
        summary.setdefault("dedup_links", []).append(
            {
                "canonical_user_pk": user.pk,
                "linked_staff_id": external_id,
                "incoming_email": (email or "").strip(),
                "matched_on": "staff_id",
            }
        )
        bundle.mapping_summary = summary
        bundle.save(update_fields=["mapping_summary"])
    except Exception:  # noqa: BLE001
        return


register("staff", StaffLander())
