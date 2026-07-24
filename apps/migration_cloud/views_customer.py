"""Customer-facing Migration Cloud intake + status views (v3.40.0 Agent 7).

These views are mounted under ``/migration/`` (NOT under
``/super/migration/`` — that namespace is for RMC operator staff).
ALL views are ``LoginRequiredMixin`` and tenant-scoped: the school's
own staff use their existing tenant credentials. Cross-tenant access
returns ``404`` (NOT ``403``) to avoid leaking the existence of
intake-request UUIDs to a probing attacker.

URL grammar (mounted at ``/migration/`` from ``config/urls.py``):

    /migration/                       — list of this tenant's intakes
    /migration/start/                 — new-intake form (GET) + POST
    /migration/<id>/sign-maa/         — MAA full-text + sign button
    /migration/<id>/status/           — 7-stage progress + audit timeline
    /migration/<id>/abandon/          — POST-only soft-cancel
    /migration/<id>/status/stream/    — SSE progress feed (transport-aware)

Defense layers:

  * Tenant queryset filter on every read — see ``_intake_for_request``.
  * MAA signing path refuses draft versions (mirrors
    ``companion_receiver.MAASignView``).
  * Soft-cancel ``/abandon/`` only valid before extraction starts.
  * NEVER logged: signature_text, counsel_signoff_pdf_url contents,
    MAA full text, school operator notes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional
from uuid import UUID

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_protect

from .models import MigrationAuthorizationAgreement, MigrationCloudAuditEvent
from .models_intake import (
    MigrationIntakeRequest,
    MigrationIntakeState,
    MigrationIntakeStateError,
)
from .services.maa_text import (
    is_draft_version,
    render_maa_text,
    resolve_active_version_for_tenant,
)

logger = logging.getLogger(__name__)


# ─── Tenant resolution + queryset helpers ────────────────────────────────


def _request_tenant(request: HttpRequest):
    """Return the active tenant for the request, or ``None``.

    Mirrors the convention used in ``companion_receiver._request_school``
    so customer views match the existing tenant-scoping pattern.
    """
    school = getattr(request, "school", None) or getattr(request, "tenant", None)
    if school is not None:
        return school
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    membership_mgr = getattr(user, "school_memberships", None)
    if membership_mgr is None:
        return None
    # tenant-isolation-allow: customer-intake-resolve-actor-membership-via-user-fk
    membership = membership_mgr.select_related("school").first()
    return getattr(membership, "school", None) if membership else None


def _tenant_intake_queryset(request: HttpRequest):
    """Return the per-tenant intake queryset, or ``None`` when no tenant.

    Callers MUST treat ``None`` as 404 (anonymous + no tenant attribution
    must not differentiate from "this UUID does not exist for me").
    """
    tenant = _request_tenant(request)
    if tenant is None:
        return None
    # tenant-isolation-allow: customer-intake-tenant-scoped-list-for-school-user
    return MigrationIntakeRequest.objects.filter(tenant=tenant).select_related(
        "tenant", "requested_by_user", "maa_signature",
    )


def _intake_for_request(request: HttpRequest, intake_id: str) -> MigrationIntakeRequest:
    """Look up an intake by ID + tenant; raise 404 on miss.

    Cross-tenant access returns ``404`` rather than ``403`` so an
    attacker probing for live UUIDs gets a uniform response.
    """
    try:
        parsed = UUID(str(intake_id))
    except (ValueError, TypeError) as exc:
        raise Http404("intake not found") from exc
    qs = _tenant_intake_queryset(request)
    if qs is None:
        raise Http404("intake not found")
    intake = qs.filter(id=parsed).first()
    if intake is None:
        raise Http404("intake not found")
    return intake


def _signal_state_change(intake: MigrationIntakeRequest, previous_state: str) -> None:
    """Best-effort dispatch of the state-change signal handler.

    The signal module is wired in ``apps.py::ready()``; we invoke it
    here directly when the receiver opts in. The transition path is
    load-bearing for the customer UX — an email-send failure must NOT
    surface as a 500.
    """
    try:
        from . import signals_intake  # local import to avoid app-load cycles
        signals_intake.dispatch_state_change(intake, previous_state)
    except Exception as exc:  # noqa: BLE001 — never break the transition
        logger.warning(
            "migration_cloud.intake: signal dispatch failed intake_id=%s err=%s",
            intake.id, type(exc).__name__,
        )


# ─── Views ───────────────────────────────────────────────────────────────


@method_decorator(csrf_protect, name="dispatch")
class MigrationIntakeStartView(LoginRequiredMixin, View):
    """GET shows the intake form. POST creates the draft + redirects."""

    template_name = "migration_cloud/customer/intake_start.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        tenant = _request_tenant(request)
        if tenant is None:
            raise Http404("tenant required")
        active_version = resolve_active_version_for_tenant(tenant)
        # Refuse to render if the active version is somehow draft
        # (shouldn't happen — defense-in-depth).
        if is_draft_version(active_version):
            logger.warning(
                "migration_cloud.intake: start refused active_version=%s tenant_pk=%s",
                active_version, getattr(tenant, "pk", None),
            )
            return HttpResponse(
                "Migration intake is temporarily unavailable while the "
                "agreement is being updated. Please contact "
                "partner-success@runmycampus.com.",
                status=503,
            )
        context = {
            "vendor_choices": (
                ("powerschool", "PowerSchool"),
                ("blackbaud", "Blackbaud"),
                ("veracross", "Veracross"),
                ("alma", "Alma"),
                ("facts", "FACTS"),
                ("skyward", "Skyward"),
            ),
            "active_agreement_version": active_version,
            "tenant": tenant,
            "form_action": reverse("migration_intake_customer:migration-intake-start"),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        tenant = _request_tenant(request)
        if tenant is None:
            raise Http404("tenant required")
        vendor = (request.POST.get("vendor_slug") or "").strip().lower()
        ack = request.POST.get("counsel_acknowledgment") == "on"
        notes = (request.POST.get("notes_for_runmycampus_team") or "").strip()[:4000]
        allowed_vendors = {"powerschool", "blackbaud", "veracross", "alma", "facts", "skyward"}
        if vendor not in allowed_vendors:
            return HttpResponseBadRequest("invalid vendor selection")
        if not ack:
            return HttpResponseBadRequest("counsel acknowledgment required")
        # tenant-isolation-allow: customer-intake-tenant-owned-request
        intake = MigrationIntakeRequest.objects.create(
            tenant=tenant,
            requested_by_user=request.user,
            vendor_slug=vendor,
            state=MigrationIntakeState.INTAKE_DRAFT.value,
            notes_for_runmycampus_team=notes,
        )
        logger.info(
            "migration_cloud.intake: created intake_id=%s tenant_pk=%s vendor=%s user_pk=%s",
            intake.id, tenant.pk, vendor, request.user.pk,
        )
        # Auto-advance into the maa-pending-counsel state so the customer
        # immediately lands on the sign-MAA step.
        try:
            intake.advance(
                MigrationIntakeState.MAA_PENDING_COUNSEL.value, actor=request.user,
            )
        except MigrationIntakeStateError as exc:
            logger.warning(
                "migration_cloud.intake: auto-advance failed intake_id=%s err=%s",
                intake.id, type(exc).__name__,
            )
        _signal_state_change(intake, MigrationIntakeState.INTAKE_DRAFT.value)
        return redirect(
            "migration_intake_customer:migration-intake-sign-maa", id=str(intake.id),
        )


@method_decorator(csrf_protect, name="dispatch")
class MigrationIntakeMAASignView(LoginRequiredMixin, View):
    """GET shows the full MAA text. POST creates the signature + advances state."""

    template_name = "migration_cloud/customer/intake_sign_maa.html"

    def get(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)
        tenant = intake.tenant
        active_version = resolve_active_version_for_tenant(tenant)
        if is_draft_version(active_version):
            return HttpResponse(
                "Agreement is in draft; cannot be signed yet.", status=503,
            )
        # Holder name preview — best-effort; user can override at sign time.
        holder = (
            getattr(request.user, "get_full_name", lambda: "")() or
            getattr(request.user, "username", "") or ""
        )
        try:
            maa_text = render_maa_text(intake.vendor_slug, holder, active_version)
        except ValueError as exc:
            return HttpResponse(f"agreement render failed: {exc}", status=500)

        context = {
            "intake": intake,
            "active_agreement_version": active_version,
            "maa_text": maa_text,
            "default_holder_name": holder,
            "already_signed": intake.maa_signature_id is not None,
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)
        if intake.state != MigrationIntakeState.MAA_PENDING_COUNSEL.value:
            return HttpResponseBadRequest(
                "intake is not awaiting MAA signature",
            )
        tenant = intake.tenant
        active_version = resolve_active_version_for_tenant(tenant)
        if is_draft_version(active_version):
            return HttpResponseBadRequest(
                "agreement is in draft; cannot be signed",
            )
        holder_name = (request.POST.get("vendor_account_holder_name") or "").strip()
        signed_by_role = (request.POST.get("signed_by_role") or "").strip()
        if not holder_name or not signed_by_role:
            return HttpResponseBadRequest(
                "vendor_account_holder_name + signed_by_role required",
            )

        try:
            signature_text = render_maa_text(
                intake.vendor_slug, holder_name, active_version,
            )
        except ValueError as exc:
            return HttpResponseBadRequest(f"agreement render failed: {exc}")

        client_ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
            or None
        )
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]

        # tenant-isolation-allow: customer-intake-create-maa-for-tenant-of-intake
        maa = MigrationAuthorizationAgreement.objects.create(
            tenant=tenant,
            signed_by_user=request.user,
            signed_by_role=signed_by_role[:128],
            vendor_source=intake.vendor_slug[:64],
            vendor_account_holder_name=holder_name[:256],
            agreement_version=active_version[:32],
            signature_text=signature_text,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        # NOTE: signature_text intentionally never logged.
        logger.info(
            "migration_cloud.intake: maa_signed_customer intake_id=%s maa_id=%s "
            "tenant_pk=%s vendor=%s version=%s",
            intake.id, maa.pk, tenant.pk, intake.vendor_slug, active_version,
        )

        intake.maa_signature = maa
        intake.save(update_fields=["maa_signature", "updated_at"])
        previous = intake.state
        intake.advance(MigrationIntakeState.MAA_SIGNED.value, actor=request.user)
        _signal_state_change(intake, previous)

        return redirect(
            "migration_intake_customer:migration-intake-status", id=str(intake.id),
        )


class MigrationIntakeStatusView(LoginRequiredMixin, View):
    """Customer-facing 7-stage progress + audit timeline + next-action banner."""

    template_name = "migration_cloud/customer/intake_status.html"

    def get(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)

        # Pull the last 10 audit events that reference this intake. The
        # audit model stores ``event_subject_hash = sha256(str(intake.id))``
        # so we match by hash to keep parity with the rest of the audit
        # surface (no raw UUID stored in audit rows).
        import hashlib
        subject_hash = hashlib.sha256(str(intake.id).encode("utf-8")).hexdigest()[:64]
        # tenant-isolation-allow: customer-intake-audit-events-by-subject-hash-of-tenant-intake
        audit_events = list(
            MigrationCloudAuditEvent.objects.filter(
                event_subject_hash=subject_hash,
            ).order_by("-created_at")[:10]
        )

        sse_enabled = (
            getattr(settings, "MIGRATION_CLOUD_SSE_TRANSPORT", "wsgi-fallback")
            in ("asgi-daphne",)
        )

        # This is the ASSISTED (concierge) migration path: after the school signs
        # the MAA, the RunMyCampus team performs extraction, validation, and
        # promotion. The stage labels must reflect who the actor is — the school
        # does NOT self-approve here (there is deliberately no approve control on
        # this surface), so "Awaiting your approval" was misleading. Schools that
        # want to self-serve use the connector file-upload flow instead.
        # See docs/MIGRATION_CLOUD_AUDIT_2026_07_24.md (G-1).
        stages = [
            ("intake-draft", "Intake submitted"),
            ("maa-pending-counsel", "MAA pending"),
            ("maa-signed", "MAA signed"),
            ("extraction-in-progress", "Extracting (RunMyCampus team)"),
            ("validation-in-progress", "Validating (RunMyCampus team)"),
            ("promotion-pending-approval", "In review by RunMyCampus"),
            ("complete", "Live"),
        ]

        context = {
            "intake": intake,
            "stages": stages,
            "audit_events": audit_events,
            "next_action": intake.next_action_banner(),
            "sse_enabled": sse_enabled,
            "pct_complete": intake.pct_complete,
            "can_abandon": intake.state in (
                MigrationIntakeState.INTAKE_DRAFT.value,
                MigrationIntakeState.MAA_PENDING_COUNSEL.value,
            ),
        }
        return render(request, self.template_name, context)


class MigrationIntakeStatusStreamView(LoginRequiredMixin, View):
    """SSE progress stream for an intake. Lightweight — replays state every 5s.

    Lives at ``/migration/<id>/status/stream/``. Transport-aware: when
    ``MIGRATION_CLOUD_SSE_TRANSPORT`` is ``wsgi-fallback`` we still
    serve the stream but only for a short capped duration so we don't
    tie up a sync worker. The status page falls back to a 30s
    ``<meta refresh>`` when SSE is not configured.
    """

    MAX_DURATION = 60.0
    TICK_SECONDS = 5.0

    def get(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)
        intake_id = str(intake.id)
        # Capture tenant-scoped queryset closure so the generator does
        # not re-resolve `request.user` after Django releases it.
        # tenant-isolation-allow: customer-intake-sse-tenant-scoped-by-captured-pk
        tenant_pk = intake.tenant_id

        def _frames():
            start = time.monotonic()
            last_state: Optional[str] = None
            while time.monotonic() - start < self.MAX_DURATION:
                refreshed = MigrationIntakeRequest.objects.filter(
                    id=intake_id, tenant_id=tenant_pk,
                ).first()
                if refreshed is None:
                    break
                if refreshed.state != last_state:
                    payload = json.dumps({
                        "state": refreshed.state,
                        "pct_complete": refreshed.pct_complete,
                        "is_terminal": refreshed.is_terminal,
                    })
                    yield f"event: intake.state\ndata: {payload}\n\n".encode("utf-8")
                    last_state = refreshed.state
                    if refreshed.is_terminal:
                        break
                yield b": ping\n\n"
                time.sleep(self.TICK_SECONDS)

        response = StreamingHttpResponse(
            _frames(), content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


@method_decorator(csrf_protect, name="dispatch")
class MigrationIntakeAbandonView(LoginRequiredMixin, View):
    """POST-only soft-cancel. Only valid before extraction begins."""

    template_name = "migration_cloud/customer/intake_abandon_confirm.html"

    def get(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)
        return render(
            request, self.template_name, {"intake": intake},
        )

    def post(self, request: HttpRequest, id: str, *args, **kwargs) -> HttpResponse:
        intake = _intake_for_request(request, id)
        confirm = request.POST.get("confirm") == "on"
        if not confirm:
            return HttpResponseBadRequest("confirmation checkbox required")
        if intake.state not in (
            MigrationIntakeState.INTAKE_DRAFT.value,
            MigrationIntakeState.MAA_PENDING_COUNSEL.value,
        ):
            return HttpResponseBadRequest(
                "intake has already progressed past the abandon window",
            )
        previous = intake.state
        try:
            intake.advance(MigrationIntakeState.ABANDONED.value, actor=request.user)
        except MigrationIntakeStateError as exc:
            return HttpResponseBadRequest(str(exc))
        _signal_state_change(intake, previous)
        return redirect(
            "migration_intake_customer:migration-intake-status", id=str(intake.id),
        )


class MigrationIntakeListView(LoginRequiredMixin, View):
    """List of this tenant's intake requests."""

    template_name = "migration_cloud/customer/intake_list.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        qs = _tenant_intake_queryset(request)
        if qs is None:
            raise Http404("tenant required")
        state_filter = (request.GET.get("state") or "").strip().lower()
        if state_filter:
            valid = {c.value for c in MigrationIntakeState}
            if state_filter in valid:
                # tenant-isolation-allow: customer-intake-tenant-list-filtered-by-state
                qs = qs.filter(state=state_filter)
        intakes = list(qs[:100])
        context = {
            "intakes": intakes,
            "active_state_filter": state_filter,
            "all_states": list(MigrationIntakeState.choices),
        }
        return render(request, self.template_name, context)
