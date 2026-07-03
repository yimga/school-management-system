"""Owner Console — Role bundles (named, reusable RoleGroups).

The follow-up to People & Roles: instead of picking the same handful of roles by
hand every time, an owner defines a **bundle** once (e.g. "Form Teacher" = form
teacher + attendance + gradebook) and applies it to many people in one click.

A bundle is authoring convenience only — applying it does ``user.roles.add(*roles)``
(additive, never strips), so permission resolution is unchanged. Owner-gated,
tenant-skinned, fail-soft. School-scoped: bundles never cross tenants.
"""

from __future__ import annotations

import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.accounts.models import AccessRole, RoleGroup, User
from apps.accounts.views_owner_console import _console_ctx, _safe, is_school_owner
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)


class RoleGroupCreateForm(forms.Form):
    """Define a named bundle of access roles."""

    name = forms.CharField(
        max_length=200, required=True, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=AccessRole.objects.none(),  # tenant-isolation-allow: set-in-init-school-scoped
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            from apps.accounts.access_roles import roles_queryset_for_school

            self.fields["roles"].queryset = roles_queryset_for_school(school)


class RoleGroupApplyForm(forms.Form):
    """Apply an existing bundle to selected people (additive)."""

    group = forms.ModelChoiceField(
        queryset=RoleGroup.objects.none(),  # tenant-isolation-allow: set-in-init-school-scoped
        required=True,
        widget=forms.RadioSelect,
        empty_label=None,
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),  # tenant-isolation-allow: set-in-init-school-scoped
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        if school is not None:
            from apps.accounts.tenant_identity import users_queryset_for_school

            self.fields["group"].queryset = RoleGroup.objects.filter(school=school)
            self.fields["users"].queryset = users_queryset_for_school(school)


def _group_rows(school) -> list[dict]:
    """Existing bundles with their member roles. Fail-soft."""
    rows: list[dict] = []
    try:
        for g in RoleGroup.objects.filter(school=school).prefetch_related("roles"):
            rows.append(
                {
                    "id": g.pk,
                    "name": g.name,
                    "roles": [r.name for r in g.roles.all()],
                }
            )
    except Exception as exc:  # noqa: BLE001 — list degrades to empty, never 500s
        logger.debug("owner console role-groups list failed: %s", exc)
    return rows


@login_required
@require_school
def owner_console_role_groups(request):
    """Role bundles — define reusable role sets and apply them in bulk (owner-gated)."""
    school = request.school
    if not is_school_owner(request.user, school):
        return HttpResponseForbidden(
            _("The Owner Console is available to school owners.")
        )

    create_form = RoleGroupCreateForm(school=school)
    apply_form = RoleGroupApplyForm(school=school)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            create_form = RoleGroupCreateForm(request.POST, school=school)
            if create_form.is_valid():
                name = create_form.cleaned_data["name"].strip()
                code = (slugify(name).replace("-", "_") or "bundle")[:120]
                try:
                    group = RoleGroup.objects.create(school=school, code=code, name=name)
                    group.roles.set(create_form.cleaned_data["roles"])
                    messages.success(request, _("Created the “%(name)s” bundle.") % {"name": name})
                    logger.info(
                        "owner_console.role_group_create actor=%s group=%s roles=%s school=%s",
                        getattr(request.user, "pk", None),
                        group.pk,
                        group.roles.count(),
                        getattr(school, "pk", None),
                    )
                    return redirect("accounts:owner_console_role_groups")
                except IntegrityError:
                    messages.error(request, _("A bundle with that name already exists."))
            else:
                messages.error(request, _("Give the bundle a name and pick at least one role."))

        elif action == "apply":
            apply_form = RoleGroupApplyForm(request.POST, school=school)
            if apply_form.is_valid():
                group = apply_form.cleaned_data["group"]
                users = list(apply_form.cleaned_data["users"])
                roles = list(group.roles.all())
                for user in users:
                    user.roles.add(*roles)  # additive — never strips existing roles
                messages.success(
                    request,
                    _("Applied “%(name)s” to %(people)d member(s).")
                    % {"name": group.name, "people": len(users)},
                )
                logger.info(
                    "owner_console.role_group_apply actor=%s group=%s people=%s roles=%s school=%s",
                    getattr(request.user, "pk", None),
                    group.pk,
                    len(users),
                    len(roles),
                    getattr(school, "pk", None),
                )
                return redirect("accounts:owner_console_role_groups")
            messages.error(request, _("Pick a bundle and at least one person."))

        elif action == "delete":
            group_id = request.POST.get("group_id")
            RoleGroup.objects.filter(school=school, pk=group_id).delete()
            messages.success(request, _("Bundle deleted. Roles already assigned are kept."))
            return redirect("accounts:owner_console_role_groups")

    ctx = _console_ctx(request, "rolegroups")
    ctx.update(
        {
            "create_form": create_form,
            "apply_form": apply_form,
            "group_rows": _group_rows(school),
            "people_url": _safe("accounts:owner_console_people"),
        }
    )
    return render(request, "accounts/owner_console/role_groups.html", ctx)
