"""Wizard server draft sync (R1) wiring and resolver tests."""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.schools.models import School
from apps.setup_studio import wizard_state_resolver


ROOT = Path(__file__).resolve().parents[3]


class WizardDraftSyncWiringTests(SimpleTestCase):
    def test_templates_wire_delta_sync(self):
        for rel in (
            "templates/setup_studio/tenant_wizard.html",
            "templates/setup_studio/operator_wizard.html",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("data-rmc-wizard-draft-sync-url", text)
            self.assertIn("rmc-wizard-delta-sync.js", text)

    def test_delta_sync_script_posts_json(self):
        js = (ROOT / "static/js/rmc-wizard-delta-sync.js").read_text(encoding="utf-8")
        self.assertIn("data-rmc-wizard-draft-sync-url", js)
        self.assertIn("rmc:wizard-draft-saved", js)
        self.assertIn("application/json", js)

    def test_draft_sync_url_resolves(self):
        url = reverse(
            "setup_studio:wizard_step_draft_sync",
            kwargs={"wizard_key": "mfa_setup", "step_key": "choose_channel"},
        )
        self.assertIn("/api/wizards/", url)
        self.assertTrue(url.endswith("/draft/"))


class WizardDraftSyncResolverTests(TestCase):
    WIZARD_KEY = "mfa_setup"
    STEP_KEY = "choose_channel"

    def setUp(self):
        self.school = School.objects.create(
            name="Draft Sync School",
            slug="draft-sync-school",
            subdomain="draft-sync-school",
            is_active=True,
        )

    def test_persist_draft_merges_into_context_shape(self):
        wizard_state_resolver.start_wizard(self.school, self.WIZARD_KEY)
        wizard_state_resolver.persist_step_draft(
            self.school,
            self.WIZARD_KEY,
            self.STEP_KEY,
            {"value": "totp"},
        )
        state = wizard_state_resolver.get_wizard_state(self.school, self.WIZARD_KEY)
        self.assertEqual(
            state["draft_answers"][self.STEP_KEY]["value"],
            "totp",
        )

    def test_apply_step_clears_draft(self):
        wizard_state_resolver.start_wizard(self.school, self.WIZARD_KEY)
        wizard_state_resolver.persist_step_draft(
            self.school, self.WIZARD_KEY, self.STEP_KEY, {"value": "totp"}
        )
        try:
            wizard_state_resolver.apply_step_answer(
                self.school,
                self.WIZARD_KEY,
                self.STEP_KEY,
                {"value": "totp"},
                actor_user_id=None,
            )
        except Exception:
            pass
        state = wizard_state_resolver.get_wizard_state(self.school, self.WIZARD_KEY)
        self.assertNotIn(self.STEP_KEY, state.get("draft_answers") or {})
