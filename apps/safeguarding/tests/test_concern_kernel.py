"""Wave R-D (v3.96.0 — 2026-05-26) — Safeguarding concern kernel tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.safeguarding.concern_kernel import (
    ACKNOWLEDGED,
    ACTION_TAKEN,
    CLOSED,
    DRAFT,
    REFERRED_EXTERNAL,
    SUBMITTED,
    DSLAssignment,
    DSLRoleRequired,
    InvalidConcernTransition,
    append_to_school_settings,
    create_concern,
    get_category,
    is_dsl,
    list_categories,
    open_concerns,
    sanitize_narrative,
    transition_concern,
)


class CategoryRegistryTests(SimpleTestCase):

    def test_kcsie_categories_present(self):
        keys = {c.key for c in list_categories()}
        # Spot-check a few KCSIE 2026 mandated categories.
        for k in (
            "physical_abuse", "emotional_abuse", "neglect", "sexual_abuse",
            "child_on_child_abuse", "online_harm", "radicalisation", "fgm",
        ):
            self.assertIn(k, keys)

    def test_urgent_flag_on_severe_categories(self):
        self.assertTrue(get_category("physical_abuse").is_urgent)
        self.assertTrue(get_category("sexual_abuse").is_urgent)
        self.assertTrue(get_category("fgm").is_urgent)
        self.assertFalse(get_category("mental_health").is_urgent)


class SanitizeNarrativeTests(SimpleTestCase):

    def test_strips_email(self):
        out = sanitize_narrative("Reported by parent@example.com today.")
        self.assertIn("[REDACTED_EMAIL]", out)
        self.assertNotIn("parent@example.com", out)

    def test_strips_phone(self):
        out = sanitize_narrative("Mother called from +44 7700 900123 last night.")
        self.assertIn("[REDACTED_PHONE]", out)
        self.assertNotIn("900123", out)

    def test_truncates_oversized(self):
        long_text = "x" * 10000
        out = sanitize_narrative(long_text)
        self.assertLessEqual(len(out), 4000)


class CreateConcernTests(SimpleTestCase):

    def test_minimal_creation(self):
        entry, audit = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="neglect",
            narrative="Child arrived without lunch on three consecutive days.",
        )
        self.assertEqual(entry.stage, DRAFT)
        self.assertEqual(entry.category_key, "neglect")
        self.assertFalse(entry.is_urgent)
        self.assertEqual(audit.sensitivity, "CRITICAL")
        self.assertEqual(audit.action, "CREATE")

    def test_urgent_category_propagates(self):
        entry, _ = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="physical_abuse",
            narrative="Visible bruising disclosed during PE lesson.",
        )
        self.assertTrue(entry.is_urgent)

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            create_concern(
                school_id=1, student_id=42, reporter_user_id=7,
                category_key="invented",
                narrative="x" * 100,
            )

    def test_narrative_too_short_raises(self):
        with self.assertRaises(ValueError):
            create_concern(
                school_id=1, student_id=42, reporter_user_id=7,
                category_key="neglect",
                narrative="short",
            )


class TransitionTests(SimpleTestCase):

    def _seed(self):
        return create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="neglect",
            narrative="Child arrived without lunch on three consecutive days.",
        )[0]

    def test_draft_to_submitted_open_to_any_actor(self):
        c = self._seed()
        c2, audit = transition_concern(
            concern=c, target_stage=SUBMITTED, actor_user_id=7,
        )
        self.assertEqual(c2.stage, SUBMITTED)
        self.assertEqual(audit.action, "UPDATE")

    def test_submitted_to_acknowledged_requires_dsl(self):
        c = self._seed()
        c, _ = transition_concern(
            concern=c, target_stage=SUBMITTED, actor_user_id=7,
        )
        with self.assertRaises(DSLRoleRequired):
            transition_concern(
                concern=c, target_stage=ACKNOWLEDGED, actor_user_id=999,
                dsl_assignments=[],
            )

    def test_acknowledged_with_valid_dsl(self):
        c = self._seed()
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        c2, audit = transition_concern(
            concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42,
            dsl_assignments=[DSLAssignment(user_id=42, school_id=1, is_active=True)],
        )
        self.assertEqual(c2.stage, ACKNOWLEDGED)
        self.assertEqual(c2.dsl_acknowledged_by, 42)
        self.assertTrue(c2.dsl_acknowledged_at)

    def test_inactive_dsl_rejected(self):
        c = self._seed()
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        with self.assertRaises(DSLRoleRequired):
            transition_concern(
                concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42,
                dsl_assignments=[DSLAssignment(user_id=42, school_id=1, is_active=False)],
            )

    def test_dsl_for_other_school_rejected(self):
        c = self._seed()
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        with self.assertRaises(DSLRoleRequired):
            transition_concern(
                concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42,
                dsl_assignments=[DSLAssignment(user_id=42, school_id=999, is_active=True)],
            )

    def test_invalid_transition_jump(self):
        c = self._seed()
        with self.assertRaises(InvalidConcernTransition):
            transition_concern(
                concern=c, target_stage=CLOSED, actor_user_id=7,
            )

    def test_external_referral_records_reference(self):
        c = self._seed()
        dsl = [DSLAssignment(user_id=42, school_id=1, is_active=True)]
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        c, _ = transition_concern(
            concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42, dsl_assignments=dsl,
        )
        c, _ = transition_concern(
            concern=c, target_stage=REFERRED_EXTERNAL, actor_user_id=42,
            dsl_assignments=dsl, referral_reference="LADO-2026-0001",
        )
        self.assertEqual(c.stage, REFERRED_EXTERNAL)
        self.assertEqual(c.referral_reference, "LADO-2026-0001")

    def test_closed_is_terminal(self):
        c = self._seed()
        dsl = [DSLAssignment(user_id=42, school_id=1, is_active=True)]
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        c, _ = transition_concern(
            concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42, dsl_assignments=dsl,
        )
        c, _ = transition_concern(
            concern=c, target_stage=CLOSED, actor_user_id=42, dsl_assignments=dsl,
        )
        with self.assertRaises(InvalidConcernTransition):
            transition_concern(
                concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42,
                dsl_assignments=dsl,
            )


class IsDSLTests(SimpleTestCase):

    def test_none_user_is_never_dsl(self):
        self.assertFalse(is_dsl(None, 1, []))

    def test_active_dsl_matches(self):
        self.assertTrue(is_dsl(
            42, 1, [DSLAssignment(user_id=42, school_id=1, is_active=True)],
        ))


class LedgerTests(SimpleTestCase):

    def test_append_seeds_safeguarding_bucket(self):
        c, _ = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="neglect",
            narrative="Child arrived without lunch on three consecutive days.",
        )
        out = append_to_school_settings(school_settings=None, concern=c)
        self.assertIn("safeguarding", out)
        self.assertEqual(len(out["safeguarding"]["concerns"]), 1)

    def test_append_replaces_existing_by_concern_id(self):
        c, _ = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="neglect",
            narrative="x" * 30,
        )
        first = append_to_school_settings(school_settings={}, concern=c)
        # Same concern_id, advanced stage — should overwrite, not duplicate.
        c2, _ = transition_concern(
            concern=c, target_stage=SUBMITTED, actor_user_id=7,
        )
        second = append_to_school_settings(school_settings=first, concern=c2)
        self.assertEqual(len(second["safeguarding"]["concerns"]), 1)
        self.assertEqual(
            second["safeguarding"]["concerns"][0]["stage"], SUBMITTED,
        )

    def test_open_concerns_filters_closed(self):
        c, _ = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="neglect", narrative="x" * 30,
        )
        s = append_to_school_settings(school_settings={}, concern=c)
        opened = open_concerns(s)
        self.assertEqual(len(opened), 1)

        dsl = [DSLAssignment(user_id=42, school_id=1, is_active=True)]
        c, _ = transition_concern(concern=c, target_stage=SUBMITTED, actor_user_id=7)
        c, _ = transition_concern(
            concern=c, target_stage=ACKNOWLEDGED, actor_user_id=42, dsl_assignments=dsl,
        )
        c, _ = transition_concern(
            concern=c, target_stage=CLOSED, actor_user_id=42, dsl_assignments=dsl,
        )
        s = append_to_school_settings(school_settings=s, concern=c)
        self.assertEqual(len(open_concerns(s)), 0)


class AuditCriticalSensitivityTests(SimpleTestCase):

    def test_every_transition_writes_critical_audit(self):
        c, audit = create_concern(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="physical_abuse", narrative="x" * 30,
        )
        self.assertEqual(audit.sensitivity, "CRITICAL")
        _, audit2 = transition_concern(
            concern=c, target_stage=SUBMITTED, actor_user_id=7,
        )
        self.assertEqual(audit2.sensitivity, "CRITICAL")
