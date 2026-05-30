"""v4.00.85 Wave 17 Target 3 — Multi-IdP SAML registry smoke.

Validates the new helpers in ``apps/api/saml.py``:

  1. Env unset -> resolve_multi_idp_record returns None
  2. Env set w/ exact entry -> match_type="exact" + matched_domain="school.edu"
  3. Env set w/ wildcard "*.staff.school.edu" -> matches
     "bob@hr.staff.school.edu" w/ match_type="wildcard_suffix"
  4. Email without "@" -> returns None
  5. multi_idp_registry_summary env unset -> configured=False, entries=0
  6. multi_idp_registry_summary env set -> configured=True + counts + samples
  7. Summary NEVER includes sso_url / cert_pem_b64
  8. Bad JSON env -> resolve returns None; summary returns
     {configured: False, error: ...}
  9. resolve_idp_target_for_email w/ registry set returns registry's sso_url
     (not the env _idp_sso_url)
 10. resolve_idp_target_for_email w/ multi-IdP unset but _hrd_mapping set
     -> falls back to HRD mapping behavior

Run:
    python scripts/smoke_v4_00_85_T3_multi_idp_registry.py
"""
from __future__ import annotations

import json
import os
import sys

# Ensure repo root is on sys.path when invoked from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Minimal Django settings hook — apps/api/saml.py imports django.conf.settings
# for env-var lookups, so Django needs to be at least minimally configured.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    django.setup()
except Exception:  # noqa: BLE001
    pass

from apps.api import saml as S  # noqa: E402


_ENV_KEYS = (
    "RMC_SAML_MULTI_IDP_REGISTRY",
    "RMC_SAML_HRD_MAPPING",
    "RMC_SAML_IDP_SSO_URL",
)


def _clear_env() -> None:
    for k in _ENV_KEYS:
        os.environ.pop(k, None)


def _check(label: str, ok: bool, *, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"  [{tag}] {label}{suffix}")
    return ok


def case_1_env_unset_returns_none() -> bool:
    _clear_env()
    out = S.resolve_multi_idp_record("alice@school.edu")
    return _check(
        "1. env unset -> resolve_multi_idp_record returns None",
        out is None,
        detail=f"got={out!r}",
    )


def case_2_exact_match() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "school.edu": {
            "label": "Acme Okta SSO",
            "sso_url": "https://acme.okta.com/app/sso",
            "entity_id": "https://acme.okta.com/exk123",
            "cert_pem_b64": "BASE64CERT",
        },
    })
    out = S.resolve_multi_idp_record("alice@school.edu")
    ok = (
        isinstance(out, dict)
        and out.get("match_type") == "exact"
        and out.get("matched_domain") == "school.edu"
        and out.get("sso_url") == "https://acme.okta.com/app/sso"
        and out.get("label") == "Acme Okta SSO"
    )
    return _check(
        "2. exact entry -> match_type=exact, matched_domain=school.edu",
        ok,
        detail=f"got={out!r}",
    )


def case_3_wildcard_suffix_match() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "*.staff.school.edu": {
            "label": "Staff Azure AD",
            "sso_url": "https://login.microsoftonline.com/tenant/saml2",
            "entity_id": "https://sts.windows.net/tenant/",
        },
    })
    out = S.resolve_multi_idp_record("bob@hr.staff.school.edu")
    ok = (
        isinstance(out, dict)
        and out.get("match_type") == "wildcard_suffix"
        and out.get("matched_domain") == "*.staff.school.edu"
        and out.get("sso_url") == "https://login.microsoftonline.com/tenant/saml2"
    )
    return _check(
        "3. wildcard *.staff.school.edu matches hr.staff.school.edu",
        ok,
        detail=f"got={out!r}",
    )


def case_4_email_without_at_returns_none() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "school.edu": {"sso_url": "https://x.example/sso"},
    })
    out_none = S.resolve_multi_idp_record("not-an-email")
    out_empty = S.resolve_multi_idp_record("")
    return _check(
        "4. email without @ -> returns None (both 'not-an-email' and '')",
        out_none is None and out_empty is None,
        detail=f"got_none={out_none!r}, got_empty={out_empty!r}",
    )


def case_5_summary_env_unset() -> bool:
    _clear_env()
    out = S.multi_idp_registry_summary()
    ok = (
        isinstance(out, dict)
        and out.get("configured") is False
        and out.get("entries") == 0
        and out.get("exact_domains") == []
        and out.get("wildcard_patterns") == []
    )
    return _check(
        "5. summary env unset -> configured=False, entries=0",
        ok,
        detail=f"got={out!r}",
    )


def case_6_summary_env_set() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "school.edu": {"sso_url": "https://a/sso"},
        "partner.edu": {"sso_url": "https://b/sso"},
        "*.staff.school.edu": {"sso_url": "https://c/sso"},
        "*.students.school.edu": {"sso_url": "https://d/sso"},
    })
    out = S.multi_idp_registry_summary()
    ok = (
        isinstance(out, dict)
        and out.get("configured") is True
        and out.get("entries") == 4
        and "school.edu" in (out.get("exact_domains") or [])
        and "partner.edu" in (out.get("exact_domains") or [])
        and "*.staff.school.edu" in (out.get("wildcard_patterns") or [])
        and "*.students.school.edu" in (out.get("wildcard_patterns") or [])
    )
    return _check(
        "6. summary env set -> configured=True + counts + samples",
        ok,
        detail=f"got={out!r}",
    )


def case_7_summary_does_not_leak_urls_or_certs() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "school.edu": {
            "sso_url": "https://SUPER_SECRET_OKTA_URL.example/SSO",
            "cert_pem_b64": "TOPSECRETCERTBASE64DATA",
            "entity_id": "https://acme.okta.com/exk_TENANT_ID",
        },
    })
    out = S.multi_idp_registry_summary()
    rendered = json.dumps(out)
    no_url_leak = "SUPER_SECRET_OKTA_URL" not in rendered
    no_cert_leak = "TOPSECRETCERTBASE64DATA" not in rendered
    no_eid_leak = "exk_TENANT_ID" not in rendered
    return _check(
        "7. summary NEVER includes sso_url / cert_pem_b64 / entity_id",
        no_url_leak and no_cert_leak and no_eid_leak,
        detail=f"rendered={rendered!r}",
    )


def case_8_bad_json_env() -> bool:
    _clear_env()
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = "{not-valid-json"
    rec = S.resolve_multi_idp_record("alice@school.edu")
    summary = S.multi_idp_registry_summary()
    ok_rec = rec is None
    ok_summary = (
        isinstance(summary, dict)
        and summary.get("configured") is False
        and "error" in summary
    )
    # Also check a JSON-but-not-dict shape.
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = '["a", "b"]'
    rec_list = S.resolve_multi_idp_record("alice@school.edu")
    summary_list = S.multi_idp_registry_summary()
    ok_rec_list = rec_list is None
    ok_summary_list = (
        isinstance(summary_list, dict)
        and summary_list.get("configured") is False
        and summary_list.get("error") == "registry_not_dict"
    )
    return _check(
        "8. bad JSON / non-dict JSON -> resolve None, summary {configured:False, error:...}",
        ok_rec and ok_summary and ok_rec_list and ok_summary_list,
        detail=(
            f"bad_json rec={rec!r} summary={summary!r}; "
            f"list rec={rec_list!r} summary={summary_list!r}"
        ),
    )


def case_9_resolve_idp_target_uses_registry() -> bool:
    _clear_env()
    os.environ["RMC_SAML_IDP_SSO_URL"] = "https://fallback.example/sso"
    os.environ["RMC_SAML_MULTI_IDP_REGISTRY"] = json.dumps({
        "school.edu": {
            "label": "Acme",
            "sso_url": "https://REGISTRY-WINS.example/sso",
        },
    })
    target = S.resolve_idp_target_for_email("alice@school.edu")
    return _check(
        "9. resolve_idp_target_for_email -> registry sso_url (not env fallback)",
        target == "https://REGISTRY-WINS.example/sso",
        detail=f"got={target!r}",
    )


def case_10_falls_back_to_hrd_mapping() -> bool:
    _clear_env()
    os.environ["RMC_SAML_IDP_SSO_URL"] = "https://fallback.example/sso"
    os.environ["RMC_SAML_HRD_MAPPING"] = json.dumps({
        "school.edu": "https://HRD-MAPPING-WINS.example/sso",
    })
    # Multi-IdP registry NOT set — should fall through to HRD mapping.
    target = S.resolve_idp_target_for_email("alice@school.edu")
    return _check(
        "10. multi-IdP unset, HRD mapping set -> HRD URL wins over env",
        target == "https://HRD-MAPPING-WINS.example/sso",
        detail=f"got={target!r}",
    )


def main() -> int:
    print("v4.00.85 Wave 17 Target 3 — Multi-IdP SAML registry smoke")
    print("=" * 64)
    cases = [
        case_1_env_unset_returns_none,
        case_2_exact_match,
        case_3_wildcard_suffix_match,
        case_4_email_without_at_returns_none,
        case_5_summary_env_unset,
        case_6_summary_env_set,
        case_7_summary_does_not_leak_urls_or_certs,
        case_8_bad_json_env,
        case_9_resolve_idp_target_uses_registry,
        case_10_falls_back_to_hrd_mapping,
    ]
    results = []
    for case in cases:
        try:
            results.append(case())
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {case.__name__} raised: {exc!r}")
            results.append(False)
        finally:
            _clear_env()
    passed = sum(1 for r in results if r)
    total = len(results)
    print("=" * 64)
    print(f"Result: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
