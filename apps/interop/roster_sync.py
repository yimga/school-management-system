"""Inbound roster sync (Clever / ClassLink) — F5c.

Pulls a district roster from Clever v3.1 or a ClassLink OneRoster endpoint and
upserts it into ONE school as User + SchoolMembership (+ StudentProfile for
students). The HTTP client (``apps.interop.clever_classlink_client``) and the
per-school credential store (a ``ServiceIntegration`` carrying
``native_clever_bearer`` / ``native_classlink_bearer`` / ``native_classlink_base_url``)
already existed; this module adds the pieces that did NOT exist before — the
JSON→RMC mapping, the persistence, a page-based pull orchestrator, credential
resolution, and connection-state recording. A management command
(``manage.py sync_roster``) drives it.

Tenant safety: a roster row sets the PER-SCHOOL ``SchoolMembership.role`` and
only sets the shared ``User.role`` when the account is first created — a
district roster for school A must never rewrite the global role of a user who is
an admin at school B. The same rule now covers the rest of that user's identity:
``email`` / ``first_name`` / ``last_name`` are create-only, filled on an existing
row only where the field is EMPTY and only for someone already in the target
school. The roster body is tenant-controlled (``native_classlink_base_url`` is
the school's own config), so an overwritable email was a way to redirect another
school's password-reset mail; the base URL itself is checked before use
(:func:`validate_roster_base_url`).

Certification boundary: live district pulls require a certified Clever/ClassLink
district bearer token (partner onboarding — see
``docs/interop/CLEVER_CLASSLINK_PARTNERSHIP.md``). The mapping + persistence +
orchestrator are fully built and unit-tested against synthetic / OneRoster-shaped
rows via an injected page fetcher; only the live token is external.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.communication.secret_config import decrypt_config

logger = logging.getLogger(__name__)


class RosterSyncError(Exception):
    """Raised when a live roster pull cannot proceed (bad creds / IdP error)."""


def _rmc_role(raw: Any, User) -> str:
    role_map = {
        "student": User.Role.STUDENT,
        "teacher": User.Role.TEACHER,
        "administrator": User.Role.ADMIN,
        "admin": User.Role.ADMIN,
        "district_admin": User.Role.ADMIN,
        "school_admin": User.Role.ADMIN,
        "staff": User.Role.ACADEMICS_STAFF,
        "aide": User.Role.ACADEMICS_STAFF,
        "proctor": User.Role.ACADEMICS_STAFF,
        "parent": User.Role.PARENT,
        "guardian": User.Role.PARENT,
        "contact": User.Role.PARENT,
        "relative": User.Role.PARENT,
    }
    return role_map.get(str(raw or "").strip().lower(), User.Role.PARENT)


def _canonical(*, source_id, username, email, first_name, last_name, role, User):
    email = str(email or "").strip().lower()
    source_id = str(source_id or "").strip()
    username = (str(username or "").strip() or (email.split("@")[0] if email else source_id))[:150]  # magic-number-allow: string-truncation-cap
    return {
        "source_id": source_id,
        "username": username,
        "email": email[:254],  # magic-number-allow: string-truncation-cap
        "first_name": str(first_name or "").strip()[:80],
        "last_name": str(last_name or "").strip()[:80],
        "role": role,
        "is_student": role == User.Role.STUDENT,
    }


def map_oneroster_user(raw: Any, *, User) -> dict[str, Any] | None:
    """Map a OneRoster (ClassLink) user object to the canonical person dict."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name") if isinstance(raw.get("name"), dict) else {}
    role_raw = raw.get("role")
    if not role_raw and isinstance(raw.get("roles"), list) and raw["roles"]:
        first = raw["roles"][0]
        role_raw = first.get("role") if isinstance(first, dict) else first
    return _canonical(
        source_id=raw.get("sourcedId") or raw.get("id"),
        username=raw.get("username"),
        email=raw.get("email"),
        first_name=raw.get("givenName") or name.get("first"),
        last_name=raw.get("familyName") or name.get("last"),
        role=_rmc_role(role_raw, User),
        User=User,
    )


def map_clever_user(raw: Any, *, User) -> dict[str, Any] | None:
    """Map a Clever v3.1 user object to the canonical person dict.

    Accepts both the wrapped list-item shape (``{"data": {...}}``) and a bare
    user object. Clever carries per-role sub-objects under ``roles``.
    """
    if not isinstance(raw, dict):
        return None
    u = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    name = u.get("name") if isinstance(u.get("name"), dict) else {}
    role_key = ""
    roles = u.get("roles")
    if isinstance(roles, dict):
        for candidate in ("student", "teacher", "staff", "school_admin", "district_admin"):
            if candidate in roles:
                role_key = candidate
                break
    creds = u.get("credentials") if isinstance(u.get("credentials"), dict) else {}
    return _canonical(
        source_id=u.get("id") or u.get("sourcedId"),
        username=creds.get("district_username") or u.get("username"),
        email=u.get("email"),
        first_name=name.get("first") or u.get("first_name"),
        last_name=name.get("last") or u.get("last_name"),
        role=_rmc_role(role_key or u.get("role") or "student", User),
        User=User,
    )


@transaction.atomic
def upsert_roster_person(school, person: dict[str, Any], *, User=None) -> dict[str, Any]:
    """Upsert one canonical person into ``school``.

    Creates/updates the shared User, ensures a per-school SchoolMembership with
    the roster role, and (for students) a StudentProfile. The shared User.role is
    set only on creation — an existing user's global role is never rewritten by a
    single school's roster.
    """
    User = User or get_user_model()
    from apps.schools.models import SchoolMembership

    username = (person.get("username") or person.get("source_id") or "").strip()[:150]  # magic-number-allow: string-truncation-cap
    if not username:
        return {"ok": False, "reason": "no_username"}
    email = (person.get("email") or "")[:254]  # magic-number-allow: string-truncation-cap
    first_name = person.get("first_name") or ""
    last_name = person.get("last_name") or ""
    role = person.get("role") or User.Role.PARENT

    user, created = User.objects.get_or_create(  # tenant-isolation-allow: roster upsert resolves the shared platform User by username, then scopes membership to the target school below
        username=username,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": role,
            "is_active": True,
        },
    )
    changed = False
    if created:
        user.set_unusable_password()
        changed = True
    # Identity is create-only, exactly like the shared ``User.role`` above.
    # ``username`` is a GLOBAL key, and the roster body is tenant-controlled
    # (``native_classlink_base_url`` is set by the school itself), so a district
    # pull for school A that names school B's principal used to overwrite that
    # account's email — redirecting its password-reset mail. An existing row is
    # only ever FILLED where it is empty, and only for someone who already
    # belongs to this school; nothing is ever overwritten.
    may_fill = not created and SchoolMembership.objects.filter(  # tenant-isolation-allow: the cross-school reach IS what this gate measures
        user=user, school=school
    ).exists()
    if may_fill:
        for field, value in (
            ("first_name", first_name), ("last_name", last_name), ("email", email),
        ):
            if value and not getattr(user, field, None):
                setattr(user, field, value)
                changed = True
    if changed:
        user.save()

    has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check across the user's schools
        user=user, is_primary=True
    ).exists()
    SchoolMembership.objects.update_or_create(
        user=user,
        school=school,
        defaults={"role": role, "is_primary": not has_primary},
    )

    is_student = False
    if person.get("is_student"):
        from apps.people.models import StudentProfile

        StudentProfile.objects.get_or_create(
            user=user,
            defaults={
                "school": school,
                "first_name": first_name or username,
                "last_name": last_name,
                "student_code": (person.get("source_id") or "")[:50],
                "status": StudentProfile.Status.NEW,
            },
        )
        is_student = True

    return {"ok": True, "created": created, "is_student": is_student, "user_id": user.pk}


def sync_roster_for_school(
    school,
    *,
    provider: str,
    fetch_pages: Callable[[], Iterable[list]],
    User=None,
    dry_run: bool = False,
    max_pages: int = 200,
) -> dict[str, Any]:
    """Pull + upsert a roster. ``fetch_pages()`` yields pages (lists of raw IdP
    user objects); injecting it keeps HTTP in the client and makes this testable.
    """
    User = User or get_user_model()
    mapper = map_clever_user if str(provider).lower() == "clever" else map_oneroster_user
    stats = {
        "provider": provider,
        "seen": 0,
        "created": 0,
        "updated": 0,
        "students": 0,
        "skipped": 0,
        "dry_run": bool(dry_run),
    }
    pages = 0
    for page in fetch_pages():
        pages += 1
        if pages > max_pages:
            logger.warning("roster_sync: page cap %s reached for %s", max_pages, getattr(school, "slug", ""))
            break
        for raw in page or []:
            stats["seen"] += 1
            person = mapper(raw, User=User)
            if not person or not (person.get("username") or person.get("source_id")):
                stats["skipped"] += 1
                continue
            if dry_run:
                continue
            try:
                result = upsert_roster_person(school, person, User=User)
            except Exception:  # noqa: BLE001 — one bad row must not abort the whole pull
                logger.exception("roster_sync: upsert failed for a row")
                stats["skipped"] += 1
                continue
            if not result.get("ok"):
                stats["skipped"] += 1
                continue
            stats["created" if result["created"] else "updated"] += 1
            if result["is_student"]:
                stats["students"] += 1
    return stats


# ----- credentials + live fetchers ----------------------------------------


def resolve_roster_bearer(school, provider: str):
    """Return ``(bearer, base_url, integration)`` from the school's stored district
    credentials (the District-interop ``ServiceIntegration``). Empty bearer =
    not connected. ``decrypt_config`` is used defensively (plaintext passes
    through; if the key is ever encrypted at rest it still resolves)."""
    from apps.integrations_marketplace.models import ServiceIntegration

    key = "native_clever_bearer" if str(provider).lower() == "clever" else "native_classlink_bearer"
    for integ in ServiceIntegration.objects.filter(  # tenant-isolation-allow: request-school-scoped district credential lookup
        school=school, is_active=True
    ):
        cfg = decrypt_config(integ.config or {})
        bearer = str(cfg.get(key) or "").strip()
        if bearer:
            base = str(cfg.get("native_classlink_base_url") or "").strip()
            return bearer, base, integ
    return "", "", None


def clever_fetch_pages(bearer: str, *, limit: int = 100):
    def _fetch():
        from apps.interop.clever_classlink_client import clever_list_users

        resp = clever_list_users(bearer, limit=limit)
        if isinstance(resp, dict) and resp.get("error"):
            raise RosterSyncError(f"clever:{resp.get('error')}")
        data = resp.get("data") if isinstance(resp, dict) else None
        yield list(data or [])

    return _fetch


#: Hosts a district OneRoster base URL may never point at. The base URL is
#: tenant-supplied config, and the puller runs server-side with no user context,
#: so an unchecked value is a server-side-request primitive aimed at the cloud
#: metadata endpoint or at anything on the deploy box's own network.
_PRIVATE_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata", ""})


def validate_roster_base_url(base_url: str) -> None:
    """Raise :class:`RosterSyncError` unless ``base_url`` is a safe public https
    target. An EMPTY value is allowed — it means "use the vendor default", which
    ``clever_classlink_client`` supplies itself.

    Literal-IP and obvious-name checks only: this does NOT resolve DNS, so a
    hostname that resolves into private space still gets through. It closes the
    direct ``http://169.254.169.254`` / ``https://10.x`` case, which is what a
    tenant can set from the district-interop form.
    """
    base_url = (base_url or "").strip()
    if not base_url:
        return
    import ipaddress
    from urllib.parse import urlsplit

    parts = urlsplit(base_url)
    if parts.scheme != "https":
        raise RosterSyncError(
            f"classlink:invalid_base_url — {parts.scheme or 'no'} scheme; https required"
        )
    host = (parts.hostname or "").strip().lower()
    if host in _PRIVATE_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise RosterSyncError(f"classlink:invalid_base_url — non-public host {host!r}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # a name, not a literal — nothing more we can check without DNS
    if not ip.is_global:
        raise RosterSyncError(f"classlink:invalid_base_url — non-public host {host!r}")


def classlink_fetch_pages(bearer: str, base_url: str, *, limit: int = 100):
    def _fetch():
        validate_roster_base_url(base_url)
        from apps.interop.clever_classlink_client import classlink_list_users

        resp = classlink_list_users(bearer, base_url, limit=limit)
        if isinstance(resp, dict) and resp.get("error"):
            raise RosterSyncError(f"classlink:{resp.get('error')}")
        users = resp.get("users") if isinstance(resp, dict) else None
        yield list(users or [])

    return _fetch


def record_sync_state(integration, stats: dict[str, Any]) -> None:
    """Persist connection-state (last sync time + counts) into the integration
    config so the tenant admin + operator can see it. Idempotent secret handling."""
    cfg = dict(integration.config or {})
    cfg["roster_last_sync_at"] = timezone.now().isoformat()
    cfg["roster_last_sync_stats"] = stats
    integration.config = cfg
    integration.save(update_fields=["config"])
