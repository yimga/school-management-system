import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.siteconfig.forms import ThemeColorsForm
from apps.platform_runtime.helpers import get_platform_site_settings_record


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
        site = get_platform_site_settings_record(create=True)
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
        """
        Rollback must persist on the real tenant site-settings row (see studio_rollback).
        We set session snapshot explicitly so the test does not depend on theme POST
        baseline caching quirks vs get_effective_site_settings.
        """
        site = get_platform_site_settings_record(create=True)
        prior = "#0d6efd"
        # Phase B: primary_color is persisted via RuntimeDefaults.payload (not a concrete tenant settings column).
        site.apply_theme_experience_state(
            field_updates={"primary_color": prior}, save=True
        )
        cache.clear()

        self.client.login(username=self.user.username, password="password")
        session = self.client.session
        session["theme_previous_state"] = {
            "values": {"primary_color": prior},
            "actor": "test",
            "timestamp": "fixture",
        }
        session.save()

        site.apply_theme_experience_state(
            field_updates={"primary_color": "#1e3a8a"}, save=True
        )

        response = self.client.post(self.rollback_url, follow=True)
        self.assertEqual(response.status_code, 200)

        cache.clear()
        site = get_platform_site_settings_record(create=False)
        self.assertEqual(site.primary_color, prior)
        self.assertNotIn("theme_previous_state", self.client.session)
