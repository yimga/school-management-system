# Core runtime certification

**Generated:** 2026-05-20T01:46:11.464767+00:00
**Verdict:** CORE RUNTIME READY — REPO SCOPE

Audit reference: `docs/generated/core_runtime_dependency_audit.json`

## Gates

| Gate | OK | Note |
|------|----|------|
| cors_no_allow_all | True | CORS_ALLOW_ALL_ORIGINS must remain disabled |
| drf_default_authenticated | True | DRF default permission is IsAuthenticated |
| jwt_simple_jwt_configured | True | SIMPLE_JWT settings block present |
| mfa_middleware_present | True | RequireMFAMiddleware wired |
| celery_eager_in_tests | True | CELERY_TASK_ALWAYS_EAGER when RUNNING_TESTS |
| route_api_token_obtain_pair | True | resolves |
| route_api_token_refresh | True | resolves |
| route_api_ai-support-assistant | True | resolves |

## External (not repo-proven)

- live_render_celery_worker_health
- production_redis_channel_layer_proof
