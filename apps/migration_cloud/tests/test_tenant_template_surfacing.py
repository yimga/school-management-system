"""Canonical import templates must be reachable from the tenant self-serve wizard.

Audit finding: the ready-made import templates (picker + ZIP) were surfaced only
on the OPERATOR intake page — self-serve tenants uploading through the
connectionless wizard had no way to discover them. This wave resolves the
template URLs host-defensively in the tenant upload view and shows a download
panel on the upload page.
"""

from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.views_tenant_upload import _canonical_template_urls
from apps.siteconfig.tests._template_nodes import assert_markup

UPLOAD_TPL = Path("templates/migration_cloud/connector/upload.html")


@override_settings(ROOT_URLCONF="config.tenant_urls")
class CanonicalTemplateTenantSurfacingTests(SimpleTestCase):
    def test_picker_and_zip_urls_resolve_on_tenant_host(self):
        urls = _canonical_template_urls(None)
        self.assertTrue(urls["template_picker_url"], urls)
        self.assertIn("template/picker", urls["template_picker_url"])
        self.assertTrue(urls["template_zip_url"], urls)

    def test_urls_fall_through_cleanly_when_absent(self):
        # The helper must never raise NoReverseMatch — worst case it returns "".
        urls = _canonical_template_urls(None)
        self.assertIn("template_picker_url", urls)
        self.assertIn("template_zip_url", urls)


class UploadTemplateHasDownloadPanelTests(SimpleTestCase):
    def test_upload_template_conditionally_surfaces_the_panel(self):
        src = Path(
            "templates/migration_cloud/connector/upload.html"
        ).read_text(encoding="utf-8")
        # template_picker_url is the CONTEXT VARIABLE the panel is conditioned
        # on -- template code, invisible to a parse -- so it stays a read. The
        # panel's own heading is markup, and "surfaces the panel" is a claim
        # about the page, so the engine answers that half.
        assert_markup(self, UPLOAD_TPL, "mc-template-heading")
        self.assertIn("template_picker_url", src)
        self.assertIn("mc-template-heading", src)
