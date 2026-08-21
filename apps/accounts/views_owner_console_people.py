"""Owner Console — slice 3: People & Roles.

The heart of "do everything, then delegate". This surfaces the school's roster with
each member's access roles + owner flag, and adds **bulk multi-role assignment**:
select many people and apply many roles at once (additive — existing roles are never
removed). Co-owner / transfer / suspend already live in the Tenant Identity hub; this
page deep-links into it rather than duplicating it.

Owner-gated (an actual owner or a platform superuser), tenant-skinned, fail-soft.

Uses the existing ``User.roles`` M2M to ``AccessRole`` — no migration. The named
reusable **RoleGroup** bundles are a follow-up slice (they need their own model).
"""

from __future__ import annotations

import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.accounts.models import AccessRole, User
from apps.accounts.views_owner_console import _console_sections, _safe, is_school_owner
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)


class OwnerBulkRolesForm(forms.Form):
    """Assign MANY roles to MANY selected members at once (additive)."""

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )
    # tenant-isolation-allow: querysets-overridden-in-init-via-school-scoped-helpers
    roles = forms.ModelMultipleChoiceField(
        queryset=AccessRole.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            from apps.accounts.access_roles import roles_queryset_for_school
            from apps.accounts.tenant_identity import users_queryset_for_school

            self.fields["users"].queryset = users_queryset_for_school(school)
            self.fields["roles"].queryset = roles_queryset_for_school(school)


def _roster_rows(school, *, limit: int = 200) -> list[dict]:
    """The member roster with each member's access roles + owner flag. Fail-soft."""
    rows: list[dict] = []
    try:
        from apps.schools.models import SchoolMembership

        memberships = (
            SchoolMembership.objects.filter(school=school)
            .select_related("user")
            .prefetch_related("user__roles")
            .order_by("-is_school_owner", "-is_primary", "user__username")[:limit]
        )
        from apps.accounts.access_roles import role_applies_to_school

        for m in memberships:
            # `school_id == school.pk` excluded every GLOBAL template row, and
            # global is what the platform actually ships: TEACHER, ADMIN, BURSAR,
            # IT_ADMIN and the rest are all school=NULL. The bulk form assigns
            # from `roles_queryset_for_school`, which offers those globals — so
            # this page, whose whole job is assigning roles, showed an empty chip
            # list for every person no matter what an owner had just granted.
            # `role_applies_to_school` is the canonical predicate and admits both.
            access_roles = [
                r.name for r in m.user.roles.all() if role_applies_to_school(r, school)
            ]
            rows.append(
                {
                    "name": (m.user.get_full_name() or m.user.get_username()),
                    "base_role": (m.role or "").replace("_", " ").title() or _("Member"),
                    "is_owner": m.is_school_owner,
                    "suspended": m.suspended_at is not None,
                    "access_roles": access_roles,
                    "url": _safe("accounts:tenant_identity_detail", m.user_id),
                }
            )
    except Exception as exc:  # noqa: BLE001 — roster degrades to empty, never 500
        logger.debug("owner console roster failed: %s", exc)
    return rows


@login_required
@require_school
def owner_console_people(request):
    """People & Roles — roster + bulk multi-role assignment (owner-gated)."""
    school = request.school
    if not is_school_owner(request.user, school):
        return HttpResponseForbidden(
            _("The Owner Console is available to school owners.")
        )

    if request.method == "POST":
        form = OwnerBulkRolesForm(request.POST, school=school)
        if form.is_valid():
            users = list(form.cleaned_data["users"])
            roles = list(form.cleaned_data["roles"])
            for user in users:
                # Additive — never strips a member's existing roles.
                user.roles.add(*roles)
            messages.success(
                request,
                _("Applied %(roles)d role(s) to %(people)d member(s).")
                % {"roles": len(roles), "people": len(users)},
            )
            # PK-only audit line (no PII — passes the logging-smell gate).
            logger.info(
                "owner_console.bulk_roles actor=%s people=%s roles=%s school=%s",
                getattr(request.user, "pk", None),
                len(users),
                len(roles),
                getattr(school, "pk", None),
            )
            return redirect("accounts:owner_console_people")
        messages.error(request, _("Select at least one person and one role."))
    else:
        form = OwnerBulkRolesForm(school=school)

    ctx = {
        "school": school,
        "owner_name": (request.user.get_full_name() or request.user.get_username()),
        "sections": _console_sections("people"),
        "form": form,
        "roster_rows": _roster_rows(school),
        "invite_url": _safe("accounts:tenant_identity_invite"),
        "roster_hub_url": _safe("accounts:tenant_identity_roster"),
        "console_url": _safe("accounts:owner_console"),
    }
    return render(request, "accounts/owner_console/people.html", ctx)
