"""Diagnose (and, on request, fix) why ONE account cannot sign in to a tenant.

The platform's login is SYSTEM-WIDE: ``authenticate()`` queries the shared
(public-schema) ``User`` table by username OR email, and every successful sign-in
returns a 302 redirect. So a login POST that returns HTTP 200 with "Invalid
username or password" means ``authenticate()`` returned ``None`` — the sign-in
failed BEFORE any MFA step. That happens for exactly three reasons, and the
existing ``recover_unactivated_owners`` command can only see ONE of them:

1. the account has a USABLE password and the wrong one was typed (or it was
   forgotten / a temp password was set and lost);
2. the account is ``is_active=False`` (``user_can_authenticate`` returns False,
   so no password works) — and ``recover_unactivated_owners`` filters
   ``user__is_active=True``, so it can't even SEE this account;
3. no account matches the identifier at all (typo, or never created).

Only case (2)-with-a-usable-password and the never-activated (active +
unusable-password) case are covered elsewhere. This command covers ALL of them:
it resolves the account the SAME way the login backend does, prints its true
state + a plain-language verdict + the exact remedy, and can set a KNOWN password
(and activate) WITHOUT needing a working mail relay — the reliable unblock when
prod email delivery is down.

Diagnose (read-only, default)::

    python manage.py fix_tenant_login --email owner@school.edu
    python manage.py fix_tenant_login --school new-school      # roster of a school

Fix (email-independent) — set a known password, activate, print it::

    python manage.py fix_tenant_login --email owner@school.edu --set-password
    python manage.py fix_tenant_login --email owner@school.edu --set-password 'ChosenPass123!'
    python manage.py fix_tenant_login --email owner@school.edu --activate  # activate only

The mutating flags require an explicit ``--email`` target (never a whole school),
and refuse to act when the identifier matches more than one account — the
operator must disambiguate by exact username.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q


def _passkey_only(user) -> bool:
    """Mirror ``login_recovery._is_passkey_only`` without importing settings twice."""
    try:
        from apps.accounts.login_recovery import _is_passkey_only

        return bool(_is_passkey_only(user))
    except Exception:  # noqa: BLE001 — best-effort; absence of the helper is not fatal
        return False


class Command(BaseCommand):
    help = "Diagnose (and optionally fix) why a specific account can't sign in."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="",
            help="Target account by email OR username (case-insensitive), as typed at login.",
        )
        parser.add_argument(
            "--school",
            default="",
            help="Roster mode: list every membership of this school slug + login-readiness.",
        )
        parser.add_argument(
            "--set-password",
            nargs="?",
            const="",
            default=None,
            metavar="PASSWORD",
            help=(
                "Set a KNOWN password on the --email target and activate it. "
                "Pass a value to choose it, or omit the value to auto-generate one. "
                "Email-independent."
            ),
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="Set is_active=True on the --email target WITHOUT changing the password.",
        )
        parser.add_argument(
            "--attach-owner",
            action="store_true",
            help=(
                "Attach the EXISTING --email account as a school OWNER of --school "
                "(idempotent, email-independent). Use for an already-claimed account "
                "that invite_school_owner rejects (username != email)."
            ),
        )

    # -- helpers ---------------------------------------------------------------

    def _resolve_school(self, ident: str):
        """Resolve a school by slug OR primary key (uuid/int), like resend_owner_setup_email."""
        from django.core.exceptions import ValidationError

        from apps.schools.models import School

        ident = (ident or "").strip()
        # tenant-isolation-allow: operator school lookup by exact slug or pk
        school = School.objects.filter(slug=ident).first()
        if school is None:
            try:
                # tenant-isolation-allow: operator school lookup by exact pk fallback
                school = School.objects.filter(pk=ident).first()
            except (ValidationError, ValueError, TypeError):
                school = None
        return school

    def _resolve_candidates(self, identifier: str):
        """Resolve accounts exactly the way ``EmailOrUsernameModelBackend`` does."""
        User = get_user_model()
        ident = (identifier or "").strip()
        if not ident:
            return []
        qs = User.objects.filter(  # tenant-isolation-allow: auth is system-wide (public User table)
            Q(**{f"{User.USERNAME_FIELD}__iexact": ident}) | Q(email__iexact=ident)
        )
        candidates = list(qs[:10])  # magic-number-allow: bounded fan-out for a shared email
        # Prefer an exact username match first (mirrors the backend's tie-break).
        candidates.sort(
            key=lambda u: (getattr(u, User.USERNAME_FIELD, "") or "").lower() != ident.lower()
        )
        return candidates

    def _memberships(self, user):
        from apps.schools.models import SchoolMembership

        return list(
            SchoolMembership.objects.filter(user=user)  # tenant-isolation-allow: owner-diagnostic user-scoped membership lookup
            .select_related("school")
            .order_by("-is_primary", "school__name")
        )

    def _verdict(self, user) -> tuple[str, str]:
        """Return (STATE, remedy) explaining whether password login can succeed."""
        if not user.is_active:
            return (
                "INACTIVE",
                "authenticate() returns None for an inactive account no matter the "
                "password — this is the silent 'reloads to sign-in' dead-end. "
                "Remedy: --activate (or --set-password to also set a known password).",
            )
        if _passkey_only(user):
            return (
                "PASSKEY-ONLY ROLE",
                "Password sign-in is refused for this role by design; the owner must "
                "use their passkey. Remedy: enroll/repair the passkey, or move the "
                "account off a PASSKEY_ONLY_ROLES role.",
            )
        if not user.has_usable_password():
            return (
                "NO USABLE PASSWORD",
                "The account was provisioned but never claimed (set_unusable_password). "
                "The login page auto-emails a set-password link; if mail delivery is "
                "down, use --set-password here to set a known one directly.",
            )
        if getattr(user, "requires_password_change", False):
            return (
                "USABLE PASSWORD (forced change on next login)",
                "Password login WILL succeed with the correct password, then the user "
                "is sent to set a new one. If the password was forgotten, --set-password.",
            )
        return (
            "USABLE PASSWORD + ACTIVE",
            "Login should succeed with the CORRECT password. If the owner forgot it "
            "(or a temp password was lost), --set-password sets a known one.",
        )

    def _print_account(self, user):
        state, remedy = self._verdict(user)
        self.stdout.write(f"  username           : {user.get_username()}")
        self.stdout.write(f"  email              : {user.email or '—'}")
        self.stdout.write(f"  is_active          : {user.is_active}")
        self.stdout.write(f"  has_usable_password: {user.has_usable_password()}")
        self.stdout.write(f"  role               : {getattr(user, 'role', '') or '—'}")
        self.stdout.write(
            f"  is_superuser/staff : {user.is_superuser} / {user.is_staff}"
        )
        self.stdout.write(
            f"  requires_pw_change : {getattr(user, 'requires_password_change', False)}"
        )
        last = getattr(user, "last_login", None)
        self.stdout.write(f"  last_login         : {last.isoformat() if last else 'never'}")
        memberships = self._memberships(user)
        if memberships:
            self.stdout.write("  memberships        :")
            for ms in memberships:
                slug = getattr(ms.school, "slug", "") or str(ms.school_id)
                flags = []
                if ms.is_school_owner:
                    flags.append("OWNER")
                if ms.is_primary:
                    flags.append("primary")
                self.stdout.write(
                    f"      - {slug}  role={ms.role or '—'}"
                    + (f"  [{', '.join(flags)}]" if flags else "")
                )
        else:
            self.stdout.write("  memberships        : (none — not attached to any school)")
        self.stdout.write(self.style.WARNING(f"  VERDICT            : {state}"))
        self.stdout.write(f"  REMEDY             : {remedy}")

    # -- handlers --------------------------------------------------------------

    def handle(self, *args, **opts):
        email = (opts.get("email") or "").strip()
        school = (opts.get("school") or "").strip()
        set_password = opts.get("set_password")  # None = not given; "" = auto-generate
        want_activate = bool(opts.get("activate"))
        want_attach = bool(opts.get("attach_owner"))
        want_mutation = set_password is not None or want_activate

        if not email and not school:
            raise CommandError("Pass --email <email-or-username> or --school <slug>.")
        if want_attach:
            if not (email and school):
                raise CommandError("--attach-owner needs BOTH --email and --school.")
            return self._handle_attach_owner(email, school)
        if want_mutation and not email:
            raise CommandError(
                "--set-password / --activate need a single --email target "
                "(they never act on a whole school)."
            )
        if school and not email:
            return self._handle_roster(school)
        return self._handle_email(email, set_password, want_activate)

    def _handle_attach_owner(self, email: str, school_ident: str):
        """Attach an EXISTING account as an OWNER of the school (idempotent).

        For an already-claimed account (e.g. username 'yimgah', email
        'yimgah@yahoo.com') that ``invite_school_owner`` refuses because
        username != email. Creates/promotes the SchoolMembership only; never
        touches the password and needs no working mail relay.
        """
        from django.db import transaction

        from apps.accounts.models import User
        from apps.schools.models import SchoolMembership

        school = self._resolve_school(school_ident)
        if school is None:
            raise CommandError(f"No school matched slug/id '{school_ident}'.")
        if not school.is_active:
            raise CommandError(
                f"{school.slug} is not active — repair provisioning before attaching an owner."
            )
        candidates = self._resolve_candidates(email)
        if not candidates:
            raise CommandError(
                f"No account matches '{email}'. Create the account first, then attach."
            )
        if len(candidates) > 1:
            raise CommandError(
                f"'{email}' matches {len(candidates)} accounts — pass the exact USERNAME."
            )
        user = candidates[0]

        with transaction.atomic():
            has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check
                user=user, is_primary=True
            ).exists()
            ms, created = SchoolMembership.objects.get_or_create(
                user=user,
                school=school,
                defaults={
                    "role": User.Role.ADMIN,
                    "is_school_owner": True,
                    # Only claim primary when the user has none — never silently
                    # move their default landing school out from under them.
                    "is_primary": not has_primary,
                },
            )
            if not created:
                changed = []
                if not ms.is_school_owner:
                    ms.is_school_owner = True
                    changed.append("is_school_owner")
                if (ms.role or "").upper() != User.Role.ADMIN:
                    ms.role = User.Role.ADMIN
                    changed.append("role")
                if changed:
                    ms.save(update_fields=changed)

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Attached {user.get_username()} <{user.email or '—'}> as OWNER of "
                    f"{school.slug}"
                    + ("  [primary]" if ms.is_primary else "")
                    + "."
                )
            )
        elif ms.is_school_owner:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{user.get_username()} is already an OWNER of {school.slug} — no change."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Promoted {user.get_username()} to OWNER of {school.slug}."
                )
            )
        ready = user.is_active and user.has_usable_password() and not _passkey_only(user)
        self.stdout.write(
            "Next: the owner signs in at the school's /authentication/login/ with their "
            "existing password"
            + ("" if ready else " (set one with --set-password if needed)")
            + ", then enrolls MFA on first sign-in. No setup email required."
        )

    def _handle_roster(self, slug: str):
        from apps.schools.models import SchoolMembership

        s = self._resolve_school(slug)
        if not s:
            raise CommandError(f"No school with slug/id '{slug}'.")
        self.stdout.write(self.style.MIGRATE_HEADING(f"School: {s.name}  (slug={s.slug}, active={s.is_active})"))
        memberships = list(
            SchoolMembership.objects.filter(school=s)  # tenant-isolation-allow: operator roster for one school
            .select_related("user")
            .order_by("-is_school_owner", "-is_primary", "user__username")
        )
        if not memberships:
            self.stdout.write(self.style.WARNING("  (no memberships — this school has no owner/staff attached)"))
            return
        for ms in memberships:
            u = ms.user
            if u is None:
                continue
            state, _remedy = self._verdict(u)
            tags = []
            if ms.is_school_owner:
                tags.append("OWNER")
            if ms.is_primary:
                tags.append("primary")
            self.stdout.write(
                f"  • {u.get_username()}  <{u.email or '—'}>"
                + (f"  [{', '.join(tags)}]" if tags else "")
                + f"  → {state}"
            )
        self.stdout.write(
            "\nDiagnose or fix one of them with: "
            "python manage.py fix_tenant_login --email <email> [--set-password]"
        )

    def _handle_email(self, email: str, set_password, want_activate: bool):
        candidates = self._resolve_candidates(email)
        if not candidates:
            self.stdout.write(
                self.style.ERROR(
                    f"No account matches '{email}' by username OR email."
                )
            )
            self.stdout.write(
                "  → The identifier is wrong, or the account was never created "
                "(e.g. a signup whose email was never verified). Check the exact "
                "address, or run:  python manage.py fix_tenant_login --school <slug>"
            )
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{len(candidates)} account(s) match '{email}':"
            )
        )
        for u in candidates:
            self.stdout.write("")
            self._print_account(u)

        if set_password is None and not want_activate:
            self.stdout.write(
                "\nDiagnose only. To unblock this account WITHOUT email, re-run with "
                "--set-password (sets a known password + activates)."
            )
            return

        if len(candidates) > 1:
            raise CommandError(
                f"'{email}' matches {len(candidates)} accounts — refusing to mutate. "
                "Re-run --set-password/--activate with the exact USERNAME to disambiguate."
            )

        user = candidates[0]
        self._apply_fix(user, set_password, want_activate)

    def _apply_fix(self, user, set_password, want_activate: bool):
        if user.is_superuser:
            self.stdout.write(
                self.style.WARNING(
                    f"NOTE: {user.get_username()} is a platform superuser — "
                    "you are changing a control-plane account."
                )
            )
        fields: list[str] = []
        chosen_password = None
        with transaction.atomic():
            if set_password is not None:
                chosen_password = (set_password or "").strip() or f"Rmc-{secrets.token_urlsafe(9)}"  # magic-number-allow: temp-token-byte-length
                user.set_password(chosen_password)
                fields.append("password")
                if not user.is_active:
                    user.is_active = True
                    fields.append("is_active")
            elif want_activate:
                if user.is_active:
                    self.stdout.write("Account is already active — nothing to change.")
                    return
                user.is_active = True
                fields.append("is_active")
            user.save(update_fields=sorted(set(fields)))

        self.stdout.write(self.style.SUCCESS(f"\nUpdated {user.get_username()} <{user.email or '—'}>:"))
        if "is_active" in fields:
            self.stdout.write("  • activated (is_active=True)")
        if chosen_password is not None:
            self.stdout.write(self.style.SUCCESS(f"  • password set to: {chosen_password}"))
            self.stdout.write(
                "\nHand this password to the owner OUT-OF-BAND. They should sign in at the "
                "tenant login, then change it and set up MFA. If MFA was already enrolled, "
                "it still applies after this password sign-in."
            )
