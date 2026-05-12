# Kill test report

**Result:** FAIL
**Critical failures:** 1

## security_audit_smoke: Security enforcement regression

- ok: **False**
  - forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=d2cfad62-a8c7-45e3-aa13-4b0813a6021e surface=tenant_plane steps=13 elapsed_ms=53.67 runtime_trace_id=a88c9b2a4813eda9
FDEBUG 2026-05-11 19:45:58,330 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- Skipping duplicate alert for audit_log 1
DEBUG 2026-05-11 19:45:58,336 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- Skipping duplicate alert for audit_log 2
DEBUG 2026-05-11 19:45:58,377 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.15 runtime_trace_id=4195f27c5c6f3048
.
======================================================================
FAIL: test_manage_without_membership_gets_403_list (apps.security.tests.test_security_enforcement.ComplianceExportEnforcementTests.test_manage_without_membership_gets_403_list)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\security\tests\test_security_enforcement.py", line 127, in test_manage_without_membership_gets_403_list
    self.assertEqual(client.get(url).status_code, 403)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 302 != 403

======================================================================
FAIL: test_compliance_download_403_without_membership (apps.security.tests.test_absolute_security_enforcement.AbsoluteSecurityExportTests.test_compliance_download_403_without_membership)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\security\tests\test_absolute_security_enforcement.py", line 50, in test_compliance_download_403_without_membership
    self.assertEqual(r.status_code, 403)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
AssertionError: 302 != 403

======================================================================
FAIL: test_membership_on_school_a_blocked_on_school_b_host (apps.security.tests.test_tenant_route_leakage.TenantHostVsControlPlaneTests.test_membership_on_school_a_blocked_on_school_b_host)
Tenant host resolves school B; user only belongs to A \u2192 export gate 403.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\security\tests\test_tenant_route_leakage.py", line 98, in test_membership_on_school_a_blocked_on_school_b_host
    self.assertEqual(c.get(url).status_code, 403)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 302 != 403

----------------------------------------------------------------------
Ran 15 tests in 3.637s

FAILED (failures=3)
Preserving test database for alias 'default'...



## feature_route_resolution: Critical routes resolve (reverse)

- ok: **True**
  - ok

## degraded_surface_fallbacks: Founder surface degrades gracefully when generated ledgers are missing

- ok: **True**
