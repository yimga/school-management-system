"""Code index must not return lines for student-facing misuse (batch 1335)."""

from django.test import SimpleTestCase

from services.ai.code_index import search_code_index


class CodeIndexRoleFenceTests(SimpleTestCase):
    def test_search_returns_list(self):
        lines = search_code_index("support_stream deflection", limit=2, visibility="staff")
        self.assertIsInstance(lines, list)

    def test_staff_visibility_skips_operator_only_paths(self):
        lines = search_code_index("migration_cloud operator super", limit=8, visibility="staff")
        joined = " ".join(lines).lower()
        self.assertNotIn("migration_cloud", joined)
