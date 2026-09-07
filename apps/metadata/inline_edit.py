"""Field-level inline editing for the tenant operational backend.

WHY THIS EXISTS. ``/authentication/backend/`` renders a school's own records --
teachers, students, classrooms, specialties -- and every detail view is
read-only. ``backend_teacher_detail``, ``backend_student_detail`` and
``backend_classroom_detail`` handle GET and nothing else, and no edit route
exists for any of them. Create forms exist (``apps.people.forms_backend``);
edit forms do not exist at all. So the only way a school can correct a record
it already holds is ``/admin/`` -- the platform's surface, not the school's.

WHY A REGISTRY AND NOT FORTY EDIT PAGES. Hand-written edit pages go stale the
day a model gains a field, and they cover only the models somebody remembered
to write. This module derives what is editable from ``Model._meta`` instead, so
a new field is editable as soon as it exists and a newly registered model needs
no field list written for it.

THE THREE DERIVATIONS. Nothing below is a per-model lookup table:

* WHICH FIELDS -- every concrete, user-editable field except those
  ``structural_lock`` refuses: the tenant key, audit stamps, offline sync
  anchors, and secrets. A denial is returned WITH ITS REASON so a caller can
  explain the missing control instead of silently omitting it.
* WHICH PERMISSION -- ``<app_label>.change_<model_name>``, Django's own code,
  so a role that can already change a model can edit it here too.
* WHICH CASCADE -- the foreign-key graph. When a model holds FKs to both A and
  B, and A itself has an FK to B, then choosing an A determines its B. That one
  rule produces ``specialty -> department`` without being told about either;
  it was not written for that pair and it holds for every other pair the schema
  happens to contain.

THE SECURITY PROPERTY THIS MODULE OWNS. ``related_choices`` scopes every
relation queryset to one school, and ``clean_value`` re-resolves the submitted
key THROUGH that same scoped queryset rather than trusting it. Those are the
same call, deliberately: a choice list that is not also the validator is a
cross-tenant write vector, because a POST is under no obligation to contain a
value the page offered. This matters more on an appliance than in the cloud --
schema-per-tenant isolates the cloud by construction, but the box runs one
schema with row-level security, and RLS does not bind a superuser connection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import models

logger = logging.getLogger(__name__)

#: The tenant discriminator. Editing it would move a record between schools,
#: which is an operator action, never an in-place field edit.
TENANT_FIELD = "school"

#: Names locked on every model. Structural rather than a per-model denylist:
#: each entry is something the platform owns, not something a school describes.
LOCKED_NAMES = frozenset(
    {
        "id",
        TENANT_FIELD,
        "created_at",
        "updated_at",
        "deleted_at",
        "last_login",
        "password",
        # Offline/edge sync identity. Rewriting it re-points which remote row a
        # local row IS, and the delta rail keys on it.
        "client_offline_id",
        # Merge tombstone pointer -- set by the merge service, never by hand.
        "merged_into",
    }
)

#: Substrings that mark credential material whatever model carries it.
LOCKED_FRAGMENTS = ("password", "secret", "token", "api_key", "private_key")


@dataclass(frozen=True)
class EditableField:
    """One in-place editable field, described for a renderer that knows no models."""

    name: str
    label: str
    kind: str
    required: bool
    help_text: str = ""
    related_model: Optional[Any] = None
    choices: tuple = ()

    @property
    def is_relation(self) -> bool:
        return self.kind == "relation"


def structural_lock(field) -> str:
    """Why this field may never be edited in place, or "" when it may.

    Returns the REASON rather than a boolean so a caller can say why a control is
    absent. A field silently missing from an edit surface is indistinguishable
    from one the registry failed to notice, and that ambiguity is exactly how a
    coverage gap survives review.
    """
    name = getattr(field, "name", "")
    if not getattr(field, "concrete", False):
        return "not a stored column"
    if getattr(field, "primary_key", False):
        return "primary key"
    if not getattr(field, "editable", True):
        return "not user-editable"
    if getattr(field, "auto_created", False):
        return "created by the framework"
    if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
        return "maintained automatically"
    # Credentials are tested BEFORE the platform-owned list, even though
    # ``password`` appears in both. The reason string is the whole point of
    # returning a reason instead of a boolean -- an operator told "password cannot
    # be edited here: credential material" understands immediately, where "owned
    # by the platform" reads like a licensing limit somebody might ask to have
    # lifted.
    if any(fragment in name for fragment in LOCKED_FRAGMENTS):
        return "credential material"
    if name in LOCKED_NAMES:
        return "owned by the platform, not the school"
    if isinstance(field, models.ManyToManyField):
        # Deliberate: a set-valued edit is a different interaction (add / remove,
        # each with its own audit row), not a single-value save. Left to a later
        # pass rather than approximated here.
        return "multi-value relation"
    if isinstance(field, models.OneToOneField):
        # A one-to-one IS an identity binding, not an attribute: TeacherProfile.user
        # says WHICH LOGIN this person is, and StudentProfile.passport says which
        # document is theirs. Re-pointing one hands a record to a different human,
        # which is an account operation with its own audit trail, never a field edit.
        return "identity binding"
    return ""


def field_kind(field) -> str:
    """The renderer-facing shape of a field, derived from its Django type."""
    if field.is_relation:
        return "relation"
    if getattr(field, "choices", None):
        return "choice"
    if isinstance(field, models.BooleanField):
        return "boolean"
    if isinstance(field, models.DateTimeField):
        return "datetime"
    if isinstance(field, models.DateField):
        return "date"
    if isinstance(field, models.EmailField):
        return "email"
    if isinstance(field, (models.IntegerField, models.DecimalField, models.FloatField)):
        return "number"
    if isinstance(field, models.TextField):
        return "text_long"
    return "text"


def describe(field) -> EditableField:
    """One ``EditableField`` for a concrete model field."""
    return EditableField(
        name=field.name,
        label=str(getattr(field, "verbose_name", field.name)).strip() or field.name,
        kind=field_kind(field),
        required=not (field.blank or field.null),
        help_text=str(getattr(field, "help_text", "") or ""),
        related_model=field.related_model if field.is_relation else None,
        choices=tuple(getattr(field, "choices", None) or ()),
    )


def editable_fields(model) -> list[EditableField]:
    """Every field of ``model`` a permitted user may edit in place.

    Derived from ``_meta``, so a field added to the model tomorrow is editable
    tomorrow without this module being touched.
    """
    out: list[EditableField] = []
    for field in model._meta.get_fields():
        if not hasattr(field, "attname"):
            continue
        if structural_lock(field):
            continue
        out.append(describe(field))
    return out


def locked_fields(model) -> dict[str, str]:
    """``{field name: reason}`` for everything ``editable_fields`` refused."""
    locked: dict[str, str] = {}
    for field in model._meta.get_fields():
        if not hasattr(field, "attname"):
            continue
        reason = structural_lock(field)
        if reason:
            locked[field.name] = reason
    return locked


def change_permission(model) -> str:
    """Django's own change code for ``model``. Never a bespoke string."""
    return f"{model._meta.app_label}.change_{model._meta.model_name}"


def scoped_queryset(related_model, *, school):
    """Every row of ``related_model`` this school may reference, and no other.

    Scoping applies when the related model actually carries a ``school`` FK. When
    it does not, the model is school-agnostic by construction (a country registry,
    say) and an unscoped queryset is the correct answer rather than an oversight.
    ``related_choices`` and ``clean_value`` share this one function so the list
    offered and the values accepted cannot drift apart.
    """
    manager = getattr(related_model, "_default_manager", None)
    if manager is None:
        return related_model.objects.none()
    qs = manager.all()
    try:
        related_model._meta.get_field(TENANT_FIELD)
    except Exception:  # noqa: BLE001 -- FieldDoesNotExist means school-agnostic
        return qs
    if school is None:
        return qs.none()
    return qs.filter(**{TENANT_FIELD: school})


def _label_for(obj) -> str:
    for attr in ("name", "title", "code", "label"):
        value = getattr(obj, attr, None)
        if value:
            return str(value)
    return str(obj)


def related_choices(model, field_name: str, *, school) -> list[tuple[Any, str]]:
    """``(pk, label)`` pairs for one relation field, scoped to ``school``."""
    field = model._meta.get_field(field_name)
    if not field.is_relation:
        return []
    return [(obj.pk, _label_for(obj)) for obj in scoped_queryset(field.related_model, school=school)]


def _is_model_class(candidate) -> bool:
    """A resolved model, not an unresolved lazy ``"app.Model"`` string.

    Django leaves ``related_model`` as a string for a reference it has not yet
    resolved. Three feedback models are in that state at import time and walking
    them raised ``AttributeError`` on the first probe run; a cascade rule that
    crashes on part of the schema is a rule that silently covers less than it
    claims.
    """
    return hasattr(candidate, "_meta")


def _relation_fields(model) -> list:
    """Concrete, editable relation fields of ``model`` with a resolved target."""
    return [
        f
        for f in model._meta.get_fields()
        if hasattr(f, "attname")
        and getattr(f, "is_relation", False)
        and not structural_lock(f)
        and _is_model_class(getattr(f, "related_model", None))
    ]


def _sole_field_targeting(fields, target) -> Optional[str]:
    """The one field in ``fields`` pointing at ``target``, or None if not exactly one.

    Ambiguity is refused rather than resolved. ``RolloverProposal`` holds
    ``source_year`` AND ``target_year``, both to ``AcademicYear``; picking either
    would be a coin toss that writes real rows, so nothing is picked.
    """
    matches = [f.name for f in fields if f.related_model is target]
    return matches[0] if len(matches) == 1 else None


def _is_actor_relation(field) -> bool:
    """Does this field record WHO, rather than WHAT a record belongs to?

    An actor is a fact about an event -- who resolved the incident, who uploaded
    the file, whose login this profile is -- and is never implied by a
    classification. The first version of ``derive_cascades`` did not draw this
    line and produced ``TeacherProfile.reports_to -> user``: setting a teacher's
    supervisor would have overwritten that teacher's own login with the
    supervisor's. Identity is not derivable, so it is excluded structurally.

    THE NAME CHECK BELOW IS REDUNDANT TODAY AND IS KEPT ANYWAY. Measured
    2026-09-07 across all installed models: 315 relation fields are actor-NAMED
    (``*_by``, ``user``, ``owner``, ``assigned_to``) and all 315 point at
    ``accounts.user`` -- so the target check alone catches every one of them, and
    a mutation disabling just the name check leaves the whole suite green. It
    stays because it is the only guard against the case the schema does not yet
    contain: an ``approved_by`` pointing at a ``TeacherProfile`` rather than a
    login. Do not delete it on the strength of a passing suite; nothing tests it,
    and that is a statement about the schema, not about the check.
    """
    if field.name.endswith("_by") or field.name in ("user", "assigned_to", "owner"):
        return True
    if isinstance(field, models.OneToOneField):
        # A one-to-one IS an identity binding (profile <-> user, person <-> passport),
        # not a category. Implying one would re-point who a record is.
        return True
    target = getattr(field, "related_model", None)
    return bool(_is_model_class(target) and target._meta.label_lower == _user_model_label())


def _user_model_label() -> str:
    from django.conf import settings

    return str(getattr(settings, "AUTH_USER_MODEL", "auth.User")).lower()


def derive_cascades(model) -> dict[str, tuple[str, ...]]:
    """``{driving field: dependent fields}`` read off the foreign-key graph.

    A model holding FKs to both A and B, where A itself has an FK to B, means an
    A already determines a B -- so choosing the A and then also being asked for
    the B invites a contradiction the schema can settle itself.
    ``TeacherProfile.specialty`` -> ``Specialty.department`` ->
    ``TeacherProfile.department`` is one instance of that, not its definition.

    THE RULE IS NARROWER THAN THAT SENTENCE, and every narrowing below was
    measured rather than guessed. Run across all 814 installed models the bare
    rule fired 344 times, and the failures were not edge cases:

      * ``TeacherProfile.reports_to -> user`` would have replaced a teacher's
        own login with their supervisor's. See ``_is_actor_relation``.
      * ``Incident.student -> resolved_by`` claimed a student determines who
        resolved their incident.
      * ``StudentProfile.academic_year -> updated_by`` claimed a school year
        determines who last touched the record.

    So a cascade fires only between CLASSIFICATIONS: what a record belongs to,
    never who acted on it, never who it is. Self-referential drivers are excluded
    too -- "inherit from my parent" is a real pattern, but a teacher may sit in a
    different department from their supervisor, and a rule that cannot tell those
    apart must not choose.
    """
    relations = _relation_fields(model)
    cascades: dict[str, set[str]] = {}
    for source in relations:
        if source.related_model is model:
            continue  # self-referential hierarchy: inheritance is opt-in, not implied
        if _is_actor_relation(source):
            continue
        for candidate in _relation_fields(source.related_model):
            if _is_actor_relation(candidate):
                continue
            dependent = _sole_field_targeting(relations, candidate.related_model)
            if not dependent or dependent == source.name:
                continue
            if _is_actor_relation(model._meta.get_field(dependent)):
                continue
            if _sole_field_targeting(_relation_fields(source.related_model), candidate.related_model) is None:
                continue  # the driving model states it twice; it states nothing
            cascades.setdefault(source.name, set()).add(dependent)
    return {key: tuple(sorted(value)) for key, value in sorted(cascades.items())}


def cascade_updates(model, field_name: str, value) -> dict[str, Any]:
    """The fields implied by setting ``field_name`` to ``value``.

    Returns only what the chosen row actually states. A driving row whose own FK
    is NULL implies nothing, and this returns nothing for it rather than writing
    a NULL over a value somebody set deliberately -- an absent answer is not the
    same as an answer of "none".
    """
    if value is None:
        return {}
    updates: dict[str, Any] = {}
    for dependent in derive_cascades(model).get(field_name, ()):
        target = model._meta.get_field(dependent).related_model
        for candidate in value._meta.get_fields():
            if not hasattr(candidate, "attname") or not candidate.is_relation:
                continue
            if candidate.related_model is not target:
                continue
            implied = getattr(value, candidate.name, None)
            if implied is not None:
                updates[dependent] = implied
    return updates


#: Fields that change what a person may DO, rather than describing them. Edited
#: through the same endpoint but behind a second gate -- see ``is_privilege_field``.
PRIVILEGE_NAMES = frozenset(
    {
        "role",
        "roles",
        "is_staff",
        "is_superuser",
        "is_school_owner",
        "suspended_at",
        # Deactivating a person removes their access as surely as demoting them.
        "is_active",
    }
)


def is_privilege_field(field) -> bool:
    """Does writing this field change someone's authority?

    Kept separate from ``structural_lock`` on purpose: these ARE editable -- a
    school must be able to make somebody a bursar without calling support -- but
    they are the one class of edit where the person doing it can profit from it.
    """
    name = getattr(field, "name", "")
    return name in PRIVILEGE_NAMES or name.endswith("_role")


def membership_joins(model) -> list:
    """Every ``(join model, fk name)`` that ties ``model`` to a school.

    Some models a school plainly owns carry no ``school`` column. ``accounts.User``
    is the one that matters: a person belongs to a school through
    ``SchoolMembership``, and a naive "must have a school FK" rule locks a school
    out of correcting its own staff members' names and roles.

    Derived, not listed. A join qualifies when it carries a ``school`` FK, a
    relation to ``model``, and a uniqueness constraint over BOTH -- which is what
    makes it a membership rather than an incidental table that happens to mention
    both. ``SchoolMembership`` declares ``unique_together = [("user", "school")]``
    and so qualifies; a log table referencing a user and a school does not, because
    one user may have many rows in it and "the" row to scope by would be a guess.
    """
    from django.apps import apps as django_apps

    found: list = []
    for candidate in django_apps.get_models():
        if candidate is model:
            continue
        try:
            candidate._meta.get_field(TENANT_FIELD)
        except Exception:  # noqa: BLE001 -- no school column: not a membership
            continue
        links = [
            f.name
            for f in candidate._meta.get_fields()
            if hasattr(f, "attname")
            and getattr(f, "is_relation", False)
            and getattr(f, "related_model", None) is model
        ]
        if len(links) != 1:
            continue  # zero, or ambiguous: which link scopes the row would be a guess
        link = links[0]
        if link == TENANT_FIELD:
            # Degenerate: ``model`` IS School, so the "link" and the tenant column
            # are one field and ``wanted`` collapses to a single-element set that
            # any per-school table satisfies. A tenant is not a row inside itself,
            # and admitting it here would make the School record editable through
            # the membership path that exists to reach its PEOPLE.
            continue
        # EXACTLY {link, school}, never a superset. Measured: a looser test
        # picked ``accounts.FeaturePermissionScope`` for ``User`` -- it carries a
        # school, a user, and a uniqueness constraint that ALSO includes the
        # permission. Scoping through it would have made only those users who
        # happen to hold a permission scope row editable, which is arbitrary. A
        # membership is the table whose identity IS (person, school) and nothing
        # further.
        wanted = {link, TENANT_FIELD}
        matched = any(
            set(u) == wanted for u in (candidate._meta.unique_together or ())
        ) or any(
            set(getattr(c, "fields", ()) or ()) == wanted
            for c in candidate._meta.constraints
        )
        if matched:
            found.append((candidate, link))
    return found


def scoped_instance(model, pk, *, school):
    """The one row of ``model`` with this pk that ``school`` may edit, or None.

    Two paths, and the second is why this is a function rather than a filter:
    a model with a ``school`` column is scoped directly, and a model without one
    is scoped through its membership join, so a school can reach its own people
    and no others. A user belonging to a different school resolves to None here
    exactly as a foreign department does in ``clean_value``.
    """
    manager = getattr(model, "_default_manager", None)
    if manager is None or school is None:
        return None
    try:
        model._meta.get_field(TENANT_FIELD)
    except Exception:  # noqa: BLE001 -- FieldDoesNotExist: try the membership path
        joins = membership_joins(model)
        if not joins:
            return None
        for join_model, link in joins:
            ids = join_model._default_manager.filter(
                **{TENANT_FIELD: school}
            ).values_list(f"{link}_id", flat=True)
            hit = manager.filter(pk=pk, pk__in=ids).first()
            if hit is not None:
                return hit
        return None
    return manager.filter(pk=pk, **{TENANT_FIELD: school}).first()


def clean_value(model, field_name: str, raw, *, school):
    """Turn one submitted value into something safe to assign, or refuse it.

    A relation is resolved THROUGH ``scoped_queryset`` -- the same call that built
    the dropdown -- so a pk belonging to another school is refused here even
    though it is a perfectly valid pk. Nothing else in the save path re-checks
    tenancy, and a POST is under no obligation to echo a value the page offered.
    """
    field = model._meta.get_field(field_name)
    reason = structural_lock(field)
    if reason:
        raise ValidationError(f"{field_name} cannot be edited here: {reason}.")

    blank = raw is None or (isinstance(raw, str) and not raw.strip())
    if blank:
        if not (field.null or field.blank):
            raise ValidationError(f"{field.verbose_name} is required.")
        return None if field.null else ""

    if field.is_relation:
        try:
            return scoped_queryset(field.related_model, school=school).get(pk=raw)
        except field.related_model.DoesNotExist:
            raise ValidationError(
                f"That {field.related_model._meta.verbose_name} is not available to this school."
            ) from None
    return field.clean(raw, None)
