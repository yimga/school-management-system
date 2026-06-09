"""Guided first-run onboarding for a brand-new school owner (2026-06-08).

After clicking the signup verification link, the owner is walked through a short,
welcoming wizard instead of being dropped onto a generic logged-in dashboard
(which read as "you already have an account"):

  1. Create your account  — choose a password + tell us your name (token-authed,
     reuses Django's password-reset-confirm token machinery). Logs them in.
  2. Your school          — confirm the school name + pick a brand colour.
  3. You're all set        — a launchpad (invite your team, open Studio, go to
     your dashboard). Marks onboarding complete so it never shows again.

Onboarding state lives in ``School.settings["owner_onboarding"]`` (JSON, no
migration). Steps 2–3 are ``@login_required`` on the tenant host (the session
set by step 1's auto-login applies). The token in step 1 is the auth, so it
works across the public→tenant host hop.
"""

from __future__ import annotations

import logging
import re
import time

from django import forms
from django.db import DatabaseError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.http import require_GET, require_http_methods

logger = logging.getLogger(__name__)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_TOTAL_STEPS = 3
_PASSWORD_RESET_SENTINEL = "set-password"


def _resolve_onboarding_token(request, token: str) -> str:
    """PasswordResetConfirmView redirects to token ``set-password``; read real token from session."""
    token = (token or "").strip()
    if token and token != _PASSWORD_RESET_SENTINEL:
        return token
    try:
        from django.contrib.auth.views import INTERNAL_RESET_SESSION_TOKEN
    except ImportError:
        INTERNAL_RESET_SESSION_TOKEN = "_password_reset_token"  # noqa: N806
    return (request.session.get(INTERNAL_RESET_SESSION_TOKEN) or token).strip()


# ── State (School.settings["owner_onboarding"]) ─────────────────────────────
def _owner_school(user):
    """The owner's primary school (or first membership)."""
    try:
        from apps.schools.models import SchoolMembership, SignupVerification

        email = (getattr(user, "email", "") or "").strip()
        if email:
            verification = (
                SignupVerification.objects.filter(email__iexact=email)
                .exclude(verified_at__isnull=True)
                .select_related("school")
                .order_by("-verified_at", "-id")
                .first()
            )
            if verification and verification.school_id:
                return verification.school

        m = (
            SchoolMembership.objects.filter(user=user, is_primary=True)
            .select_related("school")
            .first()
            or SchoolMembership.objects.filter(user=user)
            .select_related("school")
            .order_by("-school__created_at")
            .first()
        )
        return m.school if m else None
    except Exception:  # noqa: BLE001 - onboarding must never 500 on lookup
        logger.warning("owner_onboarding_school_lookup_failed", exc_info=True)
        return None


def onboarding_state(school) -> dict:
    if not school:
        return {}
    return dict((getattr(school, "settings", None) or {}).get("owner_onboarding", {}))


def _set_onboarding(school, **updates) -> None:
    if not school:
        return
    settings_blob = dict(getattr(school, "settings", None) or {})
    state = dict(settings_blob.get("owner_onboarding", {}))
    state.update(updates)
    settings_blob["owner_onboarding"] = state
    school.settings = settings_blob
    try:
        school.save(update_fields=["settings"])
    except Exception:  # noqa: BLE001 - state persistence is best-effort
        logger.warning("owner_onboarding_state_save_failed", exc_info=True)


def _dashboard_redirect():
    return redirect("accounts:redirect")


def _post_onboarding_dashboard_href(request, school) -> str:
    """Dashboard CTA after wizard — never deep-link an inactive tenant subdomain."""
    from django.urls import reverse

    from apps.schools.provision_email_urls import school_subdomain_redirect_is_safe
    from apps.schools.tenant_url import build_tenant_backend_url, is_base_domain

    if school and school_subdomain_redirect_is_safe(school):
        try:
            if is_base_domain(request):
                return build_tenant_backend_url(request, school)
        except (AttributeError, ImportError, TypeError, ValueError):
            pass
        try:
            return reverse("accounts:redirect")
        except Exception:  # noqa: BLE001 - template fallback must not 500
            pass
    try:
        return reverse("accounts:owner_onboarding_done")
    except Exception:  # noqa: BLE001
        return "/authentication/onboarding/done/"


def _run_owner_provisioning(
    request, school, user, *, cooldown_seconds: int = 0
) -> bool:
    """Queue + sync provisioning in-request so owners are not blocked by Celery."""
    if not school or getattr(school, "is_active", False):
        return True
    if cooldown_seconds:
        session_key = f"owner_provision_sync:{school.pk}"
        now_ts = time.time()
        last_ts = request.session.get(session_key)
        if last_ts and (now_ts - float(last_ts)) < cooldown_seconds:
            return False
        request.session[session_key] = now_ts
    contact_email = (getattr(user, "email", "") or "").strip()
    try:
        from apps.schools.tasks import complete_provisioning_for_school

        result = complete_provisioning_for_school(
            str(school.pk), contact_email=contact_email
        )
        school.refresh_from_db(fields=["is_active", "settings", "updated_at"])
        logger.info(
            "owner_onboarding_provision_complete school_id=%s active=%s queued=%s sync=%s",
            getattr(school, "pk", None),
            getattr(school, "is_active", False),
            result.get("queued"),
            result.get("sync_completed"),
        )
        return bool(result.get("is_active"))
    except Exception:  # noqa: BLE001 - surface message to owner, never 500 the launchpad
        logger.warning("owner_onboarding_provision_complete_failed", exc_info=True)
        return False


def _last_provisioning_error(school) -> str:
    if not school:
        return ""
    try:
        from apps.schools.models import SchoolProvisioningEvent

        event = (
            SchoolProvisioningEvent.objects.filter(
                school=school, event_type="FAILED"
            )
            .order_by("-created_at")
            .first()
        )
        if not event:
            return ""
        payload = getattr(event, "payload", None) or {}
        if isinstance(payload, dict):
            err = (payload.get("error") or "").strip()
            if err:
                return err[:500]
        return (getattr(event, "message", "") or "").strip()[:500]
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        return ""


def _recent_provision_failure(school, *, within_seconds: int = 120) -> bool:
    if not school:
        return False
    try:
        from django.utils import timezone

        from apps.schools.models import SchoolProvisioningEvent

        event = (
            SchoolProvisioningEvent.objects.filter(
                school=school, event_type="FAILED"
            )
            .order_by("-created_at")
            .first()
        )
        if not event or not getattr(event, "created_at", None):
            return False
        delta = timezone.now() - event.created_at
        return delta.total_seconds() < within_seconds
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        return False


def _kick_provisioning_on_done_page(request, school, user) -> None:
    """First visit and periodic refresh: queue + sync when the portal is still inactive."""
    if not school or getattr(school, "is_active", False):
        return
    if _recent_provision_failure(school):
        return
    session_key = f"owner_provision_kick:{school.pk}"
    now_ts = time.time()
    cooldown = 120 if _last_provisioning_error(school) else 60  # magic-number-allow: provision-queue-cooldown-seconds
    last_ts = request.session.get(session_key)
    if last_ts and (now_ts - float(last_ts)) < cooldown:
        return
    request.session[session_key] = now_ts
    _run_owner_provisioning(request, school, user, cooldown_seconds=0)


def _provisioning_timeline(school, *, limit: int = 8):
    if not school:
        return []
    try:
        from apps.schools.models import SchoolProvisioningEvent

        return list(
            SchoolProvisioningEvent.objects.filter(school=school)
            .order_by("-created_at")[:limit]
        )
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        return []


def _user_from_onboarding_token(uidb64: str, token: str):
    """Validate owner onboarding reset token without requiring a session."""
    User = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token):
        return None
    return user


def _finish_provisioning_before_done(request, school, user) -> None:
    """After the school step, try to finish provisioning before showing the launchpad."""
    if not school or getattr(school, "is_active", False):
        return
    _run_owner_provisioning(request, school, user, cooldown_seconds=0)


# ── Step 1: Create your account (token-authed) ──────────────────────────────
class OwnerAccountSetupForm(SetPasswordForm):
    """Set-password form that also captures the owner's name."""

    first_name = forms.CharField(label=_l("First name"), max_length=150, strip=True)  # magic-number-allow: AbstractUser name field length
    last_name = forms.CharField(label=_l("Last name"), max_length=150, strip=True)  # magic-number-allow: AbstractUser name field length

    field_order = ["first_name", "last_name", "new_password1", "new_password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].help_text = password_validation.password_validators_help_text_html()

    def save(self, commit=True):
        self.user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        self.user.last_name = (self.cleaned_data.get("last_name") or "").strip()
        return super().save(commit=commit)


class OwnerOnboardingAccountView(PasswordResetConfirmView):
    """Welcoming first-run account setup. Token validation + login is inherited
    from PasswordResetConfirmView; we add the name fields + advance the wizard."""

    template_name = "accounts/owner_onboarding/account.html"
    form_class = OwnerAccountSetupForm
    post_reset_login = True
    post_reset_login_backend = "django.contrib.auth.backends.ModelBackend"
    success_url = reverse_lazy("accounts:owner_onboarding_school")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(self, "user", None)
        school = _owner_school(user) if user is not None else None
        if user is not None:
            _set_onboarding(school, step="school", completed=False)
        if school is not None:
            _run_owner_provisioning(self.request, school, user, cooldown_seconds=0)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        school = _owner_school(self.user) if getattr(self, "user", None) else None
        ctx["school"] = school
        ctx["step"] = 1
        ctx["total_steps"] = _TOTAL_STEPS
        portal_ready = False
        provisioning_progress = None
        if school is not None:
            try:
                from apps.schools.provisioning_progress import (
                    resolve_portal_ready,
                    resolve_provisioning_progress,
                )

                portal_ready = resolve_portal_ready(school)
                if not portal_ready:
                    provisioning_progress = resolve_provisioning_progress(school)
            except ImportError:
                portal_ready = bool(getattr(school, "is_active", False))
        ctx["portal_ready"] = portal_ready
        ctx["provisioning_progress"] = provisioning_progress
        ctx["show_inline_provision_progress"] = bool(
            school is not None and not portal_ready and provisioning_progress
        )
        uidb64 = self.kwargs.get("uidb64")
        token = _resolve_onboarding_token(self.request, self.kwargs.get("token") or "")
        if ctx["show_inline_provision_progress"] and uidb64 and token:
            ctx["provision_progress_api_url"] = reverse(
                "accounts:owner_onboarding_account_provision_progress",
                kwargs={"uidb64": uidb64, "token": token},
            )
        return ctx


# ── Step 2: Your school ─────────────────────────────────────────────────────
@login_required
def owner_onboarding_school(request):
    school = _owner_school(request.user)
    if school is None:
        return _dashboard_redirect()
    if onboarding_state(school).get("completed"):
        return _dashboard_redirect()

    if request.method == "POST":
        if "skip" not in request.POST:
            updates = []
            name = (request.POST.get("school_name") or "").strip()
            color = (request.POST.get("primary_color") or "").strip()
            if name and name != school.name:
                school.name = name[:255]
                updates.append("name")
            if color and _HEX_COLOR_RE.match(color) and color != school.primary_color:
                school.primary_color = color
                updates.append("primary_color")
            if updates:
                try:
                    school.save(update_fields=updates)
                except Exception:  # noqa: BLE001 - never block the wizard on a save error
                    logger.warning("owner_onboarding_school_save_failed", exc_info=True)
        _set_onboarding(school, step="done")
        _finish_provisioning_before_done(request, school, request.user)
        return redirect("accounts:owner_onboarding_done")

    return render(
        request,
        "accounts/owner_onboarding/school.html",
        {"school": school, "step": 2, "total_steps": _TOTAL_STEPS},
    )


# ── Step 3: You're all set (launchpad) ──────────────────────────────────────
@login_required
@require_http_methods(["GET", "POST"])
def owner_onboarding_done(request):
    school = _owner_school(request.user)
    if school is None:
        return _dashboard_redirect()
    if request.method == "GET":
        try:
            from apps.schools.provision_email_urls import (
                build_tenant_authentication_url,
                tenant_subdomain_host_exists,
            )
            from apps.schools.tenant_url import is_base_domain

            if tenant_subdomain_host_exists(school) and is_base_domain(request):
                request.school = school
                return redirect(
                    build_tenant_authentication_url(school, request.get_full_path())
                )
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
    request.school = school
    # Idempotent: stamp "completed" once, but keep the launchpad reachable on a
    # refresh (the page is useful — invite team / open Studio / dashboard).
    if not onboarding_state(school).get("completed"):
        _set_onboarding(school, completed=True, step="done")
        try:
            from apps.schools.activation_gate import clear_activation_gate

            clear_activation_gate(school)
        except ImportError:
            pass

    try:
        from apps.schools.provisioning_progress import resolve_portal_ready

        portal_ready = resolve_portal_ready(school)
    except ImportError:
        portal_ready = bool(getattr(school, "is_active", False))

    if request.method == "POST" and (request.POST.get("recheck_provision") or "").strip() == "1":
        if portal_ready:
            messages.info(request, _l("Your portal is already live."))
        elif _run_owner_provisioning(
            request, school, request.user, cooldown_seconds=30
        ):  # magic-number-allow: provision-recheck-cooldown-seconds
            messages.success(
                request,
                _l("Your campus portal is ready — open your dashboard below."),
            )
            try:
                from apps.schools.signup_completion_notifications import (
                    notify_tenant_signup_completed,
                )

                notify_tenant_signup_completed(
                    school,
                    getattr(request.user, "email", "") or "",
                    admin_user=request.user,
                )
            except ImportError:
                pass
        else:
            messages.warning(
                request,
                _l(
                    "Setup is still finishing. We will email you at %(email)s when "
                    "your portal is ready, or try again in a minute."
                )
                % {"email": (getattr(request.user, "email", "") or "").strip() or _l("your address")},
            )
        return redirect("accounts:owner_onboarding_done")

    if not portal_ready:
        _kick_provisioning_on_done_page(request, school, request.user)

    school.refresh_from_db(fields=["is_active", "name", "settings", "updated_at"])
    try:
        from apps.schools.provisioning_progress import resolve_portal_ready as _portal_ready

        portal_ready = _portal_ready(school)
    except ImportError:
        portal_ready = bool(getattr(school, "is_active", False))
    if portal_ready:
        try:
            from apps.schools.signup_completion_notifications import (
                notify_tenant_signup_completed,
            )

            notify_tenant_signup_completed(
                school,
                getattr(request.user, "email", "") or "",
                admin_user=request.user,
            )
        except ImportError:
            pass
    return render(
        request,
        "accounts/owner_onboarding/done.html",
        {
            "school": school,
            "step": 3,
            "total_steps": _TOTAL_STEPS,
            "school_is_live": portal_ready,
            "portal_ready": portal_ready,
            "dashboard_href": _post_onboarding_dashboard_href(request, school),
            "owner_email": (getattr(request.user, "email", "") or "").strip(),
            "provisioning_events": _provisioning_timeline(school),
            "last_provisioning_error": _last_provisioning_error(school),
            "provision_status_api_url": reverse(
                "accounts:owner_onboarding_provision_progress"
            ),
            "provision_progress_api_url": reverse(
                "accounts:owner_onboarding_provision_progress"
            ),
            "provision_apply_fix_url": reverse(
                "accounts:owner_onboarding_provision_apply_fix"
            ),
        },
    )


def _owner_provisioning_progress_payload(request, school) -> dict:
    """Canonical provisioning JSON — ``resolve_provisioning_progress`` SOT."""
    from apps.schools.provisioning_progress import (
        resolve_portal_ready,
        resolve_provisioning_progress,
    )

    if not resolve_portal_ready(school):
        _kick_provisioning_on_done_page(request, school, request.user)
        school.refresh_from_db(fields=["is_active", "name", "settings", "updated_at"])
        if resolve_portal_ready(school):
            try:
                from apps.schools.signup_completion_notifications import (
                    notify_tenant_signup_completed,
                )

                notify_tenant_signup_completed(
                    school,
                    getattr(request.user, "email", "") or "",
                    admin_user=request.user,
                )
            except ImportError:
                pass

    payload = resolve_provisioning_progress(
        school,
        request=request,
        include_dashboard_href=True,
    )
    try:
        from apps.schools.pending_tenant_discovery import pending_school_state

        payload["pending_state"] = pending_school_state(school) or (
            "live" if payload.get("portal_ready") else "provisioning"
        )
    except ImportError:
        payload["pending_state"] = (
            "live" if payload.get("portal_ready") else "provisioning"
        )
    payload["school_name"] = (
        getattr(school, "name", "") or getattr(school, "slug", "") or ""
    ).strip()

    events = []
    for event in _provisioning_timeline(school, limit=6):
        created = getattr(event, "created_at", None)
        events.append(
            {
                "event_type": getattr(event, "event_type", ""),
                "message": (getattr(event, "message", "") or "")[:240],
                "created_at": created.isoformat() if created is not None else "",
            }
        )
    payload["events"] = events
    return payload


@require_GET
def owner_onboarding_account_provision_progress(request, uidb64, token):
    """Token-authenticated progress poll for step 1 (pre-login account setup)."""
    token = _resolve_onboarding_token(request, token)
    user = _user_from_onboarding_token(uidb64, token)
    if user is None:
        return JsonResponse({"ok": False, "error": "invalid_token"}, status=403)
    school = _owner_school(user)
    if school is None:
        return JsonResponse({"ok": False, "error": "no_school"}, status=404)
    from apps.schools.provisioning_progress import (
        resolve_portal_ready,
        resolve_provisioning_progress,
    )

    payload = resolve_provisioning_progress(
        school,
        request=request,
        include_dashboard_href=False,
    )
    payload["portal_ready"] = resolve_portal_ready(school)
    payload.pop("events", None)
    return JsonResponse(payload)


@login_required
@require_GET
def owner_onboarding_provision_progress(request):
    """Canonical customer provisioning progress API (bar + steps + remediation)."""
    school = _owner_school(request.user)
    if school is None:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)
    return JsonResponse(_owner_provisioning_progress_payload(request, school))


@login_required
@require_GET
def owner_onboarding_provision_status(request):
    """Legacy poll URL — identical JSON to ``owner_onboarding_provision_progress``."""
    school = _owner_school(request.user)
    if school is None:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)
    return JsonResponse(_owner_provisioning_progress_payload(request, school))


@login_required
@require_http_methods(["POST"])
def owner_onboarding_provision_apply_fix(request):
    """Owner-safe auto-fix for provisioning failures (narrow allowlist)."""
    school = _owner_school(request.user)
    if school is None:
        return JsonResponse({"ok": False, "error": "no_school"}, status=403)

    from apps.schools.provisioning_progress import (
        _latest_workflow_run,
        _suggested_remediation_payload,
    )

    run = _latest_workflow_run(school)
    remediation = _suggested_remediation_payload(run)
    kind = (
        request.POST.get("auto_fix_kind") or remediation.get("auto_fix_kind") or ""
    ).strip()
    if not remediation.get("owner_may_apply") or not kind:
        return JsonResponse({"ok": False, "error": "fix_not_allowed"}, status=403)
    if run is None:
        return JsonResponse({"ok": False, "error": "no_run"}, status=404)

    from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

    result = apply_auto_fix_kind(run=run, kind=kind)
    if not result.get("ok"):
        return JsonResponse(
            {"ok": False, "error": result.get("reason", "failed")},
            status=400,
        )
    return JsonResponse({"ok": True, "applied": kind, "result": result})
