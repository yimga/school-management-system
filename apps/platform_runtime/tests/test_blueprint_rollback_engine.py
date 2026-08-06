from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation, PlatformEventLog
from apps.schools.models import School


class BlueprintRollbackEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollback School",
            slug="rollback-school",
            subdomain="rollback-school",
            is_active=True,
            settings={"original": "kept"},
        )
        self.actor = User.objects.create_user(
            username="blueprint_rollback_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )
        applied = apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="rollback-target",
        )
        self.installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])

    def test_rollback_requires_existing_installation_and_confirmation(self):
        self.assertFalse(
            rollback_blueprint_installation(
                self.installation,
                actor=self.actor,
                confirmed=False,
            )["ok"]
        )

    def test_rollback_audits_and_updates_status(self):
        result = rollback_blueprint_installation(
            self.installation,
            actor=self.actor,
            confirmed=True,
        )

        self.assertTrue(result["ok"], msg=result)
        self.installation.refresh_from_db()
        self.school.refresh_from_db()
        self.assertEqual(self.installation.status, BlueprintInstallation.Status.ROLLED_BACK)
        self.assertEqual(self.school.settings, {"original": "kept"})
        self.assertIn("offline_manifest_invalidation", result)
        self.assertIn("offline_manifest_invalidation", result["reverted_changes"])
        self.assertTrue(
            PlatformEventLog.objects.filter(
                event_type="blueprint_rolled_back",
                tenant_id=str(self.school.pk),
            ).exists()
        )

    def test_rollback_does_not_delete_unsafe_school_data(self):
        self.school.features = {"critical": True}
        self.school.save(update_fields=["features"])

        rollback_blueprint_installation(self.installation, actor=self.actor, confirmed=True)
        self.school.refresh_from_db()

        self.assertEqual(self.school.features, {"critical": True})

    def test_rollback_preserves_other_blueprints_settings_markers(self):
        """Cross-blueprint data-loss guard: rolling back one blueprint must not
        wipe a second, still-installed blueprint's settings markers.

        The previous rollback restored ``school.settings`` wholesale from the
        pre-apply snapshot, which erased any marker a LATER blueprint had added.
        The surgical rollback removes only the target blueprint's own markers.
        """
        self.school.refresh_from_db()
        settings = dict(self.school.settings or {})
        settings.setdefault("blueprint_marketplace", {})["other-blueprint"] = {
            "status": "applied"
        }
        settings.setdefault("local_first_blueprints", {})["other-blueprint"] = {
            "status": "applied"
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings"])

        result = rollback_blueprint_installation(
            self.installation, actor=self.actor, confirmed=True
        )
        self.assertTrue(result["ok"], msg=result)
        self.school.refresh_from_db()

        # The other blueprint's markers survive the rollback of THIS blueprint.
        self.assertEqual(
            self.school.settings.get("blueprint_marketplace", {}).get("other-blueprint"),
            {"status": "applied"},
        )
        self.assertEqual(
            self.school.settings.get("local_first_blueprints", {}).get("other-blueprint"),
            {"status": "applied"},
        )
        # The target blueprint's own markers are gone.
        self.assertNotIn(
            self.installation.blueprint_key,
            self.school.settings.get("blueprint_marketplace", {}),
        )
        # Tenant's own pre-existing setting is untouched.
        self.assertEqual(self.school.settings.get("original"), "kept")

    def test_rollback_respects_tenant_isolation(self):
        other = School.objects.create(
            name="Rollback Other",
            slug="rollback-other",
            subdomain="rollback-other",
            is_active=True,
            settings={"other": "kept"},
        )

        rollback_blueprint_installation(self.installation, actor=self.actor, confirmed=True)
        other.refresh_from_db()

        self.assertEqual(other.settings, {"other": "kept"})


class BlueprintRollbackModuleBridgeTests(TestCase):
    """Apply switches modules on in ``School.features``; rollback must switch them back.

    ``apply_blueprint`` runs the module bridge (``enable_blueprint_modules``) and
    persists ``School.features``. Rollback restored only ``School.settings``, so a
    rolled-back blueprint left its modules enabled forever — a state that is neither
    pre-apply nor post-apply, and an entitlement leak once ``entitled_codes`` gating
    is enforced on paid modules.

    The inverse has to be *surgical*, not a wholesale snapshot restore: features the
    tenant set independently after the apply must survive (see
    ``test_rollback_preserves_features_the_blueprint_never_touched``).
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Module Rollback School",
            slug="module-rollback-school",
            subdomain="module-rollback-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="module_rollback_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def _apply_boarding(self):
        applied = apply_blueprint(
            "boarding-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="module-rollback-target",
        )
        self.assertTrue(applied["ok"], msg=applied)
        return BlueprintInstallation.objects.get(pk=applied["installation_id"])

    def test_apply_enables_the_blueprints_modules(self):
        self._apply_boarding()
        self.school.refresh_from_db()

        self.assertTrue(self.school.features.get("dormitory"))
        self.assertTrue(self.school.features.get("parent_chat"))

    def test_rollback_disables_modules_the_blueprint_enabled(self):
        installation = self._apply_boarding()

        result = rollback_blueprint_installation(
            installation, actor=self.actor, confirmed=True
        )
        self.school.refresh_from_db()

        self.assertTrue(result["ok"], msg=result)
        self.assertFalse(self.school.features.get("dormitory"))
        self.assertFalse(self.school.features.get("parent_chat"))
        self.assertIn("school.features", result["reverted_changes"])

    def test_rollback_preserves_features_the_blueprint_never_touched(self):
        installation = self._apply_boarding()
        self.school.refresh_from_db()
        features = dict(self.school.features or {})
        features["critical"] = True
        self.school.features = features
        self.school.save(update_fields=["features"])

        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)
        self.school.refresh_from_db()

        self.assertTrue(self.school.features.get("critical"))

    def test_rollback_keeps_a_module_the_tenant_had_on_before_apply(self):
        """Pre-existing state is restored, not blanket-disabled."""
        self.school.features = {"dormitory": True}
        self.school.save(update_fields=["features"])
        installation = self._apply_boarding()

        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)
        self.school.refresh_from_db()

        # dormitory was on before the blueprint, so rollback must leave it on;
        # parent_chat was switched on by the blueprint, so it goes back off.
        self.assertTrue(self.school.features.get("dormitory"))
        self.assertFalse(self.school.features.get("parent_chat"))
