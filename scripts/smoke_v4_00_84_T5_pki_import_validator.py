"""v4.00.84 Wave 16 Target 5 smoke — PKI bundle import + validator.

Closes the round-trip: a bundle that was built by build_lms_pki_bundle()
and serialized via export_pki_bundle_json() can be re-imported, then
structurally + tamper-validated via validate_pki_bundle().

Note on case 10 — we adopted the STRICT contract for import_pki_bundle:
missing required top-level keys ("providers", "schema_version") raises
PKIBundleImportError. This matches the docstring on the implementation.
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django  # noqa: E402
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


def _line(s): print(s, flush=True)  # noqa: E702
def _ok(name): _line(f"  OK   {name}")  # noqa: E702
def _fail(name, detail):
    _line(f"  FAIL {name} :: {detail}"); sys.exit(1)


def run_t5():
    _line("\n[T5] PKI bundle import + validator")
    from apps.integrations_marketplace import lms_pki_bundle as mod

    # Case 1: build_lms_pki_bundle() -> dict.
    bundle = mod.build_lms_pki_bundle()
    if not isinstance(bundle, dict):
        _fail("t5-c1-build-dict", f"got {type(bundle)}")
    _ok("t5-c1 build_lms_pki_bundle() -> dict")

    # Case 2: export_pki_bundle_json(bundle) -> bytes.
    blob = mod.export_pki_bundle_json(bundle)
    if not isinstance(blob, bytes):
        _fail("t5-c2-export-bytes", f"got {type(blob)}")
    if not blob.startswith(b"{"):
        _fail("t5-c2-export-json-shape", f"got {blob[:40]!r}")
    _ok("t5-c2 export_pki_bundle_json() -> bytes (canonical JSON)")

    # Case 3: import_pki_bundle(bytes) round-trips — re-imported has the
    # SAME top-level keys + same provider count. (JSON dict ordering is
    # not defined, so we compare key sets / canonical forms.)
    re_imported = mod.import_pki_bundle(blob)
    if not isinstance(re_imported, dict):
        _fail("t5-c3-roundtrip-type", f"got {type(re_imported)}")
    if set(re_imported.keys()) != set(bundle.keys()):
        _fail("t5-c3-roundtrip-keys",
              f"orig={sorted(bundle.keys())} re={sorted(re_imported.keys())}")
    if len(re_imported.get("providers", [])) != len(bundle.get("providers", [])):
        _fail("t5-c3-roundtrip-provider-count",
              f"orig={len(bundle.get('providers', []))} "
              f"re={len(re_imported.get('providers', []))}")
    # Canonical-form equality (sort_keys is the round-trip oracle).
    if (json.dumps(re_imported, sort_keys=True, separators=(",", ":")) !=
            json.dumps(bundle, sort_keys=True, separators=(",", ":"))):
        _fail("t5-c3-canonical-equal",
              "canonical re-serialization differs across round-trip")
    _ok("t5-c3 import_pki_bundle(bytes) round-trips (canonical-equal)")

    # Case 4: validate_pki_bundle(re_imported)["ok"] == True.
    result = mod.validate_pki_bundle(re_imported)
    if not isinstance(result, dict):
        _fail("t5-c4-validate-type", f"got {type(result)}")
    if not result.get("ok"):
        _fail("t5-c4-validate-ok",
              f"ok=False issues={result.get('issues')}")
    if not result.get("fingerprint"):
        _fail("t5-c4-validate-fp", "empty fingerprint on valid bundle")
    _ok(f"t5-c4 validate_pki_bundle(re_imported) ok=True fp={result['fingerprint']}")

    # Case 5: Tamper case (label string change is structurally valid).
    # Mutating a valid label to ANOTHER valid label is still structurally
    # OK (validator only flags missing/blank labels), but the fingerprint
    # changes.
    original_fp = mod.bundle_fingerprint(re_imported)
    tampered = json.loads(json.dumps(re_imported))  # deep copy via JSON
    if tampered.get("providers"):
        # Pick first provider, swap its label to something else valid.
        old_label = tampered["providers"][0].get("label", "")
        tampered["providers"][0]["label"] = old_label + " (tampered)"
    tampered_fp = mod.bundle_fingerprint(tampered)
    if tampered_fp == original_fp:
        _fail("t5-c5-fp-unchanged",
              f"fingerprint did not change after tamper: {tampered_fp}")
    # Structurally still valid (labels remain non-empty strings).
    tampered_result = mod.validate_pki_bundle(tampered)
    if not tampered_result.get("ok"):
        _fail("t5-c5-tamper-structural",
              f"label-string change incorrectly flagged: "
              f"issues={tampered_result.get('issues')}")
    _ok("t5-c5 label string change -> structurally ok=True but fingerprint differs")

    # Case 6: Tamper case w/ expected_fingerprint — mutate then validate
    # against the ORIGINAL fingerprint -> ok=False and fingerprint_mismatch.
    pinned = mod.validate_pki_bundle(tampered, expected_fingerprint=original_fp)
    if pinned.get("ok"):
        _fail("t5-c6-pinned-ok",
              f"expected ok=False, got True; issues={pinned.get('issues')}")
    issues_joined = "|".join(pinned.get("issues", []))
    if "fingerprint_mismatch:" not in issues_joined:
        _fail("t5-c6-pinned-issue",
              f"expected fingerprint_mismatch: in issues; got {issues_joined}")
    _ok("t5-c6 expected_fingerprint pinning catches tamper (fingerprint_mismatch)")

    # Case 7: Empty input bytes -> PKIBundleImportError("bad_json:...").
    try:
        mod.import_pki_bundle(b"")
    except mod.PKIBundleImportError as exc:
        if "bad_json" not in str(exc):
            _fail("t5-c7-empty-msg", f"expected bad_json:, got {exc}")
        _ok(f"t5-c7 empty input raises PKIBundleImportError ({exc})")
    else:
        _fail("t5-c7-no-raise", "expected PKIBundleImportError on b''")

    # Case 8: Malformed JSON.
    try:
        mod.import_pki_bundle(b"{not json}")
    except mod.PKIBundleImportError as exc:
        if "bad_json" not in str(exc):
            _fail("t5-c8-malformed-msg",
                  f"expected bad_json:, got {exc}")
        _ok(f"t5-c8 malformed JSON raises PKIBundleImportError ({exc})")
    else:
        _fail("t5-c8-no-raise",
              "expected PKIBundleImportError on b'{not json}'")

    # Case 9: JSON that is a list, not a dict.
    try:
        mod.import_pki_bundle(b'[1,2,3]')
    except mod.PKIBundleImportError as exc:
        if "not_a_dict" not in str(exc):
            _fail("t5-c9-list-msg", f"expected not_a_dict, got {exc}")
        _ok(f"t5-c9 list-shaped JSON raises PKIBundleImportError ({exc})")
    else:
        _fail("t5-c9-no-raise",
              "expected PKIBundleImportError on list-shaped JSON")

    # Case 10: Missing required key — STRICT contract: raise.
    # Document choice in module header: missing_required_key:<name>.
    payload = b'{"schema_version":"v4.00.84"}'  # missing 'providers'
    try:
        mod.import_pki_bundle(payload)
    except mod.PKIBundleImportError as exc:
        if "missing_required_key:providers" not in str(exc):
            _fail("t5-c10-missing-msg",
                  f"expected missing_required_key:providers, got {exc}")
        _ok(f"t5-c10 missing required key raises PKIBundleImportError ({exc})")
    else:
        _fail("t5-c10-no-raise",
              "expected PKIBundleImportError on missing 'providers'")

    # Case 11: validate_pki_bundle({}) returns ok=False with multiple
    # missing_required_key: issues, NO exception.
    empty_result = mod.validate_pki_bundle({})
    if not isinstance(empty_result, dict):
        _fail("t5-c11-empty-type", f"got {type(empty_result)}")
    if empty_result.get("ok"):
        _fail("t5-c11-empty-ok",
              f"expected ok=False on empty dict, got ok=True; "
              f"issues={empty_result.get('issues')}")
    issues = empty_result.get("issues", [])
    missing_count = sum(1 for i in issues if i.startswith("missing_required_key:"))
    if missing_count < 2:
        _fail("t5-c11-empty-issues",
              f"expected >=2 missing_required_key: issues, got {issues}")
    _ok(f"t5-c11 validate_pki_bundle({{}}) ok=False, "
        f"{missing_count} missing_required_key: issues, no exception")


if __name__ == "__main__":
    run_t5()
    _line("\nAll T5 cases green.")
