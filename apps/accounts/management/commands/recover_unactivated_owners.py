"""Operator remediation for owners stranded with no usable password.

A self-serve provisioned owner is created with ``set_unusable_password()`` and is
meant to claim the account through a one-time token set-password link. When that
link never lands (mail relay down, expired, wrong address) the owner cannot sign
in AT ALL — every password is checked against an unusable hash and fails, so the
login page just re-renders. This command surfaces those stranded owners across
EVERY tenant and offers two recoveries, one of which needs no working email.

Report (read-only, default) — list every stranded owner platform-wide::

    python manage.py recover_unactivated_owners

Set a TEMP password (email-independent, immediate) for a targeted owner and
print it so the operator can hand it over out-of-band::

    python manage.py recover_unactivated_owners --school new-school --set-temp-password
    python manage.py recover_unactivated_owners --email owner@school.edu --set-temp-password

Email a fresh WORKING set-password link (needs a live mail relay)::

    python manage.py recover_unactivated_owners --school new-school --send-links
    python manage.py recover_unactivated_owners --all --send-links

``--set-temp-password`` refuses to run unscoped unless ``--all`` is given, so an
operator cannot accidentally reset every owner on the platform.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


def _canonical_base_domain() -> str:
    try:
        from apps.schools.host_routing import get_canonical_base_domain

        return (get_canonical_base_domain() or "").strip()
    except Exception:  # noqa: BLE001 — best-effort; falls back to settings below
        return ""


class Command(BaseCommand):
    help = "Find and recover school owners stranded with no usable password."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="",
            help="Target one owner by email OR username (case-insensitive).",
        )
        parser.add_argument(
            "--school",
            default="",
            help="Target owners of one school by slug.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Act on every stranded owner (required for an unscoped --set-temp-password).",
        )
        parser.add_argument(
            "--set-temp-password",
            action="store_true",
            help="Set a random temp password (+activate) and PRINT it. Email-independent.",
        )
        parser.add_argument(
            "--send-links",
            action="store_true",
            help="Email each targeted owner a one-time set-password link.",
        )

    def handle(self, *args, **opts):
        from apps.schools.models import SchoolMembership

        email = (opts.get("email") or "").strip()
        school = (opts.get("school") or "").strip()
        want_temp = bool(opts.get("set_temp_password"))
        want_links = bool(opts.get("send_links"))
        act_all = bool(opts.get("all"))

        if want_temp and not (email or school or act_all):
            raise CommandError(
                "--set-temp-password needs a target: pass --email, --school, or --all."
            )

        qs = (
            SchoolMembership.objects.filter(
                is_school_owner=True, user__is_active=True
            )
            .select_related("user", "school")
            .order_by("school__name")
        )
        if email:
            qs = qs.filter(
                Q(user__email__iexact=email) | Q(user__username__iexact=email)
            )
        if school:
            qs = qs.filter(school__slug=school)

        # Dedupe by user (an owner can own several schools); keep the schools list.
        stranded: dict[int, dict] = {}
        for ms in qs:
            user = ms.user
            if user is None or user.has_usable_password():
                continue
            row = stranded.setdefault(
                user.pk, {"user": user, "schools": []}
            )
            row["schools"].append(getattr(ms.school, "slug", "") or str(ms.school_id))

        if not stranded:
            self.stdout.write(
                self.style.SUCCESS("No stranded owners match (nothing to recover).")
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"Found {len(stranded)} stranded owner(s) with no usable password:"
            )
        )
        for row in stranded.values():
            user = row["user"]
            last = getattr(user, "last_login", None)
            self.stdout.write(
                f"  • {user.get_username()}  <{user.email or '—'}>  "
                f"schools={','.join(row['schools']) or '—'}  "
                f"last_login={last.isoformat() if last else 'never'}"
            )

        if not (want_temp or want_links):
            self.stdout.write(
                "\nReport only. Re-run with --set-temp-password (email-independent) "
                "or --send-links to remediate."
            )
            return

        temp_set = links_sent = 0
        for row in stranded.values():
            user = row["user"]
            if want_temp:
                temp = f"Rmc-{secrets.token_urlsafe(9)}"  # magic-number-allow: temp-token-byte-length
                user.set_password(temp)
                if not user.is_active:
                    user.is_active = True
                user.save(update_fields=["password", "is_active"])
                temp_set += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  set temp password for {user.get_username()} "
                        f"<{user.email or '—'}>: {temp}"
                    )
                )
            if want_links:
                if self._send_link(user):
                    links_sent += 1
                    self.stdout.write(
                        f"  emailed set-password link to {user.email or user.get_username()}"
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  could not email {user.email or user.get_username()} "
                            "(no email or relay error)"
                        )
                    )

        summary = []
        if want_temp:
            summary.append(f"{temp_set} temp password(s) set")
        if want_links:
            summary.append(f"{links_sent} link(s) emailed")
        self.stdout.write(self.style.SUCCESS("\nDone: " + ", ".join(summary) + "."))
        if want_temp:
            self.stdout.write(
                "Hand each temp password to its owner OUT-OF-BAND; they should "
                "change it (and set up MFA) on first sign-in."
            )

    def _send_link(self, user) -> bool:
        """Email a set-password link without a live request (uses domain_override)."""
        email = (getattr(user, "email", "") or "").strip()
        if not email:
            return False
        domain = _canonical_base_domain() or getattr(
            settings, "MULTI_TENANT_BASE_DOMAIN", ""
        )
        domain = (domain or "runmycampus.com").replace("https://", "").replace(
            "http://", ""
        ).strip("/")
        try:
            from apps.accounts.password_reset import PortalPasswordResetForm

            form = PortalPasswordResetForm(data={"email": email})
            if not form.is_valid():
                return False
            form.save(
                domain_override=domain,
                use_https=True,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                email_template_name="emails/password_reset.txt",
                html_email_template_name="emails/password_reset.html",
                subject_template_name="registration/password_reset_subject.txt",
            )
            return True
        except Exception:  # noqa: BLE001 — a delivery error must not abort the sweep
            return False
