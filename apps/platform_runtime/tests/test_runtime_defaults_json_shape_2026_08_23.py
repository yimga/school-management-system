"""RuntimeDefaults' container-shaped JSONFields must reject the wrong container.

``require_mfa_roles`` is an editable JSONField on the id=1 platform singleton with
no validators and no ``clean()``. Django's forms.JSONField validates JSON SYNTAX,
not container shape, so ``7`` and ``"ADMIN,FINANCE"`` both saved from the platform
admin — and the value reaches every tenant.

Downstream, ``apps.accounts.middleware`` does
``effective_required_roles(required_roles, ...)`` inside a block whose ``except
(ImportError, AttributeError, TypeError, ValueError): pass`` swallows the
TypeError that a non-iterable raises. The whole MFA enforcement block is then
skipped, silently, for every non-staff user on every tenant.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsJsonShapeTests(TestCase):
    def _defaults(self, **kwargs) -> RuntimeDefaults:
        obj = RuntimeDefaults.objects.filter(pk=1).first() or RuntimeDefaults(pk=1)
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj

    def test_scalar_require_mfa_roles_is_rejected(self):
        obj = self._defaults(require_mfa_roles=7)
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("require_mfa_roles", ctx.exception.error_dict)

    def test_string_require_mfa_roles_is_rejected(self):
        """A comma-joined string is the natural operator typo; it iterates chars."""
        obj = self._defaults(require_mfa_roles="ADMIN,FINANCE")
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("require_mfa_roles", ctx.exception.error_dict)

    def test_map_shaped_field_rejects_a_list(self):
        obj = self._defaults(backend_feature_flags=["enable_api_center"])
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("backend_feature_flags", ctx.exception.error_dict)

    def test_list_shaped_notification_channels_rejects_a_map(self):
        obj = self._defaults(notification_channels={"email": True})
        with self.assertRaises(ValidationError) as ctx:
            obj.full_clean()
        self.assertIn("notification_channels", ctx.exception.error_dict)

    def test_valid_shapes_and_blanks_still_pass(self):
        """Vacuity guard: the validator must not simply reject everything."""
        obj = self._defaults(
            require_mfa_roles=["ADMIN", "FINANCE"],
            notification_channels=["email", "sms"],
            backend_feature_flags={"enable_api_center": True},
            portal_features={"enable_parent_portal": True},
            default_widgets_per_role={"ADMIN": ["kpi"]},
        )
        obj.full_clean()  # must not raise
        obj = self._defaults(
            require_mfa_roles=None,
            notification_channels=[],
            backend_feature_flags=None,
            portal_features={},
            default_widgets_per_role=None,
        )
        obj.full_clean()  # blank/None means "no platform default"

    def test_platform_admin_form_rejects_the_bad_shape(self):
        """The surface an operator actually types into.

        ``clean()`` only helps if the admin ModelForm surfaces it: Django's
        ``_post_clean`` runs ``full_clean(exclude=...)``, and an error keyed on a
        field the form does not render would be dropped or blow up instead of
        being shown.
        """
        from apps.platform_runtime.admin import RuntimeDefaultsBrandForm

        instance = RuntimeDefaults.objects.filter(pk=1).first() or RuntimeDefaults(pk=1)
        form = RuntimeDefaultsBrandForm(
            data={"require_mfa_roles": '"ADMIN,FINANCE"'}, instance=instance
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "require_mfa_roles",
            form.errors,
            f"the shape error never reached the operator: {form.errors.as_json()}",
        )

    def test_platform_admin_form_accepts_a_real_list(self):
        """Vacuity guard on the form test: a good value must still save."""
        from apps.platform_runtime.admin import RuntimeDefaultsBrandForm

        instance = RuntimeDefaults.objects.filter(pk=1).first() or RuntimeDefaults(pk=1)
        form = RuntimeDefaultsBrandForm(
            data={"require_mfa_roles": '["ADMIN", "FINANCE"]'}, instance=instance
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data["require_mfa_roles"], ["ADMIN", "FINANCE"])

    def test_bad_shape_really_does_break_the_mfa_role_computation(self):
        """Pins the consequence, so the validator above is not merely cosmetic."""
        from apps.accounts.mfa_defaults import effective_required_roles

        with self.assertRaises(TypeError):
            effective_required_roles(7)
        # And the string case does not raise — it iterates CHARACTERS, so the
        # operator's configured roles silently never match. REGISTRAR/NURSE are
        # deliberately NOT in BASELINE_REQUIRED_ROLES, so their absence is
        # attributable to the char iteration and nothing else.
        resolved = effective_required_roles("REGISTRAR,NURSE")
        self.assertNotIn("REGISTRAR", resolved)
        self.assertNotIn("NURSE", resolved)
        self.assertIn("R", resolved, "the value was iterated character by character")
