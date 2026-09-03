from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_markup

BUNDLE_DETAIL = Path(settings.BASE_DIR) / "templates/migration_cloud/bundle_detail.html"


class BundleDetailLayoutContractTests(SimpleTestCase):
    def test_dense_workbench_does_not_enable_auto_row_detail_transform(self):
        template = (
            Path(settings.BASE_DIR) / "templates/migration_cloud/bundle_detail.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn('data-rmc-row-detail-auto="1"', template)
        self.assertNotIn('data-rmc-row-detail-table="1"', template)
        self.assertNotIn('class="rmc-card rmc-mapping rmc-reveal"', template)
        # The three assertNotIns above are absences over bytes and stay reads.
        # The two positives are the workbench markup that has to REPLACE the auto
        # row-detail transform; a workbench that exists only in the file replaces
        # nothing, so the engine answers for those.
        assert_markup(
            self,
            BUNDLE_DETAIL,
            'class="rmc-card rmc-mapping-workbench rmc-reveal"',
            'data-rmc-native-workbench-table="1"',
        )
        self.assertIn('class="rmc-card rmc-mapping-workbench rmc-reveal"', template)
        self.assertIn('data-rmc-native-workbench-table="1"', template)

    def test_tables_and_actions_keep_the_desktop_workbench_contract(self):
        css = (
            Path(settings.BASE_DIR) / "static/css/migration-cloud-ui.css"
        ).read_text(encoding="utf-8")

        for marker in (
            ".rmc-page--migration-cloud-detail .rmc-mapping__table",
            ".rmc-page--migration-cloud-detail .rmc-mapping-workbench",
            ".rmc-page--migration-cloud-detail .rmc-mapping__actions",
            "flex-flow: row nowrap",
            ".rmc-page--migration-cloud-detail .rmc-button-row",
            "overflow-x: auto",
            "word-break: normal",
        ):
            self.assertIn(marker, css)
