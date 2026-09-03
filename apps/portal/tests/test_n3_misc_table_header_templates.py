"""N3: misc portal/report templates use scope=\"col\" (and labeled action columns)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup


def _TPL(*parts: str) -> Path:
    return Path(settings.BASE_DIR).joinpath("templates", *parts)


class MiscTableHeaderScopeTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def _assert_aria_label(self, text: str, label: str) -> None:
        """The table names itself, bare or wrapped in {% trans %}.

        Same drift as the column headers: aria-label="Teacher pay history
        records" became aria-label="{% trans 'Teacher pay history records' %}"
        and the contract went red while the accessible name never changed.
        """
        # The quote around the msgid may be either kind, so match any single
        # character there rather than nesting quotes three deep.
        pattern = r'aria-label="(?:%s|\{%% trans .%s. %%\})"' % (
            re.escape(label),
            re.escape(label),
        )
        self.assertRegex(
            text, pattern, f'no table declares the accessible name {label!r}'
        )

    def _assert_columns(self, text: str, *labels: str) -> int:
        """Every label is a scope="col" header, however the <th> is dressed.

        These were pinned as exact strings (`scope="col">Started`) and went
        red the day the labels were wrapped in {% trans %}. The header never
        moved and never lost its scope -- only the spelling changed. Matching
        the msgid inside the tag keeps the column identity, which a bare
        count of scope="col" cannot express, without pinning the class and
        style attributes that have nothing to do with the contract.
        """
        found = 0
        for label in labels:
            pattern = (
                r'<th\s+scope="col"[^>]*>\s*\{%\s*trans\s+"'
                + re.escape(label)
                + r'"\s*%\}'
            )
            with self.subTest(column=label):
                self.assertRegex(
                    text,
                    pattern,
                    f'no <th scope="col"> carries the column {label!r}',
                )
            found += 1
        return found

    def test_analytics_deadlines_table(self):
        text = self._read("templates", "analytics", "deadlines.html")
        self.assertIn('aria-label="Grading deadlines by scope and date"', text)
        self._assert_columns(text, "Scope", "Deadline")
        assert_markup(self, _TPL("analytics", "deadlines.html"), 'scope="col"')
        self.assertIn('class="visually-hidden">{% trans "Actions" %}</span>', text)

    def test_evals_grade_import_v2_validation_table(self):
        text = self._read("templates", "evals", "grade_import_upload_v2.html")
        self.assertIn('id="validationTable"', text)
        # Was `count('scope="col"') >= 6` against a five-column table. A
        # magic count cannot say WHICH column went missing; naming them can.
        self._assert_columns(
            text, "Row #", "Student Code", "Assessment", "Status", "Issues"
        )
        assert_markup(self, _TPL("evals", "grade_import_upload_v2.html"), 'id="validationTable"')

    def test_reports_term_report_subject_table(self):
        text = self._read("templates", "reports", "term_report.html")
        self._assert_columns(text, "Subject", "Coef", "Remark")
        assert_markup(self, _TPL("reports", "term_report.html"), 'scope="col"')

    def test_reports_annual_report_term_summary(self):
        text = self._read("templates", "reports", "annual_report.html")
        self.assertIn('aria-label="Annual report term summary averages and class position"', text)
        self.assertIn('scope="col">{% term_label %}', text)

    def test_teacher_pay_history_records_table(self):
        text = self._read("templates", "teacher", "pay_history.html")
        self._assert_aria_label(text, "Teacher pay history records")
        self._assert_columns(text, "Date", "Amount", "Description")
        assert_markup(self, _TPL("teacher", "pay_history.html"), 'scope="col"')

    def test_evals_grade_approval_list_actions_column(self):
        text = self._read("templates", "evals", "grade_approval_list.html")
        self.assertIn('class="visually-hidden">{% trans "Actions" %}</span>', text)

    def test_siteconfig_reportcard_builder_assignments(self):
        wrapper = self._read("templates", "siteconfig", "reportcard_builder.html")
        body = self._read(
            "templates", "siteconfig", "partials", "reportcard_builder_body.html"
        )
        text = wrapper + body
        self.assertIn('aria-label="Report card style assignments by classroom"', text)
        self.assertIn('scope="col">', text)
        self.assertIn("Classroom", text)

    def test_schools_super_metadata_catalog(self):
        text = self._read("templates", "schools", "super_metadata_catalog.html")
        self.assertIn('aria-label="Metadata catalog entities and field impact"', text)
        self.assertIn('scope="col">{% trans "Entity" %}</th>', text)

    def test_accounts_rbac_dashboard_roles(self):
        text = self._read("templates", "accounts", "rbac_dashboard.html")
        self.assertIn('aria-label="Existing RBAC roles"', text)
        self._assert_columns(text, "Code")
        assert_markup(self, _TPL("accounts", "rbac_dashboard.html"), 'scope="col"')

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
        # Five separate leaderboards each head their first column Rank.
        self.assertGreaterEqual(len(re.findall(
            r'<th\s+scope="col"[^>]*>\s*\{%\s*trans\s+"Rank"\s*%\}', text
        )), 5)
        assert_markup(self, _TPL("analytics", "dashboard.html"), 'scope="col"')

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
        self._assert_columns(text, "Started", "School", "Status")
        assert_markup(self, _TPL("schools", "super_migration_cloud.html"), 'scope="col"')

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
