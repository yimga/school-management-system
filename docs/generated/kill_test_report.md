# Kill test report

**Result:** FAIL
**Critical failures:** 1

## security_audit_smoke: Security enforcement regression

- ok: **False**
  - tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- platform_event: type=student_created tenant_id=None school_id=cb88ecaf-bc42-4863-a2b9-a569083c0b3f idempotency_key=None payload_keys=['student_id', 'school_id']
.DEBUG 2026-04-28 19:03:37,184 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=9cecdc90-337a-4136-881c-552cf077c9d6 surface=tenant_plane steps=13 elapsed_ms=149.95 runtime_trace_id=e27000fffdd9fbf8
.DEBUG 2026-04-28 19:03:38,813 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=9cecdc90-337a-4136-881c-552cf077c9d6 surface=tenant_plane steps=13 elapsed_ms=184.50 runtime_trace_id=b9bdad9741b40f51
.DEBUG 2026-04-28 19:03:40,260 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=9cecdc90-337a-4136-881c-552cf077c9d6 surface=tenant_plane steps=13 elapsed_ms=137.48 runtime_trace_id=587fd348ab0dfed5
...DEBUG 2026-04-28 19:03:44,007 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=None surface=marketing steps=13 elapsed_ms=0.30 runtime_trace_id=95a071af5c8a13eb
.DEBUG 2026-04-28 19:03:45,945 request_id=- tenant_id=- user_id=- school_id=- http_method=- request_path=- remote_addr=- http_referer=- http_user_agent=- http_host=- content_type=- accept_language=- accept_encoding=- x_forwarded_for=- x_forwarded_proto=- x_forwarded_host=- content_length=- http_origin=- query_string=- server_protocol=- request_scheme=- server_name=- runtime_resolution_complete school_id=1abd8927-1740-4432-8aaa-58815cfdf962 surface=tenant_plane steps=13 elapsed_ms=163.89 runtime_trace_id=63d5e2fa4e68f883
.F
======================================================================
FAIL: test_tenant_staff_cannot_download_super_schools_csv (apps.security.tests.test_tenant_route_leakage.TenantHostVsControlPlaneTests.test_tenant_staff_cannot_download_super_schools_csv)
``/super/export/schools.csv`` requires platform operator, not tenant admin.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\beta\school-management-system\apps\security\tests\test_tenant_route_leakage.py", line 72, in test_tenant_staff_cannot_download_super_schools_csv
    c.force_login(u)
    ~~~~~~~~~~~~~^^^
AssertionError: 302 != 403

----------------------------------------------------------------------
Ran 15 tests in 22.459s

FAILED (failures=1)
Destroying test database for alias 'default'...



## feature_route_resolution: Critical routes resolve (reverse)

- ok: **True**
  - ok

## degraded_surface_fallbacks: Founder surface degrades gracefully when generated ledgers are missing

- ok: **True**
