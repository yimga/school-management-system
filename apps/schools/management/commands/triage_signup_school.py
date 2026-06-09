"""Operator diagnostics for a signup slug (e.g. st-jude on Render shell)."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "Print signup/provision/portal-email state for a school slug. "
        "Use on Render: python manage.py triage_signup_school st-jude"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "slug",
            nargs="?",
            default="",
            help="School slug or subdomain token (e.g. st-jude).",
        )
        parser.add_argument(
            "--slug",
            dest="slug_flag",
            default="",
            help="Alternate way to pass slug.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School, SchoolProvisioningEvent, SignupVerification
        from apps.schools.pending_tenant_discovery import (
            lookup_school_by_slug_or_subdomain,
            pending_school_state,
        )
        from apps.schools.signup_completion_notifications import signup_completion_was_delivered

        token = (options.get("slug") or options.get("slug_flag") or "").strip()
        if not token:
            raise CommandError("Pass a slug, e.g. python manage.py triage_signup_school st-jude")

        school = lookup_school_by_slug_or_subdomain(token)
        if school is None:
            near = list(
                School.objects.filter(
                    Q(slug__icontains=token) | Q(subdomain__icontains=token)
                )
                .order_by("-created_at")[:5]
                .values_list("slug", "subdomain", "is_active")
            )
            self.stdout.write(self.style.ERROR(f"No school matched slug/subdomain {token!r}."))
            if near:
                self.stdout.write("Similar slugs:")
                for slug, subdomain, active in near:
                    self.stdout.write(f"  - {slug} (subdomain={subdomain}, active={active})")
            self.stdout.write(
                "Recovery: confirm signup completed; owner may need to re-register "
                "or operator creates school from /super/signup/."
            )
            return

        verif = (
            SignupVerification.objects.filter(school=school)
            .order_by("-created_at")
            .first()
        )
        pending = pending_school_state(school)
        notify_state = (getattr(school, "settings", None) or {}).get(
            "signup_completion_notifications", {}
        )
        events = list(
            SchoolProvisioningEvent.objects.filter(school=school)
            .order_by("-created_at")[:8]
            .values("event_type", "status", "message", "payload", "created_at")
        )
        failed = (
            SchoolProvisioningEvent.objects.filter(
                school=school, event_type="FAILED"
            )
            .order_by("-created_at")
            .first()
        )

        self.stdout.write(self.style.SUCCESS(f"School: {school.name} ({school.slug})"))
        self.stdout.write(f"  id={school.pk} subdomain={school.subdomain!r} is_active={school.is_active}")
        self.stdout.write(f"  pending_state={pending or 'live'}")
        if verif:
            self.stdout.write(
                f"  verification: email={verif.email!r} verified_at={verif.verified_at}"
            )
        else:
            self.stdout.write("  verification: none")

        self.stdout.write(
            f"  portal_ready_email_delivered={signup_completion_was_delivered(school)}"
        )
        if notify_state:
            self.stdout.write(f"  notification_state={notify_state}")

        if events:
            self.stdout.write("  recent_provisioning_events:")
            for row in events:
                err = ""
                payload = row.get("payload") or {}
                if isinstance(payload, dict) and payload.get("error"):
                    err = f" error={payload.get('error')!r}"
                self.stdout.write(
                    f"    - {row['created_at']} {row['event_type']} "
                    f"({row['status']}) {row['message'] or ''}{err}"
                )
        if failed is not None:
            payload = getattr(failed, "payload", None) or {}
            if isinstance(payload, dict) and payload.get("error"):
                self.stdout.write(
                    self.style.ERROR(f"  last_failure: {payload.get('error')}")
                )

        try:
            from django.conf import settings
            from django.db import connection

            self.stdout.write(
                f"  runtime: USE_DJANGO_TENANTS={getattr(settings, 'USE_DJANGO_TENANTS', False)} "
                f"db={connection.vendor}"
            )
            if connection.vendor != "postgresql" and getattr(
                settings, "USE_DJANGO_TENANTS", False
            ):
                self.stdout.write(
                    self.style.WARNING(
                        "  django-tenants requires PostgreSQL on Render — "
                        "SQLite dev skips Client/schema creation."
                    )
                )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

        if not school.is_active:
            if verif and verif.verified_at:
                self.stdout.write(
                    self.style.WARNING(
                        "Recovery: python manage.py activate_pending_signup_schools "
                        f"--slug={school.slug}"
                    )
                )
            elif verif:
                self.stdout.write(
                    self.style.WARNING(
                        "Owner must verify email first "
                        "(resend: /verify-signup/resend/ on runmycampus.com)."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("No SignupVerification row — signup may be incomplete.")
                )
        elif not signup_completion_was_delivered(school):
            self.stdout.write(
                self.style.WARNING(
                    "Portal is live but welcome email not confirmed — operator resend from "
                    "/super/signup/verifications/ or notify_tenant_signup_completed(force=True)."
                )
            )
