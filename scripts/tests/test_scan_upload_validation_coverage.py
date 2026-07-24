"""Unit tests for scripts/scan_upload_validation_coverage.py (stdlib, no Django).

Locks the coverage ratchet's core semantics: a DIRECT ``request.FILES`` intake
(subscript / ``.get`` / ``.getlist``) without a validator is a finding; a
form-routed ``Form(request.POST, request.FILES)`` is NOT (the exclusion that
keeps the baseline honest); a validator call or an ``upload-validation-allow``
marker credits the site; and the live tree scans clean against its baseline.
"""

import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_upload_validation_coverage as m  # noqa: E402


def _scan_source(src: str) -> list[str]:
    """Run the scanner over a single temp module; return finding function names."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        apps = root / "apps" / "demo"
        apps.mkdir(parents=True)
        (apps / "views.py").write_text(src, encoding="utf-8")
        findings = m.scan(apps_dir=root / "apps", root=root)
    return [f["function"] for f in findings]


class DirectIntakeIsFlaggedTests(unittest.TestCase):
    def test_files_get_without_validator_is_flagged(self):
        src = "def v(request):\n    x = request.FILES.get('f')\n    x.save()\n"
        self.assertEqual(_scan_source(src), ["v"])

    def test_files_subscript_without_validator_is_flagged(self):
        src = "def v(request):\n    x = request.FILES['f']\n    x.save()\n"
        self.assertEqual(_scan_source(src), ["v"])

    def test_getlist_without_validator_is_flagged(self):
        src = "def v(request):\n    xs = request.FILES.getlist('a')\n    return xs\n"
        self.assertEqual(_scan_source(src), ["v"])


class NotFlaggedTests(unittest.TestCase):
    def test_form_routed_intake_is_not_flagged(self):
        # request.FILES passed as a bare arg to a form -> validation is the
        # form's job, a separate concern. Must NOT be a finding.
        src = "def v(request):\n    form = MyForm(request.POST, request.FILES)\n    return form.is_valid()\n"
        self.assertEqual(_scan_source(src), [])

    def test_validator_call_credits_the_site(self):
        src = (
            "def v(request):\n"
            "    x = request.FILES.get('f')\n"
            "    validate_uploaded_file(x, allowed_mimes=S, max_bytes=1)\n"
            "    x.save()\n"
        )
        self.assertEqual(_scan_source(src), [])

    def test_persist_helper_credits_the_site(self):
        src = (
            "def v(request):\n"
            "    logo = request.FILES.get('logo')\n"
            "    persist_school_brand_logo(school=s, uploaded_file=logo)\n"
        )
        self.assertEqual(_scan_source(src), [])

    def test_allow_marker_credits_the_site(self):
        src = (
            "def v(request):\n"
            "    x = request.FILES.get('f')  # upload-validation-allow: validated-downstream\n"
            "    x.save()\n"
        )
        self.assertEqual(_scan_source(src), [])

    def test_marker_in_string_literal_does_not_credit(self):
        # tokenize-based marker detection must ignore the phrase inside a string.
        src = (
            "def v(request):\n"
            "    note = 'upload-validation-allow: not a real marker'\n"
            "    x = request.FILES.get('f')\n"
            "    x.save()\n"
        )
        self.assertEqual(_scan_source(src), ["v"])

    def test_no_intake_is_not_flagged(self):
        src = "def v(request):\n    return request.POST.get('x')\n"
        self.assertEqual(_scan_source(src), [])


class LiveTreeCalibrationTests(unittest.TestCase):
    def test_live_tree_scans_clean_against_baseline(self):
        current = Counter(m._key(f) for f in m.scan())
        baseline = Counter(m._key(f) for f in m._load_baseline())
        new = current - baseline
        self.assertEqual(dict(new), {}, f"new unvalidated intake vs baseline: {new}")

    def test_baseline_file_exists_and_matches_count(self):
        baseline = m._load_baseline()
        self.assertTrue(baseline, "baseline must be populated")
        # The documented/JSON count must equal len(findings) in the file.
        import json

        data = json.loads(m.BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(data["finding_count"], len(data["findings"]))


if __name__ == "__main__":
    unittest.main()
