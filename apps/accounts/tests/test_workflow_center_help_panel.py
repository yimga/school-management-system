"""Workflow Center contextual help panel.

Wires templates/components/workflow_help_panel.html (the "How it works /
Before you start / Common blockers / What happens next" pattern) into the live
Workflow Center page. Three complementary layers:

  * build_workflow_help_panel() — the pure payload builder, conditional blocker
    logic on both branches (no DB/shell),
  * the panel partial renders a help dict correctly (deterministic, no shell), and
  * the live Workflow Center page mounts the panel and surfaces the
    "no active academic year" blocker only when it applies.
"""

from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.accounts.views_workflow import build_workflow_help_panel, workflow_center
from apps.schools.models import School, SchoolMembership


class BuildWorkflowHelpPanelTests(SimpleTestCase):
    """The pure payload builder — conditional blocker logic, no DB/shell."""

    def test_no_active_year_includes_blocker(self):
        panel = build_workflow_help_panel(
            has_active_year=False, academic_year_url="/admin/year/"
        )
        labels = [str(b["label"]) for b in panel["common_blockers"]]
        self.assertTrue(any("No active academic year" in label for label in labels))
        self.assertEqual(panel["common_blockers"][0]["fix_url"], "/admin/year/")

    def test_active_year_has_no_year_blocker(self):
        panel = build_workflow_help_panel(
            has_active_year=True, academic_year_url="/admin/year/", year_count=2
        )
        labels = [str(b["label"]) for b in panel["common_blockers"]]
        self.assertFalse(any("No active academic year" in label for label in labels))

    def test_one_year_blocks_clone_until_target_exists(self):
        panel = build_workflow_help_panel(
            has_active_year=True, academic_year_url="/admin/year/add/", year_count=1
        )
        labels = [str(b["label"]) for b in panel["common_blockers"]]
        self.assertTrue(any("Clone needs a new target year" in label for label in labels))
        self.assertEqual(panel["common_blockers"][0]["fix_url"], "/admin/year/add/")

    def test_annotate_blocks_marks_until_classrooms_exist(self):
        from apps.accounts.views_workflow import _annotate_workflow_step_status

        steps = [
            {"step_key": "year_setup", "title": "1) Year setup"},
            {"step_key": "onboarding", "title": "2) Onboarding"},
            {"step_key": "marks", "title": "3) Marks"},
        ]
        _annotate_workflow_step_status(steps, has_year=True, has_classrooms=False)
        self.assertEqual(steps[0]["status"], "next")
        self.assertEqual(steps[1]["status"], "ready")
        self.assertEqual(steps[2]["status"], "blocked")
        self.assertIn("classrooms", str(steps[2]["blocked_reason"]))
        # De-dup: the page hero owns the Help/KB link, so the panel has none.
        panel = build_workflow_help_panel(has_active_year=True)
        self.assertIsNone(panel.get("need_help"))
        # ...and its always-on structural sections are present.
        self.assertTrue(panel["how_it_works"])
        self.assertTrue(panel["before_you_start"])
        self.assertTrue(panel["what_happens_next"])


class WorkflowHelpPanelPartialTests(TestCase):
    """The partial renders the caller contract — independent of any shell."""

    def _render(self, help_dict):
        return render_to_string(
            "components/workflow_help_panel.html", {"help": help_dict}
        )

    def test_full_help_dict_renders_all_sections(self):
        html = self._render(
            {
                "title": "How the Workflow Center works",
                "how_it_works": ["Set up the year"],
                "before_you_start": ["An active academic year"],
                "common_blockers": [
                    {"label": "No active academic year is set", "fix_url": "/admin/year/"}
                ],
                "what_happens_next": ["Reports publish to parents"],
                "need_help": {"label": "Help & Knowledge Base", "url": "/kb/"},
            }
        )
        self.assertIn('data-rmc-workflow-help="1"', html)
        self.assertIn("How the Workflow Center works", html)
        self.assertIn("How it works", html)
        self.assertIn("Before you start", html)
        self.assertIn("Common blockers", html)
        self.assertIn("What happens next", html)
        # Blocker fix link + KB support link both present and pointed at real URLs.
        self.assertIn('href="/admin/year/"', html)
        self.assertIn("rmc-workflow-help__support-link", html)
        self.assertIn('href="/kb/"', html)

    def test_no_ai_button_without_context_key(self):
        # need_help carries no ai_help → the panel must not emit a dead AI button.
        html = self._render(
            {
                "title": "X",
                "how_it_works": ["a"],
                "need_help": {"label": "Help", "url": "/kb/"},
            }
        )
        self.assertNotIn("rmc-workflow-help__ai-link", html)

    def test_empty_sections_are_skipped(self):
        # No blockers passed → the blockers section must not render.
        html = self._render({"title": "X", "how_it_works": ["a"], "common_blockers": []})
        self.assertNotIn("Common blockers", html)


@override_settings(ALLOWED_HOSTS=["*"])
class WorkflowCenterPageHelpPanelTests(TestCase):
    """The live page mounts the panel with grounded, conditional content."""

    def setUp(self):
        self.school = School.objects.create(
            name="Help Panel High",
            slug="hp-wf",
            subdomain="hp-wf",
            is_active=True,
        )
        # permission_required("settings.manage") short-circuits True for superusers.
        self.user = User.objects.create_user(
            username="adm_help_panel",
            password="x",
            is_staff=True,
            is_superuser=True,
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.factory = RequestFactory()

    def _render_page(self):
        request = self.factory.get("/studio/hubs/workflow/")
        request.user = self.user
        request.school = self.school
        # Full-shell render reads request.session / messages via context processors.
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        response = workflow_center(request)
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def test_page_mounts_help_panel(self):
        html = self._render_page()
        self.assertIn('data-rmc-workflow-help="1"', html)
        self.assertIn("How the Workflow Center works", html)
        self.assertNotIn("rmc-workflow-help__ai-link", html)
        # De-dup with the page hero: the panel carries no Help/KB footer link.
        self.assertNotIn("rmc-workflow-help__support-link", html)

    def test_no_active_year_blocker_surfaces(self):
        # setUp creates no AcademicYear → active year is None → blocker appears.
        # (The fix link is best-effort: it renders only when the admin year URL
        # resolves, which it does in production but not in the restricted test
        # urlconf — fix-link rendering is covered deterministically by the
        # partial test above. Here we assert the blocker label itself.)
        html = self._render_page()
        self.assertIn("No active academic year is set", html)
        self.assertIn("rmc-workflow-help__list--blockers", html)
        self.assertIn("Create academic year", html)
        self.assertIn("Clone needs a new target year", html)
        self.assertIn("Follow the highlighted next step", html)
