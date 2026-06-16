"""Provisioning resume contract: a half-seeded tenant must stay resumable.

Regression: Phase B swallowed seed exceptions then marked phase_b_complete=True
unconditionally, so a tenant with no terms/subjects/classrooms/ComplianceProfile
went live and was never re-seeded. The fix withholds phase_b_complete when a
critical step failed; provisioning_needs_resume() then routes it to reconcile.

These exercise the helper contract the task fix relies on (no DB needed: both
helpers operate on school.settings dicts).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.provisioning_progress import provisioning_needs_resume
from apps.schools.tasks import _merge_provisioning_settings


class _School:
    def __init__(self):
        self.settings = {}
        self.is_active = True


class ProvisioningResumeContractTests(SimpleTestCase):
    def test_failed_phase_b_is_not_complete_and_stays_resumable(self):
        school = _School()
        _merge_provisioning_settings(school, phase_a_complete=True)
        _merge_provisioning_settings(
            school, phase_b_failed_steps=["terms", "compliance_profile"]
        )
        prov = school.settings["provisioning"]
        self.assertEqual(
            prov["phase_b_failed_steps"], ["terms", "compliance_profile"]
        )
        self.assertFalse(prov.get("phase_b_complete"))
        # Phase A done + Phase B not complete => must be picked up by resume.
        self.assertTrue(provisioning_needs_resume(school))

    def test_clean_phase_b_marks_complete_and_not_resumable(self):
        school = _School()
        _merge_provisioning_settings(school, phase_a_complete=True)
        _merge_provisioning_settings(
            school, phase_b_complete=True, phase_b_failed_steps=[]
        )
        prov = school.settings["provisioning"]
        self.assertTrue(prov["phase_b_complete"])
        self.assertFalse(provisioning_needs_resume(school))

    def test_inactive_school_never_needs_resume(self):
        school = _School()
        school.is_active = False
        _merge_provisioning_settings(school, phase_a_complete=True)
        self.assertFalse(provisioning_needs_resume(school))
