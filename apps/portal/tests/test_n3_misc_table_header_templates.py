"""N3: misc portal/report templates use scope=\"col\" (and labeled action columns)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MiscTableHeaderScopeTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_analytics_deadlines_table(self):
        text = self._read("templates", "analytics", "deadlines.html")
        self.assertIn('aria-label="Grading deadlines by scope and date"', text)
        self.assertIn('scope="col">Scope', text)
        self.assertIn('class="visually-hidden">{% trans "Actions" %}</span>', text)

    def test_evals_grade_import_v2_validation_table(self):
        text = self._read("templates", "evals", "grade_import_upload_v2.html")
        self.assertIn('id="validationTable"', text)
        self.assertGreaterEqual(text.count('scope="col"'), 6)

    def test_reports_term_report_subject_table(self):
        text = self._read("templates", "reports", "term_report.html")
        self.assertIn('scope="col">Subject', text)
        self.assertIn('scope="col" class="text-end">Coef', text)
        self.assertIn('scope="col">Remark', text)

    def test_reports_annual_report_term_summary(self):
        text = self._read("templates", "reports", "annual_report.html")
        self.assertIn('aria-label="Annual report term summary averages and class position"', text)
        self.assertIn('scope="col">Term', text)

    def test_teacher_pay_history_records_table(self):
        text = self._read("templates", "teacher", "pay_history.html")
        self.assertIn('aria-label="Teacher pay history records"', text)
        self.assertIn('scope="col">Date', text)
        self.assertIn('scope="col" class="text-end">Amount', text)

    def test_evals_grade_approval_list_actions_column(self):
        text = self._read("templates", "evals", "grade_approval_list.html")
        self.assertIn('class="visually-hidden">{% trans "Actions" %}</span>', text)

    def test_siteconfig_reportcard_builder_assignments(self):
        text = self._read("templates", "siteconfig", "reportcard_builder.html")
        self.assertIn('aria-label="Report card style assignments by classroom"', text)
        self.assertIn('scope="col">{% trans "Classroom" %}</th>', text)

    def test_schools_super_metadata_catalog(self):
        text = self._read("templates", "schools", "super_metadata_catalog.html")
        self.assertIn('aria-label="Metadata catalog entities and field impact"', text)
        self.assertIn('scope="col">{% trans "Entity" %}</th>', text)

    def test_accounts_rbac_dashboard_roles(self):
        text = self._read("templates", "accounts", "rbac_dashboard.html")
        self.assertIn('aria-label="Existing RBAC roles"', text)
        self.assertIn('scope="col">Code</th>', text)

    def test_reports_annual_report_cameroon(self):
        text = self._read("templates", "reports", "annual_report_cameroon.html")
        self.assertIn('aria-label="Cameroon annual report term summary"', text)
        self.assertIn('scope="col">{% report_style_label report_style "term_label"', text)

    def test_reports_term_report_cameroon(self):
        text = self._read("templates", "reports", "term_report_cameroon.html")
        self.assertIn('aria-label="Cameroon term subject marks grid"', text)
        self.assertGreaterEqual(text.count('scope="col"'), 9)

    def test_analytics_dashboard_tables(self):
        text = self._read("templates", "analytics", "dashboard.html")
        self.assertGreaterEqual(text.count('scope="col" style="width:80px;">Rank</th>'), 5)

    def test_schools_super_feature_toggles_list(self):
        text = self._read("templates", "schools", "super_feature_toggles_list.html")
        self.assertGreaterEqual(text.count('scope="col" class="border-secondary">{% trans "Key" %}'), 1)
        self.assertIn('scope="col" class="border-secondary text-end">{% trans "Actions" %}</th>', text)

    def test_schools_super_plan_form_addons(self):
        text = self._read("templates", "schools", "super_plan_form.html")
        self.assertIn('scope="col" class="border-secondary">{% trans "Code" %}</th>', text)

    def test_schools_super_migration_cloud_runs(self):
        text = self._read("templates", "schools", "super_migration_cloud.html")
        self.assertIn('aria-label="Recent cloud migration runs"', text)
        self.assertIn('scope="col">Started</th>', text)

    def test_schools_super_regions_list_headers(self):
        text = self._read("templates", "schools", "super_regions_list.html")
        self.assertNotIn('<th class="border-secondary">', text)
        self.assertIn('scope="col" class="border-secondary">{% trans "Code" %}</th>', text)

    def test_requests_dashboard_actions_column(self):
        text = self._read("templates", "requests", "dashboard.html")
        self.assertIn('class="visually-hidden">{% trans "Actions" %}</span>', text)

    def test_all_template_th_open_tags_include_scope(self):
        """Every <th ...> in templates/ must declare scope= (col or row) for SR/table a11y."""
        root = Path(settings.BASE_DIR) / "templates"
        th_tag = re.compile(r"<th\s[^>]*>", re.IGNORECASE)
        failures: list[str] = []
        for path in sorted(root.rglob("*.html")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for m in th_tag.finditer(text):
                tag = m.group()
                if "scope=" not in tag.lower():
                    line = text.count("\n", 0, m.start()) + 1
                    rel = path.relative_to(root)
                    failures.append(f"{rel}:{line}:{tag!r}")
        self.assertEqual(
            [],
            failures,
            "These <th> tags are missing a scope attribute:\n" + "\n".join(failures[:80]),
        )
