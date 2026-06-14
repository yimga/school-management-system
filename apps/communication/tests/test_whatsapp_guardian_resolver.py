"""Backlog fix (2026-06-10) — WhatsApp parent resolver uses the real model.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

The repo-wide audit flagged apps/communication/whatsapp_parent_os_resolvers.py
importing a non-existent ``people.Guardian`` (and the verify command the same).
The import sat in a broad try/except returning None, so _find_guardian ALWAYS
returned None — WhatsApp parent phone lookup silently never matched, and the
verify command always raised CommandError.

Fixed to the real ``people.StudentGuardian`` (which has no direct school FK — it
is tenant-scoped through ``student__school``), added the real ``whatsapp_number``
field to the phone-field probe, and guarded the UUID school filter so a malformed
tenant_id yields a clean miss instead of a ValidationError.
"""

from __future__ import annotations

import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class WhatsAppGuardianResolverTests(unittest.TestCase):

    def _src(self, rel: str) -> str:
        return (REPO / rel).read_text(encoding="utf-8", errors="replace")

    def test_resolver_uses_student_guardian(self) -> None:
        src = self._src("apps/communication/whatsapp_parent_os_resolvers.py")
        self.assertIn("import StudentGuardian", src)
        self.assertNotIn("import Guardian  # type: ignore", src)
        self.assertIn("StudentGuardian.objects.all()", src)
        # bare-Guardian ORM use gone (allow the StudentGuardian.* substring)
        self.assertNotIn(" Guardian.objects", src)
        # Tenant scope goes through the student (StudentGuardian has no school FK).
        self.assertIn("student__school_id=tenant_id", src)
        # The real WhatsApp field is now probed.
        self.assertIn("whatsapp_number", src)

    def test_verify_command_uses_student_guardian(self) -> None:
        src = self._src(
            "apps/communication/management/commands/verify_whatsapp_parent_os_resolver.py"
        )
        self.assertIn("import StudentGuardian", src)
        self.assertIn("StudentGuardian.objects.filter(student__school=school)", src)
        self.assertNotIn("Guardian.objects.filter(school=school)", src)

    def test_student_guardian_has_the_referenced_fields(self) -> None:
        from apps.people.models import StudentGuardian

        names = {f.name for f in StudentGuardian._meta.get_fields()}
        self.assertIn("phone", names)
        self.assertIn("whatsapp_number", names)
        self.assertIn("student", names)
        # No direct school FK — the fix scopes via student__school.
        self.assertNotIn("school", names)


if __name__ == "__main__":
    unittest.main()
