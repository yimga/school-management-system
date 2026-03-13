import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.siteconfig.forms import ThemeColorsForm
from apps.siteconfig.models import SiteSettings


User = get_user_model()


class StudioExperienceRollbackTests(TestCase):
    def setUp(self):
        self.theme_url = reverse("siteconfig:theme_colors")
        self.studio_url = reverse("studio_os:experience")
        self.rollback_url = reverse("studio_os:rollback") + "?mode=experience"

        self.user = User.objects.create_user(
            username="studio-rollback-user",
            email="studio-rollback-user@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def _theme_form_payload(self, **overrides):
        site = SiteSettings.get_solo()
        payload = {}
        form = ThemeColorsForm(instance=site)
        for field_name in ThemeColorsForm.Meta.fields:
            value = form.initial.get(field_name, getattr(site, field_name, ""))
            if hasattr(value, "pk"):
                value = value.pk
            if isinstance(value, bool):
                if value:
                    payload[field_name] = "on"
                continue
            if isinstance(value, (dict, list)):
                payload[field_name] = json.dumps(value)
            elif value in (None, ""):
                payload[field_name] = ""
            else:
                payload[field_name] = str(value)

        payload.update(overrides)
        for field_name, value in list(payload.items()):
            if value is False:
                payload.pop(field_name, None)
        return payload

    def test_experience_rollback_reverts_last_saved_theme_state(self):
        site = SiteSettings.get_solo()
        original_primary = site.primary_color

        self.client.login(username=self.user.username, password="password")

        response = self.client.post(
            self.theme_url,
            self._theme_form_payload(primary_color="#1e3a8a", preview_confirmed="1"),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        site.refresh_from_db()
        self.assertEqual(site.primary_color, "#1e3a8a")

        session = self.client.session
        self.assertIn("theme_previous_state", session)
        previous = session.get("theme_previous_state") or {}
        self.assertIsInstance(previous, dict)
        self.assertIsInstance(previous.get("values"), dict)
        self.assertEqual(previous["values"].get("primary_color"), original_primary)

        response = self.client.post(self.rollback_url, follow=True)
        self.assertEqual(response.status_code, 200)

        site.refresh_from_db()
        self.assertEqual(site.primary_color, original_primary)
        self.assertNotIn("theme_previous_state", self.client.session)

