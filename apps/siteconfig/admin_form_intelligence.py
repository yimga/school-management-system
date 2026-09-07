"""Shared, local-first form intelligence for both RunMyCampus admin sites.

The module deliberately keeps presentation, prediction, persistence and mutation
protection separate:

* :class:`AdminFormAutomationMixin` is inherited by every tenant and operator
  ``ModelAdmin`` registration.
* :class:`AdminFieldVisibilityService` stores optional-field choices in the
  existing local ``DashboardUserPreference`` row.  The edge database is the
  source of truth; the browser script only keeps a retry envelope while offline.
* suggested business values are initial values only and therefore remain editable;
* tenant ownership and lifecycle evidence are system-owned and read-only;
* hidden optional values remain in the bound form for normal validation, while a
  crafted POST is prevented from changing them.

No model-specific visual classes or layout rules live here.  The approved admin
canvas remains the sole layout owner.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any, Iterable

from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.admin.widgets import AdminSplitDateTime
from django.core.exceptions import (
    FieldDoesNotExist,
    FieldError,
    RequestDataTooBig,
    ValidationError,
)
from django.db import DatabaseError, transaction
from django.db import models
from django.http import HttpRequest, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext
from django.views.decorators.http import require_http_methods


logger = logging.getLogger(__name__)

PREFERENCE_NAMESPACE = "_rmc_admin_field_visibility_v1"
MAX_SURFACES_PER_USER = 600
MAX_HIDDEN_FIELDS = 512
MAX_PREFERENCE_PAYLOAD_BYTES = 64 * 1024

# These values are evidence emitted by governed transitions, not business inputs.
# The list is intentionally explicit: a blanket ``*_by``/``*_at`` rule would make
# legitimate assignment and scheduling fields read-only.
SYSTEM_EVIDENCE_FIELDS = frozenset(
    {
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "modified_at",
        "modified_by",
        "deleted_at",
        "deleted_by",
        "locked_at",
        "locked_by",
        "unlocked_at",
        "unlocked_by",
        "soft_closed_at",
        "soft_closed_by",
        "soft_reopened_at",
        "soft_reopened_by",
        "activated_at",
        "activated_by",
        "deactivated_at",
        "deactivated_by",
        "archived_at",
        "archived_by",
        "published_at",
        "published_by",
        "approved_at",
        "approved_by",
        "rejected_at",
        "rejected_by",
        "revoked_at",
        "revoked_by",
        "last_synced_at",
        "client_offline_id",
        "idempotency_key",
        "access_token_hash",
        "refresh_token_hash",
        "client_secret_hash",
        "code_hash",
        "document_hash",
        "file_hash",
        "secret_hash",
        "secret_key_hash",
        "signature_hash",
        "staff_id_hash",
        "substitute_id_hash",
        "teacher_id_hash",
        "tenant_hash",
        "tenant_id_hash",
        "text_hash",
        "training_dataset_hash",
        "legacy_password_hash",
        "payload_checksum",
        "payload_key_checksums",
        "device_fingerprint",
        "draft_fingerprint",
        "email_verify_token",
        "rollback_token",
        "signature_data",
        "signature_ip",
        "signature_user_agent",
        "sync_hash",
        "content_hash",
        "checksum",
    }
)

#: (child, parent) pairs where the child record STRUCTURALLY belongs to exactly one
#: parent, so the two selections disagreeing is unambiguously a data error rather
#: than an unusual-but-legal combination.  A ``Term`` has one ``academic_year``; a
#: ``SubjectAssignment`` has one of each.  Deliberately an explicit list and NOT a
#: generic "child has an FK to parent's model" rule: ``student`` and ``classroom``
#: are related that way too, and a student sitting an exam in another room is
#: perfectly legal — a generic rule would reject real data, which is worse than not
#: checking at all.  13 registered models carry the term/year pair.
RELATION_CONTAINMENT_PAIRS = (
    ("term", "academic_year"),
    ("subject_assignment", "academic_year"),
    ("subject_assignment", "term"),
)

RANGE_FIELD_PAIRS = (
    ("start_date", "end_date"),
    ("starts_on", "ends_on"),
    ("start_at", "end_at"),
    ("starts_at", "ends_at"),
    ("valid_from", "valid_to"),
    ("effective_from", "effective_to"),
    ("active_from", "active_until"),
    ("available_from", "available_until"),
    ("published_at", "expires_at"),
)


def _safe_host(request: HttpRequest) -> str:
    try:
        host = request.get_host()
    except Exception:  # malformed/untrusted host: keep preferences isolated
        host = "invalid-host"
    return host.strip().lower()[:255] or "unknown-host"


def _mode(*, obj: Any = None, raw: str | None = None) -> str:
    if raw in {"add", "change"}:
        return str(raw)
    return "change" if obj is not None else "add"


def _surface_key(
    *, host: str, admin_site_name: str, model_label: str, mode: str
) -> str:
    return "|".join(
        (
            host.strip().lower()[:255],
            admin_site_name.strip().lower()[:64],
            model_label.strip().lower()[:160],
            _mode(raw=mode),
        )
    )


def _field_exists(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


def _preference_endpoint(admin_site, request: HttpRequest | None = None) -> str:
    try:
        return reverse(
            f"{admin_site.name}:field_preferences",
            urlconf=getattr(request, "urlconf", None),
        )
    except NoReverseMatch:
        return ""


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _declared_field_names(model_admin) -> list[str]:
    """Field names a ModelAdmin/InlineModelAdmin NAMES in its own layout.

    Reads the class attributes on purpose rather than calling
    ``get_fieldsets``/``get_fields``: those fall back to
    ``get_readonly_fields``, and the only caller is inside it.
    """

    names: list[str] = []

    def _add(entry):
        # Django allows a nested tuple to put several fields on one line.
        if isinstance(entry, (list, tuple)):
            for part in entry:
                _add(part)
        elif entry:
            names.append(str(entry))

    for _label, options in getattr(model_admin, "fieldsets", None) or ():
        _add((options or {}).get("fields", ()) or ())
    _add(getattr(model_admin, "fields", None) or ())
    return names


def _declared_but_excluded(model_admin, request, obj=None) -> list[str]:
    """Names the admin both EXCLUDES from the form and NAMES in its layout.

    That combination is a hard 500, not a cosmetic slip: Django's fieldset
    renderer looks the name up with ``form[name]`` and raises KeyError for
    every user, on every add AND change view. ``get_exclude`` on the mixins
    below drops "school" from every tenant-site form, so any admin that also
    lists "school" in its fieldsets is permanently unopenable -- exactly what
    CommunicationTemplateAdmin was, reproduced 2026-08-31.

    Returning the name for ``get_readonly_fields`` renders it read-only, which
    is the cure already applied by hand at ``siteconfig/admin.py`` and
    ``schools/admin.py``. The security property is untouched: an excluded
    field still cannot be set by a crafted POST.

    Scoped to DECLARED names so it stays a no-op for the ~485 admins that
    never mention the field. An unconditional append would ADD a school row
    to every admin that declares no fieldsets at all, because
    ``ModelAdmin.get_fields()`` returns the form fields PLUS the readonly ones.
    """

    excluded = set(model_admin.get_exclude(request, obj) or ())
    if not excluded:
        return []
    return [
        name
        for name in _declared_field_names(model_admin)
        if name in excluded and _field_exists(model_admin.model, name)
    ]


def _name_split_datetime_subwidgets(db_field, formfield) -> None:
    """Give each half of a split date/time control an accessible name.

    Django renders a DateTimeField in the admin as ``AdminSplitDateTime``:
    two text inputs preceded by the BARE TEXT "Date:" and "Time:". Neither
    has a label bound to it, and the field's own <label> carries no ``for``
    either, because ``MultiWidget.id_for_label()`` returns None by design.

    Measured 2026-08-31 with CDP ``Accessibility.getPartialAXTree`` on the
    rendered admin: every one of those inputs reported ``name: ""`` -- 32
    nodes across 5 add-forms on both sites. A screen reader announced "edit
    text" with nothing to say WHICH field, so a form with a start and an end
    datetime offered four indistinguishable boxes. WCAG 2.1 SC 4.1.2.

    Naming the sub-inputs here rather than in a template is deliberate: form
    widgets render through ``FORM_RENDERER``, a STANDALONE engine that reads
    ``django/forms/templates`` plus installed-app template dirs and NOT this
    project's ``TEMPLATES['DIRS']``.  A repo-level
    ``templates/admin/widgets/split_datetime.html`` is therefore never
    consulted (verified by rendering it), and the only app that precedes
    ``django.contrib.admin`` in INSTALLED_APPS is ``unfold``.  The
    alternatives -- switching FORM_RENDERER to TemplatesSetting, or inserting
    a shim app ahead of contrib.admin -- both change rendering for every form
    in the product, and the schema-mode SHARED_APPS/TENANT_APPS split makes
    the second one a trap.  Setting the attribute reaches exactly the two
    inputs that are broken.

    The visible "Date:"/"Time:" text is left alone, so the accessible name
    still contains the visible label (WCAG SC 2.5.3) and sighted users lose
    nothing.  ``formfield_for_dbfield`` builds a fresh widget per field per
    request, so this never leaks across requests.
    """

    widget = getattr(formfield, "widget", None)
    if not isinstance(widget, AdminSplitDateTime):
        return
    subwidgets = getattr(widget, "widgets", None) or ()
    if len(subwidgets) < 2:  # pragma: no cover - upstream shape changed
        return
    label = capfirst(str(getattr(db_field, "verbose_name", "") or db_field.name))
    for subwidget, part in zip(subwidgets, (gettext("date"), gettext("time"))):
        subwidget.attrs = dict(subwidget.attrs or {})
        subwidget.attrs.setdefault("aria-label", f"{label} {part}")


def _json_empty_means_default(db_field, formfield) -> None:
    """Clearing a NOT NULL JSON box must mean "the default", never NULL.

    ``JSONField(default=dict, blank=True)`` is the platform's standard shape --
    496 fields across 42 apps carry it.  ``blank=True`` makes the form field
    optional, and ``forms.JSONField`` returns **None** for empty input, so the
    ModelForm assigns None over the model default and the INSERT sends NULL to
    a NOT NULL column.  The request dies in ``ModelAdmin._changeform_view``,
    inside the ``transaction.atomic`` Django 5.2 wraps every non-GET changeform
    in, as an uncaught ``IntegrityError`` -- a 500, not a form error.

    Reproduced 2026-09-06 on ``/admin/people/studentprofile/add/``:

    ======================================  ==========================
    ``custom_attributes`` submitted         result
    ======================================  ==========================
    omitted                                 302, row created
    ``{}`` (the rendered initial value)     302, row created
    empty (the box was cleared)             **500 IntegrityError**
    whitespace                              200, validation error
    ======================================  ==========================

    So the page is healthy until someone empties a box that renders holding
    ``{}`` and is labelled optional -- which is simply how you say "no custom
    attributes".  Only the cleared case breaks, which is why the surface passes
    every add-form smoke test.

    The coercion is applied to the bound field rather than through
    ``formfield_overrides`` deliberately: overrides live in a class attribute
    that a subclass's own ``formfield_overrides`` shadows entirely (
    ``apps/siteconfig/admin.py`` defines one), whereas this mixin is injected as
    the FIRST base by ``BaseRunMyCampusAdminSite.register``, so wrapping the
    method composes with whatever the registered class does.

    Restricted to fields that can actually take the default: ``null=True`` JSON
    fields legitimately store NULL and are left exactly as they are.
    """

    if not isinstance(db_field, models.JSONField):
        return
    if db_field.null or not db_field.has_default():
        return
    original_clean = getattr(formfield, "clean", None)
    if original_clean is None:  # pragma: no cover - upstream shape changed
        return

    def clean(value, _original=original_clean, _default=db_field.get_default):
        cleaned = _original(value)
        if cleaned is None:
            return _default()
        return cleaned

    formfield.clean = clean


@dataclass(frozen=True)
class AdminFieldContract:
    model_label: str
    mode: str
    host: str
    admin_site: str
    endpoint: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[dict[str, Any], ...]
    recommended_fields: tuple[str, ...]
    hidden_fields: tuple[str, ...]
    system_hidden_fields: tuple[str, ...]
    #: Fields hidden because THIS school's own records never use them, not because
    #: the person chose to hide them.  Carried separately so the surface can say so.
    inferred_hidden_fields: tuple[str, ...] = ()
    #: Rows the usage inference was drawn from; 0 means no inference ran.
    inference_sample_rows: int = 0
    #: field name -> why its suggested value came from a fallback.
    suggestion_notes: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_label,
            "mode": self.mode,
            "host": self.host,
            "adminSite": self.admin_site,
            "endpoint": self.endpoint,
            "required": list(self.required_fields),
            "optional": list(self.optional_fields),
            "recommended": list(self.recommended_fields),
            "recommendedLabel": gettext("Recommended"),
            "hidden": list(self.hidden_fields),
            "systemHidden": list(self.system_hidden_fields),
            "inferredHidden": list(self.inferred_hidden_fields),
            "inferenceSampleRows": self.inference_sample_rows,
            "inferenceReason": gettext(
                "Hidden because this school's existing records have never used it."
            ),
            "suggestionNotes": dict(self.suggestion_notes),
        }


class AdminFieldVisibilityService:
    """Persist validated visibility choices in the local application database."""

    @staticmethod
    def _preference_model():
        from apps.siteconfig.models_dashboard import DashboardUserPreference

        return DashboardUserPreference

    @classmethod
    def read(cls, *, user, surface_key: str) -> dict[str, Any]:
        if not getattr(user, "is_authenticated", False):
            return {}
        try:
            preference = cls._preference_model().objects.filter(user=user).only(
                "dashboard_layout"
            ).first()
        except DatabaseError:
            logger.warning("admin field preferences unavailable", exc_info=True)
            return {}
        layout = preference.dashboard_layout if preference else {}
        if not isinstance(layout, dict):
            return {}
        namespace = layout.get(PREFERENCE_NAMESPACE, {})
        if not isinstance(namespace, dict):
            return {}
        value = namespace.get(surface_key, {})
        return value if isinstance(value, dict) else {}

    @classmethod
    def write(
        cls,
        *,
        user,
        surface_key: str,
        hidden_fields: Iterable[str],
        allowed_optional_fields: Iterable[str],
        reset: bool = False,
    ) -> dict[str, Any]:
        if not getattr(user, "is_authenticated", False):
            raise ValidationError("Authentication is required.")
        allowed = set(_ordered_unique(allowed_optional_fields))
        hidden = _ordered_unique(hidden_fields)
        if len(hidden) > MAX_HIDDEN_FIELDS:
            logger.warning(
                "admin_field_visibility_rejected user=%s surface=%s reason=too_many_fields count=%s",
                getattr(user, "pk", None),
                surface_key,
                len(hidden),
            )
            raise ValidationError(
                {
                    "hidden": (
                        f"At most {MAX_HIDDEN_FIELDS} optional fields can be hidden "
                        "in one admin surface."
                    )
                }
            )
        invalid = [name for name in hidden if name not in allowed]
        if invalid:
            logger.warning(
                "admin_field_visibility_rejected user=%s surface=%s reason=unknown_or_mandatory count=%s",
                getattr(user, "pk", None),
                surface_key,
                len(invalid),
            )
            raise ValidationError(
                {"hidden": f"Unknown or mandatory fields cannot be hidden: {', '.join(invalid[:10])}"}
            )
        Preference = cls._preference_model()
        with transaction.atomic():
            preference, _ = Preference.objects.select_for_update().get_or_create(user=user)
            layout = dict(preference.dashboard_layout or {})
            namespace = dict(layout.get(PREFERENCE_NAMESPACE) or {})
            if reset:
                namespace.pop(surface_key, None)
                result: dict[str, Any] = {}
            else:
                result = {
                    "hidden": hidden,
                    "updated_at": timezone.now().isoformat(),
                }
                namespace[surface_key] = result
            if len(namespace) > MAX_SURFACES_PER_USER:
                ordered = sorted(
                    namespace.items(),
                    key=lambda item: str((item[1] or {}).get("updated_at", "")),
                    reverse=True,
                )[:MAX_SURFACES_PER_USER]
                namespace = dict(ordered)
            layout[PREFERENCE_NAMESPACE] = namespace
            preference.dashboard_layout = layout
            preference.save(update_fields=["dashboard_layout", "updated_at"])
        logger.info(
            "admin_field_visibility_saved user=%s surface=%s hidden=%s reset=%s",
            getattr(user, "pk", None),
            surface_key,
            len(hidden),
            reset,
        )
        return result


def _system_hidden_fields(model_admin) -> list[str]:
    hidden: list[str] = []
    model = model_admin.model
    if not model_admin.admin_site.is_platform_site() and _field_exists(model, "school"):
        hidden.append("school")
    configured = getattr(model_admin, "rmc_system_hidden_fields", ())
    hidden.extend(name for name in configured if _field_exists(model, name))
    return _ordered_unique(hidden)


def _rendered_form_field_names(*, model_admin, request: HttpRequest, form, obj=None) -> tuple[str, ...]:
    """Return editable fields owned by the active admin fieldsets.

    A custom ``ModelForm`` may declare a broad reusable field surface while a
    specialized ``ModelAdmin`` intentionally renders only a governed subset.
    Advertising every declared form field in the visibility/recommendation
    contract creates controls for fields that do not exist in the DOM.  Django's
    resolved fieldsets are the authoritative render allowlist for that page.
    """

    fields = getattr(form, "fields", None) or getattr(form, "base_fields", {})
    declared_names = tuple(fields)
    try:
        rendered = set(flatten_fieldsets(model_admin.get_fieldsets(request, obj)))
    except (DatabaseError, FieldError, TypeError, ValueError):
        logger.warning(
            "admin rendered-field allowlist unavailable model=%s",
            model_admin.model._meta.label_lower,
            exc_info=True,
        )
        return declared_names
    if not rendered:
        return declared_names
    return tuple(name for name in declared_names if name in rendered)


def _inferred_hidden_fields(*, model_admin, request, optional_names) -> tuple[tuple[str, ...], int]:
    """Optional fields this school's own records have never used."""
    if model_admin.admin_site.is_platform_site():
        # The operator site is not looking at one school's records, so "this
        # tenant never uses it" is not a question that has an answer here.
        return (), 0
    school = getattr(request, "school", None)
    if school is None:
        return (), 0
    try:
        from apps.siteconfig.admin_field_usage import derive_unused_optional_fields

        unused, rows = derive_unused_optional_fields(
            model_admin.model, school, optional_names
        )
    except (DatabaseError, ImportError, TypeError, ValueError):
        logger.warning("admin field-usage inference unavailable", exc_info=True)
        return (), 0
    return tuple(sorted(unused & set(optional_names))), rows


def _suggestion_notes(model_admin, request) -> dict[str, str]:
    """Why a suggested value came from a fallback, for display beside the field."""
    try:
        from apps.siteconfig.admin_smart_initials import (
            build_admin_smart_initials_detailed,
        )

        _values, notes = build_admin_smart_initials_detailed(model_admin.model, request)
    except (DatabaseError, ImportError, TypeError, ValueError):
        return {}
    return notes


def _contract_for_form(
    *,
    model_admin,
    request: HttpRequest,
    form,
    obj=None,
    endpoint: str = "",
    mode_override: str | None = None,
) -> AdminFieldContract:
    mode = _mode(raw=mode_override) if mode_override else _mode(obj=obj)
    model_label = model_admin.model._meta.label_lower
    host = _safe_host(request)
    site_name = model_admin.admin_site.name
    surface_key = _surface_key(
        host=host, admin_site_name=site_name, model_label=model_label, mode=mode
    )
    conditional = set((getattr(model_admin, "conditional_fields", {}) or {}).keys())
    required: list[str] = []
    optional: list[dict[str, Any]] = []
    system_hidden = set(_system_hidden_fields(model_admin))
    readonly = set(model_admin.get_readonly_fields(request, obj))
    recommended = set(getattr(model_admin, "rmc_recommended_fields", ()) or ())

    fields = getattr(form, "fields", None) or getattr(form, "base_fields", {})
    rendered_names = set(
        _rendered_form_field_names(
            model_admin=model_admin,
            request=request,
            form=form,
            obj=obj,
        )
    )
    for name, field in fields.items():
        if name not in rendered_names:
            continue
        if name in system_hidden or name in readonly:
            continue
        # Conditional fields remain visible to Alpine's dependency engine.  A
        # field which can become required must never be hidden by a preference.
        if bool(getattr(field, "required", False)) or name in conditional:
            required.append(name)
            continue
        model_field = None
        try:
            model_field = model_admin.model._meta.get_field(name)
        except FieldDoesNotExist:
            pass
        has_default = bool(model_field is not None and model_field.has_default())
        if has_default or getattr(field, "initial", None) not in (None, ""):
            recommended.add(name)
        optional.append(
            {
                "name": name,
                "label": str(getattr(field, "label", None) or name.replace("_", " ").title()),
                "recommended": name in recommended,
            }
        )

    optional_names = {item["name"] for item in optional}
    stored = AdminFieldVisibilityService.read(user=request.user, surface_key=surface_key)
    hidden = [
        name
        for name in _ordered_unique(stored.get("hidden", []))
        if name in optional_names
    ]
    # Usage inference is a STARTING position, not an override.  Once this person has
    # curated this surface at all, their choice is the entire answer.
    inferred: tuple[str, ...] = ()
    sample_rows = 0
    if not stored:
        inferred, sample_rows = _inferred_hidden_fields(
            model_admin=model_admin, request=request, optional_names=optional_names
        )
        hidden = _ordered_unique(list(hidden) + list(inferred))
    editable_names = set(required) | optional_names
    return AdminFieldContract(
        model_label=model_label,
        mode=mode,
        host=host,
        admin_site=site_name,
        endpoint=endpoint,
        required_fields=tuple(required),
        optional_fields=tuple(optional),
        recommended_fields=tuple(name for name in recommended if name in editable_names),
        hidden_fields=tuple(hidden),
        system_hidden_fields=tuple(system_hidden),
        inferred_hidden_fields=inferred,
        inference_sample_rows=sample_rows,
        suggestion_notes=tuple(sorted(_suggestion_notes(model_admin, request).items())),
    )


def _range_error(cleaned_data: dict[str, Any]) -> tuple[str, str] | None:
    for start_name, end_name in RANGE_FIELD_PAIRS:
        start = cleaned_data.get(start_name)
        end = cleaned_data.get(end_name)
        if start is not None and end is not None and end < start:
            return end_name, f"Cannot be earlier than {start_name.replace('_', ' ')}."
    return None


def _containment_error(cleaned_data: dict[str, Any]) -> tuple[str, str] | None:
    """Reject a child whose parent contradicts the parent chosen on the same form.

    Computed on the SERVER against the stored relation.  Deliberately not mirrored
    in JavaScript: a second copy of this rule in the browser is a second thing that
    can disagree with the database, and the browser's answer would not be the one
    that decides whether the row saves.
    """

    for child_name, parent_name in RELATION_CONTAINMENT_PAIRS:
        child = cleaned_data.get(child_name)
        parent = cleaned_data.get(parent_name)
        if child is None or parent is None:
            continue
        if not hasattr(child, "_meta") or getattr(parent, "pk", None) is None:
            continue
        try:
            link = child._meta.get_field(parent_name)
        except FieldDoesNotExist:
            continue
        if link.remote_field is None:
            continue
        actual = getattr(child, link.attname, None)
        if actual is None or actual == parent.pk:
            continue
        return (
            child_name,
            gettext(
                "This %(child)s belongs to a different %(parent)s than the one selected."
            )
            % {
                "child": child._meta.verbose_name,
                "parent": parent._meta.verbose_name,
            },
        )
    return None


def _bind_transition_evidence(model_admin, request, obj, form, *, change: bool) -> None:
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    if user is None:
        return
    now = timezone.now()
    before = None
    if change and getattr(obj, "pk", None):
        before = model_admin.model._default_manager.filter(pk=obj.pk).first()

    for name in ("created_by", "updated_by", "modified_by"):
        if not _field_exists(model_admin.model, name):
            continue
        if name == "created_by" and change:
            continue
        setattr(obj, name, user)

    transitions = (
        ("is_locked", True, "locked_at", "locked_by"),
        ("is_locked", False, "unlocked_at", "unlocked_by"),
        ("is_soft_closed", True, "soft_closed_at", "soft_closed_by"),
        ("is_soft_closed", False, "soft_reopened_at", "soft_reopened_by"),
        ("is_active", True, "activated_at", "activated_by"),
        ("is_active", False, "deactivated_at", "deactivated_by"),
        ("is_archived", True, "archived_at", "archived_by"),
        ("is_published", True, "published_at", "published_by"),
    )
    for state_name, target, at_name, by_name in transitions:
        if not _field_exists(model_admin.model, state_name):
            continue
        previous = getattr(before, state_name, None) if before is not None else None
        current = getattr(obj, state_name, None)
        if current is target and previous is not target:
            if _field_exists(model_admin.model, at_name):
                setattr(obj, at_name, now)
            if _field_exists(model_admin.model, by_name):
                setattr(obj, by_name, user)


class AdminFormAutomationMixin:
    """Shared behavior inherited by every tenant and operator ``ModelAdmin``."""

    _rmc_admin_form_automation = True

    def get_exclude(self, request, obj=None):
        """Remove tenant ownership from client-controlled form data.

        ``save_model`` binds the school from the resolved hostname/request.  An
        excluded field is stronger than a hidden widget: it cannot be altered
        by disabling JavaScript or by crafting a POST body.
        """

        excluded = list(super().get_exclude(request, obj) or ())
        if not self.admin_site.is_platform_site() and _field_exists(
            self.model, "school"
        ):
            excluded.append("school")
        return tuple(_ordered_unique(excluded))

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for name in SYSTEM_EVIDENCE_FIELDS:
            if _field_exists(self.model, name):
                readonly.append(name)
        readonly.extend(_declared_but_excluded(self, request, obj))
        return tuple(_ordered_unique(readonly))

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None:
            _name_split_datetime_subwidgets(db_field, formfield)
            _json_empty_means_default(db_field, formfield)
        return formfield

    def get_form(self, request, obj=None, change=False, **kwargs):
        base_form = super().get_form(request, obj, change=change, **kwargs)
        if getattr(base_form, "_rmc_range_validated", False):
            return base_form

        class RangeValidatedAdminForm(base_form):
            _rmc_range_validated = True

            def clean(inner_self):
                cleaned = super().clean()
                # Restore preference-hidden values before Django's ModelForm
                # _post_clean() executes model and uniqueness validation.  The
                # exact state that will be saved is therefore the state that is
                # validated, including cross-field model rules.
                self._rmc_restore_hidden_values(
                    request,
                    inner_self.instance,
                    inner_self,
                    change=change,
                    apply_instance=False,
                )
                for check in (_range_error, _containment_error):
                    error = check(cleaned)
                    if error:
                        field_name, message = error
                        inner_self.add_error(field_name, message)
                return cleaned

        RangeValidatedAdminForm.__name__ = f"RmcValidated{base_form.__name__}"
        return RangeValidatedAdminForm

    def get_changeform_initial_data(self, request):
        initial: dict[str, Any] = {}
        try:
            from apps.siteconfig.admin_smart_initials import build_admin_smart_initials

            initial.update(build_admin_smart_initials(self.model, request))
        except (DatabaseError, ImportError, TypeError, ValueError):
            logger.warning("admin smart initials unavailable", exc_info=True)
        # Django's query-string initial values are explicit user input and win.
        initial.update(super().get_changeform_initial_data(request))
        if initial:
            logger.info(
                "admin_smart_initials model=%s fields=%s",
                self.model._meta.label_lower,
                ",".join(sorted(initial)),
            )
        return initial

    def render_change_form(
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        adminform = context.get("adminform")
        form = getattr(adminform, "form", None)
        endpoint = _preference_endpoint(self.admin_site, request)
        if form is not None:
            contract = _contract_for_form(
                model_admin=self,
                request=request,
                form=form,
                obj=obj,
                endpoint=endpoint,
            )
            context["admin_field_contract"] = contract.as_dict()
            # A value derived from a fallback rather than an unambiguous active
            # record has to say so where the person can read it.  `form.fields` is
            # deep-copied per instance, so this annotation is request-local.
            if add:
                for name, note in contract.suggestion_notes:
                    field = form.fields.get(name)
                    if field is None or note in (field.help_text or ""):
                        continue
                    field.help_text = (
                        f"{field.help_text} {note}".strip() if field.help_text else note
                    )
        return super().render_change_form(
            request,
            context,
            add=add,
            change=change,
            form_url=form_url,
            obj=obj,
        )

    def _rmc_contract_for_bound_form(self, request, form, obj=None) -> AdminFieldContract:
        return _contract_for_form(
            model_admin=self, request=request, form=form, obj=obj, endpoint=""
        )

    def _rmc_restore_hidden_values(
        self,
        request,
        obj,
        form,
        *,
        change: bool,
        apply_instance: bool = True,
    ) -> None:
        contract = self._rmc_contract_for_bound_form(
            request, form, obj=obj if change else None
        )
        hidden = set(contract.hidden_fields)
        if not hidden:
            return
        before = None
        if change and getattr(obj, "pk", None):
            before = self.model._default_manager.filter(pk=obj.pk).first()
        for name in hidden:
            if name not in getattr(form, "cleaned_data", {}):
                continue
            try:
                model_field = self.model._meta.get_field(name)
            except FieldDoesNotExist:
                continue
            if getattr(model_field, "many_to_many", False):
                if before is not None:
                    form.cleaned_data[name] = getattr(before, name).all()
                else:
                    form.cleaned_data[name] = []
                continue
            if before is not None:
                value = getattr(before, name)
            elif model_field.has_default():
                value = model_field.get_default()
            else:
                value = form.initial.get(name)
            form.cleaned_data[name] = value
            if apply_instance:
                setattr(obj, name, value)

    def save_model(self, request, obj, form, change):
        # Tenant ownership is derived from the hostname/request, never a posted FK.
        if not self.admin_site.is_platform_site() and _field_exists(self.model, "school"):
            school = getattr(request, "school", None)
            if school is None:
                raise ValidationError("A tenant school is required for this admin form.")
            obj.school = school
        self._rmc_restore_hidden_values(request, obj, form, change=change)
        _bind_transition_evidence(self, request, obj, form, change=change)
        return super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """Bind tenant ownership onto inline rows, which `save_model` never sees.

        `school` is excluded from the inline form for the same reason it is
        excluded from the parent's: an excluded field cannot be altered by a
        crafted POST.  Excluding it means nothing sets it, so it is set here from
        the resolved request.
        """
        instances = formset.save(commit=False)
        school = getattr(request, "school", None)
        tenant_scoped = (
            not self.admin_site.is_platform_site()
            and instances
            and _field_exists(instances[0].__class__, "school")
        )
        if tenant_scoped and school is None:
            raise ValidationError("A tenant school is required for this admin form.")
        for instance in instances:
            if tenant_scoped:
                instance.school = school
            instance.save()
        formset.save_m2m()
        for obsolete in formset.deleted_objects:
            obsolete.delete()


class AdminInlineAutomationMixin:
    """The same policy, applied to inline formsets.

    Inlines are where bulk entry actually happens — a timetable's rows, a fee
    plan's lines — and they were reached by none of this: 30 inline classes were
    attached across both sites and none carried any of the policy above, so system
    evidence fields were editable there and tenant ownership was posted from the
    client.  ``InlineModelAdmin`` has a different API from ``ModelAdmin`` (a
    formset, no changeform, no initial-data hook), so it needs its own mixin rather
    than the same one, but the rules it enforces are identical.
    """

    _rmc_admin_inline_automation = True

    def get_exclude(self, request, obj=None):
        excluded = list(super().get_exclude(request, obj) or ())
        if not self.admin_site.is_platform_site() and _field_exists(self.model, "school"):
            excluded.append("school")
        return tuple(_ordered_unique(excluded))

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for name in SYSTEM_EVIDENCE_FIELDS:
            if _field_exists(self.model, name):
                readonly.append(name)
        readonly.extend(_declared_but_excluded(self, request, obj))
        return tuple(_ordered_unique(readonly))

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None:
            _name_split_datetime_subwidgets(db_field, formfield)
            _json_empty_means_default(db_field, formfield)
        return formfield

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        base_form = getattr(formset, "form", None)
        if base_form is None or getattr(base_form, "_rmc_range_validated", False):
            return formset

        class RangeValidatedInlineForm(base_form):
            _rmc_range_validated = True

            def clean(inner_self):
                cleaned = super().clean()
                for check in (_range_error, _containment_error):
                    error = check(cleaned or {})
                    if error:
                        field_name, message = error
                        inner_self.add_error(field_name, message)
                return cleaned

        RangeValidatedInlineForm.__name__ = f"RmcValidated{base_form.__name__}"
        formset.form = RangeValidatedInlineForm
        return formset


def build_admin_field_contract(
    model_admin, request, *, obj=None, mode: str | None = None
) -> AdminFieldContract:
    requested_mode = _mode(raw=mode) if mode else _mode(obj=obj)
    form_class = model_admin.get_form(
        request, obj=obj, change=requested_mode == "change"
    )
    form = form_class(instance=obj)
    endpoint = _preference_endpoint(model_admin.admin_site, request)
    return _contract_for_form(
        model_admin=model_admin,
        request=request,
        form=form,
        obj=obj,
        endpoint=endpoint,
        mode_override=requested_mode,
    )


@require_http_methods(["GET", "POST"])
def admin_field_preferences_view(request: HttpRequest, *, admin_site) -> JsonResponse:
    """Read/write one validated form-visibility scope for the active admin site."""

    try:
        if request.method == "POST":
            raw_body = request.body
            if len(raw_body) > MAX_PREFERENCE_PAYLOAD_BYTES:
                logger.warning(
                    "admin_field_visibility_rejected user=%s reason=payload_too_large bytes=%s",
                    getattr(request.user, "pk", None),
                    len(raw_body),
                )
                return JsonResponse(
                    {
                        "ok": False,
                        "error": (
                            "The field-preference payload exceeds the "
                            f"{MAX_PREFERENCE_PAYLOAD_BYTES}-byte limit."
                        ),
                    },
                    status=413,
                )
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        else:
            payload = request.GET
    except RequestDataTooBig:
        return JsonResponse(
            {"ok": False, "error": "The field-preference payload is too large."},
            status=413,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)
    if not hasattr(payload, "get"):
        return JsonResponse(
            {"ok": False, "error": "The request payload must be an object."},
            status=400,
        )
    model_label = str(payload.get("model") or "").strip().lower()
    raw_mode = str(payload.get("mode") or "").strip().lower()
    if raw_mode not in {"add", "change"}:
        return JsonResponse(
            {"ok": False, "error": "Mode must be 'add' or 'change'."},
            status=400,
        )
    mode = raw_mode
    registered = {
        model._meta.label_lower: model_admin
        for model, model_admin in admin_site._registry.items()
    }
    model_admin = registered.get(model_label)
    if model_admin is None:
        return JsonResponse({"ok": False, "error": "Unknown admin model."}, status=404)
    permitted = (
        model_admin.has_add_permission(request)
        if mode == "add"
        else model_admin.has_change_permission(request)
    )
    if not permitted:
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)

    contract = build_admin_field_contract(
        model_admin, request, obj=None, mode=mode
    )
    # Endpoint requests carry mode explicitly; reconstruct the storage key for it.
    surface_key = _surface_key(
        host=_safe_host(request),
        admin_site_name=admin_site.name,
        model_label=model_label,
        mode=mode,
    )
    optional_names = [item["name"] for item in contract.optional_fields]
    if request.method == "POST":
        hidden_fields = payload.get("hidden", [])
        if not isinstance(hidden_fields, list) or not all(
            isinstance(name, str) for name in hidden_fields
        ):
            return JsonResponse(
                {"ok": False, "error": "Hidden fields must be a list of names."},
                status=400,
            )
        if len(hidden_fields) > MAX_HIDDEN_FIELDS:
            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        f"At most {MAX_HIDDEN_FIELDS} optional fields can be hidden "
                        "in one admin surface."
                    ),
                },
                status=400,
            )
        reset = payload.get("reset", False)
        if not isinstance(reset, bool):
            return JsonResponse(
                {"ok": False, "error": "Reset must be a JSON boolean."},
                status=400,
            )
        try:
            AdminFieldVisibilityService.write(
                user=request.user,
                surface_key=surface_key,
                hidden_fields=hidden_fields,
                allowed_optional_fields=optional_names,
                reset=reset,
            )
        except (DatabaseError, TypeError, ValidationError) as exc:
            message = getattr(exc, "message_dict", None) or getattr(
                exc, "messages", None
            ) or [str(exc)]
            return JsonResponse({"ok": False, "error": message}, status=400)

    stored = AdminFieldVisibilityService.read(user=request.user, surface_key=surface_key)
    hidden = [name for name in stored.get("hidden", []) if name in optional_names]
    response = contract.as_dict()
    response.update({"ok": True, "mode": mode, "hidden": hidden})
    return JsonResponse(response)
