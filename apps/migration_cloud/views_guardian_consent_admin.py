"""School-staff (tenant-scoped) guardian-consent admin views (v3.40.0 Agent 11).

These views are NOT anonymous — they are for the school's own staff
who issued the consent campaign. Tenant-isolated; cross-tenant lookups
return 404 (NOT 403) to avoid leaking the existence of intake UUIDs.

URL grammar (mounted under ``/migration/<uuid:intake_id>/consent/``):

    /migration/<intake_id>/consent/                       — status dashboard
    /migration/<intake_id>/consent/campaign/start/        — bulk-mint via CSV
    /migration/<intake_id>/consent/<uuid:token_id>/resend/ — resend email

Defense layers:

  * LoginRequiredMixin + ``_intake_for_request`` tenant scope on every
    queryset.
  * CSV ≤2000 rows enforced before any DB write.
  * Email queued via Django's ``send_mail`` with fail_silently=False
    inside try/except — a transport failure does NOT roll back the
    mint (campaign progress is captured in the DB).
  * Resend cooldown 24h per token AND hard max 3 sends per token.
  * NEVER logged: CSV body, guardian_email, guardian_name, raw token.
  * Bad CSV rows surface their line number but NOT the email/name —
    counsel-defensible error surface.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import timedelta
from typing import Optional
from uuid import UUID

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from .models_guardian_consent import (
    GuardianConsentDecision,
    GuardianConsentToken,
)
from .views_customer import _intake_for_request  # reuses Agent 7's tenant resolver
from .views_guardian_consent import (
    DEFAULT_CONSENT_TEXT_VERSION,
    _render_consent_text,
)

logger = logging.getLogger(__name__)


# ─── Constants ──────────────────────────────────────────────────────────


CSV_ROW_CAP = 2000
RESEND_COOLDOWN_HOURS = 24
RESEND_MAX = 3
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ─── Helpers ────────────────────────────────────────────────────────────


def _safe_audit(
    *,
    tenant,
    event_type: str,
    subject: str,
    payload: Optional[dict] = None,
) -> None:
    """Best-effort audit emit; never raises into the view layer."""
    try:
        from .models_audit import MigrationCloudAuditEvent
        tenant_slug = getattr(tenant, "slug", "") or ""
        MigrationCloudAuditEvent.objects.record(
            tenant_slug,
            event_type,
            subject=subject,
            payload_summary=payload or {},
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break flow
        logger.warning(
            "migration_cloud.guardian_consent_admin: audit emit failed "
            "event=%s err=%s",
            event_type, type(exc).__name__,
        )


def _from_address() -> str:
    return getattr(
        settings, "MIGRATION_CLOUD_INTAKE_FROM_EMAIL",
        getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@runmycampus.com"),
    )


def _send_consent_email(
    *,
    token: GuardianConsentToken,
    raw_token: str,
    template_base: str,
    subject: str,
    school_name: str,
) -> bool:
    """Send a consent-request / reminder / confirmation email.

    Returns True on send-success. NEVER raises. NEVER logs the raw
    token, the guardian email, or the guardian name.
    """
    subject = subject[:80]  # hard cap; NO PII in subject (counsel rule)
    # The unique consent URL embeds the raw token directly. The link
    # is the credential. Email body is the ONLY place the raw token
    # ever appears outside of the mint() return value.
    consent_path = reverse(
        "migration_guardian_consent:guardian-consent-landing",
        kwargs={"raw_token": raw_token},
    )
    public_host = getattr(
        settings, "MIGRATION_CLOUD_PUBLIC_HOSTNAME", ""
    ) or ""
    consent_url = (
        f"{public_host.rstrip('/')}{consent_path}" if public_host else consent_path
    )
    context = {
        # Student-first-name only — vendor extractors write a stripped
        # display value into student_external_id only as a fallback;
        # we don't have the student's full identifier here by design.
        "guardian_first_name": (token.guardian_name or "").split(" ", 1)[0][:64],
        "school_name": school_name[:256],
        "consent_url": consent_url,
        "expires_at": token.expires_at,
    }
    try:
        text_body = render_to_string(
            f"migration_cloud/emails/guardian/{template_base}.txt", context,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.guardian_consent_admin: email_render_txt_failed "
            "template=%s err=%s",
            template_base, type(exc).__name__,
        )
        return False
    try:
        html_body = render_to_string(
            f"migration_cloud/emails/guardian/{template_base}.html", context,
        )
    except Exception:  # noqa: BLE001 — html optional
        html_body = None
    try:
        # Precedence: bulk is signalled to upstream MTAs via the
        # `headers` field on EmailMultiAlternatives, but send_mail
        # doesn't expose that surface — we keep send_mail for parity
        # with Agent 7's signal flow. Honest deferred: bulk header.
        send_mail(
            subject=subject,
            message=text_body,
            from_email=_from_address(),
            recipient_list=[token.guardian_email],
            html_message=html_body,
            fail_silently=False,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — never break the campaign
        logger.warning(  # pii-logging-smell-allow: sha256-prefix-not-raw-token
            "migration_cloud.guardian_consent_admin: email_send_failed "
            "template=%s token_sha_prefix=%s err=%s",
            template_base, (token.token_sha256 or "")[:8], type(exc).__name__,
        )
        return False


def _parse_csv_row(row: list[str]) -> Optional[tuple[str, str, str]]:
    """Parse + validate a CSV row. Returns ``(sid, name, email)`` or None.

    NEVER returns a partially-valid row; callers should surface the
    *line number* (not the contents) on failure.
    """
    if len(row) < 3:
        return None
    sid = (row[0] or "").strip()[:128]
    name = (row[1] or "").strip()[:256]
    email = (row[2] or "").strip()[:254]
    if not sid or not name or not email:
        return None
    if not _EMAIL_RE.match(email):
        return None
    return sid, name, email


# ─── Operator views ──────────────────────────────────────────────────────


@method_decorator(csrf_protect, name="dispatch")
class GuardianConsentCampaignStartView(LoginRequiredMixin, View):
    """GET shows the upload form; POST processes the CSV + mints tokens."""

    template_name = "migration_cloud/customer/consent_campaign_start.html"

    def get(self, request: HttpRequest, intake_id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, intake_id)
        return render(request, self.template_name, {"intake": intake})

    def post(self, request: HttpRequest, intake_id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, intake_id)
        upload = request.FILES.get("csv_file")
        if upload is None:
            return HttpResponseBadRequest("csv_file upload required")
        # Cap upload size defensively at ~2MB before parsing.
        if upload.size and upload.size > 2 * 1024 * 1024:
            return HttpResponseBadRequest(
                f"csv_file exceeds 2MB cap ({upload.size} bytes)"
            )
        try:
            raw_bytes = upload.read()
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "migration_cloud.guardian_consent_admin: csv_read_failed "
                "intake_id=%s err=%s",
                intake.id, type(exc).__name__,
            )
            return HttpResponseBadRequest("csv_file could not be decoded as UTF-8")

        # stdlib csv.reader — stream-parse via StringIO. NO pandas.
        reader = csv.reader(io.StringIO(text))
        # Pre-validate row cap (count + 1 for header tolerance).
        all_rows = list(reader)
        # Trim leading header row if present (heuristic: first row's
        # first cell is non-numeric AND second cell contains "name").
        if all_rows and len(all_rows[0]) >= 3 and "name" in (all_rows[0][1] or "").lower():
            data_rows = all_rows[1:]
        else:
            data_rows = all_rows
        if len(data_rows) > CSV_ROW_CAP:
            return HttpResponseBadRequest(
                f"CSV exceeds row cap of {CSV_ROW_CAP} rows"
            )

        # Active consent text — version + sha256 captured at mint time.
        version = getattr(
            settings,
            "MIGRATION_CLOUD_GUARDIAN_CONSENT_ACTIVE_VERSION",
            DEFAULT_CONSENT_TEXT_VERSION,
        )
        consent_text = _render_consent_text(version)
        school_name = getattr(intake.tenant, "name", "") or "your school"

        minted: list[GuardianConsentToken] = []
        bad_line_numbers: list[int] = []
        for line_no, row in enumerate(data_rows, start=1):
            parsed = _parse_csv_row(row)
            if parsed is None:
                bad_line_numbers.append(line_no)
                continue
            sid, name, email = parsed
            try:
                raw_token, instance = GuardianConsentToken.mint(
                    intake=intake,
                    student_external_id=sid,
                    guardian_name=name,
                    guardian_email=email,
                    consent_text_version=version,
                    consent_text=consent_text,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "migration_cloud.guardian_consent_admin: mint_failed "
                    "intake_id=%s line=%s err=%s",
                    intake.id, line_no, type(exc).__name__,
                )
                bad_line_numbers.append(line_no)
                continue
            _send_consent_email(
                token=instance,
                raw_token=raw_token,
                template_base="consent_request",
                subject="Action requested: review and respond",
                school_name=school_name,
            )
            instance._safe_audit("migration.guardian_consent.minted")
            minted.append(instance)
            # Discard raw_token from local scope immediately. The
            # `_send_consent_email` call has already used it.
            del raw_token

        # Update intake required-count (set, do NOT increment — operator
        # is re-baselining the campaign with this CSV).
        intake.guardian_consent_required_count = len(minted)
        intake.save(update_fields=[
            "guardian_consent_required_count", "updated_at",
        ])

        _safe_audit(
            tenant=intake.tenant,
            event_type="migration.guardian_consent.campaign_started",
            subject=str(intake.id),
            payload={
                "minted_count": len(minted),
                "bad_row_count": len(bad_line_numbers),
                "intake_id_prefix": str(intake.id)[:8],
            },
        )

        context = {
            "intake": intake,
            "minted_count": len(minted),
            "bad_line_numbers": bad_line_numbers[:50],  # cap surface
            "bad_line_count": len(bad_line_numbers),
        }
        return render(
            request,
            "migration_cloud/customer/consent_campaign_start.html",
            context,
        )


class GuardianConsentCampaignStatusView(LoginRequiredMixin, View):
    """Status dashboard for a campaign."""

    template_name = "migration_cloud/customer/consent_campaign_status.html"

    def get(self, request: HttpRequest, intake_id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, intake_id)
        # tenant-isolation-allow: guardian-consent-admin-status-list-by-intake-of-tenant
        qs = GuardianConsentToken.objects.filter(
            intake_request=intake, tenant=intake.tenant,
        )
        totals = {
            "total": qs.count(),
            "pending": qs.filter(
                consent_decision=GuardianConsentDecision.PENDING.value,
            ).count(),
            "consented": qs.filter(
                consent_decision=GuardianConsentDecision.CONSENTED.value,
            ).count(),
            "declined": qs.filter(
                consent_decision=GuardianConsentDecision.DECLINED.value,
            ).count(),
            "expired": qs.filter(
                consent_decision=GuardianConsentDecision.EXPIRED.value,
            ).count(),
        }
        # "Stuck" tokens: issued >7d ago, no first-seen, still pending.
        cutoff = timezone.now() - timedelta(days=7)
        # tenant-isolation-allow: guardian-consent-admin-stuck-list-by-intake-of-tenant
        stuck = list(
            qs.filter(
                consent_decision=GuardianConsentDecision.PENDING.value,
                token_first_seen_at__isnull=True,
                token_issued_at__lt=cutoff,
            ).order_by("token_issued_at")[:25]
        )
        # Latest 50 tokens for the table.
        recent = list(qs.order_by("-token_issued_at")[:50])
        context = {
            "intake": intake,
            "totals": totals,
            "stuck": stuck,
            "recent": recent,
            "resend_cooldown_hours": RESEND_COOLDOWN_HOURS,
            "resend_max": RESEND_MAX,
        }
        return render(request, self.template_name, context)


@method_decorator(csrf_protect, name="dispatch")
class GuardianConsentResendView(LoginRequiredMixin, View):
    """POST: resend the consent-request email. Throttled."""

    def post(
        self,
        request: HttpRequest,
        intake_id: str,
        token_id: str,
        *args,
        **kwargs,
    ) -> HttpResponse:
        intake = _intake_for_request(request, intake_id)
        try:
            parsed_token_id = UUID(str(token_id))
        except (ValueError, TypeError) as exc:
            raise Http404("token not found") from exc
        # tenant-isolation-allow: guardian-consent-admin-resend-tenant-scoped-on-intake-of-tenant
        token = (
            GuardianConsentToken.objects
            .filter(id=parsed_token_id, intake_request=intake, tenant=intake.tenant)
            .first()
        )
        if token is None:
            raise Http404("token not found")
        if token.is_decided:
            return HttpResponseBadRequest("token already decided; cannot resend")
        if token.resend_count >= RESEND_MAX:
            return HttpResponseBadRequest(
                f"resend cap reached ({RESEND_MAX} max)"
            )
        if token.last_resend_at is not None:
            elapsed = timezone.now() - token.last_resend_at
            cooldown = timedelta(hours=RESEND_COOLDOWN_HOURS)
            if elapsed < cooldown:
                return HttpResponseBadRequest(
                    f"resend cooldown active ({RESEND_COOLDOWN_HOURS}h between sends)"
                )
        # We do NOT have the raw token any longer; we cannot resend the
        # original URL because we never stored it. The resend therefore
        # *rotates* the token: mint a fresh raw_token, persist its new
        # sha256, send the new URL. The original token row is replaced
        # in-place — sha256 is the only persisted form so this is safe.
        import secrets as _secrets
        from .models_guardian_consent import _sha256_hex
        new_raw = _secrets.token_urlsafe(32)
        token.token_sha256 = _sha256_hex(new_raw)
        token.resend_count = (token.resend_count or 0) + 1
        token.last_resend_at = timezone.now()
        token.save(update_fields=[
            "token_sha256", "resend_count", "last_resend_at", "updated_at",
        ])
        sent_ok = _send_consent_email(
            token=token,
            raw_token=new_raw,
            template_base="consent_reminder",
            subject="Reminder: action requested",
            school_name=getattr(intake.tenant, "name", "") or "your school",
        )
        del new_raw  # discard raw token immediately
        _safe_audit(
            tenant=intake.tenant,
            event_type="migration.guardian_consent.resent",
            subject=str(token.id),
            payload={
                "intake_id_prefix": str(intake.id)[:8],
                "consent_artifact_prefix": (token.token_sha256 or "")[:8],
                "resend_count": int(token.resend_count),
                "send_ok": bool(sent_ok),
            },
        )
        return redirect(
            "migration_guardian_consent_admin:guardian-consent-campaign-status",
            intake_id=str(intake.id),
        )
