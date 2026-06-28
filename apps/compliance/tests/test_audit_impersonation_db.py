"""DB-backed verification for AuditLog operator-impersonation provenance (Wave C #4
Phase 2). Complements the no-DB mock tests: those prove the signal passes the right
kwargs; these prove the migration-0023 schema accepts + persists + indexes them in a
real database, and that append-only still holds with the new columns.

Runs in CI (Postgres) and locally via the fast no-migration test settings.
"""

from __future__ import annotations

from django.test import TestCase

from apps.compliance.models_audit import AuditLog


class AuditLogImpersonationSchemaDBTests(TestCase):
    def test_impersonation_fields_persist_and_default(self):
        # Default (non-impersonation) row.
        plain = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name="Invoice",
            object_id="1",
            app_label="finance",
        )
        plain.refresh_from_db()
        self.assertFalse(plain.during_impersonation)
        self.assertEqual(plain.impersonated_school_id, "")

        # Impersonation-stamped row.
        stamped = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name="Invoice",
            object_id="2",
            app_label="finance",
            user_id=None,
            during_impersonation=True,
            impersonated_school_id="school-abc",
        )
        stamped.refresh_from_db()
        self.assertTrue(stamped.during_impersonation)
        self.assertEqual(stamped.impersonated_school_id, "school-abc")

    def test_during_impersonation_is_queryable(self):
        AuditLog.objects.create(
            action=AuditLog.Action.CREATE, model_name="X", object_id="1",
            app_label="x", during_impersonation=True, impersonated_school_id="s1",
        )
        AuditLog.objects.create(
            action=AuditLog.Action.CREATE, model_name="X", object_id="2", app_label="x",
        )
        # The forensic query: "what did operators do while impersonating?"
        imp = AuditLog.objects.filter(during_impersonation=True)
        self.assertEqual(imp.count(), 1)
        self.assertEqual(imp.first().impersonated_school_id, "s1")

    def test_append_only_delete_still_blocked_with_new_fields(self):
        from apps.platform_runtime.append_only import AppendOnlyDeleteError

        row = AuditLog.objects.create(
            action=AuditLog.Action.CREATE, model_name="X", object_id="1",
            app_label="x", during_impersonation=True, impersonated_school_id="s1",
        )
        # AuditLog's append-only contract blocks DELETE (instance + queryset), not
        # update — confirm the new fields don't weaken it.
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()
        with self.assertRaises(AppendOnlyDeleteError):
            AuditLog.objects.filter(pk=row.pk).delete()
