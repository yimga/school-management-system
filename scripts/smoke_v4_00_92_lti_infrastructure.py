"""v4.00.92 Wave 25 — LTI 1.3 infrastructure smoke (H7 + H8 + H9 + H10).

H10 — JWKS endpoint (4 cases):
  1. build_jwks returns valid JWKS doc with >= 1 key
  2. sign_platform_jwt + decode_and_verify_platform_jwt roundtrip
  3. kid header matches current_kid
  4. /lti/jwks/ returns 200 + JSON with keys array

H8 — Token endpoint (4 cases):
  5. POST /lti/auth/token/ with bad grant_type -> 400 unsupported_grant_type
  6. POST with unknown client_id -> 401 invalid_client
  7. POST with valid jwt_assertion -> 200 + Bearer + scope
  8. granted scopes are intersection of requested INTERSECT permitted

H9 — Scope enforcement (4 cases):
  9. AGS lineitem GET with lineitem.readonly token -> 200
 10. AGS lineitem POST with lineitem.readonly token -> 403 insufficient_scope
 11. AGS score POST with score token -> 200/201
 12. NRPS GET with contextmembership.readonly -> 200

H7 — Tool registration (4 cases):
 13. LTIToolRegistrationForm validates good input
 14. LTIToolRegistrationForm rejects bad jwks_url
 15. LTIToolRegistrationListView GET -> 200 staff-only
 16. LTIToolRegistrationCreateView POST saves ServiceIntegration + one-time secret

Run:
    python scripts/smoke_v4_00_92_lti_infrastructure.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import django  # noqa: E402

django.setup()

CASES = 0


def _ok(label: str) -> None:
    global CASES
    CASES += 1
    print(f"[OK {CASES:02d}] {label}")


def _skip(label: str, reason: str) -> None:
    print(f"[SKIP   ] {label} — {reason}")


# Verify cryptography is available; otherwise SKIP H10/H8/H9 quickly.
try:
    import cryptography  # noqa: F401
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

# ---------------------------------------------------------------------------
# H10 — JWKS endpoint
# ---------------------------------------------------------------------------
print("=" * 70)
print("H10 JWKS endpoint")
print("=" * 70)

if not _CRYPTO_OK:
    _skip("H10 all cases", "cryptography not installed")
else:
    from apps.schools import lti_platform_jwks as _jwks

    # Force a fresh ephemeral keypair so the kid is deterministic per process.
    _jwks._EPHEMERAL_KEYPAIR_CACHE.clear()

    # Case 1: build_jwks
    doc = _jwks.build_jwks()
    assert "keys" in doc and isinstance(doc["keys"], list) and doc["keys"], doc
    k = doc["keys"][0]
    assert k["kty"] == "RSA" and k["alg"] == "RS256" and k["use"] == "sig", k
    assert k.get("n") and k.get("e") and k.get("kid"), k
    _ok("H10 build_jwks returns RS256/RSA JWKS with n+e+kid")

    # Case 2: sign + verify roundtrip
    token = _jwks.sign_platform_jwt(
        claims={"sub": "smoke-test", "scope": "test:read"}, expires_in_seconds=120
    )
    claims_back = _jwks.decode_and_verify_platform_jwt(token)
    assert claims_back["sub"] == "smoke-test"
    assert claims_back["scope"] == "test:read"
    _ok("H10 sign_platform_jwt + decode roundtrip preserves claims")

    # Case 3: kid matches
    cur_kid = _jwks.current_kid()
    assert cur_kid == k["kid"], (cur_kid, k["kid"])
    # Inspect JWT header
    import base64
    import json as _json
    header_b64 = token.split(".")[0]
    header = _json.loads(
        base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4))
    )
    assert header.get("kid") == cur_kid, header
    _ok("H10 JWT kid header matches current_kid")

    # Case 4: /lti/jwks/ view
    from django.test import Client as _Client
    client = _Client()
    r = client.get("/lti/jwks/")
    assert r.status_code == 200, r.status_code
    body = r.json()
    assert "keys" in body and body["keys"], body
    _ok("H10 /lti/jwks/ returns 200 + keys array")

# ---------------------------------------------------------------------------
# Helper: a fresh ServiceIntegration row for H8/H9
# ---------------------------------------------------------------------------

def _make_lti_integration(*, client_id: str, permitted: list[str]):
    from apps.integrations_marketplace.models import ServiceIntegration
    from apps.schools.models import School

    school = School.objects.filter(is_active=True).first()
    if school is None:
        school = School.objects.create(
            name="Smoke School",
            slug=f"smoke-school-{client_id[:8]}",
            subdomain=f"smoke{client_id[:6].lower()}",
            is_active=True,
        )
    # Random salt to keep idempotent across reruns.
    import secrets as _s
    suffix = _s.token_hex(3)
    integration = ServiceIntegration.objects.create(
        school=school,
        service_name=f"Smoke LTI {suffix}",
        service_type=ServiceIntegration.ServiceType.LTI,
        client_id=client_id,
        endpoint_url="https://tool.example.com/launch",
        enabled_scopes=list(permitted),
        config={
            "tool_name": f"Smoke Tool {suffix}",
            "client_id": client_id,
            "deployment_id": "deploy-smoke-1",
            "permitted_scopes": list(permitted),
            "lti_permitted_scopes": list(permitted),
            # No jwks_url, no shared_secret -> dev fallback path (unverified)
        },
        is_active=True,
    )
    return integration


# ---------------------------------------------------------------------------
# H8 — Token endpoint
# ---------------------------------------------------------------------------
print("=" * 70)
print("H8 Tool token endpoint")
print("=" * 70)

if not _CRYPTO_OK:
    _skip("H8 all cases", "cryptography not installed")
else:
    from django.test import Client as _Client
    from apps.schools import lti_tool_token as _tt

    client = _Client()

    # Case 5: bad grant_type
    r = client.post("/lti/auth/token/", data={
        "grant_type": "password",
        "client_assertion_type": _tt.JWT_BEARER_ASSERTION_TYPE,
        "client_assertion": "x.y.z",
    })
    assert r.status_code == 400, r.status_code
    body = r.json()
    assert body["error"] == "unsupported_grant_type", body
    _ok("H8 bad grant_type -> 400 unsupported_grant_type")

    # Case 6: unknown client_id (we still need a parseable assertion to reach
    # the client_id branch — use a tiny stub JWT with iss set).
    import base64 as _b64
    import json as _json
    def _seg(d):
        return _b64.urlsafe_b64encode(_json.dumps(d).encode()).rstrip(b"=").decode()
    stub_jwt = ".".join([
        _seg({"alg": "none", "typ": "JWT"}),
        _seg({"iss": "unknown-client-id-xxx", "sub": "unknown-client-id-xxx",
              "aud": "unknown-client-id-xxx", "exp": 9999999999}),
        "sig",
    ])
    r = client.post("/lti/auth/token/", data={
        "grant_type": _tt.GRANT_CLIENT_CREDENTIALS,
        "client_assertion_type": _tt.JWT_BEARER_ASSERTION_TYPE,
        "client_assertion": stub_jwt,
        "scope": _tt.LTI_SCOPE_LINEITEM,
    })
    assert r.status_code == 401, r.status_code
    body = r.json()
    assert body["error"] == "invalid_client", body
    _ok("H8 unknown client_id -> 401 invalid_client")

    # Case 7: valid client_id + valid (unverified-dev-fallback) assertion
    integration = _make_lti_integration(
        client_id="smoke-client-h8-7",
        permitted=[_tt.LTI_SCOPE_LINEITEM, _tt.LTI_SCOPE_LINEITEM_RO,
                   _tt.LTI_SCOPE_SCORE],
    )
    good_jwt = ".".join([
        _seg({"alg": "none", "typ": "JWT"}),
        _seg({"iss": "smoke-client-h8-7", "sub": "smoke-client-h8-7",
              "aud": "smoke-client-h8-7", "exp": 9999999999}),
        "sig",
    ])
    r = client.post("/lti/auth/token/", data={
        "grant_type": _tt.GRANT_CLIENT_CREDENTIALS,
        "client_assertion_type": _tt.JWT_BEARER_ASSERTION_TYPE,
        "client_assertion": good_jwt,
        "scope": _tt.LTI_SCOPE_LINEITEM,
    })
    assert r.status_code == 200, (r.status_code, r.content[:300])
    body = r.json()
    assert body["token_type"] == "Bearer", body
    assert body["access_token"], body
    assert _tt.LTI_SCOPE_LINEITEM in body["scope"], body
    _ok("H8 valid jwt_assertion -> 200 + Bearer + scope")

    # Case 8: granted = requested INTERSECT permitted (request 2 scopes, only 1 permitted)
    integration2 = _make_lti_integration(
        client_id="smoke-client-h8-8",
        permitted=[_tt.LTI_SCOPE_SCORE],  # only score permitted
    )
    good_jwt2 = ".".join([
        _seg({"alg": "none", "typ": "JWT"}),
        _seg({"iss": "smoke-client-h8-8", "sub": "smoke-client-h8-8",
              "aud": "smoke-client-h8-8", "exp": 9999999999}),
        "sig",
    ])
    r = client.post("/lti/auth/token/", data={
        "grant_type": _tt.GRANT_CLIENT_CREDENTIALS,
        "client_assertion_type": _tt.JWT_BEARER_ASSERTION_TYPE,
        "client_assertion": good_jwt2,
        "scope": f"{_tt.LTI_SCOPE_SCORE} {_tt.LTI_SCOPE_LINEITEM}",
    })
    assert r.status_code == 200, (r.status_code, r.content[:300])
    body = r.json()
    scopes_granted = body["scope"].split()
    assert _tt.LTI_SCOPE_SCORE in scopes_granted, scopes_granted
    assert _tt.LTI_SCOPE_LINEITEM not in scopes_granted, scopes_granted
    _ok("H8 granted scopes = requested INTERSECT permitted (excludes non-permitted)")

# ---------------------------------------------------------------------------
# H9 — Scope enforcement
# ---------------------------------------------------------------------------
print("=" * 70)
print("H9 Scope enforcement on AGS + NRPS")
print("=" * 70)

if not _CRYPTO_OK:
    _skip("H9 all cases", "cryptography not installed")
else:
    from django.test import Client as _Client
    from apps.schools import lti_tool_token as _tt
    from apps.schools.lti_platform_jwks import sign_platform_jwt

    client = _Client()

    # Bake an integration that supports all the scopes we'll exercise.
    integ = _make_lti_integration(
        client_id="smoke-client-h9-all",
        permitted=[
            _tt.LTI_SCOPE_LINEITEM,
            _tt.LTI_SCOPE_LINEITEM_RO,
            _tt.LTI_SCOPE_SCORE,
            _tt.LTI_SCOPE_RESULT_RO,
            _tt.LTI_SCOPE_NRPS_MEMBERSHIP,
        ],
    )

    def _bearer(scope: str) -> dict:
        tok = sign_platform_jwt(
            claims={
                "sub": "smoke-client-h9-all",
                "scope": scope,
                "client_id": "smoke-client-h9-all",
                "integration_id": str(integ.pk),
            },
            expires_in_seconds=600,
        )
        return {"HTTP_AUTHORIZATION": f"Bearer {tok}"}

    # Case 9: AGS lineitem GET with lineitem.readonly token -> 200
    r = client.get(
        f"/lti/service/{integ.pk}/lineitems",
        **_bearer(_tt.LTI_SCOPE_LINEITEM_RO),
    )
    # Allow either 200 or 404/403 if the resolver doesn't find by pk; check
    # that scope-enforcement is the relevant filter — must NOT be 403
    # insufficient_scope.
    assert r.status_code == 200, (r.status_code, r.content[:200])
    _ok("H9 AGS lineitem GET w/ lineitem.readonly token -> 200")

    # Case 10: AGS lineitem POST with readonly token -> 403 insufficient_scope
    r = client.post(
        f"/lti/service/{integ.pk}/lineitems",
        data="{}",
        content_type="application/json",
        **_bearer(_tt.LTI_SCOPE_LINEITEM_RO),  # readonly only
    )
    assert r.status_code == 403, (r.status_code, r.content[:200])
    body = r.json()
    assert body.get("error") == "insufficient_scope", body
    _ok("H9 AGS lineitem POST w/ readonly token -> 403 insufficient_scope")

    # Case 11: AGS score POST with score scope -> 201
    # First create a lineitem to score against (with full lineitem scope).
    r = client.post(
        f"/lti/service/{integ.pk}/lineitems",
        data='{"label": "smoke"}',
        content_type="application/json",
        **_bearer(_tt.LTI_SCOPE_LINEITEM),
    )
    assert r.status_code in (200, 201), (r.status_code, r.content[:200])
    lineitem_id = r.json()["id"]
    r = client.post(
        f"/lti/service/{integ.pk}/lineitems/{lineitem_id}/scores",
        data='{"userId": "u1", "scoreGiven": 80, "scoreMaximum": 100}',
        content_type="application/json",
        **_bearer(_tt.LTI_SCOPE_SCORE),
    )
    assert r.status_code in (200, 201), (r.status_code, r.content[:200])
    _ok("H9 AGS score POST w/ score scope -> 200/201")

    # Case 12: NRPS GET with contextmembership.readonly -> 200
    r = client.get(
        f"/lti/service/{integ.pk}/memberships",
        **_bearer(_tt.LTI_SCOPE_NRPS_MEMBERSHIP),
    )
    assert r.status_code == 200, (r.status_code, r.content[:200])
    _ok("H9 NRPS GET w/ contextmembership.readonly -> 200")

# ---------------------------------------------------------------------------
# H7 — Tool registration admin UI
# ---------------------------------------------------------------------------
print("=" * 70)
print("H7 Tool registration admin")
print("=" * 70)

from apps.schools.lti_tool_admin import (  # noqa: E402
    LTIToolRegistrationForm,
)
from apps.schools.lti_tool_token import STANDARD_LTI_SCOPES  # noqa: E402

# Case 13: form validates good input
form = LTIToolRegistrationForm(data={
    "tool_name": "Khan Academy",
    "tool_client_id": "khan-tool-client-1",
    "platform_id": "https://runmycampus.com",
    "deployment_id": "deploy-1",
    "tool_jwks_url": "https://tool.example.com/jwks.json",
    "tool_oidc_login_url": "https://tool.example.com/oidc/login",
    "tool_redirect_uris": "https://tool.example.com/cb",
    "permitted_scopes": list(STANDARD_LTI_SCOPES[:2]),
    "tool_description": "Practice math",
})
assert form.is_valid(), form.errors
_ok("H7 LTIToolRegistrationForm validates good input")

# Case 14: form rejects bad jwks_url (http://)
form_bad = LTIToolRegistrationForm(data={
    "tool_name": "Bad Tool",
    "tool_client_id": "bad-tool-1",
    "platform_id": "https://runmycampus.com",
    "deployment_id": "deploy-1",
    "tool_jwks_url": "http://insecure.example.com/jwks.json",  # http -> reject
    "tool_oidc_login_url": "https://tool.example.com/oidc/login",
    "tool_redirect_uris": "https://tool.example.com/cb",
    "permitted_scopes": list(STANDARD_LTI_SCOPES[:1]),
})
assert not form_bad.is_valid()
assert "tool_jwks_url" in form_bad.errors, form_bad.errors
_ok("H7 LTIToolRegistrationForm rejects http:// jwks_url")

# Case 15: list view (staff-only)
from django.test import Client as _Client  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()
staff_user, _ = User.objects.get_or_create(
    username="smoke-lti-staff",
    defaults={"email": "smoke-lti-staff@example.com",
              "is_staff": True, "is_superuser": True},
)
if not staff_user.is_staff:
    staff_user.is_staff = True
    staff_user.is_superuser = True
    staff_user.save(update_fields=["is_staff", "is_superuser"])
client = _Client()
client.force_login(staff_user)

# Bypass the per-session security-posture-review nag redirect.
_session = client.session
_session["security_posture_review_nagged"] = True
_session.save()

r = client.get("/super/lti/tools/")
assert r.status_code == 200, (r.status_code, r.content[:200])
_ok("H7 LTIToolRegistrationListView GET as staff -> 200")

# Anonymous access -> redirect/forbidden
anon_client = _Client()
r2 = anon_client.get("/super/lti/tools/")
assert r2.status_code in (302, 403), r2.status_code
_ok("H7 LTIToolRegistrationListView blocks anonymous (302/403)")

# Case 16: POST create -> one-time secret + new ServiceIntegration row
from apps.integrations_marketplace.models import ServiceIntegration  # noqa: E402

before = ServiceIntegration.objects.filter(
    service_type=ServiceIntegration.ServiceType.LTI
).count()
r = client.post("/super/lti/tools/register/", data={
    "tool_name": "Quizlet",
    "tool_client_id": "quizlet-tool-client-1",
    "platform_id": "https://runmycampus.com",
    "deployment_id": "deploy-quizlet-1",
    "tool_jwks_url": "https://quizlet.example.com/jwks.json",
    "tool_oidc_login_url": "https://quizlet.example.com/oidc",
    "tool_redirect_uris": "https://quizlet.example.com/cb",
    "permitted_scopes": list(STANDARD_LTI_SCOPES[:3]),
})
assert r.status_code == 200, (r.status_code, r.content[:200])
after = ServiceIntegration.objects.filter(
    service_type=ServiceIntegration.ServiceType.LTI
).count()
assert after == before + 1, (before, after)
new_row = ServiceIntegration.objects.filter(
    service_type=ServiceIntegration.ServiceType.LTI,
    client_id="quizlet-tool-client-1",
).first()
assert new_row is not None
assert "lti_tool_secret_hash" in (new_row.config or {})
assert (new_row.config or {}).get("permitted_scopes") == list(
    STANDARD_LTI_SCOPES[:3]
), (new_row.config or {}).get("permitted_scopes")
# Response page must show the one-time secret as plain text (we don't ship
# it via JSON — operator must copy from rendered HTML).
assert b"one-time" in r.content.lower() or b"shown once" in r.content.lower()
_ok("H7 LTIToolRegistrationView POST saves ServiceIntegration + reveals one-time secret")

# ---------------------------------------------------------------------------
print("=" * 70)
print(f"DONE - {CASES} smoke cases green")
print("=" * 70)
