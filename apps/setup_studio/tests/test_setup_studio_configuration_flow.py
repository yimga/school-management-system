from django.test import TestCase

from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.tenant_guard import (
    SetupStudioTenantScopeError,
    assert_same_school,
    compile_setup_for_school,
    scoped_setup_progress_queryset,
)


class SetupStudioConfigurationFlowTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="Studio A",
            slug="studio-a",
            subdomain="studio-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Studio B",
            slug="studio-b",
            subdomain="studio-b",
            is_active=True,
        )

    def test_cross_tenant_compile_blocked(self):
        with self.assertRaises(SetupStudioTenantScopeError):
            compile_setup_for_school(self.school_a, self.school_b)

    def test_scoped_progress_queryset_isolated(self):
        SetupProgress.objects.create(school=self.school_a, current_step_key="plan_choice")
        SetupProgress.objects.create(school=self.school_b, current_step_key="branding")
        qs = scoped_setup_progress_queryset(self.school_a)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().school_id, self.school_a.pk)

    def test_same_school_compile_succeeds(self):
        assert_same_school(self.school_a, self.school_a)
        payload = compile_setup_for_school(self.school_a, self.school_a)
        self.assertIn("step_state", payload)
        self.assertIn("registry_alignment", payload)
