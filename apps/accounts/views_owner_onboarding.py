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
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import password_validation
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_TOTAL_STEPS = 3


# ── State (School.settings["owner_onboarding"]) ─────────────────────────────
def _owner_school(user):
    """The owner's primary school (or first membership)."""
    try:
        from apps.schools.models import SchoolMembership

        m = (
            # tenant-isolation-allow: owner-onboarding resolves the signed-in owner's own school via membership
            SchoolMembership.objects.filter(user=user, is_primary=True)
            .select_related("school")
            .first()
            or SchoolMembership.objects.filter(user=user)
            .select_related("school")
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


def _maybe_nudge_provisioning(request, school, user) -> None:
    """Queue provisioning on the done page (rate-limited). Prefer POST recheck for sync."""
    if not school or getattr(school, "is_active", False):
        return
    session_key = f"owner_provision_queue:{school.pk}"
    now_ts = time.time()
    last_ts = request.session.get(session_key)
    if last_ts and (now_ts - float(last_ts)) < 60:  # magic-number-allow: provision-queue-cooldown-seconds
        return
    request.session[session_key] = now_ts
    contact_email = (getattr(user, "email", "") or "").strip()
    try:
        from apps.schools.tasks import dispatch_provision_school

        dispatch_provision_school(str(school.pk), contact_email=contact_email)
        logger.info(
            "owner_onboarding_provision_queue school_id=%s",
            getattr(school, "pk", None),
        )
    except Exception:  # noqa: BLE001 - queue kick must never block the launchpad
        logger.warning("owner_onboarding_provision_queue_failed", exc_info=True)


def _run_sync_provisioning(request, school, user) -> bool:
    """Run provisioning in-request so Check again actually completes setup."""
    if not school or getattr(school, "is_active", False):
        return True
    session_key = f"owner_provision_sync:{school.pk}"
    now_ts = time.time()
    last_ts = request.session.get(session_key)
    if last_ts and (now_ts - float(last_ts)) < 30:  # magic-number-allow: provision-sync-cooldown-seconds
        return False
    request.session[session_key] = now_ts
    contact_email = (getattr(user, "email", "") or "").strip()
    try:
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(school.pk), contact_email=contact_email)
        school.refresh_from_db(fields=["is_active", "settings", "updated_at"])
        logger.info(
            "owner_onboarding_provision_sync school_id=%s active=%s",
            getattr(school, "pk", None),
            getattr(school, "is_active", False),
        )
        return bool(getattr(school, "is_active", False))
    except Exception:  # noqa: BLE001 - surface message to owner, never 500 the launchpad
        logger.warning("owner_onboarding_provision_sync_failed", exc_info=True)
        return False


def _finish_provisioning_before_done(request, school, user) -> None:
    """After the school step, try to finish provisioning before showing the launchpad."""
    if not school or getattr(school, "is_active", False):
        return
    if _run_sync_provisioning(request, school, user):
        return
    _maybe_nudge_provisioning(request, school, user)


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
        if user is not None:
            _set_onboarding(_owner_school(user), step="school", completed=False)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        school = _owner_school(self.user) if getattr(self, "user", None) else None
        ctx["school"] = school
        ctx["step"] = 1
        ctx["total_steps"] = _TOTAL_STEPS
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
    # Idempotent: stamp "completed" once, but keep the launchpad reachable on a
    # refresh (the page is useful — invite team / open Studio / dashboard).
    if not onboarding_state(school).get("completed"):
        _set_onboarding(school, completed=True, step="done")
        try:
            from apps.schools.activation_gate import clear_activation_gate

            clear_activation_gate(school)
        except ImportError:
            pass

    if request.method == "POST" and (request.POST.get("recheck_provision") or "").strip() == "1":
        if getattr(school, "is_active", False):
            messages.info(request, _l("Your portal is already live."))
        elif _run_sync_provisioning(request, school, request.user):
            messages.success(
                request,
                _l("Your campus portal is ready — open your dashboard below."),
            )
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

    if not getattr(school, "is_active", False):
        _maybe_nudge_provisioning(request, school, request.user)

    school.refresh_from_db(fields=["is_active", "name", "settings"])
    return render(
        request,
        "accounts/owner_onboarding/done.html",
        {
            "school": school,
            "step": 3,
            "total_steps": _TOTAL_STEPS,
            "school_is_live": bool(getattr(school, "is_active", False)),
            "dashboard_href": _post_onboarding_dashboard_href(request, school),
            "owner_email": (getattr(request.user, "email", "") or "").strip(),
        },
    )
