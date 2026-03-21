"""N17: template gallery requires impact preview session gate before metadata apply."""

from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.brand_experience.models import ThemePack
from apps.siteconfig.views import template_gallery_page
from apps.schools.models import School
from apps.accounts.models import User


def _noop_response(_request):
    return HttpResponse()


class TemplateGalleryImpactGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Gallery School",
            slug="gallery-school",
            subdomain="gallery-school",
            is_active=True,
        )
        self.user = User.objects.create_superuser("su_gallery", "su_gallery@x.edu", "pw")
        ThemePack.objects.create(
            name="Gallery Pack",
            slug="gal-tpl",
            is_active=True,
            primary_color="#111111",
            accent_color="#222222",
        )

    def _session_request(self, request):
        SessionMiddleware(_noop_response).process_request(request)
        request.user = self.user
        request.school = self.school
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_post_redirects_without_confirm(self):
        path = reverse("siteconfig:template_gallery")
        req = self._session_request(self.factory.post(path, {"template_slug": "gal-tpl"}))
        resp = template_gallery_page(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("preview_slug=gal-tpl", resp["Location"])

    def test_post_redirects_without_preview_gate_even_if_confirmed(self):
        path = reverse("siteconfig:template_gallery")
        req = self._session_request(
            self.factory.post(
                path,
                {"template_slug": "gal-tpl", "confirm_metadata_apply": "1"},
            )
        )
        resp = template_gallery_page(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("preview_slug=gal-tpl", resp["Location"])

    @patch("apps.siteconfig.views.get_effective_site_settings")
    def test_post_applies_after_preview_get(self, mock_site):
        site = MagicMock()
        site.pk = 1
        site.apply_theme_pack = MagicMock()
        mock_site.return_value = site

        get_path = reverse("siteconfig:template_gallery") + "?preview_slug=gal-tpl"
        r1 = self._session_request(self.factory.get(get_path))
        template_gallery_page(r1)
        self.assertEqual(r1.session.get("template_gallery_impact_gate", {}).get("slug"), "gal-tpl")
        r1.session.save()
        session_key = r1.session.session_key

        r2 = self.factory.post(
            reverse("siteconfig:template_gallery"),
            {"template_slug": "gal-tpl", "confirm_metadata_apply": "1"},
        )
        r2.COOKIES[settings.SESSION_COOKIE_NAME] = session_key
        SessionMiddleware(_noop_response).process_request(r2)
        r2.user = self.user
        r2.school = self.school
        setattr(r2, "_messages", FallbackStorage(r2))

        with patch(
            "apps.packages.engine.PackageEngine.apply_package",
            return_value={"ok": True},
        ) as mock_apply:
            resp = template_gallery_page(r2)
        self.assertEqual(resp.status_code, 302)
        site.apply_theme_pack.assert_called_once()
        mock_apply.assert_called_once()
        self.assertNotIn("template_gallery_impact_gate", r2.session)
