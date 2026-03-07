# Session & Inactivity (Phase 10)

## Session configuration

Session behaviour is controlled in `config/settings.py` and environment variables:

- **SESSION_SAVE_EVERY_REQUEST:** When `True` (default), the session is saved on every request, so the expiry time is extended on activity. Combined with `SESSION_COOKIE_AGE`, this gives *inactivity* timeout: after no requests for that many seconds, the session cookie expires.
- **SESSION_COOKIE_AGE:** Max session lifetime in seconds. Default from env: `SESSION_COOKIE_AGE` (e.g. 14400 = 4 hours) or, for shared computers, use **SESSION_INACTIVITY_TIMEOUT_MINUTES** (e.g. 15 or 30) which overrides to that many minutes × 60.
- **SESSION_EXPIRE_AT_BROWSER_CLOSE:** When `True`, the session cookie is a session cookie (no fixed expiry date); closing the browser ends the session. Often used with `SESSION_SAVE_EVERY_REQUEST` so that activity keeps the session alive until the browser is closed.
- **ROLE_SESSION_TIMEOUTS:** Optional per-role max session length (seconds). Used if the app applies role-based session expiry (check middleware or auth backends).

## Shared computers (e.g. school lab)

To reduce risk on shared machines:

1. Set **SESSION_INACTIVITY_TIMEOUT_MINUTES=15** (or 30) in the environment so that 15–30 minutes of inactivity logs the user out.
2. Keep **SESSION_SAVE_EVERY_REQUEST=1** so each request refreshes the timeout.
3. Optionally set **SESSION_EXPIRE_AT_BROWSER_CLOSE=1** so closing the browser also ends the session.

No extra middleware is required for inactivity-based expiry when using Django’s default session backend with the above settings; the session cookie expiry is updated on each request when `SESSION_SAVE_EVERY_REQUEST` is True.

## Related

- Phase 10 also covers SQL/input audit and RBAC audit; see the main plan for those items.
- CSRF and SameSite: `SESSION_COOKIE_SAMESITE` and `CSRF_COOKIE_SAMESITE` are set in settings (e.g. `Lax`).
