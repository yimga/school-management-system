"""One save endpoint for every in-place edit in the tenant backend shell.

WHY ONE ENDPOINT. ``apps.metadata.inline_edit`` derives what is editable from
``Model._meta``, so a per-model save view would put the one hand-written, drifting
part back in. This view knows no models: it is handed an app label, a model name,
a pk and a field, and every decision it makes -- may this user, may this field, may
this school, what else does this imply -- comes from the registry.

WHY IT LIVES IN ``apps.accounts`` AND NOT ``apps.metadata``. ``apps.metadata.urls``
is included from ``config/urls.py`` only. ``config/tenant_urls.py`` -- the urlconf a
real school host resolves against -- does not include it, so a route added there
would resolve in dev and 404 for every actual tenant. ``apps.accounts.urls`` is
mounted on both hosts, which is why the backend shell already lives there and why
this does too.

WHAT "APPLICABLE" MEANS, since the brief was every record and not a named few.
A model is editable here when all three hold, and each is a property of the model
rather than a list somebody maintains:

  1. it carries a ``school`` foreign key -- i.e. the row BELONGS to a school, so
     there is a tenant to scope it to. This is what keeps platform tables
     (``School`` itself, ``User``, billing plans) out without naming them.
  2. it is not append-only. An audit row that can be edited is not an audit row.
  3. the caller holds Django's own ``<app>.change_<model>`` permission for it.

THE PERMISSION SEEDING TRAP. (3) is Django's real permission, so a role that can
already change a model through any other surface can edit it here. But an
unseeded permission code denies EVERYONE, silently and permanently -- there is no
error, the control simply never appears. If this endpoint 403s for a user who
plainly should have access, check that the code exists before looking anywhere
else.
"""

from __future__ import annotations

import json
import logging

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import DatabaseError, transaction
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST

from apps.metadata.inline_edit import (
    TENANT_FIELD,
    cascade_updates,
    change_permission,
    clean_value,
    editable_fields,
    is_privilege_field,
    membership_joins,
    related_choices,
    scoped_instance,
    structural_lock,
)

logger = logging.getLogger(__name__)


def _is_append_only(model) -> bool:
    """An append-only table's whole guarantee is that nothing rewrites it."""
    return any(base.__name__ == "AppendOnlyModelMixin" for base in model.__mro__)


def resolve_editable_model(app_label: str, model_name: str):
    """The model for this request, or ``Http404`` when it may not be edited here.

    404 rather than 403 on every refusal is deliberate: whether a given model is
    editable is not information this endpoint owes an unauthenticated guess, and
    a distinct code would enumerate the schema for anyone with a URL bar.
    """
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        raise Http404("No such record type.") from None
    if model is None:
        raise Http404("No such record type.")
    try:
        model._meta.get_field(TENANT_FIELD)
    except FieldDoesNotExist:
        # A school owns people who carry no school column. ``accounts.User`` is
        # the case that matters: a person belongs to a school through
        # SchoolMembership (and three other membership-shaped tables), and a
        # school that cannot correct a staff member's name or role has to be sent
        # to /admin -- the platform's surface, not theirs. The tenant record
        # itself never qualifies; see the degenerate-case guard in
        # ``membership_joins``.
        if not membership_joins(model):
            raise Http404("That record type is not owned by a school.") from None
    if _is_append_only(model):
        raise Http404("That record type is a permanent log.")
    return model


def _is_self(user, instance) -> bool:
    """Is this record the requesting user, directly or through their profile?

    Covers both shapes the endpoint sees: editing ``accounts.User`` row 7 while
    logged in as user 7, and editing the ``SchoolMembership`` or
    ``TeacherProfile`` that POINTS at user 7.
    """
    pk = getattr(user, "pk", None)
    if pk is None:
        return False
    if instance._meta.label_lower == user._meta.label_lower and instance.pk == pk:
        return True
    return getattr(instance, "user_id", None) == pk


def _display(instance, field_name: str) -> str:
    """What the field should now read as on the page."""
    value = getattr(instance, field_name, None)
    if value is None:
        return ""
    if hasattr(value, "pk"):
        for attr in ("name", "title", "code", "label"):
            label = getattr(value, attr, None)
            if label:
                return str(label)
    return str(value)


def _audit(request, instance, field_name, before, after) -> None:
    """Record the change. Never blocks the save.

    Matches the house rule the backend detail views already follow: audit errors
    must not cost a school an edit it was entitled to make. A failure here is
    logged with a stack rather than swallowed, so a silently un-audited surface
    is still discoverable.
    """
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            ip_address=(request.META.get("REMOTE_ADDR") or None),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            action=AuditLog.Action.UPDATE,
            model_name=instance._meta.object_name,
            object_id=str(instance.pk),
            object_repr=str(instance)[:500],
            old_values={field_name: before},
            new_values={field_name: after},
        )
    except (DatabaseError, ImportError, TypeError, ValueError):
        # Named rather than bare: the realistic failures are the app being absent,
        # the insert being refused, and a value the JSON field will not take. The
        # save is already committed by this point, so a raise here would 500 AFTER
        # a successful write -- the worst of both. Anything outside this tuple is
        # a bug worth surfacing rather than swallowing.
        logger.exception("inline edit: audit write failed for %s", instance._meta.label)


@login_required
@require_POST
def inline_edit_save(request, app_label: str, model_name: str, pk: int):
    """Save one field of one record, with everything the schema says it implies."""
    school = getattr(request, "school", None)
    if school is None:
        raise Http404("No school on this request.")

    model = resolve_editable_model(app_label, model_name)
    if not request.user.has_perm(change_permission(model)):
        return JsonResponse(
            {
                "ok": False,
                "error": "You do not have permission to change this record.",
                "permission": change_permission(model),
            },
            status=403,
        )

    instance = scoped_instance(model, pk, school=school)
    if instance is None:
        raise Http404("Record not found.")

    field_name = (request.POST.get("field") or "").strip()
    if not field_name:
        return JsonResponse({"ok": False, "error": "No field named."}, status=400)
    try:
        field = model._meta.get_field(field_name)
    except FieldDoesNotExist:
        raise Http404("No such field.") from None
    reason = structural_lock(field)
    if reason:
        # The same refusal ``clean_value`` makes, made earlier so the response can
        # say WHY. The renderer never offers these, but a POST is not the renderer.
        return JsonResponse(
            {"ok": False, "error": f"{field_name} cannot be edited here: {reason}."},
            status=400,
        )

    # THE SECOND GATE. Everything above asks "may you edit this record". A field
    # that changes what somebody may DO is the one case where the person making
    # the edit can profit from it, so it asks two more questions.
    #
    # NOTE ON WHAT IS DELIBERATELY *NOT* DONE HERE. There is no "you may not grant
    # a role above your own" rule, because this schema has no privilege ladder to
    # read one from: User.Role is declared SUPERADMIN, ADMIN, LEADERSHIP,
    # PRINCIPAL ... TEACHER, IT_ADMIN, DPO, and IT_ADMIN sits AFTER TEACHER. Enum
    # order is not seniority, and inventing a ranking would be a guess that
    # silently decides who can promote whom. The platform already answers the
    # authority question in one place -- reuse it rather than invent a second.
    if is_privilege_field(field):
        from apps.accounts.views_tenant_identity import _can_manage_tenant_identity

        if not _can_manage_tenant_identity(request.user, school):
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "Changing roles and access needs identity-management "
                        "rights at this school."
                    ),
                    "field": field_name,
                },
                status=403,
            )
        if _is_self(request.user, instance):
            # Self-escalation. Needs no ladder to refuse: raising your OWN
            # authority is the move, whatever the roles happen to be called.
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "You cannot change your own role or access. Ask another "
                        "administrator."
                    ),
                    "field": field_name,
                },
                status=403,
            )

    try:
        value = clean_value(model, field_name, request.POST.get("value"), school=school)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    before = _display(instance, field_name)
    implied = cascade_updates(model, field_name, value)

    with transaction.atomic():
        setattr(instance, field_name, value)
        for dependent, dependent_value in implied.items():
            setattr(instance, dependent, dependent_value)
        instance.save(update_fields=[field_name, *implied.keys()])

    after = _display(instance, field_name)
    _audit(request, instance, field_name, before, after)

    return JsonResponse(
        {
            "ok": True,
            "field": field_name,
            "display": after,
            # Named separately from the edit so the page can say "department was
            # set to Sciences too" rather than silently changing a second control
            # the person did not touch. A cascade the user cannot see is a cascade
            # they will undo by hand next week.
            "also_set": {
                dependent: _display(instance, dependent) for dependent in implied
            },
        }
    )


@login_required
def inline_edit_options(request, app_label: str, model_name: str, pk: int):
    """The choices one relation field may take, scoped to this school.

    Served from ``related_choices`` -- the same call ``clean_value`` validates
    against -- so what a dropdown offers and what the save accepts cannot drift.
    Used to refresh a dependent control after a cascade without a page reload.
    """
    school = getattr(request, "school", None)
    if school is None:
        raise Http404("No school on this request.")
    model = resolve_editable_model(app_label, model_name)
    if not request.user.has_perm(change_permission(model)):
        return JsonResponse({"ok": False, "error": "Not permitted."}, status=403)

    field_name = (request.GET.get("field") or "").strip()
    offered = {f.name for f in editable_fields(model)}
    if field_name not in offered:
        raise Http404("No such editable field.")
    return JsonResponse(
        {
            "ok": True,
            "field": field_name,
            "choices": [
                {"value": value, "label": label}
                for value, label in related_choices(model, field_name, school=school)
            ],
        }
    )
