"""v4.00.65 — RequestFactory + pure-function smoke across the 5 wave targets.

T1: +14 Tier-1 subdivisions (JP-02/44/39, CN-QH/NX/GZ, KR-42/43/44/47/48,
    RU-MOW, ZA-KZN, BR-RS); SOT >= 440.
T2: SAML metadata endpoint enriched — validUntil + cacheDuration,
    AuthnRequestsSigned reflects RMC_SAML_SP_SIGN_LOGOUT, dual SLS bindings
    (HTTP-Redirect + HTTP-POST), optional Organization/ContactPerson,
    `.xml/` alias route, ?format=json shape.
T3: SAML ACS POST-binding assertion-level signature requirement —
    _parse_saml_response surfaces signature_present_response +
    signature_present_assertion; RMC_SAML_REQUIRE_ASSERTION_SIGNATURE=1
    rejects responses where only the outer wrapper carries <Signature>.
T4: OneRoster ?sort=/?orderBy= per Roster Service spec § 4.13 + Demographics
    sex enum validation (male/female/other; 400 bad_sex_enum otherwise).
T5: Diagnostics retention dry-run preview HTML dashboard — default HTML;
    ?format=json preserved.

Exits 0 on full pass; non-zero on first failure.
"""
from __future__ import annotations

import json as _json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402


def _line(s):  # noqa: ANN001
    print(s, flush=True)


def _ok(name):  # noqa: ANN001
    _line(f"  OK   {name}")


def _fail(name, detail):  # noqa: ANN001
    _line(f"  FAIL {name} :: {detail}")
    sys.exit(1)


def _staff_user():
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username="smoke-v4-00-65-staff",
        defaults={"email": "smoke@v4-00-65.local", "is_staff": True, "is_active": True},
    )
    if not u.is_staff:
        u.is_staff = True
        u.save()
    return u


def run_t1():
    _line("\n[T1] +14 Tier-1 subdivisions")
    from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
    new_keys = [
        "JP-02", "JP-44", "JP-39",
        "CN-QH", "CN-NX", "CN-GZ",
        "KR-42", "KR-43", "KR-44", "KR-47", "KR-48",
        "RU-MOW", "ZA-KZN", "BR-RS",
    ]
    for k in new_keys:
        e = COUNTRY_LOCALIZATION.get(k)
        if not isinstance(e, dict):
            _fail(f"t1-present-{k}", f"missing or non-dict: {type(e).__name__}")
        for r in ("calendar_system", "school_types", "education_levels", "terminology"):
            if r not in e:
                _fail(f"t1-shape-{k}-{r}", f"missing {r}")
        if not isinstance(e["school_types"], list) or len(e["school_types"]) < 4:
            _fail(f"t1-school-types-{k}", "need >= 4")
        if not isinstance(e["education_levels"], list) or len(e["education_levels"]) < 3:
            _fail(f"t1-education-levels-{k}", "need >= 3")
        _ok(f"t1-{k} OK ({len(e['school_types'])} types, {len(e['education_levels'])} levels)")
    if len(COUNTRY_LOCALIZATION) < 440:
        _fail("t1-sot-count", f"expected >= 440, got {len(COUNTRY_LOCALIZATION)}")
    _ok(f"t1-sot-count {len(COUNTRY_LOCALIZATION)} entries")


def run_t2():
    _line("\n[T2] SAML metadata endpoint enriched + .xml/ alias")
    from apps.api import saml as saml_mod
    rf = RequestFactory()

    # Default XML response.
    req = rf.get("/sso/saml/metadata/")
    resp = saml_mod.metadata(req)
    if resp.status_code != 200:
        _fail("t2-xml-status", f"got {resp.status_code}")
    body = resp.content.decode("utf-8")
    for required in (
        "<md:EntityDescriptor",
        'validUntil="',
        'cacheDuration="PT',
        'AuthnRequestsSigned="false"',  # default flag OFF
        'WantAssertionsSigned="',
        '<md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"',
        '<md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"',
        "/sso/saml/sls/",
        "/sso/saml/sls/idp/",
        "/sso/saml/slo/callback/",
        "/sso/saml/acs/",
        "nameid-format:emailAddress",
        "nameid-format:persistent",
        "nameid-format:transient",
        "<md:Organization>",
        "RunMyCampus",
    ):
        if required not in body:
            _fail(f"t2-xml-missing-{required[:30]}", f"absent from metadata body")
    if resp["Content-Type"] != "application/samlmetadata+xml; charset=utf-8":
        _fail("t2-content-type", resp["Content-Type"])
    _ok(f"t2-xml validUntil + cacheDuration + dual SLS bindings + Org + 3 NameIDFormats present ({len(body)} bytes)")

    # AuthnRequestsSigned reflects RMC_SAML_SP_SIGN_LOGOUT.
    os.environ["RMC_SAML_SP_SIGN_LOGOUT"] = "1"
    try:
        req = rf.get("/sso/saml/metadata/")
        resp = saml_mod.metadata(req)
        body = resp.content.decode("utf-8")
        if 'AuthnRequestsSigned="true"' not in body:
            _fail("t2-ars-flag-on", "expected AuthnRequestsSigned=true with SP_SIGN_LOGOUT=1")
        _ok("t2-AuthnRequestsSigned reflects RMC_SAML_SP_SIGN_LOGOUT=1")
    finally:
        os.environ.pop("RMC_SAML_SP_SIGN_LOGOUT", None)

    # JSON shape.
    req = rf.get("/sso/saml/metadata/?format=json")
    resp = saml_mod.metadata(req)
    if resp.status_code != 200:
        _fail("t2-json-status", f"got {resp.status_code}")
    body_json = _json.loads(resp.content)
    for k in ("entity_id", "base_url", "valid_until", "cache_duration",
              "authn_requests_signed", "want_assertions_signed", "cert_present",
              "acs_url", "sls_urls", "slo_callback_url",
              "organization_name", "organization_url", "contact_email"):
        if k not in body_json:
            _fail(f"t2-json-missing-{k}", f"got keys {sorted(body_json.keys())}")
    if body_json["sls_urls"].get("http_redirect", "") == "":
        _fail("t2-json-sls-redirect", "empty redirect URL")
    if body_json["sls_urls"].get("http_post", "") == "":
        _fail("t2-json-sls-post", "empty POST URL")
    _ok(f"t2-json shape complete (sls_urls.http_redirect + .http_post + slo_callback_url)")

    # cacheDuration ISO-8601 format.
    if not body_json["cache_duration"].startswith("PT"):
        _fail("t2-cache-duration-iso", body_json["cache_duration"])
    _ok(f"t2-cacheDuration ISO-8601 format: {body_json['cache_duration']}")

    # Env override on cache TTL.
    os.environ["RMC_SAML_METADATA_CACHE_SECONDS"] = "3600"
    try:
        req = rf.get("/sso/saml/metadata/?format=json")
        body_json = _json.loads(saml_mod.metadata(req).content)
        if body_json["cache_duration"] != "PT3600S":
            _fail("t2-cache-env", f"got {body_json['cache_duration']}")
        _ok("t2-cacheDuration env override RMC_SAML_METADATA_CACHE_SECONDS=3600 honored")
    finally:
        os.environ.pop("RMC_SAML_METADATA_CACHE_SECONDS", None)

    # URL routes resolve under both names.
    from django.urls import reverse, NoReverseMatch
    try:
        url1 = reverse("sso_saml_metadata")
        url2 = reverse("sso_saml_metadata_xml")
    except NoReverseMatch as exc:
        _fail("t2-url-reverse", str(exc))
    if url1 != "/sso/saml/metadata/":
        _fail("t2-url1", url1)
    if url2 != "/sso/saml/metadata.xml/":
        _fail("t2-url2", url2)
    _ok(f"t2-routes resolve: {url1} + {url2}")


def run_t3():
    _line("\n[T3] SAML ACS POST-binding assertion-level signature requirement")
    from apps.api import saml as saml_mod
    rf = RequestFactory()

    # Default OFF.
    os.environ.pop("RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", None)
    if saml_mod._require_assertion_signature() is not False:
        _fail("t3-default-off", "expected False")
    _ok("t3-default RMC_SAML_REQUIRE_ASSERTION_SIGNATURE unset -> disabled")

    # Flag on.
    os.environ["RMC_SAML_REQUIRE_ASSERTION_SIGNATURE"] = "1"
    try:
        if saml_mod._require_assertion_signature() is not True:
            _fail("t3-flag-on", "expected True")
        _ok("t3-flag-on RMC_SAML_REQUIRE_ASSERTION_SIGNATURE=1")
    finally:
        os.environ.pop("RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", None)

    # _parse_saml_response surfaces both signature flags.
    import base64 as _b64m
    _NS_SAMLP = saml_mod._NS_SAMLP
    _NS_SAML = saml_mod._NS_SAML
    _NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

    # No signatures anywhere.
    xml_unsigned = (
        f'<samlp:Response xmlns:samlp="{_NS_SAMLP}" xmlns:saml="{_NS_SAML}" '
        'ID="_r1" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'<saml:Assertion xmlns:saml="{_NS_SAML}" ID="_a1" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<saml:Issuer>https://idp.example/idp</saml:Issuer>'
        '<saml:Subject><saml:NameID>smoke@example.com</saml:NameID></saml:Subject>'
        '</saml:Assertion>'
        '</samlp:Response>'
    ).encode("utf-8")
    parsed = saml_mod._parse_saml_response(_b64m.b64encode(xml_unsigned).decode("ascii"))
    if parsed.get("signature_present") is not False:
        _fail("t3-parse-unsigned-overall", f"got {parsed.get('signature_present')}")
    if parsed.get("signature_present_response") is not False:
        _fail("t3-parse-unsigned-response", f"got {parsed.get('signature_present_response')}")
    if parsed.get("signature_present_assertion") is not False:
        _fail("t3-parse-unsigned-assertion", f"got {parsed.get('signature_present_assertion')}")
    _ok("t3-parse no-Signature -> all three flags False")

    # Response-level signature only (wrapper signed, assertion NOT).
    xml_wrapper_signed = (
        f'<samlp:Response xmlns:samlp="{_NS_SAMLP}" xmlns:saml="{_NS_SAML}" xmlns:ds="{_NS_DSIG}" '
        'ID="_r2" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<ds:Signature><ds:SignedInfo/></ds:Signature>'
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'<saml:Assertion ID="_a2" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<saml:Issuer>https://idp.example/idp</saml:Issuer>'
        '<saml:Subject><saml:NameID>smoke@example.com</saml:NameID></saml:Subject>'
        '</saml:Assertion>'
        '</samlp:Response>'
    ).encode("utf-8")
    parsed = saml_mod._parse_saml_response(_b64m.b64encode(xml_wrapper_signed).decode("ascii"))
    if parsed.get("signature_present_response") is not True:
        _fail("t3-parse-wrapper-only-resp", f"got {parsed}")
    if parsed.get("signature_present_assertion") is not False:
        _fail("t3-parse-wrapper-only-assertion", f"got {parsed}")
    _ok("t3-parse wrapper-only signed: response=True, assertion=False")

    # Assertion-level signature only.
    xml_assertion_signed = (
        f'<samlp:Response xmlns:samlp="{_NS_SAMLP}" xmlns:saml="{_NS_SAML}" xmlns:ds="{_NS_DSIG}" '
        'ID="_r3" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'<saml:Assertion ID="_a3" Version="2.0" IssueInstant="2026-05-29T12:00:00Z">'
        '<saml:Issuer>https://idp.example/idp</saml:Issuer>'
        '<ds:Signature><ds:SignedInfo/></ds:Signature>'
        '<saml:Subject><saml:NameID>smoke@example.com</saml:NameID></saml:Subject>'
        '</saml:Assertion>'
        '</samlp:Response>'
    ).encode("utf-8")
    parsed = saml_mod._parse_saml_response(_b64m.b64encode(xml_assertion_signed).decode("ascii"))
    if parsed.get("signature_present_response") is not False:
        _fail("t3-parse-assertion-only-resp", f"got {parsed}")
    if parsed.get("signature_present_assertion") is not True:
        _fail("t3-parse-assertion-only-assertion", f"got {parsed}")
    _ok("t3-parse assertion-only signed: response=False, assertion=True")

    # ACS rejects wrapper-only when assertion signature required.
    os.environ["RMC_SAML_REQUIRE_ASSERTION_SIGNATURE"] = "1"
    try:
        req = rf.post("/sso/saml/acs/",
                      {"SAMLResponse": _b64m.b64encode(xml_wrapper_signed).decode("ascii")})
        resp = saml_mod.acs(req)
        if resp.status_code != 401:
            _fail("t3-acs-wrapper-only-reject", f"got {resp.status_code}, body={resp.content[:200]!r}")
        body = _json.loads(resp.content)
        if body.get("stage") != "assertion_signature_required_but_missing":
            _fail("t3-acs-stage", f"got {body}")
        if body.get("signature_present_response") is not True:
            _fail("t3-acs-resp-flag", f"got {body}")
        if body.get("signature_present_assertion") is not False:
            _fail("t3-acs-assertion-flag", f"got {body}")
        _ok("t3-ACS wrapper-only signed + strict assertion -> 401 with both flags surfaced")
    finally:
        os.environ.pop("RMC_SAML_REQUIRE_ASSERTION_SIGNATURE", None)


def run_t4():
    _line("\n[T4] OneRoster ?sort=/?orderBy= + Demographics sex enum")
    from apps.api import oneroster_demographics as odm

    # Sort helper.
    items = [
        {"sourcedId": "demo-1", "dateLastModified": "2026-05-29T10:00:00+00:00"},
        {"sourcedId": "demo-2", "dateLastModified": "2026-05-29T20:00:00+00:00"},
        {"sourcedId": "demo-3", "dateLastModified": "2026-05-29T15:00:00+00:00"},
    ]
    # Empty sort -> no-op.
    out = odm._apply_sort(items, "", "")
    if [r["sourcedId"] for r in out] != ["demo-1", "demo-2", "demo-3"]:
        _fail("t4-sort-noop", f"got {[r['sourcedId'] for r in out]}")
    _ok("t4-sort empty -> no-op")

    # Asc.
    out = odm._apply_sort(items, "dateLastModified", "asc")
    if [r["sourcedId"] for r in out] != ["demo-1", "demo-3", "demo-2"]:
        _fail("t4-sort-asc", f"got {[r['sourcedId'] for r in out]}")
    _ok("t4-sort sort=dateLastModified&orderBy=asc -> demo-1,demo-3,demo-2")

    # Desc.
    out = odm._apply_sort(items, "dateLastModified", "desc")
    if [r["sourcedId"] for r in out] != ["demo-2", "demo-3", "demo-1"]:
        _fail("t4-sort-desc", f"got {[r['sourcedId'] for r in out]}")
    _ok("t4-sort orderBy=desc -> demo-2,demo-3,demo-1")

    # Bogus orderBy falls back to asc.
    out = odm._apply_sort(items, "dateLastModified", "bogus")
    if [r["sourcedId"] for r in out] != ["demo-1", "demo-3", "demo-2"]:
        _fail("t4-sort-bogus-orderby", f"got {[r['sourcedId'] for r in out]}")
    _ok("t4-sort bogus orderBy -> falls back to asc")

    # Unknown field doesn't 400 (operator-facing).
    out = odm._apply_sort(items, "nonexistent", "asc")
    if len(out) != 3:
        _fail("t4-sort-unknown-field", f"got {out}")
    _ok("t4-sort unknown field -> no error (all rows preserved)")

    # Sex enum validation.
    if odm._validate_sex_enum({}) is not None:
        _fail("t4-sex-missing", "expected None")
    if odm._validate_sex_enum({"sex": ""}) is not None:
        _fail("t4-sex-empty", "expected None")
    _ok("t4-sex missing + empty -> None (explicit clear)")

    for valid in ("male", "female", "other", "MALE", "Female"):
        err = odm._validate_sex_enum({"sex": valid})
        if err is not None:
            _fail(f"t4-sex-{valid}-valid", f"got {err}")
    _ok("t4-sex male/female/other (case-insensitive) accepted")

    for bad in ("nonbinary", "unknown", "foo", "0", "M"):
        err = odm._validate_sex_enum({"sex": bad})
        if err is None or err.status_code != 400:
            _fail(f"t4-sex-{bad}-reject", f"expected 400; got {err}")
        body = _json.loads(err.content)
        if body.get("error") != "bad_sex_enum":
            _fail(f"t4-sex-{bad}-body", f"got {body}")
    _ok("t4-sex bad enum values rejected with 400 bad_sex_enum")


def run_t5():
    _line("\n[T5] Diagnostics retention preview HTML dashboard")
    from apps.migration_cloud import views_lms_diagnostics as vld
    rf = RequestFactory()
    user = _staff_user()

    # Default HTML (no ?format).
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-html-status", f"got {resp.status_code}")
    body = resp.content.decode("utf-8")
    for required in (
        "Diag-action retention preview",
        "Preview only",
        "Retention years",
        "Considered",
        "Would delete",
        "Actually deleted",
        "Sweep parameters",
        "Forecast different windows",
        "?years=1", "?years=3", "?years=7",
        "back to LMS diagnostics",
    ):
        if required not in body:
            _fail(f"t5-html-missing-{required[:30]}", "absent")
    _ok(f"t5-HTML default render: title + 4 metric cards + sweep params + forecast buttons ({len(body)} bytes)")

    # ?format=json still works.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?format=json")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-json-status", f"got {resp.status_code}")
    body_json = _json.loads(resp.content)
    if body_json.get("success") is not True:
        _fail("t5-json-success", f"got {body_json}")
    if body_json.get("retention", {}).get("dry_run") is not True:
        _fail("t5-json-dry-run", f"got {body_json}")
    if body_json.get("retention", {}).get("deleted") != 0:
        _fail("t5-json-deleted", f"got {body_json}")
    _ok("t5-JSON path still works: ?format=json preserves dry_run=True, deleted=0")

    # ?years=3 HTML reflects override.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?years=3")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 200:
        _fail("t5-html-years-3", f"got {resp.status_code}")
    body = resp.content.decode("utf-8")
    if "years_override" not in body:
        _fail("t5-html-override-key", "years_override block missing")
    _ok("t5-HTML ?years=3 renders override block")

    # Bad years still 400.
    req = rf.get("/super/migration/lms/diagnostics/retention-preview/?years=foo")
    req.user = user
    resp = vld.lms_diagnostics_retention_preview(req)
    if resp.status_code != 400:
        _fail("t5-html-bad-years", f"got {resp.status_code}")
    _ok("t5-bad ?years=foo -> 400 (works for both HTML + JSON dispatch)")


def main():
    run_t1()
    run_t2()
    run_t3()
    run_t4()
    run_t5()
    _line("\nALL GREEN")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        sys.exit(2)
