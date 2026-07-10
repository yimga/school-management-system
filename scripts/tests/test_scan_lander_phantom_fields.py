"""Unit tests for scripts/scan_lander_phantom_fields.py (stdlib, no Django).

Locks the phantom-field gate's core semantics so the silent-data-loss seal
cannot rot: phantom direct-kwarg detection, defaults-literal-key detection, the
filter_to_model_fields sanitizer passthrough, **kwargs / variable-defaults
opacity, FK ``_id`` acceptance, the allow-marker, and leftmost-name resolution
through a ``.filter(...)`` chain. A calibration test parses the LIVE model
sources so the hardcoded backstop can never silently drift from the real models.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_lander_phantom_fields as m  # noqa: E402


# Synthetic field maps — the scan() layer is model-source-agnostic.
_FIELDS = {
    "DynamicFieldValue": {"entity_type", "entity_id", "field_key", "value_json", "school", "id", "pk"},
    "DynamicFieldDefinition": {"entity_type", "field_key", "label", "data_type", "school", "id", "pk"},
    "StudentProfile": {"first_name", "last_name", "status", "school", "admission_number", "id", "pk"},
}


class ScanTempTreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_root, self._old_dir = m.ROOT, m.LANDERS_DIR
        m.ROOT = self.root
        m.LANDERS_DIR = self.root / "apps" / "migration_cloud" / "landers"
        m.LANDERS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        m.ROOT, m.LANDERS_DIR = self._old_root, self._old_dir
        self._tmp.cleanup()

    def _write(self, name: str, text: str) -> None:
        (m.LANDERS_DIR / name).write_text(text, encoding="utf-8")

    def _scan(self):
        return m.scan(model_fields=_FIELDS)

    def test_flags_phantom_direct_kwargs(self):
        self._write(
            "a.py",
            "def f():\n"
            "    DynamicFieldValue.objects.create(definition=d, object_id=o, value=v)\n",
        )
        kwargs = sorted(f["kwarg"] for f in self._scan())
        self.assertEqual(kwargs, ["definition", "object_id", "value"])

    def test_real_fields_pass(self):
        self._write(
            "b.py",
            "def f():\n"
            "    DynamicFieldValue.objects.update_or_create(\n"
            "        entity_type='x', entity_id='y', field_key='k',\n"
            "        defaults={'value_json': {'v': 1}, 'school': s})\n",
        )
        self.assertEqual(self._scan(), [])

    def test_defaults_via_filter_to_model_fields_is_safe(self):
        self._write(
            "c.py",
            "def f():\n"
            "    DynamicFieldValue.objects.update_or_create(\n"
            "        entity_type='x', entity_id='y', field_key='k',\n"
            "        defaults=filter_to_model_fields({'bogus': 1, 'school': s}, DynamicFieldValue))\n",
        )
        self.assertEqual(self._scan(), [])

    def test_defaults_literal_phantom_key_flagged(self):
        self._write(
            "d.py",
            "def f():\n"
            "    DynamicFieldDefinition.objects.get_or_create(\n"
            "        field_key='k', school=s, defaults={'label': 'L', 'entity_kind': 'student'})\n",
        )
        findings = self._scan()
        self.assertEqual([f["kwarg"] for f in findings], ["entity_kind"])

    def test_allow_marker_suppresses(self):
        self._write(
            "e.py",
            "def f():\n"
            "    # lander-phantom-allow: legacy-column-reviewed\n"
            "    DynamicFieldValue.objects.create(definition=d)\n",
        )
        self.assertEqual(self._scan(), [])

    def test_double_star_and_variable_defaults_opaque(self):
        self._write(
            "f.py",
            "def f():\n"
            "    DynamicFieldValue.objects.update_or_create(defaults=payload, **lookup)\n",
        )
        self.assertEqual(self._scan(), [])

    def test_fk_id_form_accepted(self):
        self._write(
            "g.py",
            "def f():\n"
            "    StudentProfile.objects.create(first_name='A', school_id=1)\n",
        )
        self.assertEqual(self._scan(), [])

    def test_untracked_model_ignored(self):
        self._write(
            "h.py",
            "def f():\n"
            "    Widget.objects.create(bogus=1, whatever=2)\n",
        )
        self.assertEqual(self._scan(), [])

    def test_leftmost_name_through_filter_chain(self):
        self._write(
            "i.py",
            "def f():\n"
            "    StudentProfile.objects.filter(school=s).update_or_create(\n"
            "        enrollment_status='graduated', defaults={})\n",
        )
        findings = self._scan()
        self.assertEqual([(f["model"], f["kwarg"]) for f in findings],
                         [("StudentProfile", "enrollment_status")])


class LiveModelSourceCalibrationTest(unittest.TestCase):
    """Runs against the REAL model sources (no monkeypatch) so the hardcoded
    backstop and the AST parser can never silently drift from the models."""

    def test_real_fields_present_phantoms_absent(self):
        fields = m._resolve_fields()
        self.assertIn("value_json", fields["DynamicFieldValue"])
        self.assertIn("entity_id", fields["DynamicFieldValue"])
        self.assertNotIn("definition", fields["DynamicFieldValue"])
        self.assertNotIn("object_id", fields["DynamicFieldValue"])
        self.assertIn("incident_type", fields["Incident"])
        self.assertNotIn("type", fields["Incident"])
        self.assertNotIn("external_ref", fields["Incident"])
        self.assertIn("status", fields["StudentProfile"])
        self.assertNotIn("enrollment_status", fields["StudentProfile"])

    def test_source_parser_finds_fields(self):
        # AST layer alone (independent of the hardcoded backstop) sees them.
        dfv = m._fields_from_source("DynamicFieldValue")
        self.assertIn("value_json", dfv)
        self.assertIn("school", dfv)


class LiveTreeIsCleanTest(unittest.TestCase):
    def test_repo_landers_have_zero_phantom_writes(self):
        self.assertEqual(m.scan(), [])


if __name__ == "__main__":
    unittest.main()
