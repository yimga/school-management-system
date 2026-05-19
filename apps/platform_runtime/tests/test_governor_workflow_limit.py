"""Linux/Salesforce pillar: workflow governor hard stop."""

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.governor_limits import (
    WORKFLOW_RUNS_PER_DAY_PER_TENANT,
    record_workflow_run,
    workflow_run_limit_exceeded,
)
from apps.schools.models import School


class GovernorWorkflowLimitTests(TestCase):
    def test_workflow_limit_blocks_after_cap(self):
        school = School.objects.create(
            name="Gov School",
            slug="gov-school",
            subdomain="gov-school",
            is_active=True,
        )
        tid = str(school.pk)
        date_str = timezone.now().strftime("%Y-%m-%d")
        from django.core.cache import cache

        key = f"platform_runtime:governor:workflow_runs:{tid}:{date_str}"
        cache.set(key, WORKFLOW_RUNS_PER_DAY_PER_TENANT, timeout=86400)
        self.assertTrue(workflow_run_limit_exceeded(school_id=school.pk))
        cache.delete(key)
        self.assertFalse(workflow_run_limit_exceeded(school_id=school.pk))
        record_workflow_run(school_id=school.pk)
        self.assertGreater(
            cache.get(
                f"platform_runtime:governor:workflow_runs:{tid}:{date_str}",
                0,
            ),
            0,
        )
