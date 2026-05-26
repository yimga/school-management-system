# Kill test report

**Result:** FAIL
**Critical failures:** 2

## security_audit_smoke: Security enforcement regression

- ok: **False**
  - ame=- runtime_resolution_complete school_id=058bb043-bf74-4224-a36e-867141a6ce0d surface=tenant_plane steps=13 elapsed_ms=240.98 runtime_trace_id=af4c5a3e6b2bd681
INFO 2026-05-26 06:25:51,791 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-26 06:25:51,791 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
.INFO 2026-05-26 06:25:52,677 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-26 06:25:52,677 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
DEBUG 2026-05-26 06:25:53,027 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=f15f924e-2543-4ad8-9111-a0f8b2cabd92 surface=tenant_plane steps=13 elapsed_ms=224.15 runtime_trace_id=5fc91c459abe5fc6
INFO 2026-05-26 06:25:53,039 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-26 06:25:53,039 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
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
Ran 15 tests in 108.092s

FAILED (failures=1)
Preserving test database for alias 'default'...



## feature_route_resolution: Critical routes resolve (reverse)

- ok: **True**
  - ok

## degraded_surface_fallbacks: Founder surface degrades gracefully when generated ledgers are missing

- ok: **False**
  - for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
INFO 2026-05-26 06:26:06,225 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-26 06:26:06,225 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
DEBUG 2026-05-26 06:26:06,300 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.17 runtime_trace_id=9b71dedfea9f5814
INFO 2026-05-26 06:26:06,317 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- django_cryptography_key_derived_from_secret_key
INFO 2026-05-26 06:26:06,317 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- encrypted_jsonfield_decrypt_skipped
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
Ran 2 tests in 2.491s

FAILED (failures=2)
Preserving test database for alias 'default'...


