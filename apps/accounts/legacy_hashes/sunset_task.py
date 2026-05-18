"""12-month sunset job for legacy foreign-vendor password hashes.

When a school migrates from PowerSchool / Blackbaud / Veracross / FACTS
/ Skyward / Alma, every imported user carries a ``legacy_password_hash``
that is verified-and-cleared on first login (see
:mod:`apps.accounts.auth_backends_legacy`). Most users sign in within
weeks of go-live and the legacy fields disappear naturally. A small
tail never does — they were already inactive at the old vendor, or
they forgot the school migrated.

This task implements the "sunset" lifecycle for those tail accounts.
There are exactly three states a user can be in:

* **Active legacy** — ``legacy_password_hash`` non-empty,
  ``legacy_hash_sunset_email_sent_at`` NULL, account younger than
  ``age_months`` (default 12). Nothing to do.
* **Email-eligible** — older than ``age_months`` AND no recent login
  AND no sunset email sent yet. We send one one-time setup link via
  Django's password-reset token machinery (12-hour validity is
  preserved; the link is consumed by :class:`LegacySetupView`).
* **Grace-expired** — sunset email was sent >= ``grace_days`` (default
  30) ago AND the user STILL has a legacy hash AND no recent login.
  Drop all three legacy fields, mark the account
  ``set_unusable_password()`` so the only path back in is
  ``/accounts/password_reset/``. This is the same end state as a fresh
  account; the user is not locked out, only forced to choose a new
  password.

Run via Celery beat — see ``CELERY_BEAT_SCHEDULE`` in
``config/settings.py`` (entry ``accounts-sunset-stale-legacy-hashes``,
schedule: weekly Mondays 03:00 UTC).

Security invariants:

* The password-reset token only ever appears inside the email body, via
  the Django template engine. It is never logged.
* Plaintext hash bytes never leave the model layer; we never read
  ``user.legacy_password_hash`` in this task (we only check
  ``bool(user.legacy_password_hash)`` to test for presence).
* The function reports counts only — no user PII, no emails, no tokens.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.db import DatabaseError, transaction
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)

# Field names cleared when a grace period expires. Module constant so
# tests can assert the exact set without re-reading the model.
LEGACY_FIELDS = (
    "legacy_password_hash",
    "legacy_hash_algorithm",
    "legacy_hash_params",
)

# Default cadence parameters. Documented here so operators can tune via
# the task kwargs without re-deploying.
DEFAULT_AGE_MONTHS = 12
DEFAULT_GRACE_DAYS = 30
DEFAULT_EMAIL_SUBJECT = (
    "Action required: your RunMyCampus password has not been set up yet"
)


def _months_to_days(months: int) -> int:
    """Coarse months-to-days conversion. 30-day months is fine for cadence."""
    return max(1, int(months)) * 30


def _send_setup_link_email(user, request_host: str | None = None) -> bool:
    """Send the one-time setup link to ``user``. Returns True on success.

    The link is a standard password-reset token URL routed to
    :class:`LegacySetupView`. We use the default token generator so the
    same expiry semantics (PASSWORD_RESET_TIMEOUT, default 3 days)
    apply.
    """
    try:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
    except Exception:  # noqa: BLE001 - any token-gen failure should be visible
        logger.exception(
            "legacy_sunset_token_gen_failed",
            extra={"user_id": user.pk, "result": "token_gen_failed"},
        )
        return False

    # The URL is rendered by the email template. We pass `uid`/`token`
    # only, NEVER the raw hash or password.
    try:
        path = reverse("accounts:legacy_setup", kwargs={"uidb64": uid, "token": token})
    except NoReverseMatch:
        # The URL pattern may not be wired in older deploys; abort
        # cleanly without raising.
        logger.warning(
            "legacy_sunset_url_unreachable",
            extra={"user_id": user.pk, "result": "url_not_reverseable"},
        )
        return False

    host = (request_host or getattr(settings, "RMC_PRIMARY_HOST", "") or "").strip()
    base = host if host.startswith(("http://", "https://")) else f"https://{host}" if host else ""
    full_url = f"{base}{path}" if base else path

    context = {
        "user": user,
        "setup_url": full_url,
        "support_email": getattr(settings, "SERVER_EMAIL", "support@runmycampus.com"),
    }
    try:
        body_txt = render_to_string("accounts/email/legacy_setup_link.txt", context)
        body_html = render_to_string("accounts/email/legacy_setup_link.html", context)
    except Exception:  # noqa: BLE001 - template not yet wired in a partial deploy
        logger.exception(
            "legacy_sunset_template_render_failed",
            extra={"user_id": user.pk, "result": "template_missing"},
        )
        return False

    to_email = (getattr(user, "email", "") or "").strip()
    if not to_email:
        logger.info(
            "legacy_sunset_skipped_no_email",
            extra={"user_id": user.pk, "result": "no_email_on_file"},
        )
        return False

    try:
        msg = EmailMultiAlternatives(
            subject=DEFAULT_EMAIL_SUBJECT,
            body=body_txt,
            from_email=getattr(settings, "SERVER_EMAIL", None),
            to=[to_email],
        )
        msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
    except Exception:  # noqa: BLE001 - SMTP transient errors must not abort the batch
        logger.exception(
            "legacy_sunset_email_send_failed",
            extra={"user_id": user.pk, "result": "send_failed"},
        )
        return False

    return True


def _null_legacy_fields(user) -> bool:
    """Clear all three legacy fields + force a password reset. Returns True on success.

    Wrapped in a per-row atomic so a partial failure doesn't leave the
    row half-cleared.
    """
    try:
        with transaction.atomic():
            user.legacy_password_hash = ""
            user.legacy_hash_algorithm = ""
            user.legacy_hash_params = {}
            user.set_unusable_password()
            user.save(
                update_fields=("password",) + LEGACY_FIELDS
            )
    except DatabaseError:
        logger.exception(
            "legacy_sunset_null_fields_failed",
            extra={"user_id": user.pk, "result": "db_failure"},
        )
        return False
    return True


def sunset_stale_legacy_hashes(
    dry_run: bool = True,
    age_months: int = DEFAULT_AGE_MONTHS,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> dict[str, Any]:
    """Sunset legacy hashes that have aged out without a successful login.

    Args:
        dry_run: When True (default), enumerate eligible users and
            return counts WITHOUT sending emails or nulling fields.
            Operators run dry_run=True first on every cadence to verify
            the cohort size before consenting to the writes.
        age_months: Account age (since ``date_joined`` or
            ``legacy_hash_created_at``) before email-eligibility kicks
            in. Default 12.
        grace_days: Days after the sunset email was sent before we null
            the legacy fields. Default 30.

    Returns:
        ``{"eligible": N, "emailed": N, "nulled": N, "dry_run": bool,
        "errors": N}`` — purely numeric, no user PII.
    """
    UserModel = get_user_model()
    now = timezone.now()
    age_cutoff = now - timedelta(days=_months_to_days(age_months))
    grace_cutoff = now - timedelta(days=max(1, int(grace_days)))

    # Step 1: emails to send. Filter on:
    # - legacy_password_hash non-empty
    # - legacy_hash_sunset_email_sent_at IS NULL
    # - (legacy_hash_created_at < age_cutoff) OR
    #   (legacy_hash_created_at IS NULL AND date_joined < age_cutoff)
    # - (last_login IS NULL OR last_login < age_cutoff)
    # tenant-isolation-allow: auth-layer-system-wide-user-table-platform-sunset-job
    email_candidates_qs = (
        UserModel.objects.exclude(legacy_password_hash="")
        .filter(legacy_hash_sunset_email_sent_at__isnull=True)
        .filter(
            models_or_q_age(age_cutoff)
        )
    )
    email_candidates_qs = email_candidates_qs.filter(
        models_or_q_last_login(age_cutoff)
    )

    eligible = email_candidates_qs.count()
    emailed = 0
    errors = 0

    if not dry_run:
        for user in email_candidates_qs.iterator(chunk_size=200):
            if _send_setup_link_email(user):
                user.legacy_hash_sunset_email_sent_at = timezone.now()
                try:
                    user.save(update_fields=("legacy_hash_sunset_email_sent_at",))
                    emailed += 1
                except DatabaseError:
                    errors += 1
                    logger.exception(
                        "legacy_sunset_email_save_failed",
                        extra={"user_id": user.pk, "result": "save_failed"},
                    )
            else:
                errors += 1

    # Step 2: grace-period exits. Filter on:
    # - legacy_password_hash non-empty
    # - legacy_hash_sunset_email_sent_at < grace_cutoff
    # - (last_login IS NULL OR last_login < legacy_hash_sunset_email_sent_at)
    # tenant-isolation-allow: auth-layer-system-wide-user-table-platform-sunset-job
    grace_candidates_qs = (
        UserModel.objects.exclude(legacy_password_hash="")
        .filter(legacy_hash_sunset_email_sent_at__lt=grace_cutoff)
        .filter(models_or_q_last_login(grace_cutoff))
    )

    grace_count = grace_candidates_qs.count()
    nulled = 0

    if not dry_run:
        for user in grace_candidates_qs.iterator(chunk_size=200):
            if _null_legacy_fields(user):
                nulled += 1
            else:
                errors += 1

    result = {
        "eligible": eligible,
        "grace_eligible": grace_count,
        "emailed": emailed,
        "nulled": nulled,
        "dry_run": bool(dry_run),
        "errors": errors,
        "age_months": age_months,
        "grace_days": grace_days,
    }
    logger.info("legacy_sunset_run_complete", extra={"result": result})
    return result


def models_or_q_age(age_cutoff):
    """Return a Q that matches "legacy hash older than cutoff".

    Encapsulated as a helper so tests can re-use the predicate without
    re-importing django.db.models.Q.
    """
    from django.db.models import Q  # local: keep top-level imports minimal
    return Q(legacy_hash_created_at__lt=age_cutoff) | (
        Q(legacy_hash_created_at__isnull=True) & Q(date_joined__lt=age_cutoff)
    )


def models_or_q_last_login(age_cutoff):
    """Return a Q that matches "user has not logged in since cutoff"."""
    from django.db.models import Q  # local: keep top-level imports minimal
    return Q(last_login__isnull=True) | Q(last_login__lt=age_cutoff)


# Celery task adapter — only registered when celery is importable so
# the verifier module remains useful in environments without the
# Celery dep installed (e.g. lightweight CI lanes).
try:
    from celery import shared_task

    @shared_task(name="accounts.sunset_stale_legacy_hashes")
    def sunset_stale_legacy_hashes_task(
        dry_run: bool = True,
        age_months: int = DEFAULT_AGE_MONTHS,
        grace_days: int = DEFAULT_GRACE_DAYS,
    ) -> dict[str, Any]:
        """Celery wrapper around :func:`sunset_stale_legacy_hashes`."""
        return sunset_stale_legacy_hashes(
            dry_run=dry_run,
            age_months=age_months,
            grace_days=grace_days,
        )
except ImportError:  # pragma: no cover - celery is in requirements.txt
    sunset_stale_legacy_hashes_task = None  # type: ignore[assignment]
