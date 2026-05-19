"""MAA v2.0 re-sign campaign mgmt command (v3.35.0 Agent 3).

Sends (or, in dry-run mode, simulates sending) the
``maa_v2_resign_request`` email to every operator who signed a v1.0
MigrationAuthorizationAgreement before the v2.0 flip-date and has
not yet signed v2.0.

Usage::

    python manage.py maa_v2_resign_campaign                # dry-run by default
    python manage.py maa_v2_resign_campaign --apply        # queue real sends
    python manage.py maa_v2_resign_campaign --tenant <slug>
    python manage.py maa_v2_resign_campaign --limit 100

Safety design
-------------

  * DRY-RUN by default. ``--apply`` must be passed explicitly to
    enqueue real ``send_mail`` calls. Both modes write
    ``MigrationCloudMAACampaignNotification`` rows (with
    ``dispatch_mode='dry_run'`` or ``'queued'``) so the audit trail is
    consistent across operator runs.
  * Idempotent: re-running with the same campaign version skips
    recipients already recorded for that campaign (the
    UniqueConstraint on
    ``(agreement, recipient_email, campaign_version)`` enforces this
    at the DB level). Operators can run the command daily without
    double-sending.
  * NEVER logs MAA body content (``signature_text``). Only counts +
    recipient-domain summaries + agreement PKs.
  * ``--apply`` calls ``send_mail`` directly; we explicitly do NOT
    swap in a "bulk-mass-mail" provider here. send_mail is throttled
    by the platform email backend; mass sends are still rate-limited
    upstream.

Resolution of recipients
------------------------

For each candidate ``MigrationAuthorizationAgreement`` row:

  1. ``recipient_email`` = ``agreement.signed_by_user.email`` if set,
     else skip (no addressable recipient).
  2. The ``--tenant`` flag accepts a tenant ``subdomain`` (preferred)
     or a numeric PK. Resolution is best-effort; unknown tenants
     fail-fast with ``CommandError``.

A candidate is skipped if any of:

  * ``agreement_version != "v1.0"`` (we only ask v1.0 signers to re-sign)
  * The same ``signed_by_user`` already has a v2.0 row for the same
    ``(tenant, vendor_source)``
  * A ``MigrationCloudMAACampaignNotification`` exists for the
    ``(agreement, recipient_email, campaign_version)`` triple
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


# Stable campaign identifier. Bump on a future re-sign campaign so the
# unique constraint on (agreement, recipient_email, campaign_version)
# can let a fresh round of notifications coexist with prior ones.
CAMPAIGN_VERSION_DEFAULT = "maa_v2_resign_2026Q3"

# Subject is fixed (matches docs/MAA_V2_PROMOTION_CHECKLIST.md § 1.4
# guidance — "Action requested: ..."). i18n is honoured by the
# template engine when the message body is rendered.
EMAIL_SUBJECT = (
    "Action requested: re-sign Migration Authorization Agreement (v2.0)"
)

EMAIL_TEMPLATE_TXT = "migration_cloud/email/maa_v2_resign_request.txt"
EMAIL_TEMPLATE_HTML = "migration_cloud/email/maa_v2_resign_request.html"


class Command(BaseCommand):
    """Drive the MAA v2.0 re-sign campaign in dry-run or queued mode."""

    help = (
        "Email v1.0 MAA signers to re-sign v2.0. Dry-run by default. "
        "Idempotent across runs."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually call send_mail for each recipient. Without "
                "this flag the command runs in dry-run mode (rows "
                "logged as 'dry_run', no email sent)."
            ),
        )
        parser.add_argument(
            "--tenant",
            default="",
            help=(
                "Restrict to one tenant (by subdomain or numeric PK). "
                "Default is platform-wide."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help=(
                "Cap the per-run dispatch count. 0 (default) = no cap. "
                "Useful for partial campaigns or test runs."
            ),
        )
        parser.add_argument(
            "--campaign-version",
            default=CAMPAIGN_VERSION_DEFAULT,
            help=(
                "Override the campaign identifier (idempotency key). "
                f"Default: {CAMPAIGN_VERSION_DEFAULT!r}."
            ),
        )

    # ------------------------------------------------------------------ helpers

    def _resolve_tenant(self, tenant_arg: str):
        """Return a single School row or None for platform-wide.

        Raises ``CommandError`` if the operator passed an arg that does
        not resolve to a known tenant.
        """
        if not tenant_arg:
            return None
        try:
            from apps.schools.models import School
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                "apps.schools.School is not importable; cannot resolve --tenant"
            ) from exc
        qs = School.objects.all()
        if tenant_arg.isdigit():
            row = qs.filter(pk=int(tenant_arg)).first()
        else:
            row = qs.filter(subdomain=tenant_arg).first()
        if row is None:
            raise CommandError(f"--tenant {tenant_arg!r} did not resolve to a School row")
        return row

    def _candidate_queryset(self, tenant) -> Any:
        """Return queryset of v1.0 MAA rows eligible for re-sign mail."""
        from apps.migration_cloud.models import MigrationAuthorizationAgreement

        # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
        qs = MigrationAuthorizationAgreement.objects.filter(
            agreement_version="v1.0",
            revoked_at__isnull=True,
        ).select_related("signed_by_user", "tenant")
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        return qs.order_by("pk")

    def _already_signed_v2(self, agreement) -> bool:
        """Check whether the same signer already re-signed v2.0 for same vendor.

        Cross-tenant audit query is intentional — a signer who covers
        multiple tenants only needs to re-sign once per
        (tenant, vendor_source) pair.
        """
        from apps.migration_cloud.models import MigrationAuthorizationAgreement

        # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
        return MigrationAuthorizationAgreement.objects.filter(
            tenant_id=agreement.tenant_id,
            vendor_source=agreement.vendor_source,
            signed_by_user_id=agreement.signed_by_user_id,
            agreement_version="v2.0",
            revoked_at__isnull=True,
        ).exists()

    def _already_notified(self, agreement, recipient_email, campaign_version) -> bool:
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )

        # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
        return MigrationCloudMAACampaignNotification.objects.filter(
            agreement=agreement,
            recipient_email=recipient_email,
            campaign_version=campaign_version,
        ).exists()

    def _resign_url(self) -> str:
        """Return the URL operators land on to re-sign v2.0.

        Resolves through ``reverse`` so a future URL rename doesn't
        leave a stale string in the email. Falls back to a stable
        relative path if URL resolution fails (e.g. portal-only deploy).
        """
        try:
            return reverse("migration_cloud_portal:companion_maa_sign")
        except NoReverseMatch:
            try:
                return reverse("migration_cloud_super:companion_maa_sign")
            except NoReverseMatch:
                return "/portal/configure/migration/companion/maa/sign/"

    def _render_email(
        self, agreement, recipient_email, campaign_version, resign_url
    ) -> tuple[str, str]:
        """Render (text, html) bodies for one recipient.

        We deliberately do NOT pass MAA ``signature_text`` into the
        template context — leaking it in a transactional email would
        widen the disclosure boundary that lives only on the sign
        page. The email links to the sign UI which is the appropriate
        place to display the full body.
        """
        ctx = {
            "recipient_name": (
                getattr(agreement.signed_by_user, "get_full_name", lambda: "")()
                or getattr(agreement.signed_by_user, "username", "")
            ),
            "recipient_email": recipient_email,
            "agreement_id": agreement.pk,
            "campaign_version": campaign_version,
            "resign_url": resign_url,
        }
        text_body = render_to_string(EMAIL_TEMPLATE_TXT, ctx)
        html_body = render_to_string(EMAIL_TEMPLATE_HTML, ctx)
        return text_body, html_body

    def _record_notification(
        self,
        agreement,
        recipient_email: str,
        campaign_version: str,
        dispatch_mode: str,
    ) -> None:
        from apps.migration_cloud.models import (
            MigrationCloudMAACampaignNotification,
        )

        # tenant-isolation-allow: cross-tenant-maa-campaign-tracking
        MigrationCloudMAACampaignNotification.objects.create(
            agreement=agreement,
            recipient_email=recipient_email,
            campaign_version=campaign_version,
            dispatch_mode=dispatch_mode,
        )

    # ----------------------------------------------------------------- handle

    def handle(self, *args: Any, **options: Any) -> None:
        apply_flag: bool = bool(options.get("apply"))
        tenant_arg: str = (options.get("tenant") or "").strip()
        limit: int = int(options.get("limit") or 0)
        campaign_version: str = options.get("campaign_version") or CAMPAIGN_VERSION_DEFAULT
        mode = "queued" if apply_flag else "dry_run"

        tenant = self._resolve_tenant(tenant_arg)
        resign_url = self._resign_url()
        from_email = getattr(
            settings, "DEFAULT_FROM_EMAIL", "no-reply@runmycampus.com",
        )

        candidates = self._candidate_queryset(tenant)
        scanned = 0
        emitted = 0
        skipped_no_email = 0
        skipped_already_signed_v2 = 0
        skipped_already_notified = 0
        errors = 0
        capped = False
        sample_subject = EMAIL_SUBJECT

        for agreement in candidates.iterator():
            scanned += 1
            if limit and emitted >= limit:
                capped = True
                break

            user = agreement.signed_by_user
            recipient_email = (getattr(user, "email", "") or "").strip()
            if not recipient_email:
                skipped_no_email += 1
                continue
            if self._already_signed_v2(agreement):
                skipped_already_signed_v2 += 1
                continue
            if self._already_notified(agreement, recipient_email, campaign_version):
                skipped_already_notified += 1
                continue

            try:
                text_body, html_body = self._render_email(
                    agreement, recipient_email, campaign_version, resign_url,
                )
            except Exception:  # noqa: BLE001
                # Defensive: a bad recipient_name or template misload
                # should not nuke the batch. Count + continue.
                errors += 1
                logger.warning(
                    "maa_v2_resign_campaign_render_failed agreement_pk=%s "
                    "campaign=%s mode=%s",
                    agreement.pk, campaign_version, mode,
                )
                continue

            if apply_flag:
                try:
                    send_mail(
                        subject=EMAIL_SUBJECT,
                        message=text_body,
                        from_email=from_email,
                        recipient_list=[recipient_email],
                        html_message=html_body,
                        fail_silently=False,
                    )
                except Exception:  # noqa: BLE001
                    errors += 1
                    logger.warning(
                        "maa_v2_resign_campaign_send_failed agreement_pk=%s "
                        "campaign=%s",
                        agreement.pk, campaign_version,
                    )
                    continue

            try:
                with transaction.atomic():
                    self._record_notification(
                        agreement, recipient_email, campaign_version, mode,
                    )
            except Exception:  # noqa: BLE001
                # A concurrent operator run may have raced us; the
                # unique constraint will trip. We treat that as
                # "already notified" rather than an error.
                skipped_already_notified += 1
                continue

            emitted += 1

        summary = {
            "scanned": scanned,
            "emitted": emitted,
            "mode": mode,
            "campaign_version": campaign_version,
            "skipped_no_email": skipped_no_email,
            "skipped_already_signed_v2": skipped_already_signed_v2,
            "skipped_already_notified": skipped_already_notified,
            "errors": errors,
            "capped_by_limit": bool(capped),
            "tenant_arg": tenant_arg or "(platform-wide)",
            "sample_subject": sample_subject,
        }
        logger.info(
            "maa_v2_resign_campaign_done mode=%s campaign=%s scanned=%s "
            "emitted=%s skipped_no_email=%s skipped_already_signed_v2=%s "
            "skipped_already_notified=%s errors=%s capped=%s",
            mode, campaign_version, scanned, emitted, skipped_no_email,
            skipped_already_signed_v2, skipped_already_notified, errors,
            capped,
        )
        styler = self.style.SUCCESS if mode == "queued" else self.style.WARNING
        self.stdout.write(
            styler(
                f"[maa_v2_resign_campaign:{mode}] "
                f"scanned={summary['scanned']} "
                f"emitted={summary['emitted']} "
                f"skipped_no_email={summary['skipped_no_email']} "
                f"skipped_already_signed_v2={summary['skipped_already_signed_v2']} "
                f"skipped_already_notified={summary['skipped_already_notified']} "
                f"errors={summary['errors']} "
                f"capped={summary['capped_by_limit']} "
                f"campaign={summary['campaign_version']} "
                f"tenant={summary['tenant_arg']}"
            )
        )
        self.stdout.write(
            f"  sample subject: {summary['sample_subject']!r}"
        )
        if mode == "dry_run":
            self.stdout.write(
                "  DRY-RUN: no emails actually sent. Pass --apply to "
                "enqueue real sends."
            )
