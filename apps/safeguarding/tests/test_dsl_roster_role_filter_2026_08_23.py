"""Who counts as a DSL: the roster filter, and the fallback pool it falls back to.

Two defects, both on the gate that decides who may read every child-protection
concern in a tenant.

**The stakeholder filter fell through.** ``load_dsl_assignments`` meant to accept
only DSL-role rows out of ``stakeholder_pipeline``. It read::

    if role not in {"dsl", "designated_safeguarding_lead", ""}:
        if "user_id" not in row and "id" not in row:
            continue

-- the ``continue`` fires only when the row carries NEITHER key, so
``{"role": "nurse", "user_id": 42}`` walked straight through and became an ACTIVE
DSL. ``apply_stakeholder_pipeline`` validates nothing, and the step that feeds it
is now wired to a real people-picker, so this is no longer latent: every
non-DSL name in a tenant's escalation chain would silently gain the inbox, the
narratives, and the transition buttons.

**The fallback pool advertised a role that cannot exist.**
``_DSL_FALLBACK_ROLES`` listed ``"OWNER"``, but ``SchoolMembership.role`` draws
its choices from ``User.Role``, which has no OWNER member -- per-school ownership
is the separate boolean ``SchoolMembership.is_school_owner``. So a third of the
fallback pool matched nothing, and an owner whose membership role is not ADMIN
received no urgent alert and was refused the inbox.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.safeguarding.services import (
    load_dsl_assignments,
    resolve_dsl_recipients,
    user_is_dsl,
)
from apps.schools.models import School, SchoolMembership


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(name=f"SG {tag}", slug=slug, subdomain=slug)


def _set_pipeline(school: School, rows: list) -> None:
    settings = dict(school.settings or {})
    blob = dict(settings.get("safeguarding") or {})
    blob["stakeholder_pipeline"] = rows
    settings["safeguarding"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


class StakeholderRoleFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school("filter")
        cls.nurse = User.objects.create_user(username=f"nurse_{uuid.uuid4().hex[:6]}", password="x")
        cls.lead = User.objects.create_user(username=f"lead_{uuid.uuid4().hex[:6]}", password="x")
        for user in (cls.nurse, cls.lead):
            user.role = User.Role.TEACHER
            user.save(update_fields=["role"])
            SchoolMembership.objects.create(user=user, school=cls.school, role="TEACHER")

    def test_a_named_non_dsl_stakeholder_is_not_a_dsl(self):
        _set_pipeline(self.school, [{"role": "nurse", "user_id": self.nurse.pk}])
        self.assertEqual(
            [a.user_id for a in load_dsl_assignments(self.school)],
            [],
            "a stakeholder whose row says it is NOT a DSL must never become one",
        )
        self.assertFalse(user_is_dsl(self.nurse, self.school))

    def test_the_bare_id_variant_is_filtered_too(self):
        _set_pipeline(self.school, [{"role": "parent_liaison", "id": self.nurse.pk}])
        self.assertEqual([a.user_id for a in load_dsl_assignments(self.school)], [])

    def test_an_explicit_dsl_row_is_still_accepted(self):
        _set_pipeline(self.school, [{"role": "dsl", "user_id": self.lead.pk}])
        self.assertEqual(
            [a.user_id for a in load_dsl_assignments(self.school)], [self.lead.pk]
        )
        self.assertTrue(user_is_dsl(self.lead, self.school))

    def test_the_shape_the_real_wizard_writes_is_still_accepted(self):
        """The people-picker step stores plain stringified pks. Do not break it."""
        _set_pipeline(self.school, [str(self.lead.pk)])
        self.assertEqual(
            [a.user_id for a in load_dsl_assignments(self.school)], [self.lead.pk]
        )

    def test_a_role_less_row_is_still_accepted(self):
        """No role key means 'this is the roster', not 'this is somebody else'."""
        _set_pipeline(self.school, [{"user_id": self.lead.pk}])
        self.assertEqual(
            [a.user_id for a in load_dsl_assignments(self.school)], [self.lead.pk]
        )

    def test_a_mixed_pipeline_keeps_only_the_leads(self):
        _set_pipeline(
            self.school,
            [
                {"role": "nurse", "user_id": self.nurse.pk},
                {"role": "designated_safeguarding_lead", "user_id": self.lead.pk},
            ],
        )
        self.assertEqual(
            [a.user_id for a in load_dsl_assignments(self.school)], [self.lead.pk]
        )


class OwnerFallbackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school("owner")
        cls.owner = User.objects.create_user(username=f"own_{uuid.uuid4().hex[:6]}", password="x")
        cls.owner.role = User.Role.PROPRIETOR
        cls.owner.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=cls.owner, school=cls.school, role="PROPRIETOR", is_school_owner=True
        )

    def test_owner_is_not_a_selectable_membership_role(self):
        """Calibration: the string the fallback pool used to filter on cannot exist."""
        self.assertNotIn("OWNER", dict(User.Role.choices))

    def test_the_school_owner_reaches_the_inbox(self):
        self.assertTrue(
            user_is_dsl(self.owner, self.school),
            "with no DSL named, the person who owns the tenant must be able to "
            "triage -- the fallback filtered on a role string that never matches",
        )

    def test_the_urgent_alert_reaches_the_school_owner(self):
        self.assertIn(
            self.owner.pk,
            {u.pk for u in resolve_dsl_recipients(self.school)},
            "an owner-only membership received no urgent safeguarding alert",
        )

    def test_a_suspended_owner_is_not_alerted_or_admitted(self):
        SchoolMembership.objects.filter(school=self.school, user=self.owner).update(
            suspended_at="2026-01-01T00:00:00+00:00"
        )
        self.assertNotIn(
            self.owner.pk, {u.pk for u in resolve_dsl_recipients(self.school)}
        )
        self.assertFalse(user_is_dsl(self.owner, self.school))
