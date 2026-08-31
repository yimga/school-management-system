"""Two whole-surface invariants for every registered admin, both sites.

Both were found by rendering all 486 add_views on 2026-08-31; each was one
unconditional 500 on a screen the navigation links to.

1. DECLARED-BUT-EXCLUDED.  ``AdminFormAutomationMixin.get_exclude`` strips
   "school" from every tenant-site form so a tenant cannot post another
   school's id.  An admin whose ``fieldsets`` still NAMES "school" therefore
   asks Django's fieldset renderer to resolve a field the form does not have,
   and ``form[name]`` raises::

       KeyError: "Key 'school' not found in
                  'RmcValidatedCommunicationTemplateForm'"

   for every user, on add AND change.  ``CommunicationTemplateAdmin`` did this.
   The cure is to render the name read-only, which the mixin now does for any
   declared-but-excluded field.

2. TEMPLATE MUST LOAD.  ``ClientAdmin`` mixed in django_tenants'
   ``TenantAdminMixin``, whose entire body is
   ``change_form_template = "admin/django_tenants/tenant/change_form.html"``.
   That template ships only inside the django_tenants PACKAGE, and settings.py
   adds "django_tenants" to INSTALLED_APPS only inside
   ``if USE_DJANGO_TENANTS and postgresql``.  On a sovereign edge box, any RLS
   deployment, and every developer machine the loader had no directory to find
   it in -> ``TemplateDoesNotExist`` on Platform Backoffice -> Clients.

Both tests are DB-free: ``get_exclude`` and ``get_readonly_fields`` consult only
the model meta and the site, and template loading is a filesystem question.
"""

from __future__ import annotations

from django.contrib.admin.options import BaseModelAdmin
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase

from config.admin import platform_admin_site, tenant_admin_site

SITES = (("tenant", tenant_admin_site), ("platform", platform_admin_site))

TEMPLATE_ATTRS = (
    "add_form_template",
    "change_form_template",
    "change_list_template",
    "delete_confirmation_template",
    "object_history_template",
)


def _declared(model_admin) -> list[str]:
    """Every field name the admin names in its OWN fieldsets/fields."""

    names: list[str] = []

    def add(entry):
        if isinstance(entry, (list, tuple)):
            for part in entry:
                add(part)
        elif entry:
            names.append(str(entry))

    for _label, options in getattr(model_admin, "fieldsets", None) or ():
        add((options or {}).get("fields", ()) or ())
    add(getattr(model_admin, "fields", None) or ())
    return names


def _request(site):
    request = RequestFactory().get("/admin/")
    request.user = None
    request.urlconf = (
        "config.manager_urls" if site.is_platform_site() else "config.tenant_urls"
    )
    return request


def _inlines(model_admin):
    for inline in getattr(model_admin, "inlines", None) or ():
        try:
            yield inline(model_admin.model, model_admin.admin_site)
        except Exception:  # pragma: no cover - a broken inline is a separate bug
            continue


class DeclaredButExcludedFieldsTests(SimpleTestCase):
    """A named-but-excluded field is a guaranteed KeyError, not a style nit."""

    def _offenders(self, include_inlines: bool):
        offenders = []
        for site_name, site in SITES:
            request = _request(site)
            for model, model_admin in site._registry.items():
                targets = [(model_admin, "")]
                if include_inlines:
                    targets += [
                        (i, f" inline {type(i).__name__}")
                        for i in _inlines(model_admin)
                    ]
                for target, suffix in targets:
                    try:
                        excluded = set(target.get_exclude(request, None) or ())
                        readonly = set(target.get_readonly_fields(request, None) or ())
                    except Exception as exc:  # pragma: no cover
                        offenders.append(
                            f"{site_name}:{model._meta.label}{suffix} "
                            f"raised {type(exc).__name__}: {exc}"
                        )
                        continue
                    for name in _declared(target):
                        if name in excluded and name not in readonly:
                            offenders.append(
                                f"{site_name}:{model._meta.label}{suffix} "
                                f"declares {name!r} in its layout but excludes it "
                                "from the form and does not mark it read-only"
                            )
        return sorted(set(offenders))

    def test_no_model_admin_declares_a_field_it_excludes(self) -> None:
        self.assertEqual(self._offenders(include_inlines=False), [])

    def test_no_inline_declares_a_field_it_excludes(self) -> None:
        self.assertEqual(self._offenders(include_inlines=True), [])

    def test_the_reader_actually_discriminates(self) -> None:
        """Both assertions pass by finding nothing -- so does a broken reader."""

        class Layout:
            fieldsets = ((None, {"fields": ("school", ("key", "locale"))}),)
            fields = ("notes",)

        self.assertEqual(_declared(Layout), ["school", "key", "locale", "notes"])

        # And the pairing that defines the defect is actually detected.
        excluded, readonly = {"school"}, {"created_at"}
        hits = [n for n in _declared(Layout) if n in excluded and n not in readonly]
        self.assertEqual(hits, ["school"])


class AdminTemplateOverridesLoadTests(SimpleTestCase):
    """An override pointing into an uninstalled package is a 500, not a fallback."""

    def test_every_declared_admin_template_can_be_loaded(self) -> None:
        offenders = []
        seen = set()
        for site_name, site in SITES:
            for model, model_admin in site._registry.items():
                targets = [(model_admin, "")]
                targets += [
                    (i, f" inline {type(i).__name__}") for i in _inlines(model_admin)
                ]
                for target, suffix in targets:
                    for attr in TEMPLATE_ATTRS:
                        name = getattr(target, attr, None)
                        if not name or not isinstance(name, str):
                            continue
                        key = (name, attr)
                        if key in seen:
                            continue
                        seen.add(key)
                        try:
                            get_template(name)
                        except TemplateDoesNotExist:
                            offenders.append(
                                f"{site_name}:{model._meta.label}{suffix} "
                                f".{attr} = {name!r} does not resolve"
                            )
        self.assertEqual(sorted(set(offenders)), [])

    def test_client_admin_does_not_borrow_an_uninstallable_template(self) -> None:
        from django.apps import apps as django_apps

        from apps.customers.admin import ClientAdmin

        mixed_in = any(
            base.__name__ == "TenantAdminMixin" for base in ClientAdmin.__mro__
        )
        self.assertEqual(
            mixed_in,
            django_apps.is_installed("django_tenants"),
            "ClientAdmin must carry django_tenants' TenantAdminMixin exactly when "
            "the django_tenants app is installed -- that mixin's whole body is a "
            "change_form_template that ships inside the package. Gating on "
            "settings.USE_DJANGO_TENANTS is NOT equivalent: TENANCY_MODE=SCHEMA "
            "forces that flag True while INSTALLED_APPS still requires "
            "PostgreSQL, so the flag can be True with the package absent.",
        )

    def test_the_loader_check_actually_discriminates(self) -> None:
        with self.assertRaises(TemplateDoesNotExist):
            get_template("admin/rmc_no_such_template_2026_08_31.html")
        # A template that DOES exist must not raise, or the test above is vacuous.
        get_template("admin/base.html")


class MixinCuresItWithoutPerAdminEdits(SimpleTestCase):
    """The mixin closes the class, not just the one admin that hit it."""

    def test_mixin_marks_a_declared_but_excluded_field_readonly(self) -> None:
        from apps.communication.models import CommunicationTemplate
        from apps.siteconfig.admin_form_intelligence import AdminFormAutomationMixin

        class Bare(AdminFormAutomationMixin, BaseModelAdmin):
            # Deliberately does NOT list "school" in readonly_fields, so this
            # proves the MIXIN does the work rather than the hand edit in
            # apps/communication/admin.py.
            fieldsets = ((None, {"fields": ("school", "key")}),)

        bare = Bare()
        bare.model = CommunicationTemplate
        bare.admin_site = tenant_admin_site
        bare.opts = CommunicationTemplate._meta
        request = _request(tenant_admin_site)
        self.assertIn("school", bare.get_exclude(request, None))
        self.assertIn("school", bare.get_readonly_fields(request, None))


class SplitDateTimeHasAnAccessibleNameTests(SimpleTestCase):
    """Both halves of every admin date/time control must be announceable.

    Django renders a DateTimeField as ``AdminSplitDateTime``: two text inputs
    preceded by the bare text "Date:" and "Time:". Neither is a <label>, and the
    field's own <label> has no for= because ``MultiWidget.id_for_label()``
    returns None. Measured 2026-08-31 with CDP Accessibility.getPartialAXTree on
    the rendered admin: 6 of these inputs reported name:"" outright and 4 more
    announced a bare "Date"/"Time" that does not say WHICH field -- a form with
    a start and an end datetime offered four indistinguishable boxes.

    A form-level scan put the real exposure at 40 admin forms / 61 widgets /
    122 inputs across both sites.
    """

    def _split_datetime_widgets(self, site, urlconf):
        """(label, widget) for every AdminSplitDateTime reachable on a site."""
        from django.contrib.admin.widgets import AdminSplitDateTime

        request = RequestFactory().get("/admin/")
        request.user = None
        request.urlconf = urlconf
        for model, model_admin in site._registry.items():
            try:
                form = model_admin.get_form(request)
            except Exception:
                # Some admins need a fully populated request to build a form;
                # that is a different concern and is covered elsewhere.
                continue
            for name, field in form.base_fields.items():
                widget = getattr(field, "widget", None)
                if isinstance(widget, AdminSplitDateTime):
                    yield f"{model._meta.label}.{name}", widget

    def test_every_split_datetime_half_carries_an_aria_label(self) -> None:
        offenders = []
        checked = 0
        for site, urlconf in (
            (tenant_admin_site, "config.tenant_urls"),
            (platform_admin_site, "config.manager_urls"),
        ):
            for label, widget in self._split_datetime_widgets(site, urlconf):
                for index, half in enumerate(("date", "time")):
                    checked += 1
                    aria = (widget.widgets[index].attrs or {}).get("aria-label", "")
                    if not aria.strip():
                        offenders.append(f"{label} [{half}] has no aria-label")
                    elif half not in aria.lower():
                        offenders.append(
                            f"{label} [{half}] aria-label={aria!r} does not say "
                            "which half it is"
                        )
        self.assertEqual(sorted(offenders), [])
        # Guard against the scan silently finding nothing and "passing".
        self.assertGreater(
            checked, 0, "no AdminSplitDateTime reached -- the scan is vacuous"
        )

    def test_the_name_carries_the_field_not_just_the_half(self) -> None:
        """'Date' alone is useless on a form with two datetimes."""
        from django.contrib.admin.widgets import AdminSplitDateTime
        from django.db import models

        from apps.siteconfig.admin_form_intelligence import (
            _name_split_datetime_subwidgets,
        )

        db_field = models.DateTimeField(verbose_name="starts at")
        db_field.name = "starts_at"

        class FormField:
            widget = AdminSplitDateTime()

        formfield = FormField()
        _name_split_datetime_subwidgets(db_field, formfield)
        self.assertEqual(
            formfield.widget.widgets[0].attrs.get("aria-label"), "Starts at date"
        )
        self.assertEqual(
            formfield.widget.widgets[1].attrs.get("aria-label"), "Starts at time"
        )

    def test_it_leaves_other_widgets_alone(self) -> None:
        """A plain DateField already has a bound label; do not touch it."""
        from django.contrib.admin.widgets import AdminDateWidget
        from django.db import models

        from apps.siteconfig.admin_form_intelligence import (
            _name_split_datetime_subwidgets,
        )

        db_field = models.DateField(verbose_name="effective date")
        db_field.name = "effective_date"

        class FormField:
            widget = AdminDateWidget()

        formfield = FormField()
        _name_split_datetime_subwidgets(db_field, formfield)
        self.assertNotIn("aria-label", formfield.widget.attrs)

    def test_an_explicit_aria_label_wins(self) -> None:
        """An admin that already named the control keeps its own wording."""
        from django.contrib.admin.widgets import AdminSplitDateTime
        from django.db import models

        from apps.siteconfig.admin_form_intelligence import (
            _name_split_datetime_subwidgets,
        )

        db_field = models.DateTimeField(verbose_name="starts at")
        db_field.name = "starts_at"

        class FormField:
            widget = AdminSplitDateTime()

        formfield = FormField()
        formfield.widget.widgets[0].attrs["aria-label"] = "Promotion opens (date)"
        _name_split_datetime_subwidgets(db_field, formfield)
        self.assertEqual(
            formfield.widget.widgets[0].attrs["aria-label"], "Promotion opens (date)"
        )
        self.assertEqual(
            formfield.widget.widgets[1].attrs["aria-label"], "Starts at time"
        )
