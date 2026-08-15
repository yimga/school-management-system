"""Migrate a school's USER IDENTITIES (accounts + memberships + MFA) across deployments.

The tenant bundle (``tenant_portability``) carries only tenant-schema rows and
EXCLUDES the shared/public identity parents — ``accounts.User``,
``schools.SchoolMembership``, and the ``django_otp`` / passkey devices all live in
the public schema (or FK only to ``user``), so a pk-preserving tenant clone can
never include them. On an edge box those identities must be recreated separately,
otherwise the cloud's real admins/staff cannot sign in with their existing
credentials or authenticator apps.

This module is that missing shared-parent counterpart to ``tenant_portability``:

  * export (cloud): scope by ``SchoolMembership.school`` -> the user set -> serialize
    each User (password HASH copied verbatim, never re-hashed), its membership
    (role / is_school_owner / is_primary / suspended), and its MFA devices
    (confirmed TOTP with its secret ``key``, static backup codes, passkeys);
  * import (box): verify-before-decrypt (fail closed), then upsert everything inside
    one ``rls_bypass() + transaction.atomic()`` unit — matching users by their unique
    ``username`` so a box that already has the account reconciles instead of colliding.

Envelope + crypto are REUSED verbatim from ``tenant_dr_snapshot`` (Fernet encryption
+ HMAC signature, both bound to ``SECRET_KEY`` AND ``school_id`` under distinct
domain-separation labels). A wrong SECRET_KEY or wrong school id fails closed.

Identities are NOT part of the delta/CRDT sync engine (it deliberately excludes
shared models whose ids differ box-vs-cloud), so this is a one-shot/periodic
reconciliation tool, not a live sync path.
"""
from __future__ import annotations

import base64
import gzip
import json

from apps.lifecycle.tenant_dr_snapshot import (
    decrypt_blob,
    encrypt_blob,
    sign_payload,
    verify_signature,
)

_IDENTITY_FORMAT = "rmc-identity-bundle/1"

# User columns carried verbatim. ``password`` is the HASH — copied, never re-hashed,
# so the migrated account logs in with its EXISTING credentials. Deliberately NOT
# carried: legacy_* (encrypted-at-rest, niche foreign-vendor verify), M2M roles /
# feature_permissions / groups (RBAC catalog, re-seeded per deployment),
# profile_photo (media, copied separately), date_joined/last_login (non-login),
# requires_password_change (would force a reset the migration shouldn't).
_USER_FIELDS = (
    "username",
    "email",
    "password",
    "is_active",
    "is_staff",
    "is_superuser",
    "first_name",
    "last_name",
    "role",
    "preferred_language",
)


# --------------------------------------------------------------------------- #
# MFA device (de)serialization — all shared/public, FK to user only.
# --------------------------------------------------------------------------- #
def _dump_totp(user) -> list[dict]:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    rows = []
    for d in TOTPDevice.objects.filter(user=user):
        rows.append(
            {
                "name": d.name,
                "confirmed": bool(d.confirmed),
                "key": d.key,  # hex secret — the thing that makes the same app codes work
                "step": d.step,
                "t0": d.t0,
                "digits": d.digits,
                "tolerance": d.tolerance,
                "drift": d.drift,
            }
        )
    return rows


def _dump_static(user) -> list[dict]:
    from django_otp.plugins.otp_static.models import StaticDevice

    rows = []
    for d in StaticDevice.objects.filter(user=user):
        rows.append(
            {
                "name": d.name,
                "confirmed": bool(d.confirmed),
                "tokens": list(d.token_set.values_list("token", flat=True)),
            }
        )
    return rows


def _dump_passkeys(user) -> list[dict]:
    try:
        from apps.accounts.models import UserPasskey
    except ImportError:
        return []
    rows = []
    for p in UserPasskey.objects.filter(user=user):
        rows.append(
            {
                "name": p.name,
                "credential_id": p.credential_id,
                "public_key": p.public_key,
                "sign_count": p.sign_count,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# EXPORT (runs on the cloud; identities are always in the public schema, so no
# schema_context is needed).
# --------------------------------------------------------------------------- #
def export_tenant_identities(school) -> bytes:
    """Serialize + encrypt + sign every user identity scoped to ``school``."""
    from apps.schools.models import SchoolMembership

    school_id = str(school.id)
    identities: list[dict] = []
    seen_user_ids: set = set()

    memberships = SchoolMembership.objects.filter(school=school).select_related("user")
    for m in memberships:
        user = m.user
        if user is None or user.pk in seen_user_ids:
            continue
        seen_user_ids.add(user.pk)
        identities.append(
            {
                "user": {f: getattr(user, f, None) for f in _USER_FIELDS},
                "membership": {
                    "role": m.role,
                    "is_school_owner": bool(m.is_school_owner),
                    "is_primary": bool(m.is_primary),
                    "suspended_at": m.suspended_at.isoformat() if m.suspended_at else None,
                },
                "totp": _dump_totp(user),
                "static": _dump_static(user),
                "passkeys": _dump_passkeys(user),
            }
        )

    payload = {
        "format": _IDENTITY_FORMAT,
        "school_id": school_id,
        "school_slug": getattr(school, "slug", ""),
        "identities": identities,
    }
    compressed = gzip.compress(json.dumps(payload, default=str).encode("utf-8"))
    blob = encrypt_blob(compressed, school_id=school_id)
    sig = sign_payload(blob, school_id=school_id)
    container = {
        "format": _IDENTITY_FORMAT,
        "school_id": school_id,
        "sig": sig,
        "blob_b64": base64.b64encode(blob).decode("ascii"),
    }
    return json.dumps(container).encode("utf-8")


# --------------------------------------------------------------------------- #
# READ (verify -> decrypt -> parse). Fail-closed BEFORE any write, mirroring
# tenant_portability.import_tenant_bundle.
# --------------------------------------------------------------------------- #
def read_identity_payload(container_bytes: bytes, *, expected_school_id=None) -> dict:
    container = json.loads(container_bytes)
    school_id = str(container["school_id"])
    if expected_school_id is not None and str(expected_school_id) != school_id:
        raise ValueError("identity_bundle_school_mismatch")
    blob = base64.b64decode(container["blob_b64"])
    if not verify_signature(blob, container["sig"], school_id=school_id):
        raise ValueError("identity_bundle_signature_mismatch")  # fail closed
    return json.loads(gzip.decompress(decrypt_blob(blob, school_id=school_id)))


# --------------------------------------------------------------------------- #
# IMPORT (runs on the box). Only SchoolMembership is FORCE-RLS, but the whole op
# is wrapped in rls_bypass()+atomic() for one rollback-safe unit (harmless on the
# non-RLS user/MFA tables).
# --------------------------------------------------------------------------- #
def _load_totp(user, rows) -> int:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    n = 0
    for r in rows:
        name = r.get("name") or "default"
        dev, _ = TOTPDevice.objects.get_or_create(
            user=user, name=name, defaults={"key": r["key"]}
        )
        dev.key = r["key"]
        dev.step = r.get("step", 30)
        dev.t0 = r.get("t0", 0)
        dev.digits = r.get("digits", 6)
        dev.tolerance = r.get("tolerance", 1)
        dev.drift = r.get("drift", 0)
        dev.confirmed = bool(r.get("confirmed", True))
        dev.save()
        n += 1
    return n


def _load_static(user, rows) -> int:
    from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

    n = 0
    for r in rows:
        name = r.get("name") or "backup"
        dev, _ = StaticDevice.objects.get_or_create(user=user, name=name)
        dev.confirmed = bool(r.get("confirmed", True))
        dev.save()
        existing = set(dev.token_set.values_list("token", flat=True))
        for tok in r.get("tokens") or []:
            if tok and tok not in existing:
                StaticToken.objects.create(device=dev, token=tok)
        n += 1
    return n


def _load_passkeys(user, rows) -> int:
    try:
        from apps.accounts.models import UserPasskey
    except ImportError:
        return 0
    n = 0
    for r in rows:
        cred = r.get("credential_id")
        if not cred:
            continue
        pk, _ = UserPasskey.objects.get_or_create(
            credential_id=cred,
            defaults={
                "user": user,
                "name": r.get("name") or "",
                "public_key": r.get("public_key") or "",
                "sign_count": r.get("sign_count") or 0,
            },
        )
        pk.user = user
        pk.name = r.get("name") or pk.name
        pk.public_key = r.get("public_key") or pk.public_key
        pk.sign_count = r.get("sign_count") or 0
        pk.save()
        n += 1
    return n


def import_tenant_identities(
    container_bytes: bytes,
    *,
    expected_school_id=None,
    owner_role: str = "ADMIN",
    skip_mfa: bool = False,
) -> dict:
    """Recreate users + memberships + MFA on the current (edge) deployment.

    ``owner_role`` normalizes the User.role of any is_school_owner user (default
    ADMIN) because a ``SUPERADMIN`` role is an operator role that gets redirected
    off tenant hosts — the account keeps ``is_superuser`` if it had it, but its
    tenant role must be portal-usable. Idempotent: matches Users by username.
    """
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django.utils.dateparse import parse_datetime

    from apps.schools.models import School, SchoolMembership
    from apps.schools.rls_context import rls_bypass

    payload = read_identity_payload(container_bytes, expected_school_id=expected_school_id)
    school_id = str(payload["school_id"])
    identities = payload.get("identities", []) or []

    User = get_user_model()
    result = {
        "users": 0,
        "created_users": 0,
        "memberships": 0,
        "owners": 0,
        "totp": 0,
        "static": 0,
        "passkeys": 0,
        "usernames": [],
    }

    with rls_bypass():
        with transaction.atomic():
            school = School.objects.filter(id=school_id).first()
            if school is None:
                raise ValueError(
                    "identity_bundle_target_school_missing: create the School parent "
                    "first (import_sovereign_tenant) before importing identities."
                )

            for rec in identities:
                uf = rec.get("user") or {}
                username = uf.get("username")
                if not username:
                    continue

                user = User.objects.filter(username__iexact=username).first()
                created = user is None
                if user is None:
                    user = User(username=username)

                for f in ("email", "first_name", "last_name", "role", "preferred_language"):
                    val = uf.get(f)
                    if val is not None:
                        setattr(user, f, val)
                user.is_active = bool(uf.get("is_active", True))
                user.is_staff = bool(uf.get("is_staff", False))
                user.is_superuser = bool(uf.get("is_superuser", False))
                if uf.get("password"):
                    user.password = uf["password"]  # copy the HASH verbatim

                mem_rec = rec.get("membership") or {}
                is_owner = bool(mem_rec.get("is_school_owner"))
                if is_owner and owner_role:
                    # SUPERADMIN would be redirected off the tenant portal; keep the
                    # user portal-usable while is_superuser (if set) still grants power.
                    user.role = owner_role
                user.save()
                result["users"] += 1
                if created:
                    result["created_users"] += 1
                result["usernames"].append(user.username)

                mem, _ = SchoolMembership.objects.get_or_create(
                    user=user,
                    school=school,
                    defaults={"role": mem_rec.get("role") or "ADMIN"},
                )
                mem.role = mem_rec.get("role") or mem.role
                mem.is_school_owner = is_owner
                mem.is_primary = bool(mem_rec.get("is_primary"))
                susp = mem_rec.get("suspended_at")
                mem.suspended_at = parse_datetime(susp) if susp else None
                mem.save()
                result["memberships"] += 1
                if is_owner and mem.suspended_at is None:
                    result["owners"] += 1

                if not skip_mfa:
                    result["totp"] += _load_totp(user, rec.get("totp") or [])
                    result["static"] += _load_static(user, rec.get("static") or [])
                    result["passkeys"] += _load_passkeys(user, rec.get("passkeys") or [])

    return result
