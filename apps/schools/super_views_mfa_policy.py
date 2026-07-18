"""Operator screen: set a tenant's MFA policy (Operator + tenant, with floor).

The operator sets a per-tenant MFA policy — require MFA for all staff, and/or a
set of roles that must use MFA — stored in ``School.settings['operator_mfa']``
(the dedicated operator key read by ``apps.accounts.mfa_defaults.resolve_operator_mfa``).
No tenant-facing form writes that key, and the requirement resolver unions
everything, so a tenant can only TIGHTEN this policy, never weaken it — and neither
can drop below the platform floor (``BASELINE_REQUIRED_ROLES``).

Operator-gated (``require_super_access_with_host`` at the URL layer +
``PLATFORM_SCOPE_SECURITY_WRITE`` here); writes are audit-logged.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.mfa_defaults import (
    BASELINE_REQUIRED_ROLES,
    OPERATOR_MFA_SETTINGS_KEY,
    read_operator_mfa_settings,
)
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_SECURITY_WRITE,
    require_platform_scope,
)

from .control_plane import log_control_plane_action
from .models import School

logger = logging.getLogger(__name__)


def _role_choices() -> list[tuple[str, str]]:
    """Role tokens an operator can require MFA for (from User.Role)."""
    User = get_user_model()
    try:
        return [(str(code), str(label)) for code, label in User.Role.choices]
    except AttributeError:  # pragma: no cover - Role always present on this project
        return []


@require_http_methods(["GET", "POST"])
@require_platform_scope(PLATFORM_SCOPE_SECURITY_WRITE)
def tenant_mfa_policy(request, school_id):
    school = School.objects.filter(pk=str(school_id)).first()
    if school is None:
        messages.error(request, _("School not found."))
        return redirect("super:dashboard")

    stored = read_operator_mfa_settings(school)
    baseline = sorted({r.upper() for r in BASELINE_REQUIRED_ROLES})

    if request.method == "POST":
        require_all_staff = request.POST.get("require_all_staff") == "1"
        chosen = request.POST.getlist("required_roles")
        valid = {code for code, _label in _role_choices()}
        # Normalise to known role tokens; the baseline floor is implicit, so we
        # never need to store it here.
        required_roles = sorted(
            {c.strip().upper() for c in chosen if c and c.strip().upper() in valid}
            - {b for b in baseline}
        )
        blob = dict(getattr(school, "settings", None) or {})
        blob[OPERATOR_MFA_SETTINGS_KEY] = {
            "require_all_staff": require_all_staff,
            "required_roles": required_roles,
        }
        school.settings = blob
        try:
            school.save(update_fields=["settings"])
        except Exception:  # noqa: BLE001 — fall back to a full save if the field set drifts
            school.save()
        log_control_plane_action(
            request,
            action="UPDATE",
            model_name="School",
            object_id=school.pk,
            object_repr=f"operator MFA policy for {school.slug or school.pk}",
            reason="operator set per-tenant MFA policy",
            sensitivity="HIGH",
            new_values={
                "require_all_staff": require_all_staff,
                "required_roles": required_roles,
            },
            changed_fields=["settings.operator_mfa"],
        )
        messages.success(request, _("MFA policy saved for this tenant."))
        return redirect("super:tenant_mfa_policy", school_id=str(school.pk))

    selected = {str(r).strip().upper() for r in (stored.get("required_roles") or [])}
    baseline_set = set(baseline)
    role_rows = []
    for code, label in _role_choices():
        upper = str(code).strip().upper()
        role_rows.append(
            {
                "code": code,
                "label": label,
                "checked": upper in selected or upper in baseline_set,
                # Floor roles are always required — shown ticked and locked.
                "locked": upper in baseline_set,
            }
        )

    # Back/Cancel returns to the tenant's 360 page — the operator surface this
    # screen is linked from — falling back to the dashboard if that reverse
    # ever fails.
    try:
        back_url = reverse("super:tenant_360", args=[str(school.pk)])
    except NoReverseMatch:
        back_url = reverse("super:dashboard")
    context = {
        "school": school,
        "require_all_staff": bool(stored.get("require_all_staff")),
        "role_rows": role_rows,
        "baseline_roles": baseline,
        "back_url": back_url,
        "dashboard_url": reverse("super:dashboard"),
    }
    return render(request, "schools/super/tenant_mfa_policy.html", context)
