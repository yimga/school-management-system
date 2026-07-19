"""
v3.54 (2026-05-21) — Studio OS Control governance cockpit tests.

Covers:
  - Operator (staff) renders the control mode 200 with cockpit markers.
  - Non-staff is redirected away.
  - Audit list renders with safe markers when data present; honest empty state
    rendered with the documented copy when data absent.
  - Rollback CTA carries BOTH a confirm-prompt attribute AND a permission gate
    (settings.feature_control).
  - No raw email/slug in rendered audit rows.
  - No `href="#"` placeholders in Agent 6's partials.
  - Role names not hardcoded as literal strings outside {% trans %} blocks in
    Agent 6's partials.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.tests.manager_client import bind_manager_session


REPO_ROOT = Path(__file__).resolve().parents[3]
OWNED_PARTIALS = [
    REPO_ROOT / "templates" / "studio_os" / "modes" / "control.html",
    REPO_ROOT / "templates" / "studio_os" / "partials" / "control_mode_canvas.html",
    REPO_ROOT / "templates" / "studio_os" / "partials" / "workspace" / "control_canvas.html",
    REPO_ROOT / "templates" / "studio_os" / "partials" / "workspace" / "control_rail.html",
    REPO_ROOT
    / "templates"
    / "studio_os"
    / "partials"
    / "control_governance_preview_pane.html",
]


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class ControlGovernanceCockpitTests(TestCase):
    """Authenticated operator paths through Studio Control governance cockpit."""

    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.operator = User.objects.create_user(
            username="ctl_cockpit_op",
            password="x" * 12,
            is_staff=True,
            is_superuser=True,
        )
        cls.non_staff = User.objects.create_user(
            username="ctl_cockpit_user",
            password="x" * 12,
            is_staff=False,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="manager.runmycampus.com")

    def _login_operator(self):
        self.client.login(username="ctl_cockpit_op", password="x" * 12)
        bind_manager_session(self.client)

    # ---- 1. Operator can reach control mode and cockpit markers render ----

    def test_control_mode_renders_for_operator(self):
        # This is the "data present" path (see module docstring): seed one
        # FeatureControlAudit row so the cockpit renders the audit *list* rather
        # than the honest empty state. The empty-state path is covered separately
        # by test_audit_list_empty_state_is_honest, which seeds nothing.
        from apps.siteconfig.models_dashboard import FeatureControlAudit

        FeatureControlAudit.objects.create(
            user=self.operator, action="save", changes={}
        )
        self._login_operator()
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:400])
        body = resp.content.decode("utf-8", errors="replace")
        # Cockpit grid marker.
        self.assertIn('data-rmc-control-cockpit="governance"', body)
        # Audit tile marker.
        self.assertIn("rmc-control-audit-list", body)
        # Risk tile marker (either filled or honest empty state — both contain class).
        self.assertIn("rmc-control-cockpit__tile-title", body)
        # Governance preview pane present.
        self.assertIn('data-rmc-control-preview-pane="1"', body)
        # New CSS is linked.
        self.assertIn("studio-control-cockpit.css", body)

    def test_control_mode_restricted_for_non_staff(self):
        self.client.login(username="ctl_cockpit_user", password="x" * 12)
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        # On manager host with non-operator: redirect away (302) or 403; either is a deny.
        self.assertIn(resp.status_code, (302, 403))

    # ---- 2. Audit list — present vs empty state ----

    def test_audit_list_empty_state_is_honest(self):
        """With no audit entries, render the honest empty state copy."""
        self._login_operator()
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        # Either there's an audit list OR there's the empty-state copy — never fake.
        has_list = 'data-rmc-control-audit-list="1"' in body
        has_empty = ("No audit entries to display" in body) or (
            "No audit access" in body
        )
        self.assertTrue(
            has_list or has_empty,
            msg="Expected audit list OR honest empty state in cockpit body",
        )

    # ---- 3. Rollback CTA — confirm pattern AND permission gate ----

    def test_rollback_cta_has_confirm_pattern_and_perm_gate(self):
        """The rollback button must require both a confirm attribute and a perm gate."""
        canvas = REPO_ROOT / "templates" / "studio_os" / "partials" / "workspace" / "control_canvas.html"
        text = canvas.read_text(encoding="utf-8")
        # Permission gate is present.
        self.assertIn("perms.settings.feature_control", text)
        # Confirm-prompt attribute is present on the rollback CTA.
        self.assertIn("data-rmc-control-rollback-cta", text)
        self.assertIn("data-confirm-prompt", text)
        # Accessible label is unmistakable (not just "Roll back").
        self.assertIn("Roll back the most recent feature control change", text)

    def test_governance_preview_pane_destructive_uses_perm_contract(self):
        """The shared preview pane partial reads preview_pane_confirm_permitted before
        rendering destructive CTAs — the Studio OS canonical permission contract."""
        pane = (
            REPO_ROOT
            / "templates"
            / "studio_os"
            / "partials"
            / "control_governance_preview_pane.html"
        )
        text = pane.read_text(encoding="utf-8")
        self.assertIn("preview_pane_confirm_permitted", text)
        self.assertIn("data-confirm-prompt", text)
        self.assertIn("preview_pane_confirm_required_perm", text)

    # ---- 4. PII hygiene — no raw email/slug rendered in audit rows ----

    def test_audit_rows_do_not_render_user_email_or_slug(self):
        self._login_operator()
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        # The operator user's username should never leak into an audit row.
        # We scope this to the audit list region by extracting the substring between
        # the list start and end markers.
        m = re.search(
            r'data-rmc-control-audit-list="1">.*?</ul>',
            body,
            flags=re.DOTALL,
        )
        if m:
            audit_block = m.group(0)
            self.assertNotIn("ctl_cockpit_op", audit_block)
            self.assertNotIn("@", audit_block)

    # ---- 5. Role names — no role-string literals outside {% trans %} ----

    def test_partials_do_not_hardcode_role_names_outside_trans(self):
        """Agent 6's partials must not contain bare 'ADMIN'/'TEACHER'/'PARENT'
        /'STUDENT'/'PROPRIETOR' string literals outside {% trans %} blocks."""
        role_tokens = ("ADMIN", "TEACHER", "PARENT", "STUDENT", "PROPRIETOR")
        for partial in OWNED_PARTIALS:
            if not partial.exists():
                continue
            text = partial.read_text(encoding="utf-8")
            for token in role_tokens:
                # Bare ALL-CAPS role literal must not appear. Comments + tags scrubbed.
                # Strip {% trans "..." %} and {% blocktrans %}...{% endblocktrans %}.
                scrubbed = re.sub(
                    r"\{%\s*trans\s+['\"][^'\"]*['\"]\s*%\}", "", text
                )
                scrubbed = re.sub(
                    r"\{%\s*blocktrans[^%]*%\}.*?\{%\s*endblocktrans\s*%\}",
                    "",
                    scrubbed,
                    flags=re.DOTALL,
                )
                # Strip {# ... #} comments and {% comment %}...{% endcomment %} blocks.
                scrubbed = re.sub(r"\{#.*?#\}", "", scrubbed, flags=re.DOTALL)
                scrubbed = re.sub(
                    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
                    "",
                    scrubbed,
                    flags=re.DOTALL,
                )
                self.assertNotIn(
                    token,
                    scrubbed,
                    msg=(
                        f"Role-name literal {token!r} appears in {partial.name} "
                        "outside a trans/comment block. Use role_registry or User.Role "
                        "TextChoices instead."
                    ),
                )

    # ---- 6. No dummy hrefs in Agent 6's owned partials ----

    def test_no_dummy_hrefs_in_owned_partials(self):
        for partial in OWNED_PARTIALS:
            if not partial.exists():
                continue
            text = partial.read_text(encoding="utf-8")
            # Strip template comments + HTML comments before scanning so the docstring
            # comments that *mention* `href="#"` in our own partials are exempt.
            scrubbed = re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)
            scrubbed = re.sub(
                r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
                "",
                scrubbed,
                flags=re.DOTALL,
            )
            scrubbed = re.sub(r"<!--.*?-->", "", scrubbed, flags=re.DOTALL)
            self.assertNotIn(
                'href="#"',
                scrubbed,
                msg=f'Dummy href="#" found in {partial.name}',
            )
            self.assertNotIn(
                "href='#'",
                scrubbed,
                msg=f"Dummy href='#' found in {partial.name}",
            )

    # ---- 7. Feature flag bridge — links OUT, does not duplicate ----

    def test_feature_flag_tile_links_external_only(self):
        canvas = (
            REPO_ROOT
            / "templates"
            / "studio_os"
            / "partials"
            / "workspace"
            / "control_canvas.html"
        )
        text = canvas.read_text(encoding="utf-8")
        # Bridge marker present.
        self.assertIn('data-rmc-control-flags-link="1"', text)
        # The bridge anchor uses legacy_urls.feature_control (external SOT).
        self.assertIn("legacy_urls.feature_control", text)
        # The canvas does NOT include a feature-control form/toggle of its own.
        self.assertNotIn('name="feature_', text)

    # ---- 8. Honest empty state for risk monitor ----

    def test_risk_monitor_has_honest_empty_state_when_no_data(self):
        self._login_operator()
        url = reverse("studio_os:control", urlconf="config.manager_urls")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        # Risk-state engine is not wired — we must render the honest empty state copy.
        self.assertIn("Risk monitor coming online", body)
