"""Regression seal: provisioning must create exactly one "General" department.

Bug (2026-06-17 gap analysis, dup-general-department-provisioning): the academic-
structure provisioner created a "General" dept coded ``GEN-<id8>`` while the
Phase-B classroom seeder independently created one coded ``<slug>-GEN`` — both run
during provisioning, so every freshly provisioned tenant ended up with two
identically-named departments. ``ensure_general_department`` is now the single
creator both paths call.

Hermetic: patches the model — no DB.
"""
from unittest import mock

from django.test import SimpleTestCase

from apps.academics import structure_provisioning


def _filter_router(*, canonical=None, legacy=None):
    """Build a fake ``Department.objects.filter`` that answers per-branch.

    code-keyed filter -> ``.first()`` returns ``canonical``.
    name-keyed filter -> ``.order_by(...).first()`` returns ``legacy``.
    """

    def _filter(**kwargs):
        m = mock.Mock()
        if "code" in kwargs:
            m.first.return_value = canonical
        else:  # name="General"
            m.order_by.return_value.first.return_value = legacy
        return m

    return _filter


class EnsureGeneralDepartmentSealTests(SimpleTestCase):
    def _model(self, *, canonical=None, legacy=None):
        model = mock.MagicMock()
        model.objects.filter.side_effect = _filter_router(
            canonical=canonical, legacy=legacy
        )
        return model

    def test_none_school_returns_none(self):
        self.assertIsNone(structure_provisioning.ensure_general_department(None))

    def test_existing_canonical_is_reused(self):
        existing = mock.Mock(name="canonical_dept")
        model = self._model(canonical=existing)
        # settings={} matters: resolve_provision_seed_inputs does dict(school.settings or {}),
        # and a bare Mock attribute is truthy, so dict() raises TypeError before
        # namespaced_structure_code can derive the code prefix.
        school = mock.Mock(id="abcdef1234567890", settings={})
        with mock.patch.object(structure_provisioning, "Department", model):
            out = structure_provisioning.ensure_general_department(school)
        self.assertIs(out, existing)
        self.assertFalse(model.objects.create.called, "must not mint a duplicate")

    def test_legacy_named_department_is_adopted_not_duplicated(self):
        legacy = mock.Mock(name="legacy_slug_gen_dept")
        model = self._model(canonical=None, legacy=legacy)
        # settings={} matters: resolve_provision_seed_inputs does dict(school.settings or {}),
        # and a bare Mock attribute is truthy, so dict() raises TypeError before
        # namespaced_structure_code can derive the code prefix.
        school = mock.Mock(id="abcdef1234567890", settings={})
        with mock.patch.object(structure_provisioning, "Department", model):
            out = structure_provisioning.ensure_general_department(school)
        self.assertIs(out, legacy)
        self.assertFalse(model.objects.create.called, "must adopt, not duplicate")

    def test_creates_canonical_when_none_exist(self):
        created = mock.Mock(name="created_dept")
        model = self._model(canonical=None, legacy=None)
        model.objects.create.return_value = created
        # settings={} matters: resolve_provision_seed_inputs does dict(school.settings or {}),
        # and a bare Mock attribute is truthy, so dict() raises TypeError before
        # namespaced_structure_code can derive the code prefix.
        school = mock.Mock(id="abcdef1234567890", settings={})
        with mock.patch.object(structure_provisioning, "Department", model):
            out = structure_provisioning.ensure_general_department(school)
        self.assertIs(out, created)
        model.objects.create.assert_called_once()
        kwargs = model.objects.create.call_args.kwargs
        self.assertEqual(kwargs["name"], "General")
        self.assertEqual(kwargs["code"], "GEN-abcdef12")  # GEN-<id8>
        self.assertIs(kwargs["school"], school)
