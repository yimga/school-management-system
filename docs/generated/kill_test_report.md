# Kill test report

**Result:** FAIL
**Critical failures:** 1

## security_audit_smoke: Security enforcement regression

- ok: **False**
  -  request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.16 runtime_trace_id=b35302305b21b663
.DEBUG 2026-05-09 18:12:48,462 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=8a8c08cc-99d0-482a-afbf-b699244616fe surface=tenant_plane steps=13 elapsed_ms=52.01 runtime_trace_id=fe649dcf8f804ae0
FDEBUG 2026-05-09 18:12:48,538 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- Skipping duplicate alert for audit_log 1
DEBUG 2026-05-09 18:12:48,591 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.14 runtime_trace_id=c5562cbaee3bb550
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
Ran 15 tests in 3.568s

FAILED (failures=3)
Preserving test database for alias 'default'...



## feature_route_resolution: Critical routes resolve (reverse)

- ok: **True**
  - ok

## degraded_surface_fallbacks: Founder surface degrades gracefully when generated ledgers are missing

- ok: **True**
