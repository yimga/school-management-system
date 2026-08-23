"""A SHARED model with no ``school`` field must still be tenant-scoped on /admin/.

``TenantAdminSite.register`` auto-applies ``_TenantScopedQuerysetMixin`` to every
registered model that has a CONCRETE ``school`` field -- that column is what it
filters on. A SHARED_APPS model WITHOUT one therefore received no changelist
scoping at all, and its table lives in ``public``, which a tenant-schema
request's ``search_path`` includes. 53 registrations were in that state.

These tests exercise the resolved admin classes from the live registry, not the
source, because ``register`` synthesises the final class at registration time.
"""

import uuid

from django.apps import apps as django_apps
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.compliance.models_audit import AccessLog, AuditLog, UserActivitySession
from apps.schools.models import School, SchoolMembership
from config.admin import (
    TENANT_ADMIN_ACTOR_SCOPE,
    TENANT_ADMIN_GLOBAL_CATALOGS,
    TENANT_ADMIN_OPERATOR_ONLY,
    TENANT_ADMIN_RELATION_SCOPE,
    TENANT_ADMIN_SELF_SCOPED,
    TenantAdminSite,
    _tenancy_app_lists,
    platform_admin_site,
    tenant_admin_site,
)


def _school(tag):
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}", slug=slug, subdomain=slug, is_active=True
    )


class SharedModelActorScopeTests(TestCase):
    """The audit trail a school sees must be its own people's, and only theirs."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("aud-a")
        self.school_b = _school("aud-b")

        self.user_a = User.objects.create_user(
            username=f"ua_{uuid.uuid4().hex[:8]}", password="x", role=User.Role.ADMIN
        )
        self.user_b = User.objects.create_user(
            username=f"ub_{uuid.uuid4().hex[:8]}", password="x", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.user_a, school=self.school_a, role="ADMIN", is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.user_b, school=self.school_b, role="ADMIN", is_primary=True
        )

        self.log_a = AuditLog.objects.create(
            user=self.user_a, action=AuditLog.Action.VIEW,
            model_name="Invoice", object_id="1", app_label="finance",
        )
        self.log_b = AuditLog.objects.create(
            user=self.user_b, action=AuditLog.Action.EXPORT,
            model_name="StudentProfile", object_id="2", app_label="people",
        )
        # A system-initiated row: no actor, therefore no tenant.
        self.log_system = AuditLog.objects.create(
            user=None, action=AuditLog.Action.LOGIN,
            model_name="User", object_id="3", app_label="accounts",
        )

    def _changelist(self, model, school, as_user=None):
        # as_user defaults to that school's OWN admin. It matters: the mixin
        # always includes the REQUESTING user's own rows, so asking school B's
        # changelist while authenticated as school A's admin legitimately returns
        # A's own row -- see test_your_own_rows_are_always_visible.
        request = self.rf.get("/admin/")
        request.user = as_user or (
            self.user_a if school is self.school_a else self.user_b
        )
        request.school = school
        admin_obj = tenant_admin_site._registry[model]
        return admin_obj.get_queryset(request)

    def test_school_a_sees_only_its_own_actor_rows(self):
        pks = set(self._changelist(AuditLog, self.school_a).values_list("pk", flat=True))
        self.assertIn(self.log_a.pk, pks)
        self.assertNotIn(
            self.log_b.pk,
            pks,
            "another tenant's audit row must never appear on this school's admin",
        )

    def test_school_b_sees_only_its_own_actor_rows(self):
        pks = set(self._changelist(AuditLog, self.school_b).values_list("pk", flat=True))
        self.assertIn(self.log_b.pk, pks)
        self.assertNotIn(self.log_a.pk, pks)

    def test_an_unattributable_system_row_is_shown_to_nobody(self):
        for school in (self.school_a, self.school_b):
            pks = set(
                self._changelist(AuditLog, school).values_list("pk", flat=True)
            )
            self.assertNotIn(
                self.log_system.pk,
                pks,
                "a NULL-actor row carries no tenant; showing it to one school "
                "would show it to all of them",
            )

    def test_your_own_rows_are_always_visible(self):
        """Your own row is unambiguously yours, membership or not.

        A per-person model -- a passkey, a dashboard preference, your own audit
        trail -- must stay reachable to the person it is about, and showing it to
        them leaks nothing to anyone else. Without this, a platform superuser
        opening a tenant /admin/ could not reach their own preference row, which
        is how two existing admin-smoke tests found it.
        """
        outsider = User.objects.create_user(
            username=f"out_{uuid.uuid4().hex[:8]}", password="x"
        )
        own = AuditLog.objects.create(
            user=outsider, action=AuditLog.Action.LOGIN,
            model_name="User", object_id="9", app_label="accounts",
        )
        pks = set(
            self._changelist(AuditLog, self.school_a, as_user=outsider).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(own.pk, pks, "a person must be able to see their own row")
        self.assertNotIn(
            self.log_b.pk,
            pks,
            "and that must not widen the scope to anyone else's rows",
        )

    def test_no_school_on_the_request_yields_nothing(self):
        request = self.rf.get("/admin/")
        request.user = self.user_a
        request.school = None
        qs = tenant_admin_site._registry[AuditLog].get_queryset(request)
        self.assertEqual(
            qs.count(), 0, "fail closed: an indeterminate school must not see rows"
        )

    def test_the_platform_admin_is_deliberately_unscoped(self):
        request = self.rf.get("/admin/")
        request.user = self.user_a
        request.school = self.school_a
        qs = platform_admin_site._registry[AuditLog].get_queryset(request)
        pks = set(qs.values_list("pk", flat=True))
        self.assertTrue(
            {self.log_a.pk, self.log_b.pk, self.log_system.pk} <= pks,
            "the operator's cross-tenant view is the legitimate one and must "
            "keep working",
        )

    def test_the_sibling_audit_models_are_scoped_too(self):
        access_a = AccessLog.objects.create(user=self.user_a, resource="x")
        access_b = AccessLog.objects.create(user=self.user_b, resource="y")
        pks = set(
            self._changelist(AccessLog, self.school_a).values_list("pk", flat=True)
        )
        self.assertIn(access_a.pk, pks)
        self.assertNotIn(access_b.pk, pks)

        # ip_address is NOT NULL and session_key is UNIQUE on this model.
        sess_a = UserActivitySession.objects.create(
            user=self.user_a, ip_address="10.0.0.1", session_key=uuid.uuid4().hex
        )
        sess_b = UserActivitySession.objects.create(
            user=self.user_b, ip_address="10.0.0.2", session_key=uuid.uuid4().hex
        )
        pks = set(
            self._changelist(UserActivitySession, self.school_a).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(sess_a.pk, pks)
        self.assertNotIn(sess_b.pk, pks)


class OperatorOnlyModelsAreAbsentFromTenantAdminTests(TestCase):
    def test_platform_security_config_is_not_on_the_tenant_admin(self):
        registered = {
            f"{m._meta.app_label}.{m.__name__}" for m in tenant_admin_site._registry
        }
        for label in TENANT_ADMIN_OPERATOR_ONLY:
            with self.subTest(label=label):
                self.assertNotIn(
                    label,
                    registered,
                    f"{label} is the platform's own security perimeter or config "
                    "history, not a school's data",
                )

    def test_they_are_still_on_the_platform_admin(self):
        # Four of the operator-only models -- ThreatDetectionConfig, IPAccessRule,
        # CountryAccessRule and ConfigMutationAuditLog -- had NO platform-admin
        # registration, so a bare skip on the tenant site would have deleted the
        # operator's only surface for its own security perimeter. They are
        # re-homed, not dropped.
        registered = {
            f"{m._meta.app_label}.{m.__name__}" for m in platform_admin_site._registry
        }
        for label in sorted(TENANT_ADMIN_OPERATOR_ONLY):
            with self.subTest(label=label):
                self.assertIn(
                    label,
                    registered,
                    "removing it from the tenant admin must not remove the "
                    "operator's own access to it",
                )

    def test_site_settings_stays_on_the_tenant_admin(self):
        """Deliberately NOT operator-only, and this records why.

        siteconfig.SiteSettings is a singleton with no school column, so the
        first cut of this work classified it OPERATOR_ONLY and moved it. That was
        wrong: two existing tests assert the opposite contract on purpose --
        accounts.test_site_settings_tenant_admin_only_platform_uses_super and
        platform_runtime.test_site_settings_on_tenant_admin_only -- because the
        operator has its own surface at super:site_settings_*.

        The residual concern is real and is reported rather than silently
        accepted: its maintenance_mode is the PLATFORM-DEFAULT layer of a cascade
        (domain_ownership.py calls it "safe_platform_default"), so a tenant admin
        editing this row moves the default every non-overriding school inherits.
        Who may edit a shared default is a product decision, not a scoping bug.
        """
        registered = {
            f"{m._meta.app_label}.{m.__name__}" for m in tenant_admin_site._registry
        }
        self.assertIn("siteconfig.SiteSettings", registered)
        self.assertNotIn("siteconfig.SiteSettings", TENANT_ADMIN_OPERATOR_ONLY)


class EveryTenantRegistrationIsClassifiedTests(TestCase):
    """The seal: no SHARED model reaches the tenant admin unclassified."""

    def test_no_registration_falls_through_to_fail_closed(self):
        stragglers = [
            m._meta.label
            for m, a in tenant_admin_site._registry.items()
            if any(
                b.__name__ == "_TenantUnclassifiedFailClosedMixin"
                for b in type(a).__mro__
            )
        ]
        self.assertEqual(
            stragglers,
            [],
            "these render EMPTY on every school's admin until classified in one "
            "of the five TENANT_ADMIN_* maps in config/admin.py",
        )

    def test_the_classification_maps_do_not_overlap(self):
        maps = {
            "GLOBAL_CATALOGS": set(TENANT_ADMIN_GLOBAL_CATALOGS),
            "RELATION_SCOPE": set(TENANT_ADMIN_RELATION_SCOPE),
            "ACTOR_SCOPE": set(TENANT_ADMIN_ACTOR_SCOPE),
            "SELF_SCOPED": set(TENANT_ADMIN_SELF_SCOPED),
            "OPERATOR_ONLY": set(TENANT_ADMIN_OPERATOR_ONLY),
        }
        names = list(maps)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                with self.subTest(pair=(a, b)):
                    self.assertEqual(
                        maps[a] & maps[b],
                        set(),
                        f"a model classified both {a} and {b} has two answers; "
                        "the first branch wins silently",
                    )

    def test_every_classified_label_names_a_real_model(self):
        # A stale entry outlives the model it excused and quietly re-opens the
        # hole for a future model that happens to reuse the name.
        for group in (
            TENANT_ADMIN_GLOBAL_CATALOGS,
            TENANT_ADMIN_RELATION_SCOPE,
            TENANT_ADMIN_ACTOR_SCOPE,
            TENANT_ADMIN_SELF_SCOPED,
            TENANT_ADMIN_OPERATOR_ONLY,
        ):
            for label in group:
                with self.subTest(label=label):
                    app_label, model_name = label.split(".")
                    django_apps.get_model(app_label, model_name)  # raises if gone

    def test_every_declared_scope_path_resolves(self):
        for label, path in list(TENANT_ADMIN_RELATION_SCOPE.items()) + list(
            TENANT_ADMIN_ACTOR_SCOPE.items()
        ):
            with self.subTest(label=label, path=path):
                app_label, model_name = label.split(".")
                model = django_apps.get_model(app_label, model_name)
                cursor = model
                for segment in path.split("__"):
                    field = cursor._meta.get_field(segment)  # raises if wrong
                    cursor = field.related_model or cursor

    def test_the_tenancy_lists_were_actually_parsed(self):
        # If this ever returns empty, _model_is_schema_isolated says "not
        # isolated" for everything and the fail-closed arm blanks ~89 legitimate
        # tenant changelists. It happened once; this is the tripwire.
        shared, tenant = _tenancy_app_lists()
        self.assertGreater(len(shared), 20, "SHARED_APPS did not parse")
        self.assertGreater(len(tenant), 5, "TENANT_APPS did not parse")

    def test_tenant_app_models_are_not_wrapped(self):
        # apps.finance is TENANT_APPS: schema-isolated under django-tenants and
        # RLS-confined otherwise. Wrapping it would be wasted work at best.
        from apps.finance.models import Invoice

        admin_obj = tenant_admin_site._registry.get(Invoice)
        if admin_obj is None:
            self.skipTest("Invoice is not registered on the tenant admin")
        self.assertFalse(
            any(
                b.__name__ == "_TenantUnclassifiedFailClosedMixin"
                for b in type(admin_obj).__mro__
            )
        )

    def test_school_bearing_models_still_use_the_original_mixin(self):
        # Regression seal: the new branches must not have displaced the
        # school-field path that already covered 141 registrations.
        covered = [
            m._meta.label
            for m, a in tenant_admin_site._registry.items()
            if TenantAdminSite._model_has_concrete_school_field(m)
            and any(
                b.__name__ == "_TenantScopedQuerysetMixin" for b in type(a).__mro__
            )
        ]
        self.assertGreater(len(covered), 100, covered[:5])
