# Kill test report

**Result:** FAIL
**Critical failures:** 2

## security_audit_smoke: Security enforcement regression

- ok: **False**
  - ame=- runtime_resolution_complete school_id=85c6d00c-f966-4b6f-ab59-82f736f20500 surface=tenant_plane steps=13 elapsed_ms=611.91 runtime_trace_id=bc4a3ab7eec44ef8
INFO 2026-05-24 23:06:29,738 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-24 23:06:29,738 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
.INFO 2026-05-24 23:06:32,085 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-24 23:06:32,085 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
DEBUG 2026-05-24 23:06:33,191 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=d3a0b95c-d8d7-4b3a-a0be-5d92bd0dc0d1 surface=tenant_plane steps=13 elapsed_ms=708.09 runtime_trace_id=38055bdfb57ce3c2
INFO 2026-05-24 23:06:33,228 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-24 23:06:33,228 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
.
======================================================================
FAIL: test_super_sees_marker_and_staff_blocked (apps.security.tests.test_security_enforcement.SecuritySurfaceDashboardTests.test_super_sees_marker_and_staff_blocked)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\security\tests\test_security_enforcement.py", line 168, in test_super_sees_marker_and_staff_blocked
    self.assertEqual(resp.status_code, 200)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 302 != 200

----------------------------------------------------------------------
Ran 15 tests in 122.449s

FAILED (failures=1)
Preserving test database for alias 'default'...



## feature_route_resolution: Critical routes resolve (reverse)

- ok: **True**
  - ok

## degraded_surface_fallbacks: Founder surface degrades gracefully when generated ledgers are missing

- ok: **False**
  - for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
INFO 2026-05-24 23:07:10,009 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-24 23:07:10,009 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
DEBUG 2026-05-24 23:07:10,258 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.31 runtime_trace_id=d8ce7bd4bd539982
INFO 2026-05-24 23:07:10,311 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-24 23:07:10,311 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
F
======================================================================
FAIL: test_dashboard_degrades_when_generated_json_missing (apps.schools.tests.test_founder_dashboard.FounderDashboardTests.test_dashboard_degrades_when_generated_json_missing)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\schools\tests\test_founder_dashboard.py", line 73, in test_dashboard_degrades_when_generated_json_missing
    self.assertEqual(r.status_code, 200)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
AssertionError: 302 != 200

======================================================================
FAIL: test_superuser_sees_markers (apps.schools.tests.test_founder_dashboard.FounderDashboardTests.test_superuser_sees_markers)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\schools\tests\test_founder_dashboard.py", line 40, in test_superuser_sees_markers
    self.assertEqual(
    ~~~~~~~~~~~~~~~~^
        r.status_code,
        ^^^^^^^^^^^^^^
        200,
        ^^^^
        msg=f"redirect={r.get('Location', '')!r}",
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: 302 != 200 : redirect='/authentication/mfa/setup/?next=/super/founder/'

----------------------------------------------------------------------
Ran 2 tests in 5.304s

FAILED (failures=2)
Preserving test database for alias 'default'...
