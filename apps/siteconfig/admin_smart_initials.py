"""Registry of editable, server-calculated Django admin initial values.

Two layers, in precedence order:

1. :data:`INITIAL_BUILDERS` — exact, per-model builders.  A builder knows the
   whole shape of one add form and can compute values no generic rule could.
2. :data:`FIELD_RESOLVERS` — generic, field-level derivations that apply to any
   model carrying a matching field.  ``academic_year`` means the same thing on
   ``evals.evaluation`` as on ``analytics.gradepredictionlabel``, and writing 27
   identical builders to say so would be the wrong shape.

Layer 1 wins on conflict.  Both are suggestions only: :meth:`get_changeform_initial_data`
applies Django's query-string initials *after* these, so explicit user input always
wins, and every value stays editable.

THE RULES THESE LAYERS ARE WRITTEN AGAINST
    * Never guess.  A value is only supplied when it is *derivable* from stored
      tenant state.  ``user`` is the standing example of a field this module
      deliberately leaves empty: on ``compliance.auditlog`` it is the subject of
      an audited action, on ``apicenter.oauthauthorizationcode`` it is the token's
      resource owner, and on neither is it "whoever opened the form".  A wrong
      pre-fill is worse than an empty one, because a person will accept it.
    * Tenant scoping is load-bearing.  Every resolver takes the school from the
      request and filters by it.  A resolver that can return another tenant's row
      is a security defect, not a bug.
    * Matching is by field SHAPE, not by name.  A resolver declaring a relational
      target compares against ``_meta.concrete_model``, so the
      ``global_registries.RegionConfig`` proxy resolves through to
      ``siteconfig.RegionConfig`` without an alias table.  A non-relational
      resolver additionally checks ``choices`` membership and ``max_length``
      before offering a value.
    * Nothing raises.  :meth:`AdminFormAutomationMixin.get_changeform_initial_data`
      guards a fixed exception set; anything outside it would break the add form
      itself, so every resolver body is contained here.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
import logging
from typing import Any, Callable, Iterable


logger = logging.getLogger(__name__)


#: Fields naming *the person performing this action*, which is the request user by
#: definition.  Deliberately an explicit list, not a ``*_by`` pattern: ``reports_to``,
#: ``assigned_to`` and ``supervised_by`` also end in a person, and none of them mean
#: "me".  Names already covered by ``SYSTEM_EVIDENCE_FIELDS`` (``created_by``,
#: ``approved_by``, ...) are absent because those are read-only evidence bound at
#: save time by ``_bind_transition_evidence`` — offering them as initials would put
#: an editable control on a field the form does not render.
ACTOR_FIELD_NAMES = frozenset(
    {
        "actor",
        "author",
        "checked_by",
        "labeled_by",
        "logged_by",
        "raised_by",
        "recorded_by",
        "reported_by",
        "requested_by",
        "reviewed_by",
        "submitted_by",
        "uploaded_by",
    }
)

#: Concrete model labels the relational resolvers bind to.  Held as constants so a
#: model move shows up as one edit here rather than as silent coverage loss.
ACADEMIC_YEAR_LABEL = "academics.academicyear"
TERM_LABEL = "academics.term"
REGION_CONFIG_LABEL = "siteconfig.regionconfig"
TEACHER_PROFILE_LABEL = "people.teacherprofile"
USER_LABEL_SETTING = "AUTH_USER_MODEL"

#: Reason strings surfaced in help text when a value came from a fallback rather
#: than from an unambiguous active record.  Rule: a derived-by-fallback value must
#: say so on the form.
NOTE_YEAR_FALLBACK = "Suggested: this school's most recent academic year (no year is marked active)."
NOTE_TERM_FALLBACK = "Suggested: this school's active term (today falls outside every term's dates)."


def _request_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = str(request.GET.get("school") or "").strip()
    if not school_id:
        return None
    from apps.schools.models import School

    return School.objects.filter(pk=school_id).first()


@dataclass
class InitialContext:
    """Everything a resolver may consult, resolved once per add-form request."""

    request: Any
    school: Any
    user: Any
    #: Populated by resolvers that fell back; drained into help text by the mixin.
    notes: dict[str, str] = dataclass_field(default_factory=dict)

    _year_cache: Any = None
    _year_done: bool = False
    _term_cache: Any = None
    _term_done: bool = False

    def academic_year(self):
        """The school's operating academic year, or None. Scoped to this tenant."""
        if self._year_done:
            return self._year_cache
        self._year_done = True
        if self.school is None:
            return None
        from apps.automation.helpers import get_current_academic_year

        self._year_cache = get_current_academic_year(school=self.school)
        return self._year_cache

    def term(self):
        """The school's current term within its operating year, or None."""
        if self._term_done:
            return self._term_cache
        self._term_done = True
        year = self.academic_year()
        if year is None:
            return None
        from apps.automation.helpers import get_current_term

        self._term_cache = get_current_term(year, school=self.school)
        return self._term_cache


@dataclass(frozen=True)
class FieldResolver:
    """One derivable value, bound to the field shapes it is allowed to answer for."""

    names: frozenset[str]
    resolve: Callable[[InitialContext], Any]
    reason: str
    #: Concrete model label for relational fields. Empty means "not relational".
    target_label: str = ""
    #: Allowed field class names for non-relational fields.
    value_field_types: tuple[str, ...] = ()

    def matches(self, model_field) -> bool:
        remote = getattr(model_field, "remote_field", None)
        if self.target_label:
            if remote is None or remote.model is None:
                return False
            concrete = remote.model._meta.concrete_model
            return concrete._meta.label_lower == self.target_label
        if remote is not None:
            return False
        return type(model_field).__name__ in self.value_field_types


def _user_target_label() -> str:
    from django.conf import settings

    return str(settings.AUTH_USER_MODEL).lower()


# --------------------------------------------------------------------------- #
# Resolver bodies.  Each returns a saveable value or None; never raises.
# --------------------------------------------------------------------------- #


def _resolve_academic_year(ctx: InitialContext):
    year = ctx.academic_year()
    if year is None:
        return None
    if not getattr(year, "is_active", False):
        ctx.notes["academic_year"] = NOTE_YEAR_FALLBACK
    return year.pk


def _resolve_term(ctx: InitialContext):
    from django.utils import timezone

    term = ctx.term()
    if term is None:
        return None
    today = timezone.now().date()
    start = getattr(term, "start_date", None)
    end = getattr(term, "end_date", None)
    if not (start and end and start <= today <= end):
        ctx.notes["term"] = NOTE_TERM_FALLBACK
    return term.pk


def _resolve_region(ctx: InitialContext):
    if ctx.school is None:
        return None
    return getattr(ctx.school, "default_region_id", None)


def _resolve_actor(ctx: InitialContext):
    user = ctx.user
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user.pk


def _resolve_teacher_profile(ctx: InitialContext):
    """The requesting user's own teacher record, and only within this school."""
    user = ctx.user
    if ctx.school is None or user is None or not getattr(user, "is_authenticated", False):
        return None
    from apps.people.models import TeacherProfile

    profile = TeacherProfile.objects.filter(user=user, school=ctx.school).only("pk").first()
    return profile.pk if profile is not None else None


def _school_attr(attribute: str) -> Callable[[InitialContext], Any]:
    def _resolve(ctx: InitialContext):
        if ctx.school is None:
            return None
        value = getattr(ctx.school, attribute, "")
        return value or None

    return _resolve


FIELD_RESOLVERS: tuple[FieldResolver, ...] = (
    FieldResolver(
        names=frozenset({"academic_year"}),
        resolve=_resolve_academic_year,
        target_label=ACADEMIC_YEAR_LABEL,
        reason="the school's operating academic year",
    ),
    FieldResolver(
        names=frozenset({"term"}),
        resolve=_resolve_term,
        target_label=TERM_LABEL,
        reason="the school's current term",
    ),
    FieldResolver(
        names=frozenset({"region"}),
        resolve=_resolve_region,
        target_label=REGION_CONFIG_LABEL,
        reason="the school's configured region",
    ),
    FieldResolver(
        names=frozenset({"teacher"}),
        resolve=_resolve_teacher_profile,
        target_label=TEACHER_PROFILE_LABEL,
        reason="the requesting user's own teacher record in this school",
    ),
    FieldResolver(
        names=frozenset({"country_code"}),
        resolve=_school_attr("country_code"),
        value_field_types=("CharField",),
        reason="the school's country",
    ),
    FieldResolver(
        names=frozenset({"currency"}),
        resolve=_school_attr("currency"),
        value_field_types=("CharField",),
        reason="the school's default currency",
    ),
    FieldResolver(
        names=frozenset({"timezone"}),
        resolve=_school_attr("timezone"),
        value_field_types=("CharField",),
        reason="the school's timezone",
    ),
    FieldResolver(
        names=frozenset({"language", "language_code"}),
        resolve=_school_attr("default_language"),
        value_field_types=("CharField",),
        reason="the school's default language",
    ),
)


def _actor_resolver() -> FieldResolver:
    """Built lazily: the user model label comes from settings, not a literal."""
    return FieldResolver(
        names=ACTOR_FIELD_NAMES,
        resolve=_resolve_actor,
        target_label=_user_target_label(),
        reason="the signed-in user is the person performing this action",
    )


def _all_resolvers() -> Iterable[FieldResolver]:
    yield from FIELD_RESOLVERS
    yield _actor_resolver()


def _value_fits(model_field, value) -> bool:
    """Refuse a value the field could not store or render.

    A ``currency`` of ``NGN`` offered to a field whose choices are ISO numeric
    codes would render as nothing selected — harmless, but it is also not
    coverage, and counting it as such would inflate every number this work is
    measured by.
    """
    choices = getattr(model_field, "choices", None)
    if choices:
        allowed = {str(choice[0]) for choice in choices}
        if str(value) not in allowed:
            return False
    max_length = getattr(model_field, "max_length", None)
    if max_length and isinstance(value, str) and len(value) > max_length:
        return False
    return True


def resolve_field_initials(model, ctx: InitialContext) -> dict[str, Any]:
    """Apply every generic resolver whose shape matches a field on ``model``."""

    from django.core.exceptions import FieldDoesNotExist

    resolved: dict[str, Any] = {}
    resolvers = list(_all_resolvers())
    for model_field in model._meta.get_fields():
        name = getattr(model_field, "name", "")
        if not name or getattr(model_field, "auto_created", False):
            continue
        if not getattr(model_field, "concrete", False):
            continue
        if not getattr(model_field, "editable", False):
            continue
        for resolver in resolvers:
            if name not in resolver.names or not resolver.matches(model_field):
                continue
            try:
                value = resolver.resolve(ctx)
            except (AttributeError, FieldDoesNotExist, LookupError, TypeError, ValueError):
                logger.warning(
                    "admin initial resolver failed model=%s field=%s",
                    model._meta.label_lower,
                    name,
                    exc_info=True,
                )
                break
            if value is None or value == "":
                break
            if not _value_fits(model_field, value):
                ctx.notes.pop(name, None)
                break
            resolved[name] = value
            break
    return resolved


# --------------------------------------------------------------------------- #
# Per-model builders.  Layer 1: they win over the generic resolvers.
# --------------------------------------------------------------------------- #


def _academic_year_initials(request) -> dict[str, Any]:
    school = _request_school(request)
    if school is None:
        return {}
    from apps.academics.structure_provisioning import forecast_academic_year

    forecast = forecast_academic_year(school)
    if not forecast:
        return {}
    return {
        "school": school.pk,
        "name": forecast["name"],
        "start_date": forecast["start_date"],
        "end_date": forecast["end_date"],
        "is_active": forecast["is_active"],
    }


INITIAL_BUILDERS = {
    "academics.academicyear": _academic_year_initials,
}


#: Per-request memo attribute. Two callers ask for the same model's suggestions on
#: every add form -- the form builder and the note renderer -- and resolving twice
#: means running the year, term and teacher-profile queries twice for one page.
_REQUEST_CACHE_ATTR = "_rmc_smart_initials_cache"


def build_admin_smart_initials_detailed(model, request) -> tuple[dict[str, Any], dict[str, str]]:
    """Return ``(values, notes)``: suggestions plus why a fallback was used.

    Notes are keyed by field name and are surfaced on the rendered form, so a
    value derived from a fallback rather than from an unambiguous active record
    says so where the person can see it.
    """

    label = model._meta.label_lower
    cache = getattr(request, _REQUEST_CACHE_ATTR, None)
    if isinstance(cache, dict) and label in cache:
        values, notes = cache[label]
        return dict(values), dict(notes)

    school = _request_school(request)
    user = getattr(request, "user", None)
    ctx = InitialContext(request=request, school=school, user=user)

    values = resolve_field_initials(model, ctx)

    builder = INITIAL_BUILDERS.get(model._meta.label_lower)
    if builder is not None:
        # Layer 1 wins: an exact builder knows the whole form's shape.
        exact = dict(builder(request) or {})
        values.update(exact)
        # A note explains how the GENERIC layer derived a value.  Where a builder
        # replaced that value the note no longer describes what is on the form.
        for name in exact:
            ctx.notes.pop(name, None)

    notes = dict(ctx.notes)
    if cache is None:
        cache = {}
        try:
            setattr(request, _REQUEST_CACHE_ATTR, cache)
        except (AttributeError, TypeError):
            # A request-like object that refuses attributes still works; it just
            # does not get the memo.
            return values, notes
    cache[label] = (dict(values), dict(notes))
    return values, notes


def build_admin_smart_initials(model, request) -> dict[str, Any]:
    """Return suggestions only; bound POST data and user edits always win."""

    values, _notes = build_admin_smart_initials_detailed(model, request)
    return values
