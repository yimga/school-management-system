"""Move a school's STAFF (login + teacher profile) between deployments.

WHY THIS EXISTS
---------------
``people.TeacherProfile.user`` is a non-nullable ``OneToOneField`` to ``accounts.User``,
and ``accounts`` is a SHARED/public-schema app. Neither of the two documented paths can
therefore land a teacher on a sovereign box:

* **Delta sync refuses it.** ``_create_from_cloud_pull`` returns 409
  ``insert_held_for_entity`` for ``teacher`` -- correctly, because creating one across the
  rail would mean the rail minting an identity. See ``docs/EDGE_SYNC_IDENTITY_HOLD.md``.

* **The tenant bundle fails outright.** ``export_tenant_bundle`` walks TENANT_APP_LABELS,
  which includes ``people``, so ``people.teacherprofile`` IS in the bundle with its
  ``user_id`` intact -- while ``accounts`` is not a tenant app, so the Users are not.
  ``import_tenant_bundle`` runs inside ``transaction.atomic()``, so the dangling FK does
  not skip the teachers: it rolls back the WHOLE tenant import and nothing lands at all.

Measured on 2026-08-29: a rebuilt box pulled 322,586 rows down and refused the same 39
teacher rows on all 687 cycles of that day.

WHAT THIS IS
------------
The explicit, operator-run provisioning step ``EDGE_SYNC_IDENTITY_HOLD.md`` says is
required: "the box submits a request, an authorized human approves it... That is a
feature, not a sync-policy change, and it must never be implicit in a bundle apply."
Running this command IS that human act. Nothing here is reachable from the sync rail.

It is pk-preserving, which is the property that matters: once the rows exist with the
same pks on both sides, ordinary delta sync converges by UPDATE-by-pk -- exactly what the
identity hold permits -- and the per-cycle skip count falls to zero.

SAFETY PROPERTIES
-----------------
* Same encrypt-then-MAC envelope, bound to the school id, as the tenant bundle. This file
  carries password hashes; it is never plaintext on disk.
* ``is_superuser`` is NEVER carried. A staff import cannot mint an administrator.
* A pk that already belongs to a DIFFERENT username on the target aborts the whole import
  rather than overwriting a local account.
* ``--reset-passwords`` lands the accounts unusable + must-change instead of carrying
  hashes, for an operator who would rather not move credential material at all.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging

from django.apps import apps as django_apps
from django.core.exceptions import FieldDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from apps.lifecycle.schema_scope import school_schema
from apps.lifecycle.tenant_dr_snapshot import (
    decrypt_blob,
    encrypt_blob,
    sign_payload,
    verify_signature,
)

logger = logging.getLogger(__name__)

BUNDLE_FORMAT = "rmc-staff-bundle/1"

# Identity + the columns a login needs to work offline. Deliberately NOT the whole model:
#
#   is_superuser  -- never. A data import must not be able to create an administrator.
#   last_login    -- per-deployment fact, not identity.
#   profile_photo -- a FileField; the bundle carries no bytes, so a copied path dangles.
#   mfa_* / legacy_* / password_strength_* / last_lockdown_at
#                 -- security POSTURE, which each deployment tracks for itself. Carrying
#                    them would import one box's lockout state onto another.
_USER_FIELDS: tuple[str, ...] = (
    "id",
    "password",
    "username",
    "first_name",
    "last_name",
    "email",
    "is_staff",
    "is_active",
    "date_joined",
    "role",
    "requires_password_change",
    "preferred_language",
    "profile_setup_completed",
)

# Optional FKs on TeacherProfile whose target may legitimately be absent on the box.
# `pay_scale` points at payroll.PayScale, which does NOT ride the delta rail, so on a
# sync-filled box it is usually missing; `department` does ride and is usually present.
# Both are nullable, so a missing target is nulled and REPORTED rather than failing the
# import -- a teacher without a pay scale is a teacher, a rolled-back import is nothing.
_NULLABLE_FK_FIELDS: tuple[str, ...] = ("department", "pay_scale", "reports_to", "merged_into")

# A FileField carries no bytes in this envelope; a copied path would dangle.
_TEACHER_SKIP_FIELDS: frozenset[str] = frozenset({"profile_photo"})


def _user_model():
    return django_apps.get_model("accounts", "User")


def _teacher_model():
    return django_apps.get_model("people", "TeacherProfile")


def _teacher_rows(school) -> list[dict]:
    """Every TeacherProfile for ``school`` as a plain dict of concrete local fields."""
    model = _teacher_model()
    names = [
        f.attname
        for f in model._meta.concrete_fields
        if f.name not in _TEACHER_SKIP_FIELDS
    ]
    return list(model.objects.filter(school=school).values(*names))


def export_staff_bundle(school) -> bytes:
    """Serialize the school's teacher logins + profiles into an encrypted, signed bundle.

    The profile read runs inside the school's OWN schema. Without that it lands on
    ``public``, which on a schema-per-tenant deployment holds a legacy copy of the
    roster -- same people, different pks, not what the tenant UI serves. See
    ``apps.lifecycle.schema_scope``.
    """
    with school_schema(school) as source_schema:
        teachers = _teacher_rows(school)
    # accounts.User is a SHARED app: it lives in `public` on every deployment, so it is
    # read on the default connection rather than through the tenant schema.
    user_ids = sorted({row["user_id"] for row in teachers if row.get("user_id")})
    users = list(_user_model().objects.filter(pk__in=user_ids).values(*_USER_FIELDS))

    payload = {
        "format": BUNDLE_FORMAT,
        "school_id": str(school.id),
        "tenant_slug": getattr(school, "slug", ""),
        "users": users,
        "teachers": teachers,
        "counts": {"users": len(users), "teachers": len(teachers)},
        # Provenance: the one fact that separates a correct export from the silent
        # `public` one. Absent in bundles written before 2026-08-31.
        "source_schema": source_schema,
    }
    raw = json.dumps(payload, cls=DjangoJSONEncoder).encode("utf-8")
    blob = encrypt_blob(gzip.compress(raw), school_id=str(school.id))
    return json.dumps(
        {
            "format": BUNDLE_FORMAT,
            "school_id": str(school.id),
            "sig": sign_payload(blob, school_id=str(school.id)),
            "blob_b64": base64.b64encode(blob).decode("ascii"),
        }
    ).encode("utf-8")


def _open_bundle(container_bytes: bytes, *, expected_school_id=None) -> dict:
    """Verify the signature and school binding BEFORE decrypting. Fail closed."""
    container = json.loads(container_bytes)
    school_id = str(container["school_id"])
    if expected_school_id is not None and str(expected_school_id) != school_id:
        raise ValueError("staff_bundle_school_mismatch")
    blob = base64.b64decode(container["blob_b64"])
    if not verify_signature(blob, container["sig"], school_id=school_id):
        raise ValueError("staff_bundle_signature_mismatch")
    payload = json.loads(gzip.decompress(decrypt_blob(blob, school_id=school_id)))
    if str(payload.get("format") or "") != BUNDLE_FORMAT:
        raise ValueError("staff_bundle_format_unknown")
    return payload


def _pk_collisions(users: list[dict]) -> list[str]:
    """pks that already belong to a DIFFERENT account on this deployment.

    ``loaddata`` semantics are "write this pk", so without this check a staff import could
    silently overwrite the box's own owner login with a teacher. Same pk + same username is
    the same person and is an ordinary update; same pk + different username is not, and is
    the one case where continuing would destroy a local account.
    """
    model = _user_model()
    incoming = {int(row["id"]): str(row["username"]) for row in users}
    problems: list[str] = []

    existing = dict(
        model.objects.filter(pk__in=list(incoming)).values_list("pk", "username")
    )
    problems += [
        f"pk {pk} is {existing[pk]!r} here but {incoming[pk]!r} in the bundle"
        for pk in sorted(existing)
        if str(existing[pk]) != incoming[pk]
    ]

    # And the same clash from the other side. `username` is unique, so a name already
    # taken by a DIFFERENT pk would fail mid-transaction on the constraint. Reporting it
    # here keeps the promise the identity hold makes about its own 409: refuse with the
    # actual reason rather than let it surface as an opaque IntegrityError.
    by_name = dict(
        model.objects.filter(username__in=list(incoming.values()))
        .values_list("username", "pk")
    )
    wanted_pk = {name: pk for pk, name in incoming.items()}
    problems += [
        f"username {name!r} is pk {by_name[name]} here but pk {wanted_pk[name]} "
        "in the bundle"
        for name in sorted(by_name)
        if by_name[name] != wanted_pk.get(name)
    ]
    return problems


def _profile_collisions(teachers: "list[dict]") -> "list[str]":
    """Users who already hold a DIFFERENT teacher profile on this deployment.

    ``TeacherProfile.user`` is a ``OneToOneField``. Landing the bundle's profile at its
    cloud pk while a box-local profile already holds that same user violates the unique
    index -- mid-transaction, as an opaque ``IntegrityError`` that rolls the whole
    import back and names no cause. Refusing with the actual reason is the entire point
    of the pk guard, and checking ``accounts.User`` alone missed this: the two sides can
    agree perfectly on USER pks (minted once, on the cloud) and still disagree on
    PROFILE pks, because each side created its own profile row locally.

    Measured on a live box 2026-08-31: 39 real staff, identical people on both sides,
    user pks matching, profile pks 28+ on the box against 2+ on the cloud.
    """
    model = _teacher_model()
    incoming: "dict[int, object]" = {}
    for row in teachers:
        user_id = row.get("user_id")
        if user_id:
            incoming[int(user_id)] = row.get("id")
    if not incoming:
        return []

    existing = dict(
        model.objects.filter(user_id__in=list(incoming)).values_list("user_id", "pk")
    )
    return [
        f"user {user_id} already holds teacher profile pk {existing[user_id]} here, but "
        f"the bundle carries that person at pk {incoming[user_id]}"
        for user_id in sorted(existing)
        if existing[user_id] != incoming[user_id]
    ]


def _all_collisions(users: "list[dict]", teachers: "list[dict]") -> "list[str]":
    """Every reason this bundle cannot be landed pk-preserving, in one list.

    One seam so the dry run and the real import can never answer differently -- the
    duplication that let the profile case ship unchecked.
    """
    return _pk_collisions(users) + _profile_collisions(teachers)


def _school_for(payload) -> object:
    """The School row this bundle is for. SHARED app, so always readable from public."""
    from apps.schools.models import School

    return School.objects.filter(pk=payload.get("school_id")).first()


def inspect_staff_bundle(container_bytes: bytes, *, expected_school_id=None) -> dict:
    """Verify a bundle and report what it WOULD land. Writes nothing.

    The seam behind ``import_tenant_staff --dry-run``. Raises the same ``ValueError``s
    the real import raises for a bad signature or the wrong school, so a dry run cannot
    pass where the import would be refused.
    """
    payload = _open_bundle(container_bytes, expected_school_id=expected_school_id)
    users = payload.get("users") or []
    teachers = payload.get("teachers") or []
    with school_schema(_school_for(payload)) as target_schema:
        collisions = _all_collisions(users, teachers)
    return {
        "school_id": payload.get("school_id", ""),
        "tenant_slug": payload.get("tenant_slug", ""),
        "users": len(users),
        "teachers": len(teachers),
        "collisions": collisions,
        "source_schema": payload.get("source_schema", ""),
        "target_schema": target_schema,
    }


def import_staff_bundle(
    container_bytes: bytes, *, expected_school_id=None, reset_passwords: bool = False
) -> dict:
    """Land the bundle's logins and teacher profiles on THIS deployment, pk-preserving.

    Transactional: any failure leaves the deployment exactly as it was.
    """
    payload = _open_bundle(container_bytes, expected_school_id=expected_school_id)
    users = payload.get("users") or []
    teachers = payload.get("teachers") or []

    # Everything below touches TENANT tables (TeacherProfile and the optional FK
    # targets), so it runs in the school's own schema. accounts.User is SHARED and
    # resolves from `public` either way, since django-tenants keeps it on the
    # search_path. On a box this is a no-op: one schema, nothing to enter.
    with school_schema(_school_for(payload)):
        collisions = _all_collisions(users, teachers)
        if collisions:
            raise ValueError(
                "staff_bundle_pk_collision: refusing to overwrite local account(s) -- "
                + "; ".join(collisions)
            )

        User = _user_model()
        Teacher = _teacher_model()
        dropped: dict[str, int] = {}

        # Which optional FK targets actually exist here, asked ONCE per field rather than per
        # row: a 39-teacher import should not be 39 round trips per column.
        present: dict[str, set] = {}
        for name in _NULLABLE_FK_FIELDS:
            try:
                field = Teacher._meta.get_field(name)
            except FieldDoesNotExist:
                # A field this build does not have is not a gap -- the list above is
                # written against the model as it stands, and an older or newer tree may
                # legitimately lack one. Named rather than caught broadly, so a real
                # error here still surfaces.
                continue
            wanted = {row.get(field.attname) for row in teachers if row.get(field.attname)}
            if not wanted:
                continue
            target = field.related_model
            if target is Teacher:
                # A self-reference resolves inside this very import; anything not in the
                # bundle cannot be resolved and is dropped like any other absent target.
                present[field.attname] = {row["id"] for row in teachers} & wanted
            else:
                present[field.attname] = set(
                    target.objects.filter(pk__in=list(wanted)).values_list("pk", flat=True)
                )

        with transaction.atomic():
            for row in users:
                values = {k: v for k, v in row.items() if k != "id"}
                if reset_passwords:
                    # Land the account unusable and must-change rather than moving a hash.
                    values["password"] = ""
                    values["requires_password_change"] = True
                # is_superuser is not in _USER_FIELDS and is left at the model default, so a
                # staff import can never create an administrator on the target.
                User.objects.update_or_create(pk=row["id"], defaults=values)
                if reset_passwords:
                    obj = User.objects.get(pk=row["id"])
                    obj.set_unusable_password()
                    obj.save(update_fields=["password"])

            for row in teachers:
                values = dict(row)
                pk = values.pop("id")
                for attname, ok in present.items():
                    if values.get(attname) and values[attname] not in ok:
                        values[attname] = None
                        dropped[attname] = dropped.get(attname, 0) + 1
                Teacher.objects.update_or_create(pk=pk, defaults=values)

    return {
        "school_id": payload.get("school_id", ""),
        "tenant_slug": payload.get("tenant_slug", ""),
        "users": len(users),
        "teachers": len(teachers),
        # Named, not silent: a teacher whose pay scale did not come across is a fact the
        # operator has to know, because the sync rail will never supply it either.
        "dropped_references": dropped,
        "passwords": "reset" if reset_passwords else "carried",
    }


__all__ = [
    "BUNDLE_FORMAT",
    "export_staff_bundle",
    "import_staff_bundle",
    "inspect_staff_bundle",
]
