# Logging and header behaviour

## Log size and rotation

Logging is configured in `config/settings.py`:

- **File logging** is optional: set `USE_FILE_LOGGING=True` (or leave unset in DEBUG) to enable.
- **Rotation:** `RotatingFileHandler` with **10MB** per file and **10** backup files (configurable).
- **Path:** `logs/django.log` under the project root.
- **Total cap:** About 110MB (10MB × 11 files) when file logging is on.

So log size is bounded and should not grow without limit. If you see very large logs:

1. Set **`LOG_LEVEL=WARNING`** (or `ERROR`) in production so INFO/DEBUG are not written.
2. Optionally set **`LOG_FILE_MAX_MB`** (e.g. `5`) to reduce per-file size (see below).
3. Ensure **`USE_FILE_LOGGING`** is not enabled in environments where the log directory is shared or slow.

## Optional: cap log file size via env

You can override the per-file size with an env var. In `config/settings.py` the handler uses:

- `maxBytes`: from `LOG_FILE_MAX_MB` env (default 10) in MB.

`LOG_FILE_MAX_MB` is read in `config/settings.py` and used for the file handler `maxBytes`.

## Is log size causing the header to be slow?

Unlikely. Reasons:

- Logging is asynchronous from the request path; writing to a rotating file does not block the response.
- The **header** (control plane nav, search, shortcuts) is rendered from **templates** and **context processors** (`CONTROL_PLANE_NAV`, `build_control_plane_nav`, site settings, etc.). Slowness there is usually from:
  - **Context processors** doing DB or reverse() work on every request.
  - **Search (Ctrl+K)** calling `/api/search/` and waiting on that response.
  - **Heavy or repeated `reverse()`** when building nav (we already use `_safe_reverse` and only include resolved items).

If the header feels problematic:

1. **Check response time** for the page (e.g. Django Debug Toolbar or browser Network tab) to see if the whole request is slow or only the header area.
2. **Temporarily set `LOG_LEVEL=ERROR`** and retest; if the header is still slow, the cause is not log volume.
3. **Review context processors** that run on every request (e.g. `build_control_plane_nav`, site settings, portal sidebar) and ensure they do minimal work and no N+1 queries.
4. **Check `/api/search/`** and `/api/control-plane-preferences/`** for latency; the header depends on these when using search or pins.

## Summary

- Log size is **capped** (10MB × 10 backups by default) and is **unlikely** to be the cause of header issues.
- Use **`LOG_LEVEL=WARNING`** in production to keep log volume down.
- If the header is slow, focus on **context processors**, **nav building**, and **header-related API calls** (search, preferences), not log file size.
