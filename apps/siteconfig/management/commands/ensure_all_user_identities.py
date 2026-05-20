"""
Backfill portal preferences (and staff TeacherProfile stubs) for every user.

Run after deploy or when upgrading identity bootstrap:
  python manage.py ensure_all_user_identities
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.siteconfig.user_identity import ensure_user_identity

User = get_user_model()


class Command(BaseCommand):
    help = "Ensure UserPreference + DashboardUserPreference (+ staff TeacherProfile) for all users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Only users with is_active=True.",
        )

    def handle(self, *args, **options):
        qs = User.objects.order_by("pk")
        if options.get("active_only"):
            qs = qs.filter(is_active=True)

        total = qs.count()
        prefs_created = 0
        profiles_created = 0

        for user in qs.iterator(chunk_size=200):
            before_portal = hasattr(user, "preferences") and user.preferences
            before_dash = hasattr(user, "dashboard_preferences") and user.dashboard_preferences
            identity = ensure_user_identity(user)
            if identity.get("portal_preference") and not before_portal:
                prefs_created += 1
            if identity.get("people_profile"):
                profiles_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"ensure_all_user_identities: {total} user(s) processed "
                f"(preferences bootstrapped where missing; "
                f"{profiles_created} staff profile(s) ensured)"
            )
        )
