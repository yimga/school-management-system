"""
Compliance AuditLog rows for SchoolMembership lifecycle (enterprise permission trail).

**Run (fast, isolated file-backed sqlite):** from repo root, reuse a migrated DB::

    DJANGO_TEST_DB_FILE=.django_test_dbs/membership_audit_verify.sqlite3 \\
      python manage.py test apps.schools.tests.test_membership_enterprise_audit \\
      --settings=config.settings --keepdb

**First-time or clean-slate DB:** remove ``.django_test_dbs/membership_audit_verify.sqlite3``,
then run the same command *without* ``--keepdb`` and wait for full migrations (many minutes).
Copying an already-migrated ``default.sqlite3`` to that path is a valid bootstrap on a dev machine.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School, SchoolMembership


class SchoolMembershipEnterpriseAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mem_audit_u",
            password="x",
        )
        self.school = School.objects.create(
            name="Mem Audit School",
            slug="mem-audit-school",
            subdomain="memaudit",
            country_code="US",
            is_active=True,
        )

    def test_create_logs_permission_grant(self):
        m = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
        )
        row = AuditLog.objects.filter(
            model_name="SchoolMembership",
            object_id=str(m.pk),
            action=AuditLog.Action.PERMISSION_GRANT,
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.new_values.get("role"), User.Role.ADMIN)

    def test_role_change_logs_update(self):
        m = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
        )
        m.role = User.Role.TEACHER
        m.save()
        row = AuditLog.objects.filter(
            model_name="SchoolMembership",
            object_id=str(m.pk),
            action=AuditLog.Action.UPDATE,
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.old_values.get("role"), User.Role.ADMIN)
        self.assertEqual(row.new_values.get("role"), User.Role.TEACHER)

    def test_delete_logs_permission_revoke(self):
        m = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
        )
        pk = m.pk
        m.delete()
        row = AuditLog.objects.filter(
            model_name="SchoolMembership",
            object_id=str(pk),
            action=AuditLog.Action.PERMISSION_REVOKE,
        ).first()
        self.assertIsNotNone(row)
