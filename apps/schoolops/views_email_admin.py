"""v3.57.x Wave 8 Agent C — Operator-facing SMTP configuration view.

Endpoint:

    GET  /super/email/configure/   — render the form pre-seeded from
                                     ``SiteSettings.email_delivery``.
    POST /super/email/configure/   — validate + save (encrypts the
                                     password) + redirect ``?saved=1``.
    POST /super/email/configure/?action=send_test
                                   — send a probe email to the operator's
                                     own ``request.user.email``.

Permission model: ``staff_member_required``. URL pattern carries
``# rbac-allow: super-staff-email-configure``.

The form is the single SOT for the JSON shape on
``SiteSettings.email_delivery``; this view does NOT inline any logic
that belongs in :mod:`apps.schoolops.forms_email_delivery`.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View


logger = logging.getLogger(__name__)


def _load_existing_payload() -> dict:
    """Return the current ``SiteSettings.email_delivery`` dict (or {})."""
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = get_platform_site_settings_record(create=False)
        if row is None:
            return {}
        return getattr(row, "email_delivery", None) or {}
    except Exception as exc:  # noqa: BLE001  — defensive read
        logger.warning(
            "schoolops.email_admin.load_existing_payload_failed err_type=%s",
            type(exc).__name__,
        )
        return {}


def _persist_payload(new_payload: dict) -> bool:
    """Save the new ``SiteSettings.email_delivery`` JSON. Returns True on success."""
    try:
        from apps.platform_runtime.helpers import get_platform_site_settings_record

        # tenant-isolation-allow: platform-email-delivery-log-no-tenant-scope
        row = get_platform_site_settings_record(create=True)
        if row is None:
            return False
        row.email_delivery = new_payload
        row.save(update_fields=["email_delivery"])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "schoolops.email_admin.persist_payload_failed err_type=%s",
            type(exc).__name__,
        )
        return False


@method_decorator(staff_member_required, name="dispatch")
class EmailDeliveryConfigView(View):
    """Operator view: edit ``SiteSettings.email_delivery``.

    GET renders the form pre-seeded from the existing JSON payload.
    POST validates + persists, supports an ``action=send_test`` flow.
    """

    template_name = "schoolops/super/email_configure.html"

    def _render(
        self,
        request: HttpRequest,
        form,
        *,
        saved: bool = False,
        test_result: dict | None = None,
    ) -> HttpResponse:
        ctx = {
            "page_title": "Email delivery configuration",
            "form": form,
            "saved": saved,
            "test_result": test_result,
            "operator_email": getattr(request.user, "email", "") or "",
            "health_url": _safe_reverse("super:email_health"),
        }
        return render(request, self.template_name, ctx)

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from apps.schoolops.forms_email_delivery import EmailDeliveryForm

        payload = _load_existing_payload()
        form = EmailDeliveryForm.from_json(payload)
        saved_flag = bool(request.GET.get("saved"))
        return self._render(request, form, saved=saved_flag)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        from apps.schoolops.forms_email_delivery import EmailDeliveryForm

        action = (request.POST.get("action") or "save").strip().lower()
        existing = _load_existing_payload()
        form = EmailDeliveryForm(request.POST)

        if action == "send_test":
            return self._handle_send_test(request, form, existing)

        if not form.is_valid():
            return self._render(request, form, saved=False)

        try:
            new_payload = form.to_json(existing_payload=existing)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "schoolops.email_admin.form_to_json_failed err_type=%s",
                type(exc).__name__,
            )
            messages.error(
                request,
                "Could not save: password encryption failed. "
                "Check platform Fernet key configuration.",
            )
            return self._render(request, form, saved=False)

        ok = _persist_payload(new_payload)
        if not ok:
            messages.error(request, "Save failed — see server logs.")
            return self._render(request, form, saved=False)

        target = _safe_reverse("super:email_configure")
        return redirect(f"{target}?saved=1" if target else "?saved=1")

    def _handle_send_test(
        self,
        request: HttpRequest,
        form,
        existing: dict,
    ) -> HttpResponse:
        """POST ?action=send_test — send a probe email to the operator."""
        operator_email = (getattr(request.user, "email", "") or "").strip()
        if not operator_email:
            messages.error(
                request,
                "No email address on your operator account — cannot send test.",
            )
            return self._render(request, form, saved=False)

        # If the form is invalid we still allow the test send to run
        # against the EXISTING saved config (operator may want to test
        # the live deployment without saving WIP changes).
        from apps.schoolops.email_delivery import send_transactional

        try:
            result = send_transactional(
                subject="RunMyCampus SMTP test email",
                body=(
                    "This is a test message from your RunMyCampus operator "
                    "control plane. If you received this, your SMTP "
                    "configuration is working.\n\n"
                    "You can safely ignore or delete this email."
                ),
                to=operator_email,
                priority="transactional",
            )
        except Exception as exc:  # noqa: BLE001  — never raise out
            logger.exception(
                "schoolops.email_admin.send_test_crashed err_type=%s",
                type(exc).__name__,
            )
            result = {
                "ok": False,
                "attempts": 0,
                "delivery_event_id": None,
                "error_kind": "crashed",
            }
        # Defensive: never include the recipient address in the result
        # surfaced to the page (the operator can see it in the input).
        sanitized = {
            "ok": bool(result.get("ok")),
            "attempts": int(result.get("attempts") or 0),
            "error_kind": (result.get("error_kind") or "")[:64],
        }
        return self._render(request, form, saved=False, test_result=sanitized)


def _safe_reverse(name: str) -> str:
    """Reverse a URL name without raising if the namespace isn't loaded yet."""
    try:
        return reverse(name)
    except Exception:  # noqa: BLE001  — view-level convenience
        return ""


__all__ = [
    "EmailDeliveryConfigView",
]
