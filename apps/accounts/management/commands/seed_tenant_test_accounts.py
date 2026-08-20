"""Seed a tenant's rigorous-testing accounts in ONE command (idempotent).

For a given school (default ``gilead-tech``) this:
  1. Attaches an OWNER (super-admin) account by email — a SchoolMembership with
     is_school_owner=True (never demotes the owner's existing primary school; never
     touches their password). This is the email-INDEPENDENT owner path that
     ``invite_school_owner`` refuses for an account whose username != email.
  2. Creates/updates a TEACHER and a PARENT test account (default teacher1 / parent1,
     password Test1234) with the right role, a SchoolMembership for the tenant, and —
     when the People app is present — a TeacherProfile, so they show up in the tenant
     and can sign in on its host.
  3. Optionally emails the owner their setup/sign-in link (``--send-owner-email``),
     reusing the audited transactional path (needs the Brevo secrets configured).

Runs correctly under both USE_DJANGO_TENANTS=0 (shared-table tests) and =1 (prod
schema-per-tenant): shared models (User, SchoolMembership) are written directly; the
tenant-scoped TeacherProfile is written inside ``tenant_context`` on django-tenants.

Example (Render shell):
  python manage.py seed_tenant_test_accounts --slug gilead-tech \
      --owner-email yimgah@yahoo.com --send-owner-email
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seed a tenant's testing accounts: attach an owner by email + create "
        "teacher/parent test users (password Test1234) linked to the school."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="gilead-tech", help="School slug (default: gilead-tech).")
        parser.add_argument("--school-id", default="", help="School UUID/pk (alternative to --slug).")
        parser.add_argument("--owner-email", default="", help="Email/username of the account to attach as OWNER.")
        parser.add_argument("--teacher-username", default="teacher1")
        parser.add_argument("--parent-username", default="parent1")
        parser.add_argument("--password", default="Test1234", help="Password for the teacher/parent test accounts.")
        parser.add_argument(
            "--send-owner-email",
            action="store_true",
            help="Also email the owner their setup/sign-in link (needs Brevo configured).",
        )
        parser.add_argument(
            "--create-owner-if-missing",
            action="store_true",
            help=(
                "If no account matches --owner-email, CREATE it (unusable password — the owner "
                "sets their own via the setup email link) instead of failing. Makes the command "
                "safe to run unattended on deploy where the owner may not exist yet."
            ),
        )

    # -- helpers ---------------------------------------------------------------

    def _resolve_school(self, slug: str, school_id: str):
        from django.core.exceptions import ValidationError

        from apps.schools.models import School

        if school_id:
            try:
                s = School.objects.filter(pk=school_id).first()
            except (ValidationError, ValueError, TypeError):
                s = None
            if s:
                return s
        if slug:
            s = School.objects.filter(slug__iexact=slug.strip()).first()
            if s:
                return s
        raise CommandError(f"No school matched slug={slug!r} / id={school_id!r}.")

    def _attach_owner(self, school, email: str, *, create_if_missing: bool = False):
        from apps.schools.models import SchoolMembership

        ident = (email or "").strip()
        from django.db.models import Q

        candidates = list(
            User.objects.filter(Q(username__iexact=ident) | Q(email__iexact=ident)).distinct()
        )
        if not candidates:
            if not create_if_missing:
                raise CommandError(
                    f"No account matches owner --owner-email {ident!r}. Create it first (it must "
                    "exist), or pass --create-owner-if-missing to create it here."
                )
            # Create the owner with an UNUSABLE password: no known credential is ever
            # written, and the owner sets their own via the setup email link. Username is
            # the email (Django's username validator permits @ . + - _), so a later run
            # resolves the same account by email.
            user = User.objects.create_user(username=ident, email=ident if "@" in ident else "")
            user.set_unusable_password()
            user.is_active = True
            if hasattr(user, "role"):
                user.role = User.Role.ADMIN
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Owner account created for {ident!r} (unusable password — set via setup email)."
                )
            )
            candidates = [user]
        if len(candidates) > 1:
            exact = [u for u in candidates if (u.username or "").lower() == ident.lower()]
            if len(exact) != 1:
                raise CommandError(f"{ident!r} matches {len(candidates)} accounts — pass the exact username.")
            candidates = exact
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
                    "is_primary": not has_primary,
                },
            )
            if not created and not ms.is_school_owner:
                ms.is_school_owner = True
                ms.role = User.Role.ADMIN
                ms.save(update_fields=["is_school_owner", "role"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Owner: {user.get_username()} <{user.email or '—'}> is OWNER of {school.slug}"
                + ("  [primary]" if ms.is_primary else "")
                + "."
            )
        )
        return user

    def _seed_member(self, school, username: str, role, password: str, *, make_teacher_profile: bool):
        from apps.schools.models import SchoolMembership

        username = (username or "").strip()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@example.com",
                "first_name": "Test",
                "last_name": role.label if hasattr(role, "label") else str(role),
                "role": role,
                "is_active": True,
            },
        )
        if not created:
            user.role = role
            user.is_active = True
            user.email = user.email or f"{username}@example.com"
            user.save(update_fields=["role", "is_active", "email"])
        user.set_password(password)
        user.save()

        with transaction.atomic():
            has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check
                user=user, is_primary=True
            ).exists()
            SchoolMembership.objects.get_or_create(
                user=user,
                school=school,
                defaults={"role": role, "is_school_owner": False, "is_primary": not has_primary},
            )

        if make_teacher_profile:
            try:
                from apps.people.models import TeacherProfile
            except ImportError:
                TeacherProfile = None
            if TeacherProfile is not None:
                TeacherProfile.objects.get_or_create(
                    user=user, defaults={"position_title": "Teacher", "is_active": True}
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"{str(role)}: '{username}' {'created' if created else 'updated'} on {school.slug} "
                f"(password: {password})."
            )
        )

    def _seed_members_maybe_tenant_context(self, school, opts):
        """Create teacher/parent; wrap the tenant-scoped TeacherProfile write in the
        tenant schema when running under django-tenants."""
        from django.conf import settings

        password = opts["password"] or "Test1234"

        # Parent has no tenant-scoped profile → write directly (shared models only).
        self._seed_member(
            school, opts["parent_username"], User.Role.PARENT, password, make_teacher_profile=False
        )

        use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
        if not use_tenants:
            self._seed_member(
                school, opts["teacher_username"], User.Role.TEACHER, password, make_teacher_profile=True
            )
            return
        # Prod: TeacherProfile lives in the tenant schema.
        try:
            from apps.customers.models import Client
            from django_tenants.utils import tenant_context
        except ImportError:
            self._seed_member(
                school, opts["teacher_username"], User.Role.TEACHER, password, make_teacher_profile=True
            )
            return
        client = (
            Client.objects.filter(schema_name=school.slug).first()
            or Client.objects.filter(school__slug=school.slug).first()
            or Client.objects.filter(school_id=school.id).first()
        )
        if client is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  No tenant Client for {school.slug}; creating teacher without a schema-scoped "
                    "TeacherProfile (User + membership still created)."
                )
            )
            self._seed_member(
                school, opts["teacher_username"], User.Role.TEACHER, password, make_teacher_profile=False
            )
            return
        with tenant_context(client):
            self._seed_member(
                school, opts["teacher_username"], User.Role.TEACHER, password, make_teacher_profile=True
            )

    # -- handler ---------------------------------------------------------------

    def handle(self, *args, **opts):
        school = self._resolve_school(opts["slug"], opts["school_id"])
        if not school.is_active:
            raise CommandError(f"{school.slug} is not active — repair provisioning before seeding.")

        owner_email = (opts.get("owner_email") or "").strip()
        owner_user = None
        if owner_email:
            owner_user = self._attach_owner(
                school, owner_email, create_if_missing=opts.get("create_owner_if_missing", False)
            )

        self._seed_members_maybe_tenant_context(school, opts)

        slug_lower = (school.slug or "").lower()
        if slug_lower in {"gilead-tech", "gilead_tech", "gilead-tech-high"}:
            try:
                from django.core.management import call_command

                call_command("ensure_showcase_tenant_entitlements")
            except Exception as exc:  # noqa: BLE001 — report, never fail the seed
                self.stdout.write(
                    self.style.WARNING(
                        f"Sovereign entitlements step failed ({exc}); accounts are still seeded."
                    )
                )

        if owner_email and opts.get("send_owner_email") and owner_user is not None:
            try:
                from django.core.management import call_command

                # --only-unclaimed: this seed runs on EVERY deploy, so send the
                # "your school is ready" email ONLY to owners who still need to
                # claim their account. Once the owner has set their own password
                # and onboarded, re-welcoming them on every release is pure noise
                # (a forced resend is still available via `resend_owner_setup_email`
                # without this flag, or the tenant-360 "Resend owner setup email"
                # button).
                call_command(
                    "resend_owner_setup_email",
                    "--school",
                    school.slug,
                    "--only-unclaimed",
                )
                self.stdout.write(self.style.SUCCESS(f"Owner setup email step ran for {school.slug}."))
            except Exception as exc:  # noqa: BLE001 - report, never fail the seed
                self.stdout.write(
                    self.style.WARNING(
                        f"Owner email step failed ({exc}); accounts are still seeded. "
                        "Run `resend_owner_setup_email --school "
                        f"{school.slug}` manually once Brevo is confirmed."
                    )
                )

        host = getattr(school, "subdomain", None) or school.slug
        self.stdout.write(
            self.style.SUCCESS(
                "\nDone. Sign in at https://%s.runmycampus.com/authentication/login/ :\n"
                "  Owner:   %s (existing password; enroll MFA on first sign-in)\n"
                "  Teacher: %s / %s\n"
                "  Parent:  %s / %s"
                % (
                    host,
                    owner_email or "(none attached)",
                    opts["teacher_username"],
                    opts["password"],
                    opts["parent_username"],
                    opts["password"],
                )
            )
        )
